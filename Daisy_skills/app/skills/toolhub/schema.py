from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class ToolHubSearchInput(BaseModel):
    query: str
    top_k: Optional[int] = None
    locale: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ToolHubSearchResult(BaseModel):
    title: str
    summary: str
    url: Optional[str] = None
    site_name: Optional[str] = None


class ToolHubSearchOutput(BaseModel):
    results: List[ToolHubSearchResult]
    query_used: str


class ToolHubCalculateInput(BaseModel):
    expression: str
    metadata: Optional[Dict[str, Any]] = None


class ToolHubCalculateOutput(BaseModel):
    value: str
