from __future__ import annotations

import asyncio
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from app.skills.reflexion.scripts.metrics import metrics_service
from app.skills.reflexion.scripts.storage import reflexion_storage
from app.skills.reflexion.scripts.patching import reflexion_patcher
from app.shared.redis import redis_client, async_redis_client


class ReflexionService:
    def __init__(self):
        self.queue_key = "reflexion:queue"
        self.metrics_key_prefix = "reflexion:metrics:user:"
        self.metrics_ttl = 86400 * 7
    
    async def enqueue_event(
        self,
        user_id: int,
        session_id: str,
        user_input: str,
        agent_response: str,
        agent_emotion: Dict[str, float],
        target_emotion: Dict[str, float],
        user_emotion: Dict[str, float],
        history: List[str],
        response_time_sec: Optional[float] = None,
        user_feedback: Optional[str] = None
    ) -> Dict[str, Any]:
        try:
            event = {
                "user_id": user_id,
                "session_id": session_id,
                "user_input": user_input,
                "agent_response": agent_response,
                "agent_emotion": agent_emotion,
                "target_emotion": target_emotion,
                "user_emotion": user_emotion,
                "history": history,
                "response_time_sec": response_time_sec,
                "user_feedback": user_feedback,
                "timestamp": datetime.now().isoformat()
            }
            
            await async_redis_client.rpush(self.queue_key, json.dumps(event))
            await async_redis_client.expire(self.queue_key, 86400)
            queue_size = await async_redis_client.llen(self.queue_key)
            
            return {
                "success": True,
                "message": "Event enqueued successfully",
                "queue_size": queue_size
            }
        except Exception as e:
            print(f"Failed to enqueue event: {e}")
            return {
                "success": False,
                "message": f"Failed to enqueue event: {str(e)}"
            }
    
    async def process_turn(
        self,
        user_id: int,
        session_id: str,
        user_input: str,
        agent_response: str,
        agent_emotion: Dict[str, float],
        target_emotion: Dict[str, float],
        user_emotion: Dict[str, float],
        history: List[str],
        response_time_sec: Optional[float] = None,
        user_feedback: Optional[str] = None
    ) -> Dict[str, Any]:
        try:
            q_i_result = metrics_service.calculate_interaction_quality(
                response=agent_response,
                history=history,
                actual_emotion=agent_emotion,
                target_emotion=target_emotion
            )
            
            e_u_result = metrics_service.calculate_user_engagement(
                agent_response=agent_response,
                user_next_input=user_input,
                response_time_sec=response_time_sec or 30.0,
                prev_user_emotion=user_emotion,
                next_user_emotion=user_emotion
            )
            
            d_r_result = metrics_service.calculate_relationship_depth(
                session_count_7d=await self._get_session_count_7d(user_id),
                retention_rate_7d=await self._get_retention_rate_7d(user_id),
                memory_updates_count=await self._get_memory_updates_count(user_id),
                total_interactions=await self._get_total_interactions(user_id)
            )
            
            q_i = q_i_result["Q_I"]
            e_u = e_u_result["E_U"]
            d_r = d_r_result["D_R"]
            
            s_total = 0.4 * q_i + 0.3 * e_u + 0.3 * d_r
            
            metrics_data = {
                "Q_I": q_i,
                "E_U": e_u,
                "D_R": d_r,
                "S_total": s_total,
                "details": {
                    "Q_I": q_i_result,
                    "E_U": e_u_result,
                    "D_R": d_r_result
                },
                "timestamp": datetime.now().isoformat()
            }
            
            await self._save_metrics(user_id, session_id, metrics_data)
            
            if s_total >= 0.8:
                await reflexion_storage.store_exemplar(
                    text=user_input,
                    metadata={
                        "user_id": user_id,
                        "session_id": session_id,
                        "agent_response": agent_response,
                        "score": s_total,
                        "log_id": hash(f"{user_id}_{session_id}_{datetime.now().timestamp()}")
                    }
                )
            elif s_total < 0.5:
                await reflexion_patcher.generate_patch(
                    user_id=user_id,
                    user_input_context=user_input,
                    agent_response=agent_response,
                    user_feedback=user_feedback or "",
                    score=s_total,
                    metrics=metrics_data["details"]
                )
            
            return {
                "success": True,
                "metrics": metrics_data
            }
        except Exception as e:
            print(f"Failed to process turn: {e}")
            return {
                "success": False,
                "message": f"Failed to process turn: {str(e)}"
            }
    
    async def get_metrics(
        self,
        user_id: int,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        try:
            key = f"{self.metrics_key_prefix}{user_id}"
            raw_data = await async_redis_client.get(key)
            
            if not raw_data:
                return {
                    "success": True,
                    "metrics": {
                        "Q_I": 0.5,
                        "E_U": 0.5,
                        "D_R": 0.5,
                        "S_total": 0.5
                    }
                }
            
            data = json.loads(raw_data)
            
            if session_id:
                result = data.get(session_id)
            else:
                result = data
            
            if result:
                return {
                    "success": True,
                    "metrics": result
                }
            else:
                return {
                    "success": True,
                    "metrics": {
                        "Q_I": 0.5,
                        "E_U": 0.5,
                        "D_R": 0.5,
                        "S_total": 0.5
                    }
                }
        except Exception as e:
            print(f"Failed to get metrics: {e}")
            return {
                "success": False,
                "message": f"Failed to get metrics: {str(e)}"
            }
    
    async def get_patches(self, user_id: int) -> Dict[str, Any]:
        try:
            patches = await reflexion_patcher.get_patches(user_id)
            
            return {
                "success": True,
                "patches": patches
            }
        except Exception as e:
            print(f"Failed to get patches: {e}")
            return {
                "success": False,
                "message": f"Failed to get patches: {str(e)}"
            }
    
    async def retrieve_exemplars(
        self,
        query_text: str,
        limit: int = 3,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        try:
            exemplars = await reflexion_storage.retrieve_exemplars(
                query_text=query_text,
                limit=limit,
                user_id=user_id
            )
            
            return {
                "success": True,
                "exemplars": exemplars
            }
        except Exception as e:
            print(f"Failed to retrieve exemplars: {e}")
            return {
                "success": False,
                "message": f"Failed to retrieve exemplars: {str(e)}",
                "exemplars": []
            }
    
    async def _save_metrics(
        self,
        user_id: int,
        session_id: str,
        metrics_data: Dict[str, Any]
    ):
        try:
            key = f"{self.metrics_key_prefix}{user_id}"
            raw_data = await async_redis_client.get(key)
            
            if raw_data:
                data = json.loads(raw_data)
            else:
                data = {}
            
            data[session_id] = metrics_data
            
            await async_redis_client.set(key, json.dumps(data))
            await async_redis_client.expire(key, self.metrics_ttl)
        except Exception as e:
            print(f"Failed to save metrics: {e}")
    
    async def _get_session_count_7d(self, user_id: int) -> int:
        try:
            key = f"user:{user_id}:sessions:7d"
            count = await async_redis_client.get(key)
            return int(count) if count else 1
        except Exception:
            return 1
    
    async def _get_retention_rate_7d(self, user_id: int) -> float:
        try:
            key = f"user:{user_id}:retention:7d"
            rate = await async_redis_client.get(key)
            return float(rate) if rate else 0.7
        except Exception:
            return 0.7
    
    async def _get_memory_updates_count(self, user_id: int) -> int:
        try:
            key = f"user:{user_id}:memory:updates"
            count = await async_redis_client.get(key)
            return int(count) if count else 10
        except Exception:
            return 10
    
    async def _get_total_interactions(self, user_id: int) -> int:
        try:
            key = f"user:{user_id}:interactions:total"
            count = await async_redis_client.get(key)
            return int(count) if count else 50
        except Exception:
            return 50


reflexion_service = ReflexionService()
