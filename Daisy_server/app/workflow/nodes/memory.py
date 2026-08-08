from datetime import datetime, timezone
import asyncio
import json
import time
import structlog
from ..capability import essential, enhancement
from ...core.llm import get_llm_service
from ...services.memory.store import get_memory_service
from ...core.constants import MEMORY_SEARCH_MIN_WORDS, MEMORY_SEARCH_MIN_CHARS, RL_STATE_DIM
from ...core.redis import redis_client
from ...core.metrics import bucket_label, E2E_HIST_THRESHOLDS_MS
from ...services.memory.chat_history import history_service
from .state import AgentState
from .tools import add_trace, get_common_settings_async, monitor_execution_time, sanitize_trace_payload
from ...core.exceptions import NodeError

logger = structlog.get_logger()

@enhancement(fallback={"retrieved_memories": []})
@monitor_execution_time
async def retrieve_memory(state: AgentState) -> AgentState:
    """
    节点：记忆检索
    基于用户输入生成语义查询，并检索相关记忆
    """
    try:
        text = state["user_input"]
        user_id = state["user_id"]
        
        # 语义查询生成 (Semantic Query Generation)
        llm = get_llm_service()
        search_query = text
        
        # 优化：如果输入很短且明确，跳过 LLM 生成，直接使用原句
        # 比如 "hello", "who are you", "what time is it"
        should_use_llm = len(text.split()) > MEMORY_SEARCH_MIN_WORDS or len(text) > MEMORY_SEARCH_MIN_CHARS

        if should_use_llm:
            # 获取 Common Settings
            common = await get_common_settings_async(user_id)
            
            # 尝试获取 Topic Summary 以优化查询上下文
            topic_summary = state.get("topic_summary")
            session_id = state.get("session_id")
            if not topic_summary and session_id:
                 # Try fetch from Redis if not in state
                 try:
                     summary_key = f"topic:summary:session:{session_id}"
                     cached_summary = await redis_client.get(summary_key)
                     if cached_summary:
                         try:
                             payload = json.loads(cached_summary)
                             if isinstance(payload, dict):
                                 topic_summary = payload.get("summary")
                             elif isinstance(payload, str):
                                 topic_summary = payload
                         except json.JSONDecodeError:
                             topic_summary = cached_summary
                 except Exception as e:
                     logger.warning(f"Failed to fetch topic summary from Redis: {e}")

            # Check if LLM is available (using user settings or global)
            # Since get_llm does the check, we just proceed.
            
            from ...prompts.templates import get_memory_search_query_prompt, get_memory_search_query_system_prompt
            query_prompt = get_memory_search_query_prompt(text, topic_summary=topic_summary)
            
            try:
                # 使用 generate_response_async
                generated_query = search_query
                if hasattr(llm, "generate_response_async"):
                    generated_query = await llm.generate_response_async(
                        system_prompt=get_memory_search_query_system_prompt(),
                        user_input=query_prompt,
                        context="",
                        user_settings=common, # Pass user settings
                        metadata={
                            "trigger_message": text, 
                            "agent_name": "MemoryAgent", 
                            "user_id": user_id,
                            "execution_id": state.get("execution_id"),
                            "trigger_message_id": state.get("user_message_id")
                        }
                    )
                else:
                    # Fallback
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        loop = asyncio.get_event_loop()
                    generated_query = await loop.run_in_executor(
                        None,
                        llm.generate_response,
                        get_memory_search_query_system_prompt(),
                        query_prompt,
                        "",
                        common,
                        {
                            "trigger_message": text, 
                            "agent_name": "MemoryAgent", 
                            "user_id": user_id,
                            "execution_id": state.get("execution_id"),
                            "trigger_message_id": state.get("user_message_id")
                        }
                    )

                if generated_query and "Error" not in generated_query and "[MOCK LLM]" not in generated_query:
                    search_query = generated_query.strip()
                    logger.info(f"优化后的搜索查询: '{text}' -> '{search_query}'")
            except Exception as e:
                logger.error(f"生成搜索查询失败: {e}")
                raise e
        else:
            logger.info(f"输入较短，跳过 LLM 查询优化，直接使用: '{text}'")

        memory_service = get_memory_service()
        # 异步执行内存检索 (IO bound)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        
        # 这里不需要 try-except 包装，如果 search_memory 失败，run_in_executor 会抛出异常，外层应该捕获或让其崩溃
        memories = await loop.run_in_executor(None, memory_service.search_memory, search_query, user_id)
        
        # 添加日志供前端展示
        logger.info("记忆检索", 
            original_input=text,
            search_query=search_query,
            retrieved_count=len(memories),
            top_results_preview=memories[:3] if memories else []
        )
        
        # 更新 Trace
        trace = await add_trace(state, "retrieve", 
            input_data={
                "original_input": text,
                "generated_search_query": search_query
            }, 
            output_data={
                "retrieved_count": len(memories), 
                "memories": memories
            } 
        )
        
        return {"retrieved_memories": memories, "workflow_trace": trace}
    except Exception as e:
        logger.error(f"Error in retrieve_memory: {e}")
        # Soft fail: return empty memories so chat can continue
        # Don't raise NodeError, just log and proceed
        return {"retrieved_memories": [], "workflow_trace": {}}

