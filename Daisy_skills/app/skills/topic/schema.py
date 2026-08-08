from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from ...shared.models import ChatMessage


class TopicSummarizeInput(BaseModel):
    history: List[ChatMessage]
    latest_message: str
    session_id: str
    max_tokens: Optional[int] = None
    language_hint: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class TopicSummarizeOutput(BaseModel):
    summary: str
    session_id: str
    topic_tags: Optional[List[str]] = None
