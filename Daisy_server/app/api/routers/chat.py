from fastapi import APIRouter, HTTPException, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
import datetime
import structlog
import json
import asyncio
import time

from app.core.time_utils import naive_utc_to_iso
from app.core.sse import build_protocol_event, decode_pubsub_payload, encode_sse_message
from app.core.database import get_db
from app.core.time_utils import utc_now_naive
from app.models import UserDB, ChatHistoryDB, ReflexionLogDB
from app.api.deps import get_current_user, get_current_user_from_token_param
from app.services.memory.chat_history import history_service
from app.services.proactive.state import StateService
from app.services.system.session import session_service
from app.core.cache import redis_client
from app.core.task_queue import get_arq_pool
from app.core.utils import split_response_into_parts, group_chat_history_by_pairs

logger = structlog.get_logger()
router = APIRouter()


async def _publish_stream_event(
    *,
    user_id: int,
    event: str,
    data: Dict[str, Any],
    legacy_type: Optional[str] = None,
    **legacy_fields: Any,
) -> None:
    redis = redis_client
    if not redis.enabled:
        await redis.connect()
    if not redis.enabled or not redis.redis:
        return

    payload = build_protocol_event(
        event=event,
        data=data,
        legacy_type=legacy_type,
        **legacy_fields,
    )
    await redis.redis.publish(
        f"chat:stream:{user_id}",
        json.dumps(payload, ensure_ascii=False),
    )

class ChatRequest(BaseModel):
    message: str
    user_id: Optional[str] = "user_default" # 可选，将被当前登录用户覆盖
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    response_parts: Optional[List[str]] = None # 分段响应
    emotion_analysis: Dict[str, Any]
    personality: str
    personality_weights: Dict[str, float]
    engagement_score: float
    system_prompt: Optional[str] = None
    workflow_trace: Optional[Dict[str, Any]] = None # 工作流追踪数据
    user_message_id: Optional[int] = None # 用户消息 ID
    ai_message_id: Optional[int] = None # AI 消息 ID

class HistoryItem(BaseModel):
    id: int
    session_id: Optional[str] = None
    role: str
    content: str
    state_snapshot: Optional[Dict[str, Any]] = None
    timestamp: datetime.datetime
    status: str = "completed"
    parts: Optional[List[str]] = []

def _convert_to_history_item(db_obj: ChatHistoryDB) -> HistoryItem:
    parts = []
    if db_obj.role == "ai" and db_obj.content:
        parts = split_response_into_parts(db_obj.content)
    
    return HistoryItem(
        id=db_obj.id,
        session_id=db_obj.session_id,
        role=db_obj.role,
        content=db_obj.content,
        state_snapshot=db_obj.state_snapshot,
        timestamp=db_obj.timestamp,
        status=db_obj.status,
        parts=parts
    )

@router.get("/message/{message_id}/analysis")
async def get_message_analysis(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user)
):
    """
    获取特定消息的沟通情感分析数据 (心理学专家)。
    如果消息是用户的，尝试查找其后的 AI 回复。
    """
    # 1. & 2. 查找消息及其回复
    target_msg, ai_response = history_service.get_message_with_response(message_id, current_user.id, db)
    
    if not target_msg:
        raise HTTPException(status_code=404, detail="Message not found")
        
    final_msg = ai_response if ai_response else target_msg
    
    # 3. 从快照中提取
    analysis_data = None
    if final_msg.state_snapshot:
        snapshot = final_msg.state_snapshot
        
        # 路径 A: workflow_trace -> analyze_communication_style -> output -> ui_card_data
        trace = snapshot.get("workflow_trace", {})
        if "analyze_communication_style" in trace:
            node_output = trace["analyze_communication_style"].get("output", {})
            if "ui_card_data" in node_output:
                analysis_data = node_output["ui_card_data"]
        
        # 路径 B: 根级别的 analysis 字段 (如果以后有)
        
    # 4. 如果快照中没有，尝试从 WorkflowTraceDB 查找 (作为备份)
    if not analysis_data and final_msg.state_snapshot:
        exec_id = final_msg.state_snapshot.get("execution_id")
        if exec_id:
            traces = history_service.get_traces(
                session_id=final_msg.session_id,
                execution_id=exec_id,
                user_id=current_user.id,
                db=db
            )
            trace_record = next((t for t in traces if t.node_id == "analyze_communication_style"), None)
            
            if trace_record and trace_record.output_data:
                analysis_data = trace_record.output_data.get("ui_card_data")

    if not analysis_data:
        return {"status": "no_data", "message": "No analysis data found for this message."}
        
    return analysis_data

@router.get("/reflexion/history")
async def get_reflexion_history(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user)
):
    """
    获取用户的反思评价历史数据 (Reflexion Logs)
    """
    logs = db.query(ReflexionLogDB)\
        .filter(ReflexionLogDB.user_id == current_user.id)\
        .order_by(ReflexionLogDB.timestamp.asc())\
        .limit(limit)\
        .all()
        
    return [
        {
            # 必须带 UTC 标记 —— 裸 isoformat 会被浏览器当本地时间,整轴偏一个时区
            "timestamp": naive_utc_to_iso(log.timestamp),
            "metrics": log.metrics,
            "session_id": log.session_id,
            "user_input": log.user_input,
            "agent_response": log.agent_response,
            "status": log.status
        }
        for log in logs
    ]

