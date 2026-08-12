import asyncio
import random
import structlog
from typing import Dict, Any, List
from app.services.learning.reflexion.service import ReflexionService
from app.services.memory.chat_history import history_service
from app.core.database import SessionLocal
from app.models import UserDB

logger = structlog.get_logger()

class AsyncReflexionSystem:
    """
    Asynchronous Reflexion System (v3.2).
    Analyzes conversation logs in the background to learn and improve.
    Uses ReflexionService for Q_I calculation and pending turn management.
    """
    def __init__(self):
        self.queue = None  # 延迟到 start() 中创建,确保绑定到正确的 event loop
        self._running = False
        self.service = ReflexionService()
        
    async def start(self):
        if self._running:
            return
        self._running = True
        # 在 start() 中创建 Queue,确保绑定到当前运行的 event loop
        if self.queue is None:
            self.queue = asyncio.Queue()
        logger.info("Starting AsyncReflexionSystem worker...")
        asyncio.create_task(self._worker())

    async def enqueue_event(self, event: Dict[str, Any]):
        """
        Put a conversation event into the queue.
        Event structure:
        {
            "user_id": int/str,
            "session_id": str,
            "user_input": str,
            "agent_response": str,
            "agent_emotion": dict (optional),
            "target_emotion": dict (optional),
            "history": list (optional)
        }
        """
        if self.queue is None:
            logger.warning("Reflexion queue not initialized, dropping event")
            return
        qsize = self.queue.qsize()
        await self.queue.put(event)
        logger.info(f"Reflexion event enqueued for user {event.get('user_id')}", 
                    session_id=event.get("session_id"),
                    queue_size=qsize + 1)

    async def _worker(self):
        while self._running:
            try:
                event = await self.queue.get()
                logger.info("Reflexion worker picked up event", 
                            user_id=event.get("user_id"), 
                            queue_size=self.queue.qsize())
                
                start_time = asyncio.get_running_loop().time()
                await self._process_event(event)
                duration = asyncio.get_running_loop().time() - start_time
                
                logger.info("Reflexion event processed", 
                            user_id=event.get("user_id"),
                            duration=f"{duration:.2f}s")
                            
                self.queue.task_done()
            except Exception as e:
                logger.error(f"Reflexion worker error: {e}", exc_info=True)
                await asyncio.sleep(1)

    def _should_process(self, event: Dict[str, Any]) -> bool:
        """
        Determine whether to process this event (Sampling & Triggering).
        """
        user_input = event.get("user_input", "")
        
        # 1. Always process if input is long enough (meaningful content)
        if len(user_input) > 10:
            return True
            
        # 2. Check emotion intensity (if available)
        user_emotion = event.get("user_emotion", {})
        # Simple heuristic: if any emotion > 0.6, process it (Emotional Spike)
        if user_emotion and any(score > 0.6 for score in user_emotion.values()):
            return True
            
        # 3. Random sampling for short/neutral inputs (20%)
        return random.random() < 0.2

    async def _process_event(self, event: Dict[str, Any]):
        if not self._should_process(event):
            logger.info("Reflexion: Skipped event due to sampling strategy.")
            return

        try:
            user_id = int(event.get("user_id"))
            session_id = event.get("session_id")
            user_input = event.get("user_input")
            agent_response = event.get("agent_response")
            agent_emotion = event.get("agent_emotion", {})
            target_emotion = event.get("target_emotion")
            user_emotion = event.get("user_emotion", {})
            history = event.get("history", [])

            # 1. Fetch History if missing (for Coherence calculation)
            if not history:
                try:
                    loop = asyncio.get_running_loop()
                    def _get_history():
                        # Get recent context (e.g. last 10 turns)
                        # We use synchronous service in executor
                        msgs = history_service.get_recent_history_limit(user_id, limit=10)
                        return [m.content for m in msgs]
                    
                    history = await loop.run_in_executor(None, _get_history)
                except Exception as e:
                    logger.warning(f"Reflexion: Failed to fetch history: {e}")
                    history = []

            # 2. Process via Service
            await self.service.process_turn(
                user_id=user_id,
                session_id=session_id,
                user_input=user_input,
                agent_response=agent_response,
                agent_emotion=agent_emotion,
                target_emotion=target_emotion,
                history=history,
                user_emotion=user_emotion
            )

        except Exception as e:
            logger.error(f"Reflexion processing failed: {e}", exc_info=True)

reflexion_system = AsyncReflexionSystem()
