from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MemoryPolicy:
    short_term_k: int = 5
    long_term_k: int = 5
    similarity_threshold: float = 0.2
    write_strategy: str = "append"


@dataclass
class MemoryRecord:
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    dedup_key: str = ""


def _compute_dedup_key(text: str, metadata: Optional[Dict[str, Any]] = None) -> str:
    content = text
    if metadata:
        meta_str = str(sorted(metadata.items()))
        content = f"{text}|{meta_str}"
    return hashlib.sha256(content.encode()).hexdigest()


class MemoryStore:
    def __init__(self):
        self._data: Dict[str, List[MemoryRecord]] = {}
        self._dedup_index: Dict[str, set[str]] = {}
        self.policy = MemoryPolicy()

    def add(self, user_id: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        dedup_key = _compute_dedup_key(text, metadata)
        user_key = str(user_id)
        if user_key not in self._dedup_index:
            self._dedup_index[user_key] = set()
        if dedup_key in self._dedup_index[user_key]:
            return False
        items = self._data.setdefault(user_key, [])
        items.append(MemoryRecord(text=text, metadata=metadata or {}, dedup_key=dedup_key))
        self._dedup_index[user_key].add(dedup_key)
        return True

    def search(self, user_id: str, query: str, limit: int) -> List[MemoryRecord]:
        items = self._data.get(str(user_id), [])
        if not items:
            return []
        scored = []
        query_tokens = set(query.lower().split())
        for item in items:
            tokens = set(item.text.lower().split())
            overlap = len(tokens & query_tokens)
            score = overlap / max(len(query_tokens), 1)
            scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for score, item in scored[:limit] if score >= self.policy.similarity_threshold]


store = MemoryStore()


def update_policy(short_term_k: Optional[int] = None, long_term_k: Optional[int] = None, similarity_threshold: Optional[float] = None, write_strategy: Optional[str] = None) -> List[str]:
    updated: List[str] = []
    if short_term_k is not None:
        store.policy.short_term_k = short_term_k
        updated.append("short_term_k")
    if long_term_k is not None:
        store.policy.long_term_k = long_term_k
        updated.append("long_term_k")
    if similarity_threshold is not None:
        store.policy.similarity_threshold = similarity_threshold
        updated.append("similarity_threshold")
    if write_strategy is not None:
        store.policy.write_strategy = write_strategy
        updated.append("write_strategy")
    return updated
