from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
import structlog

from app.api.deps import get_current_user
from app.models import UserDB
from app.services.learning.rl_agent import get_rl_agent
from app.services.system.session import session_service

logger = structlog.get_logger()
router = APIRouter()

class SessionInfoResponse(BaseModel):
    session_id: Optional[str] = None
    previous_session_id: Optional[str] = None
    status: str
    meta: Dict[str, Any] = Field(default_factory=dict)

class StartSessionRequest(BaseModel):
    end_current: bool = True

class SessionFeedback(BaseModel):
    session_id: str
    duration_seconds: float
    interaction_count: int

@router.get("/current", response_model=SessionInfoResponse)
async def get_current_session(
    create_if_missing: bool = Query(True),
    current_user: UserDB = Depends(get_current_user)
):
    """
    获取当前用户的业务会话。
    create_if_missing=false 时仅探测，不会创建新会话。
    """
    user_id = str(current_user.id)
    session_id = (
        await session_service.get_active_conversation(user_id)
        if create_if_missing
        else await session_service.peek_active_conversation(user_id)
    )
    meta = await session_service.get_conversation_meta(session_id) if session_id else {}

    return SessionInfoResponse(
        session_id=session_id,
        status="active" if session_id else "idle",
        meta=meta,
    )

@router.post("/start", response_model=SessionInfoResponse)
async def start_session(
    payload: StartSessionRequest,
    current_user: UserDB = Depends(get_current_user)
):
    """
    显式创建新的业务会话边界，供前端“新对话”按钮接入。
    """
    user_id = str(current_user.id)
    result = await session_service.start_new_conversation(user_id, end_current=payload.end_current)
    session_id = result["session_id"]
    meta = await session_service.get_conversation_meta(session_id) if session_id else {}
    return SessionInfoResponse(
        session_id=session_id,
        previous_session_id=result.get("previous_session_id"),
        status="active",
        meta=meta,
    )

@router.post("/end")
async def end_session(
    feedback: SessionFeedback,
    current_user: UserDB = Depends(get_current_user)
):
    """
    当前端检测到会话结束或用户离开时调用。
    1. 计算奖励并更新 RL 智能体 (可选)。
    2. 显式结束业务会话，触发归档。
    """
    # 显式结束业务会话
    await session_service.end_conversation(str(current_user.id), feedback.session_id)

    reward = (feedback.interaction_count * 0.5) + (feedback.duration_seconds / 60.0 * 0.2)
    
    agent = get_rl_agent(user_id=str(current_user.id))
    
    try:
        logger.info(f"Session ended. Reward calculated: {reward} (RL Training moved to RLTrainer)")
        return {"status": "success", "reward": reward, "session_id": feedback.session_id}
    except Exception as e:
        logger.error(f"RL Update failed: {e}")
        return {"status": "error", "detail": str(e)}
