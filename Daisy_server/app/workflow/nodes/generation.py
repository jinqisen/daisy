"""
汇聚生成节点(§6.2:全图最强控制点)。

职责(重构后收敛为四段):
1. 汇聚检查   —— 校验并行分支产物齐备,否则跳过生成
2. 上下文装配 —— 调 context_assembly 格式化任务产物、构建 CO-STAR;注入 Reflexion
                patches / exemplars / 工具结果
3. 最终生成   —— 带路由级超时的 LLM 调用
4. 后处理     —— 内心独白解析、线下见面违规校正、分段、trace、异步 Reflexion 投递

并行子节点(summarize_topic 等)在 context_tasks.py;纯装配函数在 context_assembly.py。
本模块 re-export 拆出的符号以保持向后兼容。
"""

import asyncio
import re
import structlog

from ..capability import essential, enhancement
from .state import AgentState
from .tools import add_trace, get_common_settings_async, monitor_execution_time
from ...core.exceptions import NodeError
from ...core.cache import redis_client
from ...services.learning.reflexion_system import reflexion_system
from ...core.utils import is_offline_meetup_intent, is_offline_meetup_violation, split_response_into_parts
from ...prompts import get_core_system_instructions
from ...services.persona.character_card import get_character_card, build_channel_prompt_addendum, infer_relationship_stage
from ...core.llm import get_llm_service
from ...services.learning.reflexion import reflexion_patcher
from ...services.learning.reflexion.storage import reflexion_storage

from .context_assembly import _format_task_outputs, _generate_costar_instruction
# 向后兼容 re-export:历史上这些符号定义在本模块
from .context_tasks import (  # noqa: F401
    summarize_topic,
    ensure_portrait,
    analyze_style,
    _get_active_profiles_sync,
    _calculate_active_personas,
)

logger = structlog.get_logger()


async def _generate_final_llm_response(common, state: AgentState, system_instructions: str, full_context: str) -> str:
    """Generate final response using the assembled context"""
    from ...core.config import settings
    llm = get_llm_service()
    metadata = {
        "trigger_message": state["user_input"],
        "agent_name": "FinalResponseAgent",
        "user_id": state["user_id"],
        "trigger_message_id": state.get("user_message_id"),
        "route": state.get("route"),
        "execution_id": state.get("execution_id")
    }

    if hasattr(llm, "generate_response_async"):
        if state.get("route") == "DEEP":
            return await asyncio.wait_for(
                llm.generate_response_async(
                    system_instructions,
                    "",
                    full_context,
                    user_settings=common,
                    metadata=metadata,
                ),
                timeout=settings.DEEP_FINAL_TIMEOUT_SEC,
            )
        return await llm.generate_response_async(
            system_instructions, "", full_context, user_settings=common, metadata=metadata
        )
    else:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, llm.generate_response, system_instructions, "", full_context, common, metadata)


