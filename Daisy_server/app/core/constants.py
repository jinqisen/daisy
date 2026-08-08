import json
import os
import logging
from typing import List, Dict, Any

# =============================================================================
# Configuration Loading Logic
# =============================================================================

def _load_config() -> Dict[str, Any]:
    """
    Load configuration from server_config.json located at the project root.
    """
    try:
        # app/core/constants.py -> app/core -> app -> Daisy_server
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        config_path = os.path.join(base_dir, "server_config.json")
        
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            logging.warning(f"server_config.json not found at {config_path}. Using hardcoded defaults.")
            return {}
    except Exception as e:
        logging.error(f"Failed to load server_config.json: {e}")
        return {}

_CONFIG = _load_config()

def _get(key: str, default: Any) -> Any:
    """Helper to retrieve config value with fallback."""
    return _CONFIG.get(key, default)


# =============================================================================
# 情感分析 (Emotion Analysis) 配置
# =============================================================================
EMOTION_TEXT_TRUNCATE_LIMIT = _get("EMOTION_TEXT_TRUNCATE_LIMIT", 2048)       # 情感分析模型的输入文本最大长度截断，避免超过模型限制
EMOTION_CACHE_TTL = _get("EMOTION_CACHE_TTL", 86400)               # 情感分析结果在 Redis 中的缓存时间（秒），默认 24 小时
EMOTION_TOP_K = _get("EMOTION_TOP_K", 3)                       # 每次分析返回置信度最高的前 K 个情感标签

# 投入度 (Engagement) 计算权重配置
ENGAGEMENT_LENGTH_THRESHOLD = _get("ENGAGEMENT_LENGTH_THRESHOLD", 50.0)      # 文本长度评分的基准阈值（字符数），达到此长度得满分
ENGAGEMENT_WEIGHT_INTENSITY = _get("ENGAGEMENT_WEIGHT_INTENSITY", 0.5)       # 投入度计算中“情感强度”的权重
ENGAGEMENT_WEIGHT_AROUSAL = _get("ENGAGEMENT_WEIGHT_AROUSAL", 0.3)         # 投入度计算中“唤醒度”的权重
ENGAGEMENT_WEIGHT_LENGTH = _get("ENGAGEMENT_WEIGHT_LENGTH", 0.2)          # 投入度计算中“文本长度”的权重

# =============================================================================
# 强化学习 (RL Agent) 与人格 (Personality) 配置
# =============================================================================
PERSONALITY_TYPES = _get("PERSONALITY_TYPES", ["Eros", "Ludus", "Storge", "Pragma", "Mania", "Agape"])  # 系统支持的六种恋爱人格类型
DEFAULT_PERSONALITY = _get("DEFAULT_PERSONALITY", "Pragma")          # 系统默认初始人格
RL_STATE_DIM = _get("RL_STATE_DIM", 28)                       # RL 模型的输入状态向量维度 (28种 GoEmotions 情感维度)
RL_ACTION_DIM = _get("RL_ACTION_DIM", 6)                       # RL 模型的输出动作维度 (对应 6 种人格)

ORDERED_EMOTIONS = _get("ORDERED_EMOTIONS", [
    "admiration", "amusement", "anger", "annoyance", "approval", "caring",
    "confusion", "curiosity", "desire", "disappointment", "disapproval",
    "disgust", "embarrassment", "excitement", "fear", "gratitude", "grief",
    "joy", "love", "nervousness", "optimism", "pride", "realization",
    "relief", "remorse", "sadness", "surprise", "neutral"
])

# 人格主导性判断阈值
RL_DOMINANT_THRESHOLD = _get("RL_DOMINANT_THRESHOLD", 0.6)             # 判定某一人格为主导人格的最小概率阈值
RL_DOMINANT_TARGET = _get("RL_DOMINANT_TARGET", 0.65)               # 当触发主导模式时，将该人格权重提升到的目标值

# 混合人格模式阈值
RL_MIXED_MODE_TOP1_THRESHOLD = _get("RL_MIXED_MODE_TOP1_THRESHOLD", 0.25)     # 混合模式下，第一候选人格的最小概率阈值
RL_MIXED_MODE_TOP2_THRESHOLD = _get("RL_MIXED_MODE_TOP2_THRESHOLD", 0.20)     # 混合模式下，第二候选人格的最小概率阈值

# =============================================================================
# Multi-Agent 协作相关 (Lite Implementation)
MULTI_AGENT_ACTIVE_THRESHOLD = _get("MULTI_AGENT_ACTIVE_THRESHOLD", 0.15)            # 人格参与多智能体讨论的权重门槛
MULTI_AGENT_TOP_PERSONAS_COUNT = _get("MULTI_AGENT_TOP_PERSONAS_COUNT", 3)             # 参与多智能体讨论的最大人格数量限制

# =============================================================================
# 生成与缓存 (Generation / Cache) 配置
# =============================================================================
STYLE_ANALYSIS_CACHE_TTL = _get("STYLE_ANALYSIS_CACHE_TTL", 3600)         # 风格分析结果的缓存时间（秒），默认 1 小时
DEFAULT_LLM_TEMPERATURE = _get("DEFAULT_LLM_TEMPERATURE", 0.7)           # LLM 生成回复时的默认温度参数 (创造性控制)

# =============================================================================
# 记忆服务 (Memory) 配置
# =============================================================================
# 搜索触发条件
MEMORY_SEARCH_MIN_WORDS = _get("MEMORY_SEARCH_MIN_WORDS", 5)             # 触发记忆搜索的最小单词数 (英文分词)
MEMORY_SEARCH_MIN_CHARS = _get("MEMORY_SEARCH_MIN_CHARS", 5)            # 触发记忆搜索的最小字符数 (用于中文/短文本)

# 记忆服务专用 LLM 配置
MEMORY_LLM_TEMPERATURE = _get("MEMORY_LLM_TEMPERATURE", 0.1)            # 记忆处理 (摘要/提取) 时的温度，需保持低创造性以确保准确
MEMORY_LLM_MAX_TOKENS = _get("MEMORY_LLM_MAX_TOKENS", 1000)            # 记忆处理时的最大输出 Token 限制
