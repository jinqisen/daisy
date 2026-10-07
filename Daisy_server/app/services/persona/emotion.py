import os
import asyncio
import hashlib
from typing import List, Dict, Any, Optional
from transformers import pipeline
import structlog
from functools import lru_cache
from app.core.config import settings
from app.core.constants import EMOTION_TEXT_TRUNCATE_LIMIT, EMOTION_CACHE_TTL, EMOTION_TOP_K
from app.core.utils import is_chinese
from app.core.llm import get_llm_service, LLM_ERROR_PREFIX
from app.core.cache import cache_result
import re

logger = structlog.get_logger()

def emotion_key_builder(*args, **kwargs) -> str:
    """
    为 analyze_async 生成缓存键。

    `cache_result` 以**被装饰方法收到的原样参数**调用 key_builder,也就是
    `key_builder(self, text, user_settings=..., ...)`,并不会把函数对象传进来。
    旧签名写成 `(func, *args, **kwargs)`:self 被当成 func 吃掉、text 落在 args[0],
    代码却去读 args[1],于是任何输入都得到常量 "emotion:empty" ——
    一旦开启缓存(Redis 或嵌入模式的进程内 KV),所有文本命中同一条目:
    同一用户第 2 轮起翻译与 GoEmotions 全被跳过,top_emotions 恒等于第 1 轮。

    键只由 text 决定:analyze 节点传进来的 text 是「最近 EMOTION_CONTEXT_TURNS 条
    历史 + 当前输入」合并后的 full_text,同一句话落在不同上下文里天然得到不同的键,
    不必再把窗口大小单独编进键。original_text / user_id / trigger_message_id /
    execution_id 不参与:模型输出只取决于送进去的文本,把每轮都变的元数据编进键
    只会让缓存永远不命中。
    """
    text: Optional[str] = kwargs.get("text")
    if text is None:
        # 位置参数形态是 (self, text, ...)。只认字符串,不会再把 self 误当成文本
        text = next((a for a in args if isinstance(a, str)), None)

    if not text or not text.strip():
        # 空文本没有情绪可分析,保留固定键
        return "emotion:empty"

    text_hash = hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()
    return f"emotion:{text_hash}"

