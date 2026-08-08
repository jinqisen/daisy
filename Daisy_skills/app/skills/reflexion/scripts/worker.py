from __future__ import annotations

import asyncio
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from .service import reflexion_service
from ....shared.redis import redis_client, async_redis_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AsyncReflexionWorker:
    def __init__(
        self,
        queue_key: str = "reflexion:queue",
        poll_interval: float = 1.0,
        max_retries: int = 3
    ):
        self.queue_key = queue_key
        self.poll_interval = poll_interval
        self.max_retries = max_retries
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self):
        if self._running:
            logger.warning("ReflexionWorker is already running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info("ReflexionWorker started")
    
    async def stop(self):
        if not self._running:
            return
        
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("ReflexionWorker stopped")
    
    async def _process_loop(self):
        while self._running:
            try:
                await self._process_next_event()
            except Exception as e:
                logger.error(f"Error in process loop: {e}")
                await asyncio.sleep(self.poll_interval)
    
    async def _process_next_event(self):
        raw_event = await async_redis_client.lpop(self.queue_key)
        
        if not raw_event:
            await asyncio.sleep(self.poll_interval)
            return
        
        try:
            event = json.loads(raw_event)
            await self._process_event(event)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode event: {e}")
        except Exception as e:
            logger.error(f"Failed to process event: {e}")
    
    async def _process_event(self, event: Dict[str, Any]):
        user_id = event.get("user_id")
        session_id = event.get("session_id")
        user_input = event.get("user_input", "")
        agent_response = event.get("agent_response", "")
        agent_emotion = event.get("agent_emotion", {})
        target_emotion = event.get("target_emotion", {})
        user_emotion = event.get("user_emotion", {})
        history = event.get("history", [])
        response_time_sec = event.get("response_time_sec")
        user_feedback = event.get("user_feedback")
        
        if not user_id or not session_id:
            logger.warning(f"Invalid event: missing user_id or session_id")
            return
        
        result = await reflexion_service.process_turn(
            user_id=user_id,
            session_id=session_id,
            user_input=user_input,
            agent_response=agent_response,
            agent_emotion=agent_emotion,
            target_emotion=target_emotion,
            user_emotion=user_emotion,
            history=history,
            response_time_sec=response_time_sec,
            user_feedback=user_feedback
        )
        
        if result.get("success"):
            metrics = result.get("metrics", {})
            s_total = metrics.get("S_total", 0.0)
            logger.info(
                f"Processed event for user {user_id}, session {session_id}: "
                f"S_total={s_total:.2f}"
            )
        else:
            logger.error(
                f"Failed to process event for user {user_id}, session {session_id}: "
                f"{result.get('message')}"
            )
    
    async def get_queue_size(self) -> int:
        return await async_redis_client.llen(self.queue_key)
    
    async def get_stats(self) -> Dict[str, Any]:
        queue_size = await self.get_queue_size()
        
        return {
            "running": self._running,
            "queue_size": queue_size,
            "poll_interval": self.poll_interval,
            "max_retries": self.max_retries
        }


_reflexion_worker: Optional[AsyncReflexionWorker] = None


def get_reflexion_worker() -> AsyncReflexionWorker:
    global _reflexion_worker
    
    if _reflexion_worker is None:
        _reflexion_worker = AsyncReflexionWorker()
    
    return _reflexion_worker


async def start_reflexion_worker():
    worker = get_reflexion_worker()
    await worker.start()


async def stop_reflexion_worker():
    worker = get_reflexion_worker()
    await worker.stop()
