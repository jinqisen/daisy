import asyncio
import json
import uuid
from typing import Optional, Dict, Any

import structlog

from app.core.database import SessionLocal
from app.core.redis import redis_client
from app.core.time_utils import utc_now_naive
from app.models import ChatHistoryDB

logger = structlog.get_logger()

class SessionService:
    """
    业务会话管理服务 (Session Management V2)
    负责管理 Conversation Session 的生命周期。
    """
    
    # 业务会话 TTL (默认 4 小时)
    SESSION_TTL = 14400 
    
    # Redis Key 前缀
    KEY_PREFIX_ACTIVE = "session:active_conversation"
    KEY_PREFIX_META = "session:conversation_meta"

    def _active_key(self, user_id: str) -> str:
        return f"{self.KEY_PREFIX_ACTIVE}:{user_id}"

    def _meta_key(self, conversation_id: str) -> str:
        return f"{self.KEY_PREFIX_META}:{conversation_id}"

    async def _load_meta(self, conversation_id: str) -> Dict[str, Any]:
        raw = await redis_client.get(self._meta_key(conversation_id))
        if not raw:
            return {}

        if isinstance(raw, dict):
            return raw

        if isinstance(raw, str):
            try:
                payload = json.loads(raw)
                return payload if isinstance(payload, dict) else {}
            except json.JSONDecodeError:
                logger.warning(
                    "SessionService: failed to decode conversation meta",
                    conversation_id=conversation_id,
                    raw=raw,
                )
        return {}

    async def get_conversation_meta(self, conversation_id: str) -> Dict[str, Any]:
        return await self._load_meta(conversation_id)

    async def peek_active_conversation(self, user_id: str) -> Optional[str]:
        """
        读取当前活跃会话，但不自动创建新会话。
        """
        active_key = self._active_key(user_id)
        conversation_id = await redis_client.get(active_key)

        if conversation_id:
            return conversation_id

        try:
            last_session_id, last_time = await self._get_last_session_from_db(user_id)
            if last_session_id and last_time:
                time_diff = utc_now_naive() - last_time
                if time_diff.total_seconds() < self.SESSION_TTL:
                    logger.info(
                        "SessionService: recovered active session from DB",
                        user_id=user_id,
                        conversation_id=last_session_id,
                        idle_seconds=round(time_diff.total_seconds(), 1),
                    )
                    await self._activate_session(user_id, last_session_id, is_new=False)
                    return last_session_id
        except Exception as e:
            logger.error(f"SessionService: DB check failed: {e}")

        return None

    async def get_active_conversation(self, user_id: str) -> str:
        """
        获取当前用户的活跃业务会话 ID。
        如果 Redis 中不存在，则检查 DB 中最近一条消息的时间。
        如果都过期，则生成新 ID。
        """
        conversation_id = await self.peek_active_conversation(user_id)
        if conversation_id:
            await self.touch_conversation(user_id, conversation_id)
            return conversation_id

        new_id = str(uuid.uuid4())
        logger.info(f"SessionService: Starting NEW session: {new_id}")
        await self._activate_session(user_id, new_id, is_new=True)
        return new_id

    async def start_new_conversation(self, user_id: str, end_current: bool = True) -> Dict[str, Optional[str]]:
        """
        显式开启一个新的业务会话，用于前端“新对话/会话边界”操作。
        """
        previous_session_id = await self.peek_active_conversation(user_id)
        if previous_session_id and end_current:
            await self.end_conversation(user_id, previous_session_id, reason="manual_boundary")

        new_session_id = str(uuid.uuid4())
        await self._activate_session(user_id, new_session_id, is_new=True)
        logger.info(
            "SessionService: started new conversation",
            user_id=user_id,
            previous_session_id=previous_session_id,
            new_session_id=new_session_id,
        )
        return {
            "previous_session_id": previous_session_id,
            "session_id": new_session_id,
        }

    async def touch_conversation(self, user_id: str, conversation_id: str):
        """
        续期会话心跳
        """
        await self._activate_session(user_id, conversation_id, is_new=False)

    async def end_conversation(self, user_id: str, conversation_id: str, reason: str = "manual_end"):
        """
        显式结束会话
        """
        active_key = self._active_key(user_id)
        meta_key = self._meta_key(conversation_id)

        current_active = await redis_client.get(active_key)
        if current_active == conversation_id:
            await redis_client.delete(active_key)

        now_str = utc_now_naive().isoformat()
        meta = await self._load_meta(conversation_id)
        meta.update(
            {
                "user_id": user_id,
                "status": "archived",
                "end_time": now_str,
                "last_interaction": now_str,
                "ended_reason": reason,
            }
        )
        if "start_time" not in meta:
            meta["start_time"] = now_str

        await redis_client.set(meta_key, json.dumps(meta, ensure_ascii=False), ttl=86400)
        logger.info(f"SessionService: Ended session {conversation_id} for user {user_id}")

        # TODO: 触发归档任务 (Archive & Summarize)

    async def _activate_session(self, user_id: str, conversation_id: str, is_new: bool = False):
        """
        激活会话 (写入 Redis)
        """
        active_key = self._active_key(user_id)
        meta_key = self._meta_key(conversation_id)
        await redis_client.set(active_key, conversation_id, ttl=self.SESSION_TTL)

        now_str = utc_now_naive().isoformat()
        meta = await self._load_meta(conversation_id)
        if is_new:
            meta = {
                "start_time": now_str,
                "status": "active",
                "user_id": user_id,
            }

        meta.update(
            {
                "user_id": user_id,
                "status": "active",
                "last_interaction": now_str,
            }
        )

        if "start_time" not in meta:
            meta["start_time"] = now_str

        await redis_client.set(meta_key, json.dumps(meta, ensure_ascii=False), ttl=86400)

    async def _get_last_session_from_db(self, user_id: str):
        """
        Helper: 从 DB 获取最后一条消息的 Session ID 和 时间
        需要运行在 Executor 中因为是同步 DB 操作
        """
        def _sync_query():
            with SessionLocal() as db:
                last_msg = db.query(ChatHistoryDB).filter(
                    ChatHistoryDB.user_id == user_id
                ).order_by(ChatHistoryDB.timestamp.desc()).first()
                
                if last_msg:
                    return last_msg.session_id, last_msg.timestamp
                return None, None

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sync_query)

# 全局实例
session_service = SessionService()
