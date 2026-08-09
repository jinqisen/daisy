import json
import structlog
from typing import Tuple, List, Optional, Any
import asyncio

from app.core.cache import redis_client
from app.core.config import settings
from app.models import ChatHistoryDB
from app.prompts import get_topic_summary_prompt, get_incremental_topic_summary_prompt, CommonSettings
from app.core.llm import get_llm_service
from app.services.memory.chat_history import history_service

logger = structlog.get_logger()

class TopicAnalysisAgent:
    """
    Topic Analysis Agent
    
    职责:
    1. 检索和管理短期对话历史 (Short-term Context).
    2. 分析对话流，生成话题总结 (Topic Summary).
    3. 构建包含话题和最近对话的上下文提示词 (Context Prompt).
    
    这是一个工具型 Agent，通常被上层工作流调用以准备上下文。
    """
    
    def __init__(self):
        self.llm_service = get_llm_service()

    @staticmethod
    def _summary_cache_key(session_id: str) -> str:
        return f"topic:summary:session:{session_id}"

    @staticmethod
    def _decode_summary_cache(cache_value: Any) -> tuple[Optional[str], Optional[int]]:
        """兼容旧 string 缓存与新 JSON payload。"""
        if cache_value is None:
            return None, None

        if isinstance(cache_value, dict):
            summary = cache_value.get("summary")
            last_msg_id = cache_value.get("last_msg_id")
            return summary, int(last_msg_id) if last_msg_id is not None else None

        if isinstance(cache_value, str):
            try:
                payload = json.loads(cache_value)
            except json.JSONDecodeError:
                return cache_value, None

            if isinstance(payload, dict):
                summary = payload.get("summary")
                last_msg_id = payload.get("last_msg_id")
                return summary, int(last_msg_id) if last_msg_id is not None else None

            if isinstance(payload, str):
                return payload, None

        return str(cache_value), None

    @staticmethod
    def _encode_summary_cache(summary: str, last_msg_id: Optional[int]) -> str:
        return json.dumps(
            {
                "summary": summary,
                "last_msg_id": last_msg_id,
            },
            ensure_ascii=False,
        )

    async def get_cached_session_summary(self, session_id: Optional[str]) -> tuple[Optional[str], Optional[int]]:
        if not session_id:
            return None, None

        cached_summary_raw = await redis_client.get(self._summary_cache_key(session_id))
        return self._decode_summary_cache(cached_summary_raw)

    def _generate_summary_llm(self, history_msgs: List[ChatHistoryDB], current_input: str, user_id: str, common: CommonSettings, trigger_message_id: int = None, execution_id: str = None) -> str:
        """调用 LLM 生成话题总结"""
        if not history_msgs:
            return "(No history)"
            
        msgs_text = ""
        for msg in history_msgs:
            role_display = "User" if msg.role == "user" else common.name
            msgs_text += f"{role_display}: {msg.content}\n"
        
        summary_prompt = get_topic_summary_prompt(msgs_text, current_input)
        
        try:
            summary = self.llm_service.generate_response(
                system_prompt="你是一位对话分析专家。",
                user_input=summary_prompt,
                context="",
                user_settings=common,
                metadata={
                    "trigger_message": current_input, 
                    "agent_name": "TopicAgent", "execution_id": execution_id, 
                    "user_id": user_id,
                    "trigger_message_id": trigger_message_id
                }
            )
            return summary
        except Exception as e:
            # 之前修改为直接抛出异常
            raise Exception(f"LLM Topic Analysis failed: {str(e)}")

    async def _generate_summary_llm_async(self, history_msgs: List[ChatHistoryDB], current_input: str, user_id: str, common: CommonSettings, trigger_message_id: int = None, execution_id: str = None) -> str:
        """调用 LLM 生成话题总结 (异步版本)"""
        if not history_msgs:
            return "(No history)"
            
        msgs_text = ""
        for msg in history_msgs:
            role_display = "User" if msg.role == "user" else common.name
            msgs_text += f"{role_display}: {msg.content}\n"
        
        summary_prompt = get_topic_summary_prompt(msgs_text, current_input)
        
        try:
            metadata = {
                "trigger_message": current_input, 
                "agent_name": "TopicAgent", "execution_id": execution_id, 
                "user_id": user_id,
                "trigger_message_id": trigger_message_id
            }
            
            if hasattr(self.llm_service, "generate_response_async"):
                summary = await self.llm_service.generate_response_async(
                    system_prompt="你是一位对话分析专家。",
                    user_input=summary_prompt,
                    context="",
                    user_settings=common,
                    metadata=metadata
                )
            else:
                loop = asyncio.get_running_loop()
                summary = await loop.run_in_executor(
                    None,
                    self.llm_service.generate_response,
                    "你是一位对话分析专家。",
                    summary_prompt,
                    "",
                    common,
                    metadata
                )
            return summary
        except Exception as e:
            logger.error(f"Async LLM Topic Analysis failed: {e}")
            raise Exception(f"Async LLM Topic Analysis failed: {str(e)}")

    def _sync_process(self, user_id: str, common: CommonSettings, current_input: str, cached_summary: Optional[str], trigger_message_id: int = None) -> Tuple[str, str]:
        """同步执行核心逻辑 (数据库 + LLM)"""
        
        # 1. 获取处理后的数据 (已经分组并切片)
        limit = settings.TOPIC_SUMMARY_HISTORY_LIMIT
        # Exclude pending and processing messages to avoid duplication with current_input
        recent_pairs = history_service.get_recent_pairs(
            user_id, 
            limit, 
            exclude_statuses=["pending", "processing", "failed"]
        )
        
        # 展平用于 LLM
        long_history_msgs = [msg for pair in recent_pairs for msg in pair]
        
        # 2. 生成 Summary (如果无缓存)
        summary = None
        if not cached_summary:
            # 优化：如果历史记录较短（<= 10条消息），直接使用原始上下文，跳过昂贵的 LLM 总结
            # limit 是对话轮数 (pairs)，所以 limit=5 意味着 10 条消息
            if len(long_history_msgs) <= 10:
                logger.info(f"Skipping LLM Topic Summary for short history ({len(long_history_msgs)} msgs)")
                summary = "(Short history, raw context provided below)"
            else:
                summary = "(No history)"
                if long_history_msgs:
                    summary = self._generate_summary_llm(long_history_msgs, current_input, user_id, common, trigger_message_id, execution_id=execution_id)
        
        # 3. 构建上下文输出字符串
        final_summary = summary if summary else cached_summary
        
        context_str = f"**最近几轮对话记录 (最新 {limit} 轮)**:\n"
        
        if long_history_msgs:
            for msg in long_history_msgs:
                role_display = "User" if msg.role == "user" else common.name
                context_str += f"{role_display}: {msg.content}\n"
        else:
            context_str += "(No previous conversation history.)\n"
            
        context_str += f"用户最新消息: {current_input}\n\n"
        context_str += f"**Topic & Context Analysis**:\n{final_summary}\n"
        
        return summary, context_str

    async def _generate_incremental_summary(self, old_summary: str, new_msgs: List[ChatHistoryDB], current_input: str, user_id: str, common: CommonSettings, trigger_message_id: int = None, execution_id: str = None) -> str:
        """生成增量总结"""
        
        msgs_text = ""
        if new_msgs:
            for msg in new_msgs:
                role_display = "User" if msg.role == "user" else common.name
                msgs_text += f"{role_display}: {msg.content}\n"
        
        # 将当前用户输入也加入到“新增对话”中，确保 LLM 能看到最新的反馈
        if current_input:
            msgs_text += f"User (Latest): {current_input}\n"
            
        prompt = get_incremental_topic_summary_prompt(old_summary, msgs_text)
        
        try:
            if hasattr(self.llm_service, "generate_response_async"):
                summary = await self.llm_service.generate_response_async(
                    system_prompt="你是一位对话分析专家。",
                    user_input=prompt,
                    context="",
                    user_settings=common,
                    metadata={
                        "trigger_message": "Incremental Summary Update", 
                        "agent_name": "TopicAgent", "execution_id": execution_id, 
                        "user_id": user_id,
                        "trigger_message_id": trigger_message_id
                    }
                )
            else:
                 # Fallback
                loop = asyncio.get_running_loop()
                summary = await loop.run_in_executor(
                    None,
                    self.llm_service.generate_response,
                    "你是一位对话分析专家。",
                    prompt,
                    "",
                    common,
                    {
                        "trigger_message": "Incremental Summary Update", 
                        "agent_name": "TopicAgent", "execution_id": execution_id, 
                        "user_id": user_id,
                        "trigger_message_id": trigger_message_id
                    }
                )
            return summary
        except Exception as e:
            logger.error(f"Incremental summary failed: {e}")
            return old_summary # Fallback to old summary

    async def run(self, user_id: str, common: CommonSettings, current_input: str, trigger_message_id: int = None, execution_id: str = None) -> str:
        """
        执行 Agent 任务 (增量优化版)。
        """
        # 1. 获取当前 Session ID
        session_id = None
        current_msg = None
        
        # 我们需要知道当前消息的 Session ID
        # 假设 trigger_message_id 对应的是 current_input 消息
        if trigger_message_id:
            # 这是一个数据库操作，需要放在 executor 中
            def get_msg_info():
                with history_service._get_db() as db:
                    return db.query(ChatHistoryDB).filter(ChatHistoryDB.id == trigger_message_id).first()
            
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.get_event_loop()
                
            current_msg = await loop.run_in_executor(None, get_msg_info)
            if current_msg:
                session_id = current_msg.session_id
        
        # 如果无法获取 Session ID，回退到基于数量的旧逻辑
        if not session_id:
            logger.warning(f"Could not determine session_id for msg {trigger_message_id}, falling back to count-based summary.")
            return await self._run_legacy(user_id, common, current_input, trigger_message_id)

        # 2. 读取当前 Session 的摘要缓存
        summary_key = self._summary_cache_key(session_id)
        cached_summary, cached_last_msg_id = await self.get_cached_session_summary(session_id)
        
        # 3. 获取当前 Session 的历史消息
        def fetch_session_history():
            return history_service.get_session_history(
                user_id,
                session_id,
                exclude_statuses=["pending", "processing", "failed"],
            )

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
            
        session_msgs = await loop.run_in_executor(None, fetch_session_history)
        
        # 4. 执行 session 内的全量 / 增量逻辑
        final_summary = "(New conversation)"
        should_persist_summary = False
        session_last_msg_id = session_msgs[-1].id if session_msgs else None
        persisted_last_msg_id = session_last_msg_id
        if trigger_message_id is not None:
            persisted_last_msg_id = max(persisted_last_msg_id or 0, trigger_message_id)
        
        if not session_msgs:
            # Session 刚开始，没有历史
            logger.info(f"New session {session_id}, skipping summary.")
            final_summary = "(New conversation started)"
        
        elif not cached_summary:
            # Session 有消息但无缓存 (可能是首次分析，或缓存丢失)
            # 执行全量分析
            logger.info(f"Full summary for session {session_id} ({len(session_msgs)} msgs)")
            if len(session_msgs) > 2: # 至少有几条才分析
                final_summary = await self._generate_summary_llm_async(session_msgs, current_input, user_id, common, trigger_message_id, execution_id=execution_id)
            else:
                 final_summary = "(Short conversation)"
            should_persist_summary = persisted_last_msg_id is not None
        elif cached_last_msg_id is not None and session_last_msg_id is not None and session_last_msg_id <= cached_last_msg_id:
            logger.info(
                "Topic summary cache hit without new completed messages",
                session_id=session_id,
                last_msg_id=session_last_msg_id,
                cached_last_msg_id=cached_last_msg_id,
            )
            final_summary = cached_summary
        else:
            # 增量更新：仅处理上次摘要之后的新消息
            new_msgs = (
                [msg for msg in session_msgs if msg.id > cached_last_msg_id]
                if cached_last_msg_id is not None
                else session_msgs
            )

            if not new_msgs:
                final_summary = cached_summary
            else:
                logger.info(
                    "Incremental summary for session",
                    session_id=session_id,
                    new_message_count=len(new_msgs),
                    cached_last_msg_id=cached_last_msg_id,
                    session_last_msg_id=session_last_msg_id,
                )
                final_summary = await self._generate_incremental_summary(
                    cached_summary,
                    new_msgs,
                    current_input,
                    user_id,
                    common,
                    trigger_message_id,
                    execution_id=execution_id,
                )
                should_persist_summary = persisted_last_msg_id is not None

        # 5. 更新缓存
        if should_persist_summary and final_summary:
            await redis_client.set(
                summary_key,
                self._encode_summary_cache(final_summary, persisted_last_msg_id),
                ttl=4 * 3600,
            )
            
        # 6. 构建输出 (Context + Summary)
        # 上下文只展示最近 N 条，减少 Token 消耗
        display_limit = settings.TOPIC_SUMMARY_HISTORY_LIMIT
        display_msgs = session_msgs[-display_limit:] if session_msgs else []
        
        context_str = f"**Current Session Context (Last {len(display_msgs)} msgs)**:\n"
        for msg in display_msgs:
            role_display = "User" if msg.role == "user" else common.name
            context_str += f"{role_display}: {msg.content}\n"
            
        context_str += f"User Latest: {current_input}\n\n"
        context_str += f"**Session Summary**:\n{final_summary}\n"
        
        return context_str

    async def _run_legacy(self, user_id: str, common: CommonSettings, current_input: str, trigger_message_id: int = None) -> str:
        """旧的基于数量的逻辑 (作为回退)"""
        # ... (保留原有 run 方法的逻辑)
        # 1. 尝试读取缓存
        cache_suffix = f"{user_id}:{trigger_message_id}" if trigger_message_id else f"{user_id}:latest"
        cache_key = f"topic_summary:{cache_suffix}"
        
        cached_summary = await redis_client.get(cache_key)
        # ... (原有代码逻辑复制过来)
        # 为了避免代码重复过长，这里只做结构示意，实际代码中会将原有 run 重命名为 _run_legacy
        
        # 2. 获取历史记录
        limit = settings.TOPIC_SUMMARY_HISTORY_LIMIT
        def fetch_history():
             return history_service.get_recent_pairs(
                user_id, limit, exclude_statuses=["pending", "processing", "failed"]
            )
        
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
            
        recent_pairs = await loop.run_in_executor(None, fetch_history)
        long_history_msgs = [msg for pair in recent_pairs for msg in pair]
        
        # 3. 生成 Summary (异步 LLM)
        summary = None
        new_summary_generated = False
        
        if not cached_summary:
            if len(long_history_msgs) <= 10:
                # logger.info(f"Skipping LLM Topic Summary for short history ({len(long_history_msgs)} msgs)")
                summary = "(Short history, raw context provided below)"
            else:
                summary = "(No history)"
                if long_history_msgs:
                    summary = await self._generate_summary_llm_async(long_history_msgs, current_input, user_id, common, trigger_message_id, execution_id=execution_id)
                    new_summary_generated = True
        else:
            summary = cached_summary

        final_summary = summary
        
        context_str = f"**最近几轮对话记录 (最新 {limit} 轮)**:\n"
        if long_history_msgs:
            for msg in long_history_msgs:
                role_display = "User" if msg.role == "user" else common.name
                context_str += f"{role_display}: {msg.content}\n"
        else:
            context_str += "(No previous conversation history.)\n"
            
        context_str += f"用户最新消息: {current_input}\n\n"
        context_str += f"**Topic & Context Analysis**:\n{final_summary}\n"
        
        if new_summary_generated and final_summary and final_summary != "(No history)":
             await redis_client.set(cache_key, final_summary, ttl=600)
             
        return context_str

# Global instance
topic_agent = TopicAnalysisAgent()
