import json
import asyncio
import structlog
from typing import Dict, Any, Optional
from datetime import datetime
from app.core.redis import redis_client
from app.core.database import SessionLocal
from app.models import ReflexionLogDB, UserDB
from app.agents.daisy.character_card import CharacterCard
from app.services.memory.chat_history import history_service
from app.services.learning.reflexion.metrics import metrics_service
from app.services.learning.reflexion.storage import reflexion_storage

# D_R(关系深度)需要足够历史才有统计意义。低于此阈值时视为不可信,
# S 分数改用 Q_I + E_U 归一化,避免把噪声当信号喂给后续学习。
MIN_INTERACTIONS_FOR_DR = 20
from app.services.learning.reflexion.patching import reflexion_patcher

logger = structlog.get_logger()

class ReflexionService:
    def __init__(self):
        self.metrics = metrics_service
        self.storage = reflexion_storage
        self.patcher = reflexion_patcher

    async def process_turn(
        self,
        user_id: int,
        session_id: str,
        user_input: str,
        agent_response: str,
        agent_emotion: Dict[str, float],
        target_emotion: Dict[str, float], # From Strategy
        history: list[str],
        user_emotion: Dict[str, float] = None # Current user emotion (from input)
    ):
        """
        Main entry point for Reflexion.
        1. Finalize PREVIOUS turn (calculate E_U and Total Score).
        2. Calculate CURRENT turn Q_I and store for next time.
        """
        if user_emotion is None:
            user_emotion = {}

        # 1. Finalize Previous Turn (if exists)
        # Here, user_input acts as the "next user input" for the previous turn
        await self._finalize_previous_turn(
            user_id, session_id, user_input, user_emotion
        )

        # 2. Process Current Turn (Q_I)
        q_i_result = self.metrics.calculate_interaction_quality(
            response=agent_response,
            history=history,
            actual_emotion=agent_emotion,
            target_emotion=target_emotion
        )
        
        # Store pending data for next turn
        pending_data = {
            "user_input": user_input, # Store context for RAG
            "agent_response": agent_response,
            "q_i_result": q_i_result,
            "timestamp": datetime.now().timestamp(),
            "agent_emotion": agent_emotion,
            "user_emotion": user_emotion # Store current user emotion for Sentiment Lift calc next turn
        }
        
        # Save pending log to DB
        try:
            loop = asyncio.get_running_loop()
            log_id = await loop.run_in_executor(
                None,
                lambda: history_service.create_pending_reflexion_log(
                    user_id=user_id,
                    session_id=session_id,
                    user_input=user_input,
                    agent_response=agent_response,
                    metrics=q_i_result
                )
            )
            pending_data["log_id"] = log_id
        except Exception as e:
            logger.error(f"Reflexion: Failed to save pending log: {e}")

        # Save to Redis (TTL 24h)
        key = f"reflexion:pending:{session_id}"
        await redis_client.set(key, json.dumps(pending_data), ttl=86400)
        
        logger.info(f"Reflexion: Q_I calculated for {session_id}", 
                    q_i=q_i_result["Q_I"])

    async def _finalize_previous_turn(
        self,
        user_id: int,
        session_id: str,
        current_user_input: str,
        current_user_emotion: Dict[str, float] 
    ):
        """
        Calculate E_U using current user input as feedback for previous agent response.
        Then compute Total Score S and trigger Evolution.
        """
        key = f"reflexion:pending:{session_id}"
        data_str = await redis_client.get(key)
        
        if not data_str:
            return # First turn or expired
            
        prev_data = json.loads(data_str)
        prev_user_input = prev_data.get("user_input", "")
        prev_response = prev_data["agent_response"]
        q_i_result = prev_data["q_i_result"]
        log_id = prev_data.get("log_id")
        # prev_agent_emotion = prev_data.get("agent_emotion", {})
        prev_user_emotion = prev_data.get("user_emotion", {}) # Retrieved from storage
        
        # Calculate E_U
        # Note: We need response time. 
        # Approx: Now - Prev_Timestamp (includes user think time)
        response_time = datetime.now().timestamp() - prev_data["timestamp"]
        
        e_u_result = self.metrics.calculate_user_engagement(
            agent_response=prev_response,
            user_next_input=current_user_input,
            response_time_sec=response_time,
            prev_user_emotion=prev_user_emotion,
            next_user_emotion=current_user_emotion
        )

        # Calculate D_R
        dr_stats = await self._get_relationship_stats(user_id)
        d_r_result = self.metrics.calculate_relationship_depth(
            session_count_7d=dr_stats.get("session_count_7d", 0),
            retention_rate_7d=dr_stats.get("retention_rate_7d", 0.0),
            memory_updates_count=dr_stats.get("memory_updates_count", 0),
            total_interactions=dr_stats.get("total_interactions", 1)
        )
        
        # Composite Score S (v3.2)
        # Weights: Q_I=0.5, E_U=0.3, D_R=0.2
        #
        # 新用户历史太少时 D_R 不可信(样本不足算出的频次/留存是噪声)。此时不再把
        # 一个猜测值按 20% 权重掺进去,而是丢弃 D_R 并把 Q_I/E_U 重新归一化 ——
        # 让 S 只由可信分量构成。这对后续基于 S 的学习(bandit/RL)尤其重要:
        # 掺入常量或噪声会让模型拟合到假信号。
        dr_is_real = bool(dr_stats.get("is_real"))
        if dr_is_real:
            s_total = 0.5 * q_i_result["Q_I"] + 0.3 * e_u_result["E_U"] + 0.2 * d_r_result["D_R"]
        else:
            # 权重按 0.5:0.3 重新归一化为 0.625:0.375
            s_total = (0.5 * q_i_result["Q_I"] + 0.3 * e_u_result["E_U"]) / 0.8

        logger.info(f"Reflexion: Finalized Turn. S={s_total:.2f}",
                    q_i=q_i_result["Q_I"], e_u=e_u_result["E_U"],
                    d_r=d_r_result["D_R"], d_r_reliable=dr_is_real)

        # 把 S 作为奖励与上一轮暂存的 (context, action) 配对落库。
        # 纯记录,不影响任何线上决策;供后续离线策略评估判断 bandit 是否值得上线。
        try:
            from app.services.learning.rl_dataset import record_reward
            await record_reward(
                session_id=session_id,
                reward=s_total,
                reward_reliable=dr_is_real,
                metrics={**q_i_result, **e_u_result, **d_r_result},
            )
        except Exception as e:
            logger.warning(f"RL dataset: record_reward skipped: {e}")

        # Trigger Evolution
        all_metrics = {**q_i_result, **e_u_result, **d_r_result, "D_R_reliable": dr_is_real}
        
        # Log to DB (Update existing or create new for legacy)
        try:
            loop = asyncio.get_running_loop()
            if log_id:
                await loop.run_in_executor(
                    None,
                    lambda: history_service.update_reflexion_log(
                        log_id=log_id,
                        critique="",
                        improvement_plan="",
                        metrics={**all_metrics, "S_total": s_total},
                        status="processed"
                    )
                )
            else:
                # Legacy path for pending data without log_id
                await loop.run_in_executor(
                    None,
                    lambda: history_service.save_reflexion_log(
                        user_id=user_id,
                        session_id=session_id,
                        user_input=prev_user_input,
                        agent_response=prev_response,
                        critique="",
                        improvement_plan="",
                        metrics={**all_metrics, "S_total": s_total},
                        status="processed"
                    )
                )
        except Exception as e:
            logger.error(f"Reflexion: Failed to save/update log: {e}")

        await self._trigger_evolution(
            user_id, 
            prev_user_input,
            prev_response, 
            current_user_input, 
            s_total, 
            all_metrics
        )

    async def _get_relationship_stats(self, user_id: int) -> Dict[str, Any]:
        """
        从数据库真实统计关系深度(D_R)所需指标。

        此前返回硬编码常量(session_count_7d=20 / retention=0.95 ...),使 D_R 恒为
        约 0.98 —— 而 D_R 在总分中占 20% 权重,等于给每轮固定加同一个偏置。
        后果:S 分数方差被压缩、阈值难以校准,且任何基于 S 的学习都会拟合到假信号。

        返回值中的 `is_real` 标记供上层判断数据是否可信(新用户样本过少时为 False,
        此时应降级为仅用 Q_I + E_U,而不是继续用估算值充数)。
        """
        import asyncio
        from datetime import datetime, timedelta, timezone

        def _query() -> Dict[str, Any]:
            from app.core.database import SessionLocal
            from app.models import ChatHistoryDB

            with SessionLocal() as db:
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                since = now - timedelta(days=7)

                rows = db.query(ChatHistoryDB).filter(
                    ChatHistoryDB.user_id == user_id,
                    ChatHistoryDB.timestamp >= since,
                ).all()

                total_interactions = db.query(ChatHistoryDB).filter(
                    ChatHistoryDB.user_id == user_id,
                ).count()

                sessions_7d = {r.session_id for r in rows if r.session_id}
                # 留存:近 7 天里有对话的天数占比(比"会话数"更能反映粘性)
                active_days = {r.timestamp.date() for r in rows if r.timestamp}
                retention_rate_7d = len(active_days) / 7.0

                return {
                    "session_count_7d": len(sessions_7d),
                    "retention_rate_7d": round(min(1.0, retention_rate_7d), 4),
                    # 记忆密度用用户消息数近似(每条用户输入都可能沉淀事实)
                    "memory_updates_count": sum(1 for r in rows if r.role == "user"),
                    "total_interactions": total_interactions,
                    "is_real": total_interactions >= MIN_INTERACTIONS_FOR_DR,
                }

        try:
            loop = asyncio.get_running_loop()
            stats = await loop.run_in_executor(None, _query)
            if not stats["is_real"]:
                logger.info(
                    "D_R: insufficient history, will fall back to Q_I+E_U only",
                    user_id=user_id, total_interactions=stats["total_interactions"],
                )
            return stats
        except Exception as e:
            logger.error(f"Failed to compute relationship stats: {e}")
            return {
                "session_count_7d": 0,
                "retention_rate_7d": 0.0,
                "memory_updates_count": 0,
                "total_interactions": 0,
                "is_real": False,
            }

    async def _trigger_evolution(
        self, 
        user_id: int, 
        user_input_context: str,
        agent_response: str, 
        user_feedback: str, 
        score: float,
        metrics: Dict
    ):
        """
        Decide action based on score.
        """
        from app.core.config import settings

        if score >= settings.REFLEXION_EXEMPLAR_THRESHOLD:
            # High Satisfaction -> RAG
            logger.info("Reflexion: High Score! Triggering RAG Storage.",
                        score=score, threshold=settings.REFLEXION_EXEMPLAR_THRESHOLD)
            metadata = {
                "user_id": user_id,
                "agent_response": agent_response,
                "score": score,
                "metrics": metrics,
                "timestamp": datetime.now().isoformat()
            }
            # Store (User Input -> Agent Response) pair
            await self.storage.store_exemplar(
                text=user_input_context, 
                metadata=metadata
            )
            
        elif score <= settings.REFLEXION_PATCH_THRESHOLD:
            # Dissatisfaction -> Patching
            logger.info("Reflexion: Low Score. Triggering Instruction Patching.",
                        score=score, threshold=settings.REFLEXION_PATCH_THRESHOLD)
            await self.patcher.generate_patch(
                user_id=user_id,
                user_input_context=user_input_context,
                agent_response=agent_response,
                user_feedback=user_feedback,
                score=score,
                metrics=metrics
            )

reflexion_service = ReflexionService()
