from typing import Dict, Optional, Any
from langchain_core.messages import SystemMessage, HumanMessage
from ..shared.llm import create_default_llm

class LLMService:
    def __init__(self):
        self.client = create_default_llm()

    async def generate_response_async(
        self,
        system_prompt: str,
        user_input: str,
        context: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"{context}\n\n{user_input}" if context else user_input)
        ]
        
        response = await self.client.ainvoke(messages)
        return response.content

_llm_service = LLMService()

def get_llm_service() -> LLMService:
    return _llm_service
