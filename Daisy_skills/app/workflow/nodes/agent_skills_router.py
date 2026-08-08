from typing import Any, Dict, List, Optional
from enum import Enum
import structlog

from ...runtime import (
    SkillExecutor,
    SkillDiscovery,
    DialogueFlowOrchestrator,
    DialogueFlowBuilder,
    PredefinedFlows,
    DialogueContext,
    FlowType,
    FlowStatus,
    StateManager,
    StateType
)

logger = structlog.get_logger()


class RouteDecision(Enum):
    STANDARD = "standard"
    QUICK = "quick"
    CONTEXT_AWARE = "context_aware"
    TOOL_REQUIRED = "tool_required"


class AgentSkillsRouter:
    def __init__(
        self,
        skill_executor: SkillExecutor,
        skill_discovery: SkillDiscovery,
        flow_orchestrator: DialogueFlowOrchestrator,
        state_manager: StateManager
    ):
        self.skill_executor = skill_executor
        self.skill_discovery = skill_discovery
        self.flow_orchestrator = flow_orchestrator
        self.state_manager = state_manager
        
    async def route(
        self,
        message: str,
        user_id: str,
        session_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> RouteDecision:
        try:
            emotion_result = await self.skill_executor.execute(
                skill_name="emotion",
                operation="analyze",
                input_data={
                    "text": message,
                    "user_id": user_id,
                    "session_id": session_id or "",
                    "context_history": (context or {}).get("chat_history", [])
                },
                context=context or {}
            )

            top_emotion = "neutral"
            if emotion_result and emotion_result.success and emotion_result.data:
                emotion_data = emotion_result.data
                emotion_scores = emotion_data.get("scores") or emotion_data.get("emotion_scores") or {}
                ekman_scores = emotion_data.get("ekman_scores") or {}
                scores_for_route = ekman_scores or emotion_scores
                if scores_for_route:
                    top_emotion = max(scores_for_route.items(), key=lambda x: x[1])[0]

            if top_emotion in ["anger", "fear", "sadness"]:
                return RouteDecision.CONTEXT_AWARE
            
            message_length = len(message)
            has_question = any(q in message for q in ["?", "？", "什么", "如何", "怎么", "为什么"])
            
            if message_length < 50 and not has_question:
                return RouteDecision.QUICK
            
            tool_keywords = ["搜索", "查询", "计算", "翻译", "天气", "时间", "日期", "记住", "保存"]
            if any(keyword in message for keyword in tool_keywords):
                return RouteDecision.TOOL_REQUIRED

            return RouteDecision.CONTEXT_AWARE
            
        except Exception as e:
            logger.error("route_error", error=str(e))
            return RouteDecision.STANDARD


class AgentSkillsGenerator:
    def __init__(
        self,
        skill_executor: SkillExecutor,
        flow_orchestrator: DialogueFlowOrchestrator,
        state_manager: StateManager
    ):
        self.skill_executor = skill_executor
        self.flow_orchestrator = flow_orchestrator
        self.state_manager = state_manager
        
    async def generate(
        self,
        message: str,
        user_id: str,
        session_id: str,
        conversation_id: str,
        route_decision: RouteDecision,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        try:
            import uuid
            flow_id = str(uuid.uuid4())
            
            dialogue_context = DialogueContext(
                session_id=session_id,
                user_id=user_id,
                message=message,
                metadata=context or {}
            )
            
            if route_decision == RouteDecision.STANDARD:
                builder = PredefinedFlows.create_standard_dialogue_flow(flow_id)
            elif route_decision == RouteDecision.QUICK:
                builder = PredefinedFlows.create_quick_response_flow(flow_id)
            elif route_decision == RouteDecision.CONTEXT_AWARE:
                builder = PredefinedFlows.create_context_aware_flow(flow_id)
            elif route_decision == RouteDecision.TOOL_REQUIRED:
                builder = PredefinedFlows.create_context_aware_flow(flow_id)
            else:
                builder = PredefinedFlows.create_context_aware_flow(flow_id)
            
            steps = builder.build()
            self.flow_orchestrator.create_flow(flow_id, FlowType.SEQUENTIAL, steps, dialogue_context)
            
            flow_result = await self.flow_orchestrator.execute_flow(flow_id, dialogue_context)
            
            await self.state_manager.add_message(conversation_id, "user", message)
            
            response_text = ""
            if flow_result.final_result:
                response_text = flow_result.final_result.get("response", "")
            
            if not response_text:
                for step in flow_result.steps:
                    if step.result and "response" in step.result:
                        response_text = step.result["response"]
                        break
            
            await self.state_manager.add_message(conversation_id, "assistant", response_text)
            
            return {
                "response": response_text,
                "flow_id": flow_id,
                "flow_status": flow_result.status.value,
                "steps": [
                    {
                        "step_id": step.step_id,
                        "skill_name": step.skill_name,
                        "operation": step.operation,
                        "status": step.status.value,
                        "result": step.result
                    }
                    for step in flow_result.steps
                ],
                "route": route_decision.value
            }
            
        except Exception as e:
            logger.error("generate_error", error=str(e))
            return {
                "response": "抱歉，我遇到了一些问题，请稍后再试。",
                "error": str(e),
                "route": route_decision.value
            }


async def agent_skills_router_node(state: Dict[str, Any]) -> Dict[str, Any]:
    try:
        message = state.get("user_input", "")
        user_id = state.get("user_id", "")
        session_id = state.get("session_id")
        conversation_id = state.get("conversation_id")
        context = state.get("context", {})
        
        skill_executor = state.get("_skill_executor")
        skill_discovery = state.get("_skill_discovery")
        flow_orchestrator = state.get("_flow_orchestrator")
        state_manager = state.get("_state_manager")
        
        router = AgentSkillsRouter(
            skill_executor=skill_executor,
            skill_discovery=skill_discovery,
            flow_orchestrator=flow_orchestrator,
            state_manager=state_manager
        )
        
        route_decision = await router.route(
            message=message,
            user_id=user_id,
            session_id=session_id,
            conversation_id=conversation_id,
            context=context
        )
        
        state["route"] = route_decision.value
        state["next_step"] = route_decision.value
        
        return state
        
    except Exception as e:
        logger.error("agent_skills_router_node_error", error=str(e))
        state["route"] = "standard"
        state["next_step"] = "standard"
        return state


async def agent_skills_generate_node(state: Dict[str, Any]) -> Dict[str, Any]:
    try:
        message = state.get("user_input", "")
        user_id = state.get("user_id", "")
        session_id = state.get("session_id", "")
        conversation_id = state.get("conversation_id", "")
        route = state.get("route", "standard")
        context = state.get("context", {})
        
        skill_executor = state.get("_skill_executor")
        flow_orchestrator = state.get("_flow_orchestrator")
        state_manager = state.get("_state_manager")
        
        generator = AgentSkillsGenerator(
            skill_executor=skill_executor,
            flow_orchestrator=flow_orchestrator,
            state_manager=state_manager
        )
        
        route_decision = RouteDecision(route)
        
        result = await generator.generate(
            message=message,
            user_id=user_id,
            session_id=session_id,
            conversation_id=conversation_id,
            route_decision=route_decision,
            context=context
        )
        
        state["response"] = result.get("response", "")
        state["flow_id"] = result.get("flow_id")
        state["flow_status"] = result.get("flow_status")
        state["steps"] = result.get("steps", [])
        state["tool_calls"] = []
        state["tool_results"] = []
        state["next_step"] = "end"
        
        return state
        
    except Exception as e:
        logger.error("agent_skills_generate_node_error", error=str(e))
        state["response"] = "抱歉，我遇到了一些问题，请稍后再试。"
        state["next_step"] = "end"
        return state


__all__ = [
    "RouteDecision",
    "AgentSkillsRouter",
    "AgentSkillsGenerator",
    "agent_skills_router_node",
    "agent_skills_generate_node"
]
