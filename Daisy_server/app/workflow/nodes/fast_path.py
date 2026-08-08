import datetime
import time
import uuid
import asyncio
from ..capability import essential, enhancement
from ...core.llm import LLMService
from ...services.memory.store import get_memory_service
from ...services.memory.chat_history import history_service
from ...services.memory.topic_agent import topic_agent
from .state import AgentState
from .tools import add_trace, monitor_execution_time, get_common_settings_async
from .prompt_base import build_base_system_prompt
from ...core.exceptions import NodeError
import structlog

logger = structlog.get_logger()


def _build_history_text(messages) -> str:
    lines = []
    for message in messages:
        role = "User" if message.role == "user" else "AI"
        lines.append(f"{role}: {message.content}")
    return "\n".join(lines)

@essential
@monitor_execution_time
async def fast_generate(state: AgentState) -> AgentState:
    """
    Fast path generation node.
    Bypasses complex analysis and generates a quick response.
    """
    user_input = state["user_input"]
    logger.info("Entering FAST path generation")

    if "request_start_ts" not in state:
        state["request_start_ts"] = time.time()
    if "execution_id" not in state:
        state["execution_id"] = str(uuid.uuid4())
    trace = state.get("workflow_trace", {})
    if not trace:
        trace = await add_trace(
            state,
            "__start__",
            input_data={
                "session_id": state.get("session_id"),
                "user_id": state.get("user_id"),
                "execution_id": state.get("execution_id"),
                "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
            },
            output_data={"user_input": user_input, "status": "started"},
        )
        state["workflow_trace"] = trace
    
    common = state.get("common_settings")
    if not common:
        try:
            common = await get_common_settings_async(state["user_id"])
            if common:
                state["common_settings"] = common
        except Exception as e:
            logger.warning(f"FAST path failed to load common settings: {e}")

    llm_service = LLMService()
    llm = llm_service.get_lightweight_llm() or llm_service.get_llm()
    if not llm:
        logger.error("LLM not available for fast path")
        return {"response": "System Error: LLM unavailable", "response_parts": ["System Error"], "_skip_generation": False}

    try:
        # 统一装配层(prompt_base.py):core instructions + 模板 + 线下见面检查 + 角色卡
        system_prompt = build_base_system_prompt(common, state.get("user_id"), "FAST", user_input)
        content = await llm_service.generate_response_async(
            system_prompt=system_prompt,
            user_input=user_input,
            context="",
            user_settings=common,
            metadata={
                "trigger_message": user_input,
                "agent_name": "FastPathAgent",
                "user_id": state.get("user_id"),
                "trigger_message_id": state.get("user_message_id"),
                "route": "FAST",
                "execution_id": state.get("execution_id"),
            },
        )
        content = (content or "").strip()
        
        trace = await add_trace(state, "fast_generate", 
            input_data={"user_input": user_input}, 
            output_data={"response": content}
        )
        selected_personality = common.name if common and getattr(common, "name", None) else "Default"

        return {
            "response": content,
            "response_parts": [content],
            "selected_personality": selected_personality,
            "system_prompt": system_prompt,
            "workflow_trace": trace,
            "_skip_generation": False,
            # 就地赋值不进 LangGraph 通道(见 state.py 契约第 4/5 条),必须显式返回,
            # 否则下游 save 节点拿到 execution_id=None → trace 归因断裂、SLO 漏记
            "execution_id": state["execution_id"],
            "request_start_ts": state["request_start_ts"],
            "route": "FAST",
        }

    except Exception as e:
        logger.error(f"Fast generation failed: {e}", exc_info=True)
        raise NodeError("FastGenerate", e)

