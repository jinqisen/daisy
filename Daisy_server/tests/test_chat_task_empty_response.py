"""
chat_task 空回复可见性测试(F1:消除「生成被跳过→前端静默转圈」)。

当工作流返回空 response(如 _skip_generation 跳过生成),chat_task 必须:
1. 把用户消息状态置为 failed(而非 completed);
2. 向前端发布 chat.error 事件,而不是什么都不发。
"""

import asyncio
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import ChatHistoryDB, UserDB
from app.models.base import Base
from app.tasks import chat_task as chat_task_module


def test_empty_response_publishes_error_and_marks_failed(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as session:
        session.add(UserDB(username="tester", hashed_password="x", is_active=True))
        session.flush()
        user_id = session.query(UserDB).filter(UserDB.username == "tester").first().id
        session.add(ChatHistoryDB(user_id=user_id, role="user", content="触发跳过", status="pending", session_id="s1"))
        session.commit()

    class SkippingGraph:
        async def ainvoke(self, state):
            # 模拟 generate 因依赖缺失跳过:无 response、带跳过标志
            return {"response": "", "response_parts": [], "_skip_generation": True}

    class FakeRedisConnection:
        def __init__(self):
            self.locked = False
            self.published = []

        async def set(self, _key, _value, nx=True, ex=600):
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
    monkeypatch.setattr(chat_task_module, "app_graph", SkippingGraph())
    monkeypatch.setattr(chat_task_module, "redis_client", fake_redis)

    asyncio.run(chat_task_module.chat_task({}, user_id))

    events = [payload["event"] for _, payload in fake_redis.redis.published]
    assert events == ["chat.started", "chat.error"], f"实际事件: {events}"

    error_payload = fake_redis.redis.published[-1][1]
    assert error_payload.get("type") == "error"  # 前端按 legacy type 分支处理

    with TestingSessionLocal() as session:
        msg = session.query(ChatHistoryDB).filter(ChatHistoryDB.user_id == user_id).first()
        assert msg.status == "failed"
