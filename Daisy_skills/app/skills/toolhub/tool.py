from __future__ import annotations

from typing import Any, Dict

from ...core.registry import ToolRegistry, ToolSpec
from .schema import ToolHubSearchInput, ToolHubSearchOutput, ToolHubSearchResult, ToolHubCalculateInput, ToolHubCalculateOutput
from .service import search_web, calculate_expression


async def toolhub_search(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = ToolHubSearchInput.model_validate(payload)
    top_k = data.top_k or 3
    results = await search_web(data.query, top_k)
    items = [ToolHubSearchResult(**item).model_dump() for item in results]
    output = ToolHubSearchOutput(results=items, query_used=data.query)
    return output.model_dump()


async def toolhub_calculate(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = ToolHubCalculateInput.model_validate(payload)
    value = calculate_expression(data.expression)
    output = ToolHubCalculateOutput(value=value)
    return output.model_dump()


def register_toolhub_tools(registry: ToolRegistry):
    registry.add(
        ToolSpec(
            name="toolhub.search",
            description="Search web for information",
            input_model=ToolHubSearchInput,
            handler=toolhub_search,
            skill="toolhub",
        )
    )
    registry.add(
        ToolSpec(
            name="toolhub.calculate",
            description="Calculate a math expression",
            input_model=ToolHubCalculateInput,
            handler=toolhub_calculate,
            skill="toolhub",
        )
    )