@essential
@monitor_execution_time
async def standard_generate(state: AgentState) -> AgentState:
    try:
        user_input = state["user_input"]
        logger.info("Entering STANDARD path generation")

        if "request_start_ts" not in state:
            state["request_start_ts"] = time.time()
        if "execution_id" not in state:
            state["execution_id"] = str(uuid.uuid4())
        trace = state.get("workflow_trace", {})
        if not trace:
            trace = await add_trace(
                state,
                "__start__",
                input_data={
                    "session_id": state.get("session_id"),
                    "user_id": state.get("user_id"),
                    "execution_id": state.get("execution_id"),
                    "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
                },
                output_data={"user_input": user_input, "status": "started"},
            )
            state["workflow_trace"] = trace

        common = state.get("common_settings")
        if not common:
            common = await get_common_settings_async(state["user_id"])
            if common:
                state["common_settings"] = common

        # 统一装配层(prompt_base.py):core instructions + 模板 + 线下见面检查 + 角色卡
        # 注:角色卡加载失败现与 FAST 一致降级为无 addendum,不再让 STANDARD 整体失败
        system_prompt = build_base_system_prompt(common, state.get("user_id"), "STANDARD", user_input)

        session_id = state.get("session_id")
        session_history = []
        history_text = ""
        try:
            if session_id:
                session_history = history_service.get_recent_history_limit(
                    user_id=state["user_id"],
                    limit=8,
                    session_id=session_id,
                    exclude_statuses=["pending", "processing", "failed"],
                )
                history_text = _build_history_text(session_history)
            else:
                logger.warning("STANDARD path missing session_id; session-scoped context unavailable")
        except Exception as e:
            logger.warning(f"STANDARD path failed to load history: {e}")

        memories = []
        try:
            memory_service = get_memory_service()
            loop = asyncio.get_running_loop()
            memories = await loop.run_in_executor(None, memory_service.search_memory, user_input, state["user_id"])
            memories = memories[:3] if memories else []
        except Exception as e:
            logger.warning(f"STANDARD path failed to load memory: {e}")

        topic_summary = ""
        topic_summary_source = "none"
        try:
            topic_summary, _ = await topic_agent.get_cached_session_summary(session_id)
            if topic_summary:
                topic_summary_source = "session_summary_cache"
            else:
                recent_user_lines = [
                    msg.content.strip()
                    for msg in session_history
                    if msg.role == "user" and msg.content
                ]
                combined = " / ".join([text for text in recent_user_lines[-3:] if text])
                topic_summary = combined[:120] if combined else ""
                topic_summary_source = "session_history_fallback" if topic_summary else "none"
        except Exception:
            topic_summary = ""
            topic_summary_source = "error"

        llm_service = LLMService()
        llm = llm_service.get_standard_llm()
        if not llm:
            return {"response": "System Error: LLM unavailable", "response_parts": ["System Error"], "_skip_generation": False}

        memory_block = ""
        if memories:
            memory_lines = []
            for i, m in enumerate(memories, 1):
                memory_lines.append(f"{i}. {m}")
            memory_block = "\n".join(memory_lines)

        context = f"""# STANDARD CONTEXT
Topic Summary: {topic_summary if topic_summary else "(none)"}

# SESSION CHAT
{history_text if history_text else "(none)"}

# RELEVANT MEMORY
{memory_block if memory_block else "(none)"}
"""
        content = await llm_service.generate_response_async(
            system_prompt=system_prompt,
            user_input=user_input,
            context=context,
            user_settings=common,
            metadata={
                "trigger_message": user_input,
                "agent_name": "StandardPathAgent",
                "user_id": state.get("user_id"),
                "trigger_message_id": state.get("user_message_id"),
                "route": "STANDARD",
                "execution_id": state.get("execution_id"),
            },
        )
        content = (content or "").strip()

        trace = await add_trace(
            state,
            "standard_generate",
            input_data={
                "user_input": user_input,
                "session_id": session_id,
                "session_history_count": len(session_history),
                "history_len": len(history_text),
                "memory_count": len(memories),
                "topic_summary": topic_summary,
                "topic_summary_source": topic_summary_source,
            },
            output_data={"response": content},
        )

        selected_personality = common.name if common and getattr(common, "name", None) else "Default"
        return {
            "response": content,
            "response_parts": [content],
            "selected_personality": selected_personality,
            "system_prompt": system_prompt,
            "workflow_trace": trace,
            "_skip_generation": False,
            # 同 fast_generate:就地赋值不进通道,必须显式返回给下游 save
            "execution_id": state["execution_id"],
            "request_start_ts": state["request_start_ts"],
            "route": "STANDARD",
        }
    except Exception as e:
        logger.error(f"Standard generation failed: {e}")
        raise NodeError("StandardGenerate", e)
