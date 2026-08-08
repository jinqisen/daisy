from __future__ import annotations

from typing import Any, Dict

from ...core.error import make_admin_result
from ...core.logging import get_trace_id
from ...core.registry import ToolRegistry, ToolSpec
from .schema import PersonaSelectInput, PersonaSelectOutput, PersonaStrategyInput
from .service import select_persona, update_strategy


async def persona_select(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = PersonaSelectInput.model_validate(payload)
    result = select_persona(data.emotion_scores)
    output = PersonaSelectOutput(
        selected_personality=result["selected_personality"],
        target_emotion=result["target_emotion"],
        weights=data.ekman_scores,
        metadata={"mode": data.mode},
    )
    return output.model_dump()


async def persona_update_strategy(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = PersonaStrategyInput.model_validate(payload)
    updated_fields = update_strategy(mode=data.mode, weight_overrides=data.weight_overrides)
    trace_id = get_trace_id()
    return make_admin_result(status="ok", message="updated", updated_fields=updated_fields, trace_id=trace_id).model_dump()


def register_persona_tools(registry: ToolRegistry):
    registry.add(
        ToolSpec(
            name="persona.select",
            description="Select persona based on emotion scores",
            input_model=PersonaSelectInput,
            handler=persona_select,
            skill="persona",
        )
    )
    registry.add(
        ToolSpec(
            name="persona.update_strategy",
            description="Update persona strategy",
            input_model=PersonaStrategyInput,
            handler=persona_update_strategy,
            skill="persona",
            admin=True,
        )
    )
