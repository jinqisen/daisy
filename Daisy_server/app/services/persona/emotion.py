import os
import asyncio
import hashlib
from typing import List, Dict, Any
from transformers import pipeline
import structlog
from functools import lru_cache
from app.core.config import settings
from app.core.constants import EMOTION_TEXT_TRUNCATE_LIMIT, EMOTION_CACHE_TTL, EMOTION_TOP_K
from app.core.utils import is_chinese
from app.core.llm import get_llm_service # Import LLM service
from app.core.cache import cache_result
import re

logger = structlog.get_logger()

def emotion_key_builder(func, *args, **kwargs):
    # args[0] is self, args[1] is text
    text = kwargs.get("text")
    if not text and len(args) > 1:
        text = args[1]
    
    if not text:
        # Fallback if text is empty (shouldn't happen usually)
        return f"emotion:empty"
        
    text_hash = hashlib.md5(text.encode()).hexdigest()
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

    def _translate_to_english(self, text: str, user_settings=None, trigger_message_id: int = None, user_id: str = None, original_text: str = None, execution_id: str = None) -> str:
        """使用 LLM 将文本翻译为英文"""
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
            # 清理 LLM 可能产生的多余输出 (尽管提示词要求 ONLY)
            english_text = english_text.strip().strip('"')
            logger.info(f"Translated for Emotion: '{text[:20]}...' -> '{english_text[:50]}...'")
            return english_text
        except Exception as e:
            logger.warning(f"Translation failed (fallback to original): {e}")
            return text

    def analyze(self, text: str, user_settings=None, trigger_message_id: int = None, user_id: str = None, original_text: str = None, execution_id: str = None) -> Dict[str, float]:
        """
        分析文本并返回 {emotion: score} 字典
        """
        if not self.classifier:
            logger.warning("Emotion classifier not initialized, returning neutral scores")
            return {"neutral": 1.0}

        try:
            # 1. 检查是否需要翻译
            analysis_text = text
            if is_chinese(text):
                # 如果是中文，先翻译成英文（因为 GoEmotions 是英文模型）
                analysis_text = self._translate_to_english(text, user_settings, trigger_message_id, user_id, original_text, execution_id=execution_id)
            
            # 2. 截断文本至 512 字符以避免超出模型限制
            results = self.classifier(analysis_text[:EMOTION_TEXT_TRUNCATE_LIMIT])
            
            # results 是字典列表的列表: [[{'label': 'joy', 'score': 0.9}, ...]]
            # 展平并转换为字典
            scores = {item['label']: item['score'] for item in results[0]}
            return scores
        except Exception as e:
            logger.error(f"Error during emotion analysis: {e}")
            return {"error": 0.0}

    def get_ekman_scores(self, text: str) -> Dict[str, float]:
        scores = self.analyze(text)
        return self._map_to_ekman(scores)

    def get_top_emotions(self, text: str, top_k: int = EMOTION_TOP_K) -> List[tuple]:
        scores = self.analyze(text)
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_scores[:top_k]

    @cache_result(ttl=EMOTION_CACHE_TTL, key_builder=emotion_key_builder)
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