import json
import uuid
import structlog
from typing import Any, Optional

from ..core.sse import build_protocol_event
from ..core.database import SessionLocal
from ..core.redis import redis_client
from ..core.utils import split_response_into_parts
from ..models import ChatHistoryDB
from ..workflow.graph import app_graph

logger = structlog.get_logger()


async def _publish_stream_event(
    *,
    user_id: int,
    event: str,
    data: dict[str, Any],
    sequence: Optional[int] = None,
    legacy_type: Optional[str] = None,
    **legacy_fields: Any,
) -> None:
    redis = redis_client
    if not redis.enabled or not redis.redis:
        return

    user_message_id = data.get("user_message_id")
    event_id = (
        f"{user_message_id}:{sequence}"
        if user_message_id is not None and sequence is not None
        else str(uuid.uuid4())
    )
    payload = build_protocol_event(
        event=event,
        data=data,
        sequence=sequence,
        event_id=event_id,
        legacy_type=legacy_type,
        **legacy_fields,
    )
    await redis.redis.publish(
        f"chat:stream:{user_id}",
        json.dumps(payload, ensure_ascii=False),
    )


async def chat_task(_ctx, user_id: int):
    """
    聊天任务：处理用户的 Pending 消息
    
    流程：
    1. 获取 Redis 分布式锁 (确保同一用户串行处理)
    2. 循环：
       a. 从 DB 获取该用户所有 status='pending' 的消息
       b. 如果无消息 -> 退出
       c. 合并消息内容
       d. 调用 Workflow 生成回复
       e. 事务提交：保存 AI 回复 + 更新 User 消息状态 -> 'completed'
       f. 推送 SSE 通知
    """
    lock_key = f"lock:user:{user_id}"
    
    redis = redis_client
    if not redis.enabled:
        await redis.connect()
        
    # 1. 获取锁
    # NX=True (Not Exist), EX=600 (10分钟过期 - 任务超时时间应大于此或自动续期)
    acquired = await redis.redis.set(lock_key, "1", nx=True, ex=600)
    if not acquired:
        logger.info(f"User {user_id} is busy. Skipping this job (active task will handle pending msgs).")
        return "skipped_busy"
        
    try:
        # 2. 循环处理直到没有 pending 消息
        while True:
            pending_msg: Optional[dict[str, Any]] = None
            sequence = 0
            try:
                with SessionLocal() as db:
                    next_msg = db.query(ChatHistoryDB).filter(
                        ChatHistoryDB.user_id == user_id,
                        ChatHistoryDB.status == "pending",
                    ).order_by(ChatHistoryDB.timestamp.asc(), ChatHistoryDB.id.asc()).first()

                    if not next_msg:
                        logger.info(f"No more pending messages for user {user_id}. Task finishing.")
                        break

                    pending_msg = {
                        "id": next_msg.id,
                        "content": next_msg.content,
                        "session_id": getattr(next_msg, "session_id", "default") or "default",
                    }

                    db.query(ChatHistoryDB).filter(
                        ChatHistoryDB.id == next_msg.id,
                    ).update(
                        {"status": "processing"},
                        synchronize_session=False,
                    )
                    db.commit()

                logger.info(
                    "Processing single pending message",
                    user_id=user_id,
                    user_message_id=pending_msg["id"],
                    session_id=pending_msg["session_id"],
                    content_length=len(pending_msg["content"]),
                )

                sequence += 1
                await _publish_stream_event(
                    user_id=user_id,
                    event="chat.started",
                    legacy_type="chat_started",
                    sequence=sequence,
                    data={
                        "user_message_id": pending_msg["id"],
                        "session_id": pending_msg["session_id"],
                        "status": "processing",
                    },
                    user_message_id=pending_msg["id"],
                    session_id=pending_msg["session_id"],
                    status="processing",
                )

                input_state = {
                    "user_input": pending_msg["content"],
                    "user_id": user_id,
                    "user_message_id": pending_msg["id"],
                    "session_id": pending_msg["session_id"],
                }

                await redis.redis.expire(lock_key, 600)
                result = await app_graph.ainvoke(input_state)
                ai_response_text = result.get("response", "")
                response_parts = result.get("response_parts") or split_response_into_parts(ai_response_text)
                emotion_analysis = {
                    "top": result.get("top_emotions", []),
                    "scores": result.get("emotion_scores", {}),
                    "ekman": result.get("ekman_scores", {}),
                }
                ai_message_id = result.get("ai_message_id")
                execution_id = result.get("execution_id")

                ai_response_data = {
                    "user_input": pending_msg["content"],
                    "response": ai_response_text,
                    "response_parts": response_parts,
                    "emotion_analysis": emotion_analysis,
                    "personality": result.get("selected_personality", "Default"),
                    "engagement_score": result.get("engagement_score", 0.5),
                    "workflow_trace": result.get("workflow_trace"),
                    "user_message_id": pending_msg["id"],
                    "ai_message_id": ai_message_id,
                    "session_id": pending_msg["session_id"],
                    "execution_id": execution_id,
                }

                with SessionLocal() as db:
                    db.query(ChatHistoryDB).filter(
                        ChatHistoryDB.id == pending_msg["id"],
                    ).update(
                        {"status": "completed"},
                        synchronize_session=False,
                    )
                    db.commit()

                for index, part in enumerate(response_parts, start=1):
                    sequence += 1
                    await _publish_stream_event(
                        user_id=user_id,
                        event="chat.delta",
                        legacy_type="chat_delta",
                        sequence=sequence,
                        data={
                            "user_message_id": pending_msg["id"],
                            "session_id": pending_msg["session_id"],
                            "ai_message_id": ai_message_id,
                            "execution_id": execution_id,
                            "part_index": index - 1,
                            "part_total": len(response_parts),
                            "delta": part,
                        },
                        user_message_id=pending_msg["id"],
                        session_id=pending_msg["session_id"],
                        ai_message_id=ai_message_id,
                        execution_id=execution_id,
                        part_index=index - 1,
                        part_total=len(response_parts),
                        delta=part,
                    )

                if ai_response_text or response_parts:
                    sequence += 1
                    await _publish_stream_event(
                        user_id=user_id,
                        event="chat.completed",
                        legacy_type="chat_completed",
                        sequence=sequence,
                        data=ai_response_data,
                        **ai_response_data,
                    )
                else:
                    # 生成被跳过(如并行分支依赖缺失,_skip_generation)时图会无响应结束。
                    # 必须向前端发布显式错误,否则用户侧表现为"静默无回复+一直转圈"。
                    logger.warning(
                        "Workflow returned empty response (skipped generation?)",
                        user_id=user_id,
                        user_message_id=pending_msg["id"],
                        skip_flag=result.get("_skip_generation"),
                    )
                    with SessionLocal() as db:
                        db.query(ChatHistoryDB).filter(
                            ChatHistoryDB.id == pending_msg["id"],
                        ).update({"status": "failed"}, synchronize_session=False)
                        db.commit()
                    sequence += 1
                    empty_payload = {
                        "message": "生成流程被跳过,未产生回复,请重试",
                        "node": "Generation",
                        "user_message_id": pending_msg["id"],
                        "session_id": pending_msg["session_id"],
                    }
                    await _publish_stream_event(
                        user_id=user_id,
                        event="chat.error",
                        legacy_type="error",
                        sequence=sequence,
                        data=empty_payload,
                        **empty_payload,
                    )

                logger.info(
                    "Single pending message finished",
                    user_id=user_id,
                    user_message_id=pending_msg["id"],
                    ai_message_id=ai_message_id,
                )
            except Exception as e:
                logger.error("Error in chat_task loop", error=str(e), user_id=user_id, exc_info=True)
                
                # 1. Update DB status to failed
                if pending_msg:
                    try:
                        with SessionLocal() as db:
                            db.query(ChatHistoryDB).filter(
                                ChatHistoryDB.id == pending_msg["id"],
                            ).update(
                                {"status": "failed"},
                                synchronize_session=False,
                            )
                            db.commit()
                    except Exception as db_err:
                        logger.error(f"Failed to update message status to failed: {db_err}")

                # 2. Publish error event to frontend
                try:
                    sequence += 1
                    error_payload = {
                        "message": str(e),
                        "node": getattr(e, "node_name", "Unknown Node"),
                        "user_message_id": pending_msg["id"] if pending_msg else None,
                        "session_id": pending_msg["session_id"] if pending_msg else None,
                    }
                    await _publish_stream_event(
                        user_id=user_id,
                        event="chat.error",
                        legacy_type="error",
                        sequence=sequence,
                        data=error_payload,
                        **error_payload,
                    )
                except Exception as pub_err:
                    logger.error(f"Failed to publish error event: {pub_err}")

                break
                
    finally:
        # 3. 释放锁
        await redis.redis.delete(lock_key)
        logger.info(f"Task lock released for user {user_id}")
        
    return "ok"
