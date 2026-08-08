import structlog
from langchain_core.messages import HumanMessage, AIMessage
from typing import Dict, Any, Optional
import uuid
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ..core.config import settings
from runtime import (
    SkillLoader,
    SkillDiscovery,
    SkillExecutor,
    DialogueFlowOrchestrator,
    StateManager,
    StateType
)
from .graph import create_graph, initialize_runtime

logger = structlog.get_logger()

_skill_loader = None
_skill_discovery = None
_skill_executor = None
_flow_orchestrator = None
_state_manager = None


async def get_runtime():
    global _skill_loader, _skill_discovery, _skill_executor, _flow_orchestrator, _state_manager
    
    if _skill_loader is None:
        _skill_loader = SkillLoader()
        await _skill_loader.discover_skills("/Users/anykong/Daisy_Demo/Daisy_skills/app/skills")
        
        _skill_discovery = SkillDiscovery(_skill_loader)
        await _skill_discovery.build_index()
        
        _skill_executor = SkillExecutor(_skill_loader)
        _flow_orchestrator = DialogueFlowOrchestrator(_skill_executor)
        _state_manager = StateManager()
        
        logger.info("agent_skills_runtime_initialized")
    
    return {
        "skill_loader": _skill_loader,
        "skill_discovery": _skill_discovery,
        "skill_executor": _skill_executor,
        "flow_orchestrator": _flow_orchestrator,
        "state_manager": _state_manager
    }


class AgentWorkflow:
    def __init__(self):
        self.graph = create_graph()

    async def run(
        self,
        user_input: str,
        user_id: str = "test_user",
        session_id: Optional[str] = None,
        conversation_id: Optional[str] = None
    ) -> str:
        """
        Run the LangGraph workflow with Agent Skills.
        """
        await get_runtime()
        
        if session_id is None:
            session_id = f"{user_id}_default"
        if conversation_id is None:
            conversation_id = f"{session_id}_conv"
        
        initial_state = {
            "user_input": user_input,
            "user_id": user_id,
            "session_id": session_id,
            "conversation_id": conversation_id,
            "chat_history": [],
            "route": "standard",
            "response": "",
            "tool_calls": [],
            "tool_results": [],
            "next_step": ""
        }

        try:
            final_state = await self.graph.ainvoke(initial_state)
            return final_state.get("response", "No response generated.")
        except Exception as e:
            logger.error("workflow_execution_failed", error=str(e))
            return f"Error executing workflow: {e}"


__all__ = ["AgentWorkflow", "get_runtime"]
