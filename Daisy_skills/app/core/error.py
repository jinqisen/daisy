from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class SkillError(Exception):
    code: str

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class RateLimitError(SkillError):
    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__("SKILL_RATE_LIMITED", message)


class UnauthorizedError(SkillError):
    def __init__(self, message: str = "Unauthorized"):
        super().__init__("SKILL_UNAUTHORIZED", message)


class ErrorResult(BaseModel):
    code: str
    message: str
    trace_id: str
    details: Optional[Dict[str, Any]] = None
    retryable: Optional[bool] = None
    tool: Optional[str] = None
    skill: Optional[str] = None


class AdminResult(BaseModel):
    status: str
    message: Optional[str] = None
    updated_fields: Optional[List[str]] = None
    trace_id: Optional[str] = None
    error: Optional[ErrorResult] = None


def make_error(code: str, message: str, trace_id: str, details: Optional[Dict[str, Any]] = None, retryable: Optional[bool] = None, tool: Optional[str] = None, skill: Optional[str] = None) -> ErrorResult:
    return ErrorResult(
        code=code,
        message=message,
        trace_id=trace_id,
        details=details,
        retryable=retryable,
        tool=tool,
        skill=skill,
    )


def make_admin_result(status: str, message: Optional[str] = None, updated_fields: Optional[List[str]] = None, trace_id: Optional[str] = None, error: Optional[ErrorResult] = None) -> AdminResult:
    return AdminResult(
        status=status,
        message=message,
        updated_fields=updated_fields,
        trace_id=trace_id,
        error=error,
    )


def map_exception(exc: Exception) -> str:
    if isinstance(exc, SkillError):
        return exc.code
    if isinstance(exc, (ValueError, TypeError)):
        return "SKILL_INVALID_INPUT"
    if isinstance(exc, PermissionError):
        return "SKILL_FORBIDDEN"
    if isinstance(exc, TimeoutError):
        return "SKILL_TIMEOUT"
    if isinstance(exc, ConnectionError):
        return "SKILL_DEPENDENCY_UNAVAILABLE"
    return "SKILL_INTERNAL"
