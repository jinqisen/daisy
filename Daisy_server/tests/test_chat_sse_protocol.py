import asyncio
import json
import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.sse import build_protocol_event, decode_pubsub_payload, encode_sse_message
from app.models import ChatHistoryDB, UserDB
from app.models.base import Base
from app.tasks import chat_task as chat_task_module


def test_sse_protocol_helpers_roundtrip():
    payload = build_protocol_event(
        event="chat.completed",
        data={"user_message_id": 42, "response": "你好"},
        sequence=3,
        event_id="42:3",
        legacy_type="chat_response",
        response="你好",
    )

    encoded = encode_sse_message(payload, retry_ms=1500)

    assert "event: message" in encoded
    assert "id: 42:3" in encoded
    assert "retry: 1500" in encoded

    data_line = next(line for line in encoded.splitlines() if line.startswith("data: "))
    decoded = decode_pubsub_payload(data_line.removeprefix("data: "))
    assert decoded["event"] == "chat.completed"
    assert decoded["data"]["user_message_id"] == 42
    assert decoded["response"] == "你好"


def test_chat_task_processes_pending_messages_one_by_one(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as session:
        session.add(UserDB(username="tester", hashed_password="x", is_active=True))
        session.flush()
        user_id = session.query(UserDB).filter(UserDB.username == "tester").first().id
        session.add_all(
            [
                ChatHistoryDB(user_id=user_id, role="user", content="第一条", status="pending", session_id="s1"),
                ChatHistoryDB(user_id=user_id, role="user", content="第二条", status="pending", session_id="s1"),
            ]
        )
        session.commit()

    seen_inputs: list[str] = []

    class FakeGraph:
        async def ainvoke(self, state):
            seen_inputs.append(state["user_input"])
            return {
                "response": f"回复:{state['user_input']}",
                "response_parts": [f"回复:{state['user_input']}"],
                "selected_personality": "Default",
                "engagement_score": 0.8,
                "workflow_trace": {"save": {"output": "ok"}},
                "ai_message_id": state["user_message_id"] + 1000,
                "execution_id": f"exec-{state['user_message_id']}",
            }

    class FakeRedisConnection:
        def __init__(self):
            self.locked = False
            self.published: list[tuple[str, dict]] = []

        async def set(self, _key, _value, nx=True, ex=600):
            _ = ex
            if nx and self.locked:
                return False
            self.locked = True
            return True

        async def expire(self, _key, _seconds):
            return True

        async def publish(self, channel, payload):
            self.published.append((channel, json.loads(payload)))
            return 1

        async def delete(self, _key):
            self.locked = False
            return 1

    class FakeRedisClient:
        def __init__(self):
            self.enabled = True
            self.redis = FakeRedisConnection()

        async def connect(self):
            self.enabled = True

    fake_redis = FakeRedisClient()

    monkeypatch.setattr(chat_task_module, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(chat_task_module, "app_graph", FakeGraph())
    monkeypatch.setattr(chat_task_module, "redis_client", fake_redis)

    result = asyncio.run(chat_task_module.chat_task({}, user_id))

    assert result == "ok"
    assert seen_inputs == ["第一条", "第二条"]

    with TestingSessionLocal() as session:
        stored = session.query(ChatHistoryDB).filter(ChatHistoryDB.user_id == user_id).order_by(ChatHistoryDB.id.asc()).all()
        assert [item.status for item in stored] == ["completed", "completed"]

    published_events = [payload["event"] for _, payload in fake_redis.redis.published]
    assert published_events == [
        "chat.started",
        "chat.delta",
        "chat.completed",
        "chat.started",
        "chat.delta",
        "chat.completed",
    ]

    published_types = [payload.get("type") for _, payload in fake_redis.redis.published]
    assert published_types == [
        "chat_started",
        "chat_delta",
        "chat_completed",
        "chat_started",
        "chat_delta",
        "chat_completed",
    ]

    sequence_numbers = [payload.get("sequence") for _, payload in fake_redis.redis.published]
    assert sequence_numbers == [1, 2, 3, 1, 2, 3]

    event_ids = [payload.get("event_id") for _, payload in fake_redis.redis.published]
    assert event_ids == ["1:1", "1:2", "1:3", "2:1", "2:2", "2:3"]

    completed_payloads = [payload for _, payload in fake_redis.redis.published if payload["event"] == "chat.completed"]
    assert [payload["response"] for payload in completed_payloads] == ["回复:第一条", "回复:第二条"]
    assert [payload["data"]["response"] for payload in completed_payloads] == ["回复:第一条", "回复:第二条"]
