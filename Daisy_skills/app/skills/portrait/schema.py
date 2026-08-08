from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from ...shared.models import ChatMessage


class PortraitGenerateInput(BaseModel):
    user_id: str
    common_settings: Dict[str, Any]
    history: Optional[List[ChatMessage]] = None
    persona_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class PortraitGenerateOutput(BaseModel):
    portrait_text: str
    character_card: Dict[str, Any]