@router.get("/history", response_model=List[HistoryItem])
async def get_chat_history(
    limit: int = 50,
    mode: str = Query("count", enum=["all", "count", "pair"]),
    session_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user)
):
    """
    获取当前用户的聊天记录。
    """
    if session_id and mode == "all":
        records = history_service.get_session_history(current_user.id, session_id, db)
        return [_convert_to_history_item(r) for r in records]

    if session_id and mode == "count":
        records = history_service.get_recent_history_limit(
            current_user.id,
            limit,
            db,
            session_id=session_id,
        )
        return [_convert_to_history_item(r) for r in records]

    if session_id and mode == "pair":
        records = history_service.get_session_history(current_user.id, session_id, db)
        selected_groups = group_chat_history_by_pairs(records)
        if limit > 0:
            selected_groups = selected_groups[-limit:]

        result = []
        for group in selected_groups:
            result.extend(group)
        return [_convert_to_history_item(r) for r in result]

    if mode == "all":
        records = history_service.get_all_history(current_user.id, db)
        return [_convert_to_history_item(r) for r in records]
    
    elif mode == "count":
        records = history_service.get_recent_history_limit(current_user.id, limit, db)
        return [_convert_to_history_item(r) for r in records]

    elif mode == "pair":
        # 获取最近的 N 组 (基于所有历史)
        selected_groups = history_service.get_recent_pairs_from_all(current_user.id, limit, db)
        
        # 展平
        result = []
        for group in selected_groups:
            result.extend(group)
            
        return [_convert_to_history_item(r) for r in result]

    return []

@router.post("")
async def chat(
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
    pool = Depends(get_arq_pool)
):
    """
    发送聊天消息 (异步模式)
    """
    try:
        body = await request.json()
        user_input = body.get("message")
        session_id = body.get("session_id")
        
        if not user_input:
            raise HTTPException(status_code=400, detail="Message is required")

        # 0. Session Management (Auto-Session)
        if not session_id:
            # 架构调整：使用统一的 SessionService 管理会话生命周期
            session_id = await session_service.get_active_conversation(str(current_user.id))
            logger.info(f"Chat Router: Using active session {session_id} for user {current_user.id}")
        else:
             # 如果前端显式传递了 session_id，则尝试续期它
             await session_service.touch_conversation(str(current_user.id), session_id)

        await StateService.mark_user_active(current_user.id)

        # 1. 存入数据库 (Pending)
        msg_id = history_service.save_user_message(
            session_id=session_id,
            user_id=current_user.id,
            content=user_input,
            status="pending",
            timestamp=utc_now_naive(),
            db=db
        )

        # Get the message object for response
        user_msg = history_service.get_message_by_id(msg_id, db)
        
        logger.info(f"User message saved with ID {msg_id}, status=pending")

        # 2. 触发 ARQ 任务
        await pool.enqueue_job('chat_task', current_user.id)
        await _publish_stream_event(
            user_id=current_user.id,
            event="chat.queued",
            legacy_type="chat_queued",
            data={
                "user_message_id": msg_id,
                "session_id": session_id,
                "status": "pending",
            },
            user_message_id=msg_id,
            session_id=session_id,
            status="pending",
        )
        
        logger.info(f"Enqueued chat_task for user {current_user.id}")

        return {
            "status": "queued", 
            "message": "Message received and processing started.",
            "data": {
                "user_message_id": msg_id,
                "session_id": session_id,
                "timestamp": naive_utc_to_iso(user_msg.timestamp) if user_msg else naive_utc_to_iso(utc_now_naive())
            }
        }

    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.get("/stream")
async def chat_stream(
    request: Request,
    token: str = Query(...),
    db: Session = Depends(get_db)
):
    """
    SSE 接口：实时推送 AI 回复
    """
    current_user = get_current_user_from_token_param(token, db)
    
    async def event_generator():
        redis = redis_client
        if not redis.enabled:
            await redis.connect()
            
        if not redis.enabled or not redis.redis:
            logger.error("Redis is not available for SSE.")
            yield encode_sse_message(
                build_protocol_event(
                    event="system.error",
                    data={"message": "Redis connection failed"},
                    legacy_type="error",
                    message="Redis connection failed",
                )
            )
            return

        pubsub = redis.redis.pubsub()
        channel = f"chat:stream:{current_user.id}"
        await pubsub.subscribe(channel)
        
        logger.info(f"User {current_user.id} subscribed to SSE channel {channel}")
        
        # Initial mark online
        await StateService.mark_user_online(current_user.id)
        last_heartbeat = time.time()
        yield encode_sse_message(
            build_protocol_event(
                event="system.connected",
                data={
                    "user_id": current_user.id,
                    "channel": channel,
                },
                legacy_type="connected",
                user_id=current_user.id,
                channel=channel,
            ),
            retry_ms=1500,
        )
        
        try:
            while True:
                if await request.is_disconnected():
                    break
                
                # Heartbeat: Refresh online status every 60 seconds
                if time.time() - last_heartbeat > 60:
                    await StateService.mark_user_online(current_user.id)
                    last_heartbeat = time.time()
                    yield ": keepalive\n\n"
                    
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message:
                    try:
                        payload = decode_pubsub_payload(message["data"])
                    except Exception as parse_error:
                        logger.error(
                            "Failed to decode SSE payload from Redis",
                            error=str(parse_error),
                            user_id=current_user.id,
                        )
                        payload = build_protocol_event(
                            event="system.payload_error",
                            data={"message": str(parse_error)},
                            legacy_type="error",
                            message="Invalid SSE payload received from Redis",
                        )
                    yield encode_sse_message(payload)
                
        except asyncio.CancelledError:
            logger.info(f"SSE connection cancelled for user {current_user.id}")
        except Exception as e:
            logger.error(f"SSE Error: {e}")
            yield encode_sse_message(
                build_protocol_event(
                    event="system.error",
                    data={"message": f"Internal SSE Error: {str(e)}"},
                    legacy_type="error",
                    message=f"Internal SSE Error: {str(e)}",
                )
            )
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
            await StateService.mark_user_offline(current_user.id)
            logger.info(f"User {current_user.id} unsubscribed from SSE")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
