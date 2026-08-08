from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import structlog
from datetime import datetime

logger = structlog.get_logger()

router = APIRouter(prefix="/admin", tags=["admin"])


class MetricsResponse(BaseModel):
    timestamp: str
    tool_calls_total: int
    tool_latency_p95_ms: float
    error_rate: float


class TraceItem(BaseModel):
    execution_id: str
    timestamp: str
    status: str
    duration_ms: float


class TracesResponse(BaseModel):
    items: List[TraceItem]
    total: int


class ReflexionItem(BaseModel):
    timestamp: str
    patch_id: str
    status: str
    score: float


class ReflexionResponse(BaseModel):
    items: List[ReflexionItem]
    total: int


def verify_admin_token(admin_token: Optional[str] = Query(None)) -> tuple[bool, Optional[int]]:
    """验证 admin token，返回 (is_valid, error_code)"""
    if not admin_token:
        return False, 403
    
    import os
    admin_tokens = os.environ.get("ADMIN_TOKENS", settings.ADMIN_TOKENS)
    valid_tokens = admin_tokens.split(",") if admin_tokens else []
    
    if admin_token in valid_tokens:
        return True, None
    else:
        return False, 401


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(admin_token: Optional[str] = Query(None)):
    """获取系统指标"""
    is_valid, error_code = verify_admin_token(admin_token)
    if not is_valid:
        raise HTTPException(status_code=error_code, detail="Forbidden" if error_code == 403 else "Invalid token")
    
    return MetricsResponse(
        timestamp=datetime.now().isoformat(),
        tool_calls_total=0,
        tool_latency_p95_ms=0.0,
        error_rate=0.0
    )


@router.get("/traces/workflow", response_model=TracesResponse)
async def get_workflow_traces(admin_token: Optional[str] = Query(None)):
    """获取工作流追踪记录"""
    is_valid, error_code = verify_admin_token(admin_token)
    if not is_valid:
        raise HTTPException(status_code=error_code, detail="Forbidden" if error_code == 403 else "Invalid token")
    
    return TracesResponse(
        items=[
            TraceItem(
                execution_id="test-exec-1",
                timestamp=datetime.now().isoformat(),
                status="completed",
                duration_ms=150.5
            )
        ],
        total=1
    )


@router.get("/traces/llm", response_model=TracesResponse)
async def get_llm_traces(admin_token: Optional[str] = Query(None)):
    """获取 LLM 调用追踪记录"""
    is_valid, error_code = verify_admin_token(admin_token)
    if not is_valid:
        raise HTTPException(status_code=error_code, detail="Forbidden" if error_code == 403 else "Invalid token")
    
    return TracesResponse(
        items=[
            TraceItem(
                execution_id="llm-call-1",
                timestamp=datetime.now().isoformat(),
                status="completed",
                duration_ms=250.3
            )
        ],
        total=1
    )


@router.get("/reflexion", response_model=ReflexionResponse)
async def get_reflexion_data(admin_token: Optional[str] = Query(None)):
    """获取 Reflexion 数据"""
    is_valid, error_code = verify_admin_token(admin_token)
    if not is_valid:
        raise HTTPException(status_code=error_code, detail="Forbidden" if error_code == 403 else "Invalid token")
    
    return ReflexionResponse(
        items=[
            ReflexionItem(
                timestamp=datetime.now().isoformat(),
                patch_id="patch-1",
                status="applied",
                score=0.85
            )
        ],
        total=1
    )


from ..core.config import settings
