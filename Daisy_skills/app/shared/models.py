from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str
    name: Optional[str] = None
    timestamp_ms: Optional[int] = None
    message_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
