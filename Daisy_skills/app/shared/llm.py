from __future__ import annotations

from typing import List, Optional
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..core.config import settings


def _resolve_api_key() -> Optional[str]:
    if settings.DEFAULT_LLM_PROVIDER == "siliconflow":
        return settings.SILICONFLOW_API_KEY
    if settings.DEFAULT_LLM_PROVIDER == "huaweicloud":
        return settings.MAAS_API_KEY
    return settings.OPENAI_API_KEY


def create_default_llm() -> ChatOpenAI:
    return ChatOpenAI(
        api_key=_resolve_api_key(),
        base_url=settings.DEFAULT_LLM_BASE_URL,
        model=settings.DEFAULT_LLM_MODEL_NAME,
        temperature=0.7,
    )


async def simple_generate(system_prompt: str, messages: List[BaseMessage]) -> str:
    llm = create_default_llm()
    payload = [SystemMessage(content=system_prompt)] + messages
    response = await llm.ainvoke(payload)
    return response.content
