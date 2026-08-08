from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel


class PersonaSelectInput(BaseModel):
    user_id: str
    emotion_scores: Dict[str, float]
    ekman_scores: Optional[Dict[str, float]] = None
    mode: Optional[str] = None
    context_summary: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class PersonaSelectOutput(BaseModel):
    selected_personality: str
    weights: Optional[Dict[str, float]] = None
    target_emotion: str
    metadata: Optional[Dict[str, Any]] = None


class PersonaStrategyInput(BaseModel):
    mode: Optional[str] = None
    weight_overrides: Optional[Dict[str, float]] = None
    metadata: Optional[Dict[str, Any]] = None
