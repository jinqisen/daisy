from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Any, Callable, Dict, Optional

from .error import ErrorResult, make_error, map_exception, RateLimitError
from .logging import get_logger, set_trace_context


class RateLimiter:
    def __init__(self, default_qps: int = 10):
        self.default_qps = default_qps
        self.user_qps: Dict[str, int] = {}
        self.tokens: Dict[str, float] = defaultdict(float)
        self.last_update: Dict[str, float] = defaultdict(float)
        self._lock = asyncio.Lock()

    def set_user_qps(self, user_id: str, qps: int):
        self.user_qps[user_id] = qps

    def get_qps(self, user_id: str) -> int:
        return self.user_qps.get(user_id, self.default_qps)

    async def acquire(self, user_id: str) -> bool:
        async with self._lock:
            qps = self.get_qps(user_id)
            now = time.time()
            elapsed = now - self.last_update[user_id]
            self.tokens[user_id] = min(self.tokens[user_id] + elapsed * qps, qps)
            self.last_update[user_id] = now

            if self.tokens[user_id] >= 1:
                self.tokens[user_id] -= 1
                return True
            return False

    async def wait_for_token(self, user_id: str, timeout: float = 5.0) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            if await self.acquire(user_id):
                return True
            await asyncio.sleep(0.01)
        return False


class ExecutionConfig:
    DEFAULT_TIMEOUT_SEC: int = 30
    MAX_RETRIES: int = 3
    INITIAL_BACKOFF_SEC: float = 1.0
    MAX_BACKOFF_SEC: float = 10.0
    RETRYABLE_ERRORS: set[str] = {"SKILL_DEPENDENCY_UNAVAILABLE", "SKILL_TIMEOUT"}

    @staticmethod
    def get_timeout(payload: Dict[str, Any]) -> int:
        metadata = payload.get("metadata") or {}
        model_meta = metadata.get("model") or {}
        timeout = model_meta.get("timeout_sec")
        if timeout is not None and isinstance(timeout, (int, float)):
            return int(timeout)
        return ExecutionConfig.DEFAULT_TIMEOUT_SEC

    @staticmethod
    def should_retry(error_code: str) -> bool:
        return error_code in ExecutionConfig.RETRYABLE_ERRORS

    @staticmethod
    def get_backoff(attempt: int) -> float:
        backoff = ExecutionConfig.INITIAL_BACKOFF_SEC * (2 ** attempt)
        return min(backoff, ExecutionConfig.MAX_BACKOFF_SEC)


_rate_limiter = RateLimiter()


async def execute_with_strategy(
    handler: Callable,
    payload: Dict[str, Any],
    user_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    tool_name: Optional[str] = None,
    skill_name: Optional[str] = None,
) -> Dict[str, Any]:
    logger = get_logger()
    set_trace_context(trace_id=trace_id)

    if user_id:
        acquired = await _rate_limiter.wait_for_token(user_id)
        if not acquired:
            logger.warning("rate_limit_exceeded", user_id=user_id, tool=tool_name, skill=skill_name)
            error = make_error(
                code="SKILL_RATE_LIMITED",
                message="Rate limit exceeded",
                trace_id=trace_id,
                tool=tool_name,
                skill=skill_name,
                retryable=True,
            )
            return error.model_dump()

    timeout = ExecutionConfig.get_timeout(payload)
    last_error: Optional[ErrorResult] = None

    for attempt in range(ExecutionConfig.MAX_RETRIES + 1):
        try:
            result = await asyncio.wait_for(handler(payload), timeout=timeout)
            if attempt > 0:
                logger.info("tool_retry_success", tool=tool_name, skill=skill_name, attempt=attempt)
            return result
        except asyncio.TimeoutError:
            error_code = "SKILL_TIMEOUT"
            error_msg = f"Tool execution timeout after {timeout}s"
        except Exception as exc:
            error_code = map_exception(exc)
            error_msg = str(exc)

        last_error = make_error(
            code=error_code,
            message=error_msg,
            trace_id=trace_id,
            tool=tool_name,
            skill=skill_name,
            retryable=ExecutionConfig.should_retry(error_code),
        )

        if attempt < ExecutionConfig.MAX_RETRIES and ExecutionConfig.should_retry(error_code):
            backoff = ExecutionConfig.get_backoff(attempt)
            logger.warning(
                "tool_retry",
                tool=tool_name,
                skill=skill_name,
                attempt=attempt + 1,
                error_code=error_code,
                backoff_sec=backoff,
            )
            await asyncio.sleep(backoff)
        else:
            break

    logger.error(
        "tool_failed",
        tool=tool_name,
        skill=skill_name,
        error_code=last_error.code,
        final_attempt=attempt,
    )
    return last_error.model_dump()


def get_rate_limiter() -> RateLimiter:
    return _rate_limiter
