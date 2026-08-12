from typing import Dict, Any
from langgraph.graph import StateGraph, END
import structlog
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from .state import AgentState
from .nodes.generation import (
    standard_generate,
    context_aware_generate,
    tool_required_generate,
    quick_generate
)
from runtime import (
    SkillLoader,
    SkillDiscovery,
    SkillExecutor,
    DialogueFlowOrchestrator,
    StateManager,
    StateType
)

logger = structlog.get_logger()

_skill_loader = None
_skill_discovery = None
_skill_executor = None
_flow_orchestrator = None
_state_manager = None


async def initialize_runtime():
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


def create_graph():
    workflow = StateGraph(AgentState)
    
    workflow.add_node("router", router_node)
    workflow.add_node("generate", generate_node)
    
    workflow.set_entry_point("router")
    
    workflow.add_conditional_edges(
        "router",
        route_decision,
        {
            "standard": "generate",
            "quick": "generate",
            "context_aware": "generate",
            "tool_required": "generate"
        }
    )
    
    workflow.add_edge("generate", END)
    
    return workflow.compile()


async def router_node(state: AgentState) -> AgentState:
    try:
        await initialize_runtime()
        
        user_input = state["user_input"]
        user_id = state["user_id"]
        session_id = state.get("session_id", f"{user_id}_default")
        conversation_id = state.get("conversation_id", f"{session_id}_conv")
        
        if _state_manager:
            session = await _state_manager.get_session(session_id)
            if not session:
                await _state_manager.create_session(session_id, user_id)
            
            conversation = await _state_manager.get_conversation(conversation_id)
            if not conversation:
                await _state_manager.create_conversation(conversation_id, session_id, user_id)
            
            await _state_manager.add_message(conversation_id, "user", user_input)
            
            conversation = await _state_manager.get_conversation(conversation_id)
            if conversation:
                state["chat_history"] = [
                    {"role": msg["role"], "content": msg["content"]}
                    for msg in conversation.get_recent_messages(10)[:-1]
                ]
        
        emotion_result = None
        if _skill_executor:
            try:
                emotion_result = await _skill_executor.execute(
                    skill_name="emotion",
                    operation="analyze",
                    input_data={
                        "text": user_input,
                        "user_id": user_id,
                        "session_id": session_id,
                        "context_history": state.get("chat_history", [])
                    },
                    context={"user_id": user_id, "session_id": session_id}
                )
            except Exception as e:
                logger.warning("emotion_analysis_in_router_failed", error=str(e))

        route = "context_aware"

        if emotion_result and emotion_result.success and emotion_result.data:
            emotion_data = emotion_result.data
            emotion_scores = emotion_data.get("scores") or emotion_data.get("emotion_scores") or {}
            ekman_scores = emotion_data.get("ekman_scores") or {}
            scores_for_route = ekman_scores or emotion_scores
            top_emotion = max(scores_for_route.items(), key=lambda x: x[1])[0] if scores_for_route else "neutral"

            if top_emotion in ["anger", "fear", "sadness"]:
                route = "context_aware"

            if _state_manager:
                await _state_manager.set_state(
                    StateType.CONVERSATION,
                    conversation_id,
                    "last_emotion",
                    top_emotion
                )
        
        message_length = len(user_input)
        has_question = any(q in user_input for q in ["?", "？", "什么", "如何", "怎么", "为什么"])
        
        if message_length < 50 and not has_question:
            lower_input = user_input.lower().strip()
            if lower_input in ["hi", "hello", "ok", "yes", "no"]:
                route = "quick"
        
        tool_keywords = ["搜索", "查询", "计算", "翻译", "天气", "时间", "日期", "记住", "保存"]
        if route != "quick" and any(keyword in user_input for keyword in tool_keywords):
            route = "tool_required"
        
        # 将 emotion 结果存入 state，避免 generation 中重复分析
        if emotion_result and emotion_result.success and emotion_result.data:
            state["emotion_data"] = emotion_result.data
        else:
            state["emotion_data"] = None

        state["route"] = route
        state["next_step"] = "generate"
        state["session_id"] = session_id
        state["conversation_id"] = conversation_id
        
        return state
        
    except Exception as e:
        logger.error("router_node_error", error=str(e))
        state["route"] = "standard"
        state["next_step"] = "generate"
        return state


def route_decision(state: AgentState) -> str:
    return state.get("route", "standard")


async def generate_node(state: AgentState) -> AgentState:
    try:
        await initialize_runtime()
        
        route = state.get("route", "standard")
        conversation_id = state.get("conversation_id")
        
        if route == "quick":
            result = await quick_generate(
                state,
                skill_executor=_skill_executor,
                flow_orchestrator=_flow_orchestrator,
                state_manager=_state_manager
            )
        elif route == "context_aware":
            result = await context_aware_generate(
                state,
                skill_executor=_skill_executor,
                flow_orchestrator=_flow_orchestrator,
                state_manager=_state_manager
            )
        elif route == "tool_required":
            result = await tool_required_generate(
                state,
                skill_executor=_skill_executor,
                flow_orchestrator=_flow_orchestrator,
                state_manager=_state_manager
            )
        else:
            result = await standard_generate(
                state,
                skill_executor=_skill_executor,
                flow_orchestrator=_flow_orchestrator,
                state_manager=_state_manager
            )
        
        response = result.get("response", "")
        state["response"] = response
        state["next_step"] = ""
        
        if _state_manager and conversation_id:
            await _state_manager.add_message(conversation_id, "assistant", response)
        
        return state
        
    except Exception as e:
        logger.error("generate_node_error", error=str(e))
        state["response"] = "I'm sorry, I encountered an error generating a response."
        state["next_step"] = ""
        return state
