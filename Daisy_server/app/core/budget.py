"""
工作流级预算账本(深改点 #4 首增量:从「有观测」到「可控制」)。

- 记账:LLMService 每次调用把估算 token/成本按 execution_id 累计到
  Redis 哈希 `metrics:exec:{execution_id}`(带 TTL,自动过期)。
- 控制:evaluate_budget() 是纯函数(可单测);is_over_budget() 是异步封装,
  供工具循环等控制点做超预算早退。
- 默认关闭:EXEC_BUDGET_MAX_TOKENS / EXEC_BUDGET_MAX_LLM_CALLS 均为 None 时
  永不判超,行为与迁移前完全一致;在 .env 配置后生效。

覆盖范围说明:记账依赖调用方 metadata 携带 execution_id,当前接入了最终生成与
FAST/STANDARD 路径;services/generation.py 的并行任务调用尚未携带(后续增量)。
"""

from typing import Optional, Tuple

import structlog

from .config import settings
from .redis import redis_client

logger = structlog.get_logger()

EXEC_KEY_PREFIX = "metrics:exec:"
EXEC_KEY_TTL_SEC = 3600  # 单轮执行的账本保留 1 小时,足够在线检查与事后排查


def _exec_key(execution_id: str) -> str:
    return f"{EXEC_KEY_PREFIX}{execution_id}"


async def record_llm_usage(
    execution_id: Optional[str],
    in_tokens: int,
    out_tokens: int,
    cost_usd: float = 0.0,
) -> None:
    """按 execution_id 累计一次 LLM 调用的用量。无 execution_id 或 Redis 不可用时静默跳过。"""
    if not execution_id:
        return
    try:
        if not redis_client.enabled or not redis_client.redis:
            return
        key = _exec_key(execution_id)
        pipe = redis_client.redis.pipeline()
        pipe.hincrby(key, "llm_calls", 1)
        pipe.hincrby(key, "in_tokens", int(in_tokens))
        pipe.hincrby(key, "out_tokens", int(out_tokens))
        if cost_usd:
            pipe.hincrbyfloat(key, "cost_usd", float(cost_usd))
        pipe.expire(key, EXEC_KEY_TTL_SEC)
        await pipe.execute()
    except Exception:
        # 记账失败绝不影响主链路
        return


async def get_execution_usage(execution_id: Optional[str]) -> dict:
    """读取某次执行的累计用量;不可用时返回空 dict。"""
    if not execution_id:
        return {}
    try:
        if not redis_client.enabled or not redis_client.redis:
            return {}
        raw = await redis_client.redis.hgetall(_exec_key(execution_id))
        usage = {}
        for k, v in (raw or {}).items():
            k = k.decode() if isinstance(k, bytes) else k
            v = v.decode() if isinstance(v, bytes) else v
            usage[k] = float(v) if k == "cost_usd" else int(float(v))
        return usage
    except Exception:
        return {}


def evaluate_budget(usage: dict) -> Tuple[bool, str]:
    """
    纯函数:判断用量是否超出配置上限。
    返回 (是否超预算, 原因描述);未配置任何上限时恒为 (False, "")。
    """
    max_tokens = settings.EXEC_BUDGET_MAX_TOKENS
    max_calls = settings.EXEC_BUDGET_MAX_LLM_CALLS

    if max_calls is not None:
        calls = usage.get("llm_calls", 0)
        if calls >= max_calls:
            return True, f"llm_calls {calls} >= {max_calls}"
    if max_tokens is not None:
        total = usage.get("in_tokens", 0) + usage.get("out_tokens", 0)
        if total >= max_tokens:
            return True, f"total_tokens {total} >= {max_tokens}"
    return False, ""


async def is_over_budget(execution_id: Optional[str]) -> Tuple[bool, str]:
    """异步封装:读账本 + 判断。任何异常都按「不超预算」处理,保证可用性优先。"""
    if settings.EXEC_BUDGET_MAX_TOKENS is None and settings.EXEC_BUDGET_MAX_LLM_CALLS is None:
        return False, ""
    usage = await get_execution_usage(execution_id)
    over, reason = evaluate_budget(usage)
    if over:
        logger.warning("Execution budget exceeded", execution_id=execution_id, reason=reason, usage=usage)
    return over, reason
