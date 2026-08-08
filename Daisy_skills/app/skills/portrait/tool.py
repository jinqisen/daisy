from __future__ import annotations

from typing import Any, Dict

from ...core.registry import ToolRegistry, ToolSpec
from ...shared.utils import normalize_chat_messages
from .schema import PortraitGenerateInput, PortraitGenerateOutput
from .service import generate_portrait


async def portrait_generate(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = PortraitGenerateInput.model_validate(payload)
    history = normalize_chat_messages(data.history or [], max_items=len(data.history or []), max_chars=400)
    history_texts = [item.content for item in history]
    result = generate_portrait(data.common_settings, history_texts)
    output = PortraitGenerateOutput(portrait_text=result["portrait_text"], character_card=result["character_card"])
    return output.model_dump()


def register_portrait_tools(registry: ToolRegistry):
    registry.add(
        ToolSpec(
            name="portrait.generate",
            description="Generate portrait text and character card",
            input_model=PortraitGenerateInput,
            handler=portrait_generate,
            skill="portrait",
        )
    )
