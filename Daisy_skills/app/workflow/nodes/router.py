from typing import Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage
from ..state import AgentState
from ...core.config import settings
from langchain_openai import ChatOpenAI

async def router_node(state: AgentState) -> Dict[str, Any]:
    """
    Decides the complexity of the response: STANDARD vs DEEP.
    """
    user_input = state["user_input"]
    
    # Simple heuristic for now, can be replaced by LLM classifier
    if len(user_input) < 5 and user_input.lower() in ["hi", "hello", "ok", "yes", "no"]:
        return {"route": "STANDARD"}
        
    return {"route": "DEEP"}