@essential
@monitor_execution_time
async def generate_response(state: AgentState) -> AgentState:
    """
    节点：生成回复
    整合所有分析结果，使用 CO-STAR 框架生成最终回复
    """
    try:
        # --- 并行汇聚检查 (Sync Point) ---
        # 依赖：style_analysis
        missing = [k for k in ["topic_summary", "retrieved_memories", "portrait", "style_analysis"] if k not in state]
        if missing:
            logger.info(f"Generate Node: Waiting for dependencies {missing}. Skipping generation.")
            return {"_skip_generation": True}

        state["_skip_generation"] = False

        # 1. 获取所有必要数据
        history_analysis_result = state["topic_summary"]
        portrait_from_state = state["portrait"]
        style_analysis = state["style_analysis"]
        retrieved_memories = state.get("retrieved_memories", [])
        tool_results = state.get("tool_results", {})

        # 1.1 当前情感状态 —— 取自本轮 analyze 节点的真实分析结果
        #
        # 原实现读 Redis 的 `user:{uid}:emotional_state`,而**全库没有任何地方写过这个键**
        # (set_emotional_state 只在 get 内部的衰减回写里被调用,那要求键已存在)。
        # 于是 get 永远返回默认对象 EmotionalState(),而 pydantic 模型**恒为真**,
        # `if emotional_obj:` 拦不住 —— 结果每一次生成都往提示词里注入
        #     当前情感状态 (Redis): Neutral (强度: 0)
        # 哪怕用户刚说完宠物去世。对一个以情绪陪伴为核心的产品,这不是"少了个功能",
        # 而是**持续给模型一个与事实相反的信号**,且完全静默、日志正常。
        #
        # 真实情绪本来就在图状态里(analyze 节点用 GoEmotions 算出 top_emotions),
        # 直接用它,不必绕一趟从来没被写入过的缓存。
        user_id = state["user_id"]
        emotional_state_data = None
        try:
            top = state.get("top_emotions") or []
            if top:
                label, score = top[0][0], float(top[0][1])
                emotional_state_data = {
                    "current_mood": label,
                    "intensity": int(max(0.0, min(1.0, score)) * 100),
                }
                logger.info("当前情感状态", mood=label,
                            intensity=emotional_state_data["intensity"])
        except Exception as e:
            logger.warning(f"读取情感状态失败: {e}")

        # 2. 获取 Common Settings
        # 优化：从 State 获取 Common Settings
        common = state.get("common_settings")
        if common:
            logger.info(f"Generate: Using cached common_settings from state (Type: {type(common)})")
        if not common:
            logger.warning("Generate: Common settings not in state, fetching from DB")
            common = await get_common_settings_async(state["user_id"])
            if common: state["common_settings"] = common

        if not common:
            raise ValueError(f"Failed to load common settings for user {state['user_id']}")

        # Get weights for OS formatting
        weights = {}
        if "love_style_weights" in state and "weights" in state["love_style_weights"]:
            weights = state["love_style_weights"]["weights"]

        # 3. 格式化输出 (Tasks 1-4)
        portrait_text, style_text, os_text, history_text = _format_task_outputs(portrait_from_state, style_analysis, history_analysis_result, retrieved_memories, weights)

        # 4. 生成 CO-STAR Prompt (Task 5)
        # 优化：直接使用 Python 代码构建 CO-STAR 指令，避免额外的 LLM 调用
        costar_text = await _generate_costar_instruction(
            common, state,
            portrait_text=portrait_text,
            style_text=style_text,
            history_text=history_text,
            emotional_state=emotional_state_data
        )

        # --- 记录任务详情供调试/前端展示 ---
        logger.info("Prompt 生成任务完成",
                    task1_portrait=portrait_text,
                    task2_style=style_text,
                    task3_os=os_text,
                    task4_history=history_text,
                    task5_costar=costar_text)

        # 5. 最终上下文组装
        # Append Tool Results if any
        tool_context = ""
        if tool_results:
            tool_context = "\n# TOOL RESULTS\n"
            for tool_name, result in tool_results.items():
                tool_context += f"- {tool_name}: {result}\n"

        # Reflexion: Active Patches Injection
        active_patches = await reflexion_patcher.get_active_patches(state["user_id"])
        patches_text = ""

        global_patches = active_patches.get("global", [])
        personal_patches = active_patches.get("personal", [])

        if global_patches or personal_patches:
            patches_text = "\n# REFLEXION INTELLIGENCE (Dynamic Rules)\n"

            if global_patches:
                patches_text += "### 🛡️ Global Protocols (Universal Rules)\n"
                patches_text += "\n".join([f"- {p}" for p in global_patches]) + "\n"

            if personal_patches:
                patches_text += f"\n### 👤 Personal Adaptations (User {state['user_id']})\n"
                patches_text += "\n".join([f"- {p}" for p in personal_patches]) + "\n"

        # Reflexion: Retrieve Exemplars (RAG)
        rag_context = ""
        try:
            # Use user input for retrieval
            exemplars = await reflexion_storage.retrieve_exemplars(state["user_input"], limit=2)

            if exemplars:
                rag_context = "\n# REFLEXION MEMORY (Successful Past Interactions)\n"
                for i, ex in enumerate(exemplars, 1):
                    payload = ex.payload
                    rag_context += f"Example {i}:\nUser: {payload.get('user_input', '')}\nAI: {payload.get('agent_response', '')}\n"
        except Exception as e:
            logger.warning(f"Reflexion RAG failed: {e}")

        full_context = f"""
        # FINAL GENERATION INSTRUCTION
        {costar_text}

        {rag_context}
        {patches_text}
        {tool_context}

        # CONTEXT DATA (For Reference)
        {history_text}
        """
        if is_offline_meetup_intent(state.get("user_input", "")):
            full_context = f"""{full_context}

    [CRITICAL CONSTRAINT]
    你们是绝对异地关系，不能答应任何线下见面或提出线下邀约，也不能编造具体时间地点。"""

        route = state.get("route", "STANDARD")
        system_instructions = state.get("system_prompt_override") or get_core_system_instructions(common)

        # Phase 2: Unified Character Card Loading (Ensure character_card is available if needed)
        try:
            character_card = get_character_card(state["user_id"])
        except Exception:
            character_card = None

        if route == "DEEP":
            # Unified Loading
            if character_card:
                stage = infer_relationship_stage(getattr(common, "relationship", None) if common else None)
                addendum = build_channel_prompt_addendum(character_card, "DEEP", state.get("user_input", ""), stage)
                if addendum:
                    system_instructions = f"{system_instructions}\n\n{addendum}".strip()

        logger.debug("System Instructions", instructions=system_instructions)

        logger.info("Daisy_server Generation Prompt",
                    system_instructions=system_instructions,
                    full_context=full_context,
                    route=route,
                    user_input=state["user_input"])

        # Debug Context
        logger.info("Context Debug", history_len=len(history_text), summary_preview=history_analysis_result[:200] if history_analysis_result else "None")

        # 8. 生成最终回复
        logger.info(f"Generate Final Response (Route: {route})")

        raw_response = await _generate_final_llm_response(common, state, system_instructions, full_context)

        # Parse out Final Inner Thought (New Logic for Merge OS)
        final_thought = ""
        actual_response = raw_response

        # Strategy 1: Explicit Tags (Robust)
        tag_match = re.search(r"\[Final Inner Thought\]:\s*(.+?)\s*\[/Final Inner Thought\]", raw_response, re.DOTALL)
        if tag_match:
            final_thought = tag_match.group(1).strip()
            actual_response = raw_response.replace(tag_match.group(0), "").strip()
        else:
            # Strategy 2: Fallback to Double Newline (Legacy)
            # Match [Final Inner Thought]: ... until double newline or end
            thought_match = re.search(r"\[Final Inner Thought\]:\s*(.+?)(?:\n\s*\n|$)", raw_response, re.DOTALL)
            if thought_match:
                final_thought = thought_match.group(1).strip()
                # Safety check: if thought takes up > 90% of response and no double newline found,
                # it might be a parsing error where response is swallowed.
                # But hard to distinguish from just a long thought.
                # We rely on the new explicit tags for future stability.
                actual_response = raw_response.replace(thought_match.group(0), "").strip()

        if final_thought:
            logger.info("Final Inner Thought Synthesized", thought=final_thought)

        if is_offline_meetup_intent(state.get("user_input", "")) and is_offline_meetup_violation(actual_response):
            actual_response = "别闹，我们是异地，见不了的。你想我可以直说，但时间地点别提。"

        # 9. 后处理：分割回复
        final_parts = split_response_into_parts(actual_response)
        if not final_parts:
             final_parts = [actual_response if actual_response else "..."]

        logger.info("最终回复生成",
            response_parts_count=len(final_parts),
            parts_preview=final_parts
        )

        # 10. Trace 记录
        trace = await add_trace(state, "generate",
            input_data={
                "system_instructions": system_instructions,
                "full_context": full_context
            },
            output_data={
                "final_response": actual_response,
                "final_inner_thought": final_thought,
                "response_parts": final_parts,
                "internal_tasks": {
                    "task1_portrait": portrait_text,
                    "task2_style": style_text,
                    "task3_os": os_text,
                    "task4_history": history_text,
                    "task5_costar": costar_text
                }
            }
        )

        # 11. Async Reflexion Trigger
        # Fire and forget: enqueue event for background analysis
        try:
            # Construct agent emotion vector from Redis state (if available)
            agent_emotion_vector = {}
            if emotional_state_data:
                # Simple mapping: mood -> 1.0, others -> 0.0 (intensity as weight)
                mood = emotional_state_data.get("current_mood", "neutral").lower()
                intensity = emotional_state_data.get("intensity", 50) / 100.0
                agent_emotion_vector = {mood: intensity}

            await reflexion_system.enqueue_event({
                "user_id": state["user_id"],
                "session_id": state["session_id"],
                "user_input": state["user_input"],
                "agent_response": actual_response,
                "agent_emotion": agent_emotion_vector,
                "user_emotion": state.get("ekman_scores", {}), # Pass user emotion for Reflexion
                "target_emotion": state.get("target_emotion"), # Retrieved from Strategy Node
                "history": [] # ReflexionService will fetch if empty
            })
        except Exception as e:
            logger.error(f"Failed to enqueue reflexion event: {e}")

        return {
            "response": actual_response,
            "response_parts": final_parts,
            "selected_personality": common.name,
            "system_prompt": system_instructions,
            "workflow_trace": trace,
            "final_thought": final_thought,  # 保留用于下一轮上下文连续性
            "_skip_generation": False # 明确重置跳过标志，确保 save 节点执行
        }
    except Exception as e:
        logger.error(f"Error in generate_response: {e}")
        raise NodeError("Generation", e)