class EmotionService:
    def __init__(self, model_name: str = None):
        self.model_name = model_name or settings.EMOTION_MODEL_NAME
        self.classifier = None
        self._initialize_model()

    def _initialize_model(self):
        # 移除 try-except 块，让任何初始化错误（特别是 FileNotFoundError）直接抛出
        # 从而导致服务启动失败，满足"不降级、直接报错"的严格要求
        model_path = os.path.abspath(self.model_name)
        logger.info(f"Loading Emotion model from: {model_path}...")
        
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Local emotion model not found at: {model_path}")
            
        # 检查目录是否为空
        if os.path.isdir(model_path) and not os.listdir(model_path):
             raise ValueError(f"Emotion model directory is empty: {model_path}. Please check volume mounts or image build.")
             
        # 检查关键文件是否存在 (config.json)
        config_path = os.path.join(model_path, "config.json")
        if not os.path.exists(config_path):
             # 尝试检查子目录 (例如 git clone 后的结构)
             subdirs = [d for d in os.listdir(model_path) if os.path.isdir(os.path.join(model_path, d))]
             if len(subdirs) == 1:
                 potential_path = os.path.join(model_path, subdirs[0])
                 if os.path.exists(os.path.join(potential_path, "config.json")):
                     logger.info(f"Found model in subdirectory, updating path to: {potential_path}")
                     model_path = potential_path
                 else:
                     logger.warning(f"config.json not found in {model_path} or its subdirectory. Transformers might try to download.")
             else:
                 logger.warning(f"config.json not found in {model_path}. Transformers might try to download or fail with 'Repo id' error.")

        self.classifier = pipeline(
            "text-classification",
            model=model_path,
            top_k=None,  # 返回所有分数
            device=-1    # CPU
        )
        logger.info("Emotion model loaded successfully.")

    def _map_to_ekman(self, scores: Dict[str, float]) -> Dict[str, float]:
        """
        将 GoEmotions 分数映射到 Ekman 的 6 种基本情绪 + 中性。
        """
        ekman_mapping = {
            "anger": ["anger", "annoyance", "disapproval"],
            "disgust": ["disgust"],
            "fear": ["fear", "nervousness"],
            "joy": ["joy", "amusement", "approval", "excitement", "gratitude", "love", "optimism", "relief", "pride", "admiration", "desire", "caring"],
            "sadness": ["sadness", "disappointment", "embarrassment", "grief", "remorse"],
            "surprise": ["surprise", "confusion", "curiosity", "realization"],
            "neutral": ["neutral"]
        }
        
        ekman_scores = {k: 0.0 for k in ekman_mapping.keys()}
        
        for ekman, go_emotions in ekman_mapping.items():
            for emotion in go_emotions:
                if emotion in scores:
                    ekman_scores[ekman] += scores[emotion]
        
        return ekman_scores

    def _translate_to_english(self, text: str, user_settings=None, trigger_message_id: int = None, user_id: str = None, original_text: str = None, execution_id: str = None) -> Optional[str]:
        """
        使用 LLM 将文本翻译为英文;失败返回 None。

        失败时**不能**退回原文:GoEmotions 是英文模型,中文原文喂进去实测恒为
        neutral 0.99999 —— 看起来像一个很确定的结果,其实是噪声。调用方据 None
        放弃本轮分析,比交出一个假的 neutral 诚实得多。
        """
        from app.prompts.templates import get_translation_prompt, get_translation_system_prompt
        llm = get_llm_service()
        
        try:
            # 简单的翻译提示词
            prompt = get_translation_prompt(text)
            
            # 从 user_settings 提取 user_id 如果存在，否则使用参数传入的 user_id
            final_user_id = user_id or (getattr(user_settings, 'user_id', None) if user_settings else None)
            
            metadata = {
                "trigger_message": original_text if original_text else text, 
                "agent_name": "EmotionTranslator",
                "trigger_message_id": trigger_message_id,
                "execution_id": execution_id,
            }
            if final_user_id:
                metadata["user_id"] = final_user_id
            
            english_text = llm.generate_response(
            system_prompt=get_translation_system_prompt(), 
            user_input=prompt, 
            context="",
            user_settings=user_settings,
            metadata=metadata,
            request_timeout=60, # 60秒超时
            max_retries=0      # 不重试
        )
            # generate_response 失败时不抛异常,而是返回 "Error generating response: ..." 字符串。
            # 旧实现只接异常,这段错误文案就被当成译文送进模型 —— 结果同样是 neutral 0.99999。
            if not english_text or english_text.startswith(LLM_ERROR_PREFIX):
                logger.warning(f"Translation failed (LLM error): {(english_text or '')[:80]!r}")
                return None
            # 清理 LLM 可能产生的多余输出 (尽管提示词要求 ONLY)
            english_text = english_text.strip().strip('"')
            if not english_text:
                logger.warning("Translation failed (empty translation)")
                return None
            logger.info(f"Translated for Emotion: '{text[:20]}...' -> '{english_text[:50]}...'")
            return english_text
        except Exception as e:
            logger.warning(f"Translation failed: {e}")
            return None

    def analyze(self, text: str, user_settings=None, trigger_message_id: int = None, user_id: str = None, original_text: str = None, execution_id: str = None) -> Dict[str, float]:
        """
        分析文本并返回 {emotion: score} 字典。

        分析不可用时返回**空字典**,而不是编一个结果:
        - 中文翻译失败:英文模型吃中文原文实测恒为 neutral 0.99999,是噪声不是信号;
        - 模型报错:旧实现返回 {"error": 0.0},节点对全 0 的 Ekman 分布排序后首位恒为
          anger,会被写进用户状态并注入回复提示词 —— 一个与用户无关的信号。
        空字典不会被 analyze_async 缓存(见 should_cache),下一轮会重新分析。
        """
        if not self.classifier:
            logger.warning("Emotion classifier not initialized, returning neutral scores")
            return {"neutral": 1.0}

        # 1. 检查是否需要翻译
        analysis_text = text
        if is_chinese(text):
            # 如果是中文，先翻译成英文（因为 GoEmotions 是英文模型）
            analysis_text = self._translate_to_english(text, user_settings, trigger_message_id, user_id, original_text, execution_id=execution_id)
            if analysis_text is None:
                logger.warning("Emotion analysis skipped this turn: translation unavailable")
                return {}

        try:
            # 2. 先按字符截断,再让 tokenizer 按 512 token 截断。字符数防不住 token 数:
            #    2048 个字符的短词文本实测 685 token,不开 truncation 直接 RuntimeError,
            #    长上下文下情绪分析整轮失败。
            results = self.classifier(analysis_text[:EMOTION_TEXT_TRUNCATE_LIMIT], truncation=True)
            
            # results 是字典列表的列表: [[{'label': 'joy', 'score': 0.9}, ...]]
            # 展平并转换为字典
            scores = {item['label']: item['score'] for item in results[0]}
            return scores
        except Exception as e:
            logger.error(f"Error during emotion analysis: {e}")
            return {}

    def get_ekman_scores(self, text: str) -> Dict[str, float]:
        scores = self.analyze(text)
        return self._map_to_ekman(scores)

    def get_top_emotions(self, text: str, top_k: int = EMOTION_TOP_K) -> List[tuple]:
        scores = self.analyze(text)
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_scores[:top_k]

    # should_cache=bool:空字典表示"本轮分析不可用"(翻译失败/模型报错)。
    # 若也缓存 24 小时,一次 LLM 抖动就会把这段文本钉死成"没有情绪"。
    @cache_result(ttl=EMOTION_CACHE_TTL, key_builder=emotion_key_builder, should_cache=bool)
    async def analyze_async(self, text: str, user_settings=None, trigger_message_id: int = None, user_id: str = None, original_text: str = None, execution_id: str = None) -> Dict[str, float]:
        """
        Async wrapper for analyze with Redis caching.
        TTL = 24 hours (emotions for static text don't change).
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
            
        return await loop.run_in_executor(
            None, 
            lambda: self.analyze(text, user_settings, trigger_message_id, user_id, original_text, execution_id)
        )

@lru_cache()
def get_emotion_service():
    return EmotionService()