@essential
@monitor_execution_time
async def save_memory_and_log(state: AgentState) -> AgentState:
    """
    节点：保存与日志
    将对话记录保存到数据库，更新记忆服务，并处理 RL 反馈
    """
    try:
        # 0. 首先生成 Save 节点的 Trace (以便包含在快照中)
        trace = await add_trace(state, "save", 
            input_data={"response_len": len(state.get("response", ""))}, 
            output_data={"status": "saving", "memory_id": "pending"}
        )
        
        # 从 DB 检索完整 Trace 以供快照 (Wrapper)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()

        def _save_logic():
            full_trace_from_db = {}
            saved_ids = {}
            try:
                full_trace_from_db = history_service.load_workflow_trace_map(state.get("execution_id"))
            except Exception as e:
                logger.error(f"从数据库检索 Trace 失败: {e}")

            if not full_trace_from_db:
                full_trace_from_db = trace

            try:
                if "user_message_id" in state:
                    saved_ids["user_message_id"] = state["user_message_id"]
                else:
                    saved_ids["user_message_id"] = history_service.save_user_message(
                        session_id=state["session_id"],
                        user_id=state["user_id"],
                        content=state["user_input"],
                        timestamp=datetime.now(timezone.utc),
                    )

                snapshot = {
                    "execution_id": state.get("execution_id"),
                    "session_id": state.get("session_id"),
                    "emotions": state.get("top_emotions"),
                    "all_emotions": state.get("ekman_scores"),
                    "personality": state.get("selected_personality"),
                    "weights": state.get("personality_weights"),
                    "engagement_score": state.get("engagement_score"),
                    "workflow_trace": sanitize_trace_payload(full_trace_from_db),
                }

                saved_ids["ai_message_id"] = history_service.save_ai_message(
                    session_id=state["session_id"],
                    user_id=state["user_id"],
                    content=state["response"],
                    state_snapshot=snapshot,
                    timestamp=datetime.now(timezone.utc),
                )
            except Exception as e:
                logger.error(f"保存聊天记录失败: {e}")
                # Save failure is critical for history integrity
                raise e
                
            return saved_ids

        saved_ids = await loop.run_in_executor(None, _save_logic)

        # 将交互保存到记忆服务 (Mem0 - 长期/事实记忆)
        # 优化：使用 Fire-and-forget 模式，避免阻塞 SSE 推送
        personality = state.get("selected_personality", "Default")
        text = f"User: {state['user_input']}\nAI ({personality}): {state['response']}"
        
        def _add_memory_task(mem_text, mem_uid, mem_meta):
            try:
                ms = get_memory_service()
                ms.add_memory(mem_text, mem_uid, None, None, mem_meta)
                logger.info("记忆保存成功")
            except Exception as e:
                error_str = str(e)
                if "403" in error_str and "ModelArts" in error_str:
                    logger.warning(f"保存至记忆服务被拦截 (敏感信息/风控): {error_str}")
                else:
                    logger.error(f"保存至记忆服务失败: {e}")

        try:
            # 不使用 await，让其在后台执行
            loop.run_in_executor(
                None,
                _add_memory_task,
                text, 
                state["user_id"], 
                {"emotion": str(state.get('top_emotions', []))}
            )
            logger.info("已触发后台记忆保存任务")
        except Exception as e:
            logger.error(f"触发记忆保存任务失败: {e}")
        
        # 记录 RL 数据
        state_vector = [0.0] * RL_STATE_DIM # 重构或传递
        
        def _rl_update():
            try:
                # agent = get_rl_agent(user_id=state["user_id"])
                # agent.store_transition(state_vector, state["rl_action_idx"], 0) # 暂时 0 奖励
                pass
            except Exception as e:
                logger.error(f"更新 RL 代理失败: {e}")
                
        await loop.run_in_executor(None, _rl_update)

        start_ts = state.get("request_start_ts")
        if start_ts:
            duration_ms = int((time.time() - start_ts) * 1000)
            route = state.get("route", "UNKNOWN")
            logger.info("SLO_E2E_LATENCY", duration_ms=duration_ms, route=route)
            try:
                if redis_client.enabled and redis_client.redis:
                    await redis_client.redis.incr("metrics:e2e:count")
                    await redis_client.redis.incrby("metrics:e2e:sum_ms", duration_ms)
                    await redis_client.redis.hincrby("metrics:e2e:by_route", route, 1)
                    await redis_client.redis.hincrby("metrics:e2e:hist", bucket_label(duration_ms, E2E_HIST_THRESHOLDS_MS), 1)
            except Exception:
                pass
        
        return {"workflow_trace": trace, **(saved_ids or {})}
    except Exception as e:
        logger.error(f"Error in save_memory_and_log: {e}")
        raise NodeError("MemorySave", e)
