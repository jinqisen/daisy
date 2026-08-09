"""
(context, action, reward) 数据管线 —— contextual bandit / RL 的离线数据基础。

设计约束(重要):
  **只记录,不改变线上行为。** 线上仍由现有策略(默认 LLM 策略)决策;
  本模块仅把"当时的上下文 / 实际采取的动作 / 事后算出的奖励"落盘。
  这样可以零风险地积累数据,之后用离线策略评估(OPE)判断 bandit 是否值得上线 ——
  若离线评估打不过现有策略,就该停手,而不是先上线再观察。

数据流:
  1. 决策时(strategy 节点)→ record_decision() 暂存 context+action
  2. 下一轮 Reflexion 结算出 S → record_reward() 配对落库
  3. scripts/export_rl_dataset.py 导出为训练/评估数据集

奖励说明:S 由 Q_I/E_U(/D_R)组成,D_R 不可信时会被剔除并重新归一化,
见 services/reflexion/service.py。样本里保留 reward_reliable 标记供筛选。
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()

# 决策暂存的有效期:超过则认为该轮不会再有反馈(用户离开)
PENDING_TTL_SEC = 3600

# 人格动作空间(与 RL_ACTION_DIM=6 对应)
ACTION_SPACE: List[str] = ["Eros", "Ludus", "Storge", "Pragma", "Mania", "Agape"]


def _pending_key(session_id: str) -> str:
    return f"rl:pending:{session_id}"


def build_context_vector(state: Dict[str, Any]) -> Dict[str, float]:
    """
    构造决策上下文。

    刻意使用**低维**特征(Ekman 6 + 投入度 + 关系阶段),而非原始 28 维 GoEmotions:
    单用户桌面场景样本稀疏(实测数百量级),高维 context 必然过拟合。
    维度应远小于样本数,这是 bandit 能在小数据上工作的前提。
    """
    ekman = state.get("ekman_scores") or {}
    ctx = {f"emo_{k}": float(v) for k, v in sorted(ekman.items())[:6]}
    ctx["engagement"] = float(state.get("engagement_score") or 0.0) / 100.0

    stage_map = {"acquaintance": 0.0, "trust": 0.5, "bond": 1.0}
    ctx["relationship"] = stage_map.get(state.get("relationship_stage", "acquaintance"), 0.0)
    return ctx


async def record_decision(
    session_id: str,
    user_id: int,
    context: Dict[str, float],
    action: str,
    action_weights: Optional[Dict[str, float]] = None,
    policy: str = "llm",
) -> None:
    """
    暂存本轮决策(context + action)。奖励要等下一轮用户反应才能算出,
    故先存 Redis,由 record_reward() 配对。
    """
    from app.core.cache import redis_client

    if not session_id:
        return
    try:
        payload = {
            "user_id": user_id,
            "context": context,
            "action": action,
            "action_weights": action_weights or {},
            "policy": policy,  # 记录数据由哪个策略产生 —— 离线评估需要它做重要性加权
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        await redis_client.set(_pending_key(session_id), json.dumps(payload), ttl=PENDING_TTL_SEC)
    except Exception as e:
        logger.warning(f"RL dataset: failed to record decision: {e}")


async def record_reward(session_id: str, reward: float, reward_reliable: bool = True,
                        metrics: Optional[Dict[str, Any]] = None) -> bool:
    """
    用 Reflexion 算出的 S 作为奖励,与暂存的决策配对后落库。
    返回是否成功配对(无暂存决策时返回 False,属正常:如首轮或过期)。
    """
    from app.core.cache import redis_client
    from app.core.database import SessionLocal
    from app.models import RLSampleDB

    if not session_id:
        return False
    try:
        raw = await redis_client.get(_pending_key(session_id))
        if not raw:
            return False
        pending = json.loads(raw)

        def _save():
            with SessionLocal() as db:
                db.add(RLSampleDB(
                    user_id=pending.get("user_id"),
                    session_id=session_id,
                    context_json=pending.get("context"),
                    action=pending.get("action"),
                    action_weights_json=pending.get("action_weights"),
                    policy=pending.get("policy"),
                    reward=float(reward),
                    reward_reliable=bool(reward_reliable),
                    metrics_json=metrics or {},
                    timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
                ))
                db.commit()

        import asyncio
        await asyncio.get_running_loop().run_in_executor(None, _save)
        await redis_client.delete(_pending_key(session_id))
        logger.info("RL dataset: sample recorded",
                    action=pending.get("action"), reward=round(float(reward), 3))
        return True
    except Exception as e:
        logger.warning(f"RL dataset: failed to record reward: {e}")
        return False
