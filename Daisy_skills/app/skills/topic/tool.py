from __future__ import annotations

from typing import Any, Dict

from ...core.registry import ToolRegistry, ToolSpec
from ...shared.utils import normalize_chat_messages
from .schema import TopicSummarizeInput, TopicSummarizeOutput
from .service import summarize_topic


async def topic_summarize(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = TopicSummarizeInput.model_validate(payload)
    history = normalize_chat_messages(data.history, max_items=len(data.history), max_chars=400)
    history_texts = [item.content for item in history]
    summary = summarize_topic(history_texts, data.latest_message, max_tokens=data.max_tokens)
    output = TopicSummarizeOutput(summary=summary, session_id=data.session_id, topic_tags=None)
    return output.model_dump()


def register_topic_tools(registry: ToolRegistry):
    registry.add(
        ToolSpec(
            name="topic.summarize",
            description="Summarize conversation topic",
            input_model=TopicSummarizeInput,
            handler=topic_summarize,
            skill="topic",
        )
    )
