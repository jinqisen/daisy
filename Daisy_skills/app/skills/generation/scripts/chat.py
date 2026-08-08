from typing import Any, Dict, List, Optional
import json
from app.services.llm import get_llm_service

async def execute(input_data: Dict[str, Any], context: Optional[Any] = None) -> Dict[str, Any]:
    llm = get_llm_service()
    messages = input_data.get("messages")
    system_prompt = input_data.get("system_prompt")
    user_input = input_data.get("user_input")
    raw_context = input_data.get("context")

    if raw_context is None and context is not None:
        raw_context = getattr(context, "metadata", None)

    context_payload = {}
    for key in ("emotion", "topic_summary", "memories", "portrait", "retrieved_context", "history"):
        value = input_data.get(key)
        if value not in (None, "", [], {}):
            context_payload[key] = value

    if raw_context is None and context_payload:
        raw_context = context_payload

    if raw_context is None:
        context_text = ""
    elif isinstance(raw_context, str):
        context_text = raw_context
    else:
        context_text = json.dumps(raw_context, ensure_ascii=False)

    if not user_input and messages:
        last_message = messages[-1]
        if isinstance(last_message, dict):
            user_input = last_message.get("content")
        else:
            user_input = str(last_message)

    if not user_input and not messages:
        return {
            "error": "No input provided (messages, system_prompt, or user_input required)"
        }

    response_text = await llm.generate_response_async(
        system_prompt=system_prompt or "You are a helpful assistant.",
        user_input=user_input or "",
        context=context_text
    )

    return {
        "content": response_text,
        "role": "assistant"
    }
