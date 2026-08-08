from __future__ import annotations

from typing import List

from ...shared.utils import compact_texts, truncate_text


def summarize_topic(history_texts: List[str], latest_message: str, max_tokens: int | None) -> str:
    max_chars = max_tokens * 4 if max_tokens else 400
    combined = compact_texts(history_texts + [latest_message], max_chars)
    return truncate_text(combined, max_chars)
