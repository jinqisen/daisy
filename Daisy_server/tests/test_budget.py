"""
工作流级预算账本测试(深改点 #4 首增量)。

- evaluate_budget 是纯函数,直接测阈值语义(默认关闭 / 调用数上限 / token 上限)。
- record/get 的 Redis 集成测试仅在本地 Redis 可达时运行,否则跳过。
"""

import asyncio
import uuid

import pytest

from app.core import budget
from app.core.config import settings


@pytest.fixture
def budget_limits(monkeypatch):
    """临时启用预算上限,测试后还原(默认配置下预算检查关闭)。"""
    def _set(max_tokens=None, max_calls=None):
        monkeypatch.setattr(settings, "EXEC_BUDGET_MAX_TOKENS", max_tokens)
        monkeypatch.setattr(settings, "EXEC_BUDGET_MAX_LLM_CALLS", max_calls)
    return _set


def test_budget_disabled_by_default(budget_limits):
    budget_limits(None, None)
    over, reason = budget.evaluate_budget({"llm_calls": 999, "in_tokens": 10**9, "out_tokens": 10**9})
    assert not over and reason == ""


def test_budget_call_limit(budget_limits):
    budget_limits(max_calls=5)
    assert budget.evaluate_budget({"llm_calls": 4})[0] is False
    over, reason = budget.evaluate_budget({"llm_calls": 5})
    assert over and "llm_calls" in reason


def test_budget_token_limit_counts_in_plus_out(budget_limits):
    budget_limits(max_tokens=1000)
    assert budget.evaluate_budget({"in_tokens": 400, "out_tokens": 599})[0] is False
    over, reason = budget.evaluate_budget({"in_tokens": 400, "out_tokens": 600})
    assert over and "total_tokens" in reason


def test_budget_empty_usage_never_over(budget_limits):
    budget_limits(max_tokens=1, max_calls=1)
    assert budget.evaluate_budget({})[0] is False


from tests.redis_test_utils import probe_redis, fresh_redis


@pytest.mark.skipif(not probe_redis(), reason="本地 Redis 不可达,跳过账本集成测试")
def test_record_and_read_usage_roundtrip():
    exec_id = f"test-{uuid.uuid4()}"

    async def _run():
        async with fresh_redis() as client:
            await budget.record_llm_usage(exec_id, in_tokens=100, out_tokens=50, cost_usd=0.002)
            await budget.record_llm_usage(exec_id, in_tokens=30, out_tokens=20)
            usage = await budget.get_execution_usage(exec_id)
            # 清理测试键
            await client.redis.delete(f"{budget.EXEC_KEY_PREFIX}{exec_id}")
            return usage

    usage = asyncio.run(_run())
    assert usage["llm_calls"] == 2
    assert usage["in_tokens"] == 130
    assert usage["out_tokens"] == 70
    assert usage["cost_usd"] == pytest.approx(0.002)
