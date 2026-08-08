from __future__ import annotations

from typing import Any, Dict

from ...core.error import make_error, make_admin_result
from ...core.logging import get_trace_id
from ...core.registry import ToolRegistry, ToolSpec
from ...shared.utils import normalize_chat_messages
from .schema import EmotionAnalyzeInput, EmotionAnalyzeOutput, EmotionConfigInput, EmotionScore
from .service import analyze_text, update_config, _map_to_ekman, _config


async def emotion_analyze(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = EmotionAnalyzeInput.model_validate(payload)
    scores = analyze_text(data.text)
    ekman_scores = _map_to_ekman(scores)
    top_items = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:3]
    top_emotions = [EmotionScore(name=name, score=score).model_dump() for name, score in top_items]
    output = EmotionAnalyzeOutput(
        scores=scores,
        ekman_scores=ekman_scores,
        top_emotions=top_emotions,
        engagement_score=float(sum(scores.values())),
    )
    return output.model_dump()


async def emotion_update_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = EmotionConfigInput.model_validate(payload)
    updated_fields = update_config(
        model_name=data.model_name,
        context_turns=data.context_turns,
        context_max_chars=data.context_max_chars,
        ekman_mapping_version=data.ekman_mapping_version,
    )
    trace_id = get_trace_id()
    return make_admin_result(status="ok", message="updated", updated_fields=updated_fields, trace_id=trace_id).model_dump()


def register_emotion_tools(registry: ToolRegistry):
    registry.add(
        ToolSpec(
            name="emotion.analyze",
            description="Analyze emotion scores and Ekman mapping",
            input_model=EmotionAnalyzeInput,
            handler=emotion_analyze,
            skill="emotion",
            admin=False,
        )
    )
    registry.add(
        ToolSpec(
            name="emotion.update_config",
            description="Update emotion runtime config",
            input_model=EmotionConfigInput,
            handler=emotion_update_config,
            skill="emotion",
            admin=True,
        )
    )
