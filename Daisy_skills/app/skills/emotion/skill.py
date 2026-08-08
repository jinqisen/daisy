from typing import Dict, Any, List, Optional
from datetime import datetime


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
        self.model_name = "default"
        self.context_turns = 3
        self.context_max_chars = 512
        self.ekman_mapping_version = "v1"


_config = EmotionConfig()


def _truncate_text(text: str, max_length: int = 512) -> str:
    if len(text) <= max_length:
        return text
    return text[:max_length]


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


def _get_top_emotions(scores: Dict[str, float], top_n: int = 3) -> List[Dict[str, Any]]:
    sorted_emotions = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [{"name": k, "score": v} for k, v in sorted_emotions[:top_n] if v > 0]


def _calculate_engagement_score(scores: Dict[str, float]) -> float:
    positive_emotions = ["joy", "surprise"]
    negative_emotions = ["anger", "fear", "sadness", "disgust"]
    
    positive_score = sum(scores.get(e, 0.0) for e in positive_emotions)
    negative_score = sum(scores.get(e, 0.0) for e in negative_emotions)
    
    total = positive_score + negative_score
    if total == 0:
        return 0.5
    
    return (positive_score - negative_score) / 2 + 0.5


async def analyze(input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    text = input_data.get("text", "")
    user_id = input_data.get("user_id", "")
    session_id = input_data.get("session_id", "")
    language_hint = input_data.get("language_hint", "en")
    context_history = input_data.get("context_history", [])
    
    trimmed_text = _truncate_text(text, _config.context_max_chars)
    
    scores = _score_text(trimmed_text)
    ekman_scores = _map_to_ekman(scores)
    top_emotions = _get_top_emotions(scores)
    engagement_score = _calculate_engagement_score(scores)
    
    return {
        "scores": scores,
        "ekman_scores": ekman_scores,
        "top_emotions": top_emotions,
        "engagement_score": engagement_score,
        "metadata": {
            "user_id": user_id,
            "session_id": session_id,
            "language_hint": language_hint,
            "model_name": _config.model_name,
            "ekman_mapping_version": _config.ekman_mapping_version,
            "timestamp": datetime.utcnow().isoformat()
        }
    }


async def update_config(input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    updated_fields = []
    
    model_name = input_data.get("model_name")
    if model_name is not None:
        _config.model_name = model_name
        updated_fields.append("model_name")
    
    context_turns = input_data.get("context_turns")
    if context_turns is not None:
        _config.context_turns = context_turns
        updated_fields.append("context_turns")
    
    context_max_chars = input_data.get("context_max_chars")
    if context_max_chars is not None:
        _config.context_max_chars = context_max_chars
        updated_fields.append("context_max_chars")
    
    ekman_mapping_version = input_data.get("ekman_mapping_version")
    if ekman_mapping_version is not None:
        _config.ekman_mapping_version = ekman_mapping_version
        updated_fields.append("ekman_mapping_version")
    
    return {
        "status": "ok",
        "message": "Configuration updated successfully",
        "updated_fields": updated_fields,
        "current_config": {
            "model_name": _config.model_name,
            "context_turns": _config.context_turns,
            "context_max_chars": _config.context_max_chars,
            "ekman_mapping_version": _config.ekman_mapping_version
        }
    }


__all__ = ["analyze", "update_config"]
