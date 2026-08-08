from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class MemorySearchInput(BaseModel):
    query: str
    user_id: str
    limit: Optional[int] = None
    topic_summary: Optional[str] = None
    session_id: Optional[str] = None
    filters: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class MemoryItem(BaseModel):
    text: str
    score: float
    metadata: Optional[Dict[str, Any]] = None


class MemorySearchOutput(BaseModel):
    memories: List[MemoryItem]
    query_used: str


class MemoryAddInput(BaseModel):
    text: str
    user_id: str
    metadata: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None
    memory_type: Optional[str] = None


class MemoryPolicyInput(BaseModel):
    short_term_k: Optional[int] = None
    long_term_k: Optional[int] = None
    similarity_threshold: Optional[float] = None
    write_strategy: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
