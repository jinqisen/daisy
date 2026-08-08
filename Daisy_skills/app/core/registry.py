from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Type
from pydantic import BaseModel


ToolHandler = Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]


@dataclass
class ToolSpec:
    name: str
    description: str
    input_model: Type[BaseModel]
    handler: ToolHandler
    skill: str
    admin: bool = False


class ToolRegistry:
    def __init__(self):
        self._tools: List[ToolSpec] = []

    def add(self, tool: ToolSpec):
        self._tools.append(tool)

    def list(self) -> List[ToolSpec]:
        return list(self._tools)


registry = ToolRegistry()
