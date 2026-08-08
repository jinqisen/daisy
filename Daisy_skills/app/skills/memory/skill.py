import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime


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
    created_at: str = ""
    memory_type: str = "short"


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

    def add(self, user_id: str, text: str, metadata: Optional[Dict[str, Any]] = None, memory_type: str = "short") -> bool:
        dedup_key = _compute_dedup_key(text, metadata)
        user_key = str(user_id)
        if user_key not in self._dedup_index:
            self._dedup_index[user_key] = set()
        if dedup_key in self._dedup_index[user_key]:
            return False
        items = self._data.setdefault(user_key, [])
        items.append(MemoryRecord(
            text=text,
            metadata=metadata or {},
            dedup_key=dedup_key,
            created_at=datetime.utcnow().isoformat(),
            memory_type=memory_type
        ))
        self._dedup_index[user_key].add(dedup_key)
        return True

    def search(self, user_id: str, query: str, limit: int, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        items = self._data.get(str(user_id), [])
        if not items:
            return []
        
        if filters:
            filtered_items = []
            for item in items:
                match = True
                for key, value in filters.items():
                    if key not in item.metadata or item.metadata[key] != value:
                        match = False
                        break
                if match:
                    filtered_items.append(item)
            items = filtered_items
        
        scored = []
        query_tokens = set(query.lower().split())
        for item in items:
            tokens = set(item.text.lower().split())
            overlap = len(tokens & query_tokens)
            score = overlap / max(len(query_tokens), 1)
            scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        
        results = []
        for score, item in scored[:limit]:
            if score >= self.policy.similarity_threshold:
                results.append({
                    "text": item.text,
                    "score": score,
                    "metadata": item.metadata,
                    "created_at": item.created_at,
                    "memory_type": item.memory_type
                })
        
        return results


store = MemoryStore()


async def search(input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    query = input_data.get("query", "")
    user_id = input_data.get("user_id", "")
    limit = input_data.get("limit", 5)
    topic_summary = input_data.get("topic_summary", "")
    session_id = input_data.get("session_id", "")
    filters = input_data.get("filters", {})
    
    memories = store.search(user_id, query, limit, filters)
    
    return {
        "memories": memories,
        "query_used": query,
        "total_count": len(memories),
        "metadata": {
            "user_id": user_id,
            "session_id": session_id,
            "topic_summary": topic_summary,
            "limit": limit,
            "similarity_threshold": store.policy.similarity_threshold,
            "timestamp": datetime.utcnow().isoformat()
        }
    }


async def add(input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    text = input_data.get("text", "")
    user_id = input_data.get("user_id", "")
    metadata = input_data.get("metadata", {})
    session_id = input_data.get("session_id", "")
    memory_type = input_data.get("memory_type", "short")
    
    success = store.add(user_id, text, metadata, memory_type)
    dedup_key = _compute_dedup_key(text, metadata)
    
    return {
        "success": success,
        "dedup_key": dedup_key,
        "message": "Memory added successfully" if success else "Memory already exists (dedup)",
        "metadata": {
            "user_id": user_id,
            "session_id": session_id,
            "memory_type": memory_type,
            "timestamp": datetime.utcnow().isoformat()
        }
    }


async def update_policy(input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    updated_fields = []
    
    short_term_k = input_data.get("short_term_k")
    if short_term_k is not None:
        store.policy.short_term_k = short_term_k
        updated_fields.append("short_term_k")
    
    long_term_k = input_data.get("long_term_k")
    if long_term_k is not None:
        store.policy.long_term_k = long_term_k
        updated_fields.append("long_term_k")
    
    similarity_threshold = input_data.get("similarity_threshold")
    if similarity_threshold is not None:
        store.policy.similarity_threshold = similarity_threshold
        updated_fields.append("similarity_threshold")
    
    write_strategy = input_data.get("write_strategy")
    if write_strategy is not None:
        store.policy.write_strategy = write_strategy
        updated_fields.append("write_strategy")
    
    return {
        "status": "ok",
        "message": "Policy updated successfully",
        "updated_fields": updated_fields,
        "current_policy": {
            "short_term_k": store.policy.short_term_k,
            "long_term_k": store.policy.long_term_k,
            "similarity_threshold": store.policy.similarity_threshold,
            "write_strategy": store.policy.write_strategy
        }
    }


__all__ = ["search", "add", "update_policy"]
