from __future__ import annotations

from typing import Dict, List

from ...core.config import settings
from ...shared.utils import truncate_text


_emotion_keywords = {
    "joy": ["开心", "快乐", "高兴", "喜悦", "喜欢", "幸福", "happy", "joy", "glad"],
    "sadness": ["难过", "伤心", "沮丧", "失落", "悲伤", "sad", "down"],
    "anger": ["生气", "愤怒", "火大", "烦", "怒", "angry", "mad"],
    "fear": ["害怕", "恐惧", "担心", "焦虑", "fear", "scared", "anxious"],
    "surprise": ["惊讶", "震惊", "意外", "surprise", "shocked"],
    "disgust": ["厌恶", "恶心", "讨厌", "disgust", "gross"],
}


class EmotionConfig:
    def __init__(self):
        self.model_name = settings.EMOTION_MODEL_NAME
        self.context_turns = settings.EMOTION_CONTEXT_TURNS
        self.context_max_chars = settings.EMOTION_CONTEXT_MAX_CHARS
        self.ekman_mapping_version = "v1"


_config = EmotionConfig()


def update_config(model_name: str | None = None, context_turns: int | None = None, context_max_chars: int | None = None, ekman_mapping_version: str | None = None) -> List[str]:
    updated: List[str] = []
    if model_name is not None:
        _config.model_name = model_name
        updated.append("model_name")
    if context_turns is not None:
        _config.context_turns = context_turns
        updated.append("context_turns")
    if context_max_chars is not None:
        _config.context_max_chars = context_max_chars
        updated.append("context_max_chars")
    if ekman_mapping_version is not None:
        _config.ekman_mapping_version = ekman_mapping_version
        updated.append("ekman_mapping_version")
    return updated


def _score_text(text: str) -> Dict[str, float]:
    lowered = text.lower()
    scores = {k: 0.0 for k in _emotion_keywords.keys()}
    for emotion, keywords in _emotion_keywords.items():
        for kw in keywords:
            if kw.lower() in lowered:
                scores[emotion] += 1.0
    total = sum(scores.values())
    if total == 0:
        return {"neutral": 1.0}
    return {k: v / total for k, v in scores.items()}


def _map_to_ekman(scores: Dict[str, float]) -> Dict[str, float]:
    ekman = {
        "anger": scores.get("anger", 0.0),
        "disgust": scores.get("disgust", 0.0),
        "fear": scores.get("fear", 0.0),
        "joy": scores.get("joy", 0.0),
        "sadness": scores.get("sadness", 0.0),
        "surprise": scores.get("surprise", 0.0),
        "neutral": scores.get("neutral", 0.0),
    }
    return ekman


def analyze_text(text: str) -> Dict[str, float]:
    trimmed = truncate_text(text, 512)
    return _score_text(trimmed)
