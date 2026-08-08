import asyncio
import pytest
from app.core.execution import RateLimiter, ExecutionConfig, execute_with_strategy, get_rate_limiter


@pytest.mark.asyncio
async def test_rate_limiter_basic():
    limiter = RateLimiter(default_qps=2)
    assert await limiter.acquire("user1") is True
    assert await limiter.acquire("user1") is True
    assert await limiter.acquire("user1") is False


@pytest.mark.asyncio
async def test_rate_limiter_wait_for_token():
    limiter = RateLimiter(default_qps=10)
    start = asyncio.get_event_loop().time()
    acquired = await limiter.wait_for_token("user1", timeout=1.0)
    end = asyncio.get_event_loop().time()
    assert acquired is True
    assert end - start < 0.5


@pytest.mark.asyncio
async def test_rate_limiter_wait_timeout():
    limiter = RateLimiter(default_qps=1)
    await limiter.acquire("user1")
    acquired = await limiter.wait_for_token("user1", timeout=0.1)
    assert acquired is False


@pytest.mark.asyncio
async def test_rate_limiter_user_qps():
    limiter = RateLimiter(default_qps=1)
    limiter.set_user_qps("user1", 5)
    assert limiter.get_qps("user1") == 5
    assert limiter.get_qps("user2") == 1


def test_execution_config_timeout():
    payload = {"metadata": {"model": {"timeout_sec": 60}}}
    assert ExecutionConfig.get_timeout(payload) == 60

    payload = {"metadata": {}}
    assert ExecutionConfig.get_timeout(payload) == ExecutionConfig.DEFAULT_TIMEOUT_SEC

    payload = {}
    assert ExecutionConfig.get_timeout(payload) == ExecutionConfig.DEFAULT_TIMEOUT_SEC


def test_execution_config_retryable():
    assert ExecutionConfig.should_retry("SKILL_DEPENDENCY_UNAVAILABLE") is True
    assert ExecutionConfig.should_retry("SKILL_TIMEOUT") is True
    assert ExecutionConfig.should_retry("SKILL_INVALID_INPUT") is False
    assert ExecutionConfig.should_retry("SKILL_INTERNAL") is False


def test_execution_config_backoff():
    backoff = ExecutionConfig.get_backoff(0)
    assert backoff == ExecutionConfig.INITIAL_BACKOFF_SEC

    backoff = ExecutionConfig.get_backoff(1)
    assert backoff == ExecutionConfig.INITIAL_BACKOFF_SEC * 2

    backoff = ExecutionConfig.get_backoff(10)
    assert backoff == ExecutionConfig.MAX_BACKOFF_SEC


@pytest.mark.asyncio
async def test_execute_with_strategy_success():
    async def handler(payload):
        return {"result": "success"}

    result = await execute_with_strategy(
        handler=handler,
        payload={},
        user_id="user1",
        trace_id="test-trace",
        tool_name="test.tool",
        skill_name="test",
    )
    assert result == {"result": "success"}


@pytest.mark.asyncio
async def test_execute_with_strategy_timeout():
    async def handler(payload):
        await asyncio.sleep(10)
        return {"result": "success"}

    result = await execute_with_strategy(
        handler=handler,
        payload={"metadata": {"model": {"timeout_sec": 1}}},
        user_id="user1",
        trace_id="test-trace",
        tool_name="test.tool",
        skill_name="test",
    )
    assert result["code"] == "SKILL_TIMEOUT"
    assert result["retryable"] is True


@pytest.mark.asyncio
async def test_execute_with_strategy_retry():
    attempts = 0

    async def handler(payload):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionError("Temporary failure")
        return {"result": "success"}

    result = await execute_with_strategy(
        handler=handler,
        payload={},
        user_id="user1",
        trace_id="test-trace",
        tool_name="test.tool",
        skill_name="test",
    )
    assert result == {"result": "success"}
    assert attempts == 3


@pytest.mark.asyncio
async def test_execute_with_strategy_rate_limit():
    limiter = get_rate_limiter()
    limiter.set_user_qps("user1", 0)

    async def handler(payload):
        return {"result": "success"}

    result = await execute_with_strategy(
        handler=handler,
        payload={},
        user_id="user1",
        trace_id="test-trace",
        tool_name="test.tool",
        skill_name="test",
    )
    assert result["code"] == "SKILL_RATE_LIMITED"
    assert result["retryable"] is True

    limiter.set_user_qps("user1", 10)


def test_get_rate_limiter():
    limiter1 = get_rate_limiter()
    limiter2 = get_rate_limiter()
    assert limiter1 is limiter2
