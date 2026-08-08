from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from ...shared.models import ChatMessage


class EmotionAnalyzeInput(BaseModel):
    text: str
    user_id: str
    session_id: str
    language_hint: Optional[str] = None
    context_history: Optional[List[ChatMessage]] = None
    metadata: Optional[Dict[str, Any]] = None


class EmotionScore(BaseModel):
    name: str
    score: float


class EmotionAnalyzeOutput(BaseModel):
    scores: Dict[str, float]
    ekman_scores: Dict[str, float]
    top_emotions: List[EmotionScore]
    engagement_score: float


class EmotionConfigInput(BaseModel):
    model_name: Optional[str] = None
    context_turns: Optional[int] = None
    context_max_chars: Optional[int] = None
    ekman_mapping_version: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
