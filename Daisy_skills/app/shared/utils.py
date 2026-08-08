from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from .models import ChatMessage


def truncate_text(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def normalize_chat_messages(raw: Iterable[Any], max_items: int, max_chars: int) -> List[ChatMessage]:
    items = list(raw)[-max_items:] if max_items > 0 else list(raw)
    normalized: List[ChatMessage] = []
    for item in items:
        if isinstance(item, ChatMessage):
            normalized.append(ChatMessage(**item.model_dump()))
            continue
        if isinstance(item, dict):
            data = dict(item)
            content = data.get("content") or ""
            data["content"] = truncate_text(str(content), max_chars)
            normalized.append(ChatMessage(**data))
            continue
        if isinstance(item, str):
            normalized.append(ChatMessage(role="user", content=truncate_text(item, max_chars)))
            continue
        normalized.append(ChatMessage(role="user", content=truncate_text(str(item), max_chars)))
    return normalized


def compact_texts(texts: Iterable[str], max_chars: int) -> str:
    combined = "\n".join([t for t in texts if t])
    return truncate_text(combined, max_chars)
