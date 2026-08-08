from __future__ import annotations

from typing import Any, Dict

from ...core.error import make_admin_result
from ...core.logging import get_trace_id
from ...core.registry import ToolRegistry, ToolSpec
from .schema import MemoryAddInput, MemorySearchInput, MemorySearchOutput, MemoryItem, MemoryPolicyInput
from .service import store, update_policy


async def memory_search(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = MemorySearchInput.model_validate(payload)
    limit = data.limit or store.policy.short_term_k
    records = store.search(data.user_id, data.query, limit=limit)
    memories = [MemoryItem(text=item.text, score=1.0, metadata=item.metadata).model_dump() for item in records]
    output = MemorySearchOutput(memories=memories, query_used=data.query)
    return output.model_dump()


async def memory_add(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = MemoryAddInput.model_validate(payload)
    added = store.add(data.user_id, data.text, metadata=data.metadata)
    trace_id = get_trace_id()
    if added:
        return make_admin_result(status="ok", message="added", updated_fields=["memory"], trace_id=trace_id).model_dump()
    else:
        return make_admin_result(status="ok", message="skipped (duplicate)", updated_fields=[], trace_id=trace_id).model_dump()


async def memory_update_policy(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = MemoryPolicyInput.model_validate(payload)
    updated_fields = update_policy(
        short_term_k=data.short_term_k,
        long_term_k=data.long_term_k,
        similarity_threshold=data.similarity_threshold,
        write_strategy=data.write_strategy,
    )
    trace_id = get_trace_id()
    return make_admin_result(status="ok", message="updated", updated_fields=updated_fields, trace_id=trace_id).model_dump()


def register_memory_tools(registry: ToolRegistry):
    registry.add(
        ToolSpec(
            name="memory.search",
            description="Search memories for a user",
            input_model=MemorySearchInput,
            handler=memory_search,
            skill="memory",
        )
    )
    registry.add(
        ToolSpec(
            name="memory.add",
            description="Add a memory for a user",
            input_model=MemoryAddInput,
            handler=memory_add,
            skill="memory",
        )
    )
    registry.add(
        ToolSpec(
            name="memory.update_policy",
            description="Update memory policy",
            input_model=MemoryPolicyInput,
            handler=memory_update_policy,
            skill="memory",
            admin=True,
        )
    )
