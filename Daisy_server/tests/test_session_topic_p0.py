import json
import os
import sys
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models.base import Base
from app.models.chat import ChatHistoryDB
from app.core.time_utils import utc_now_naive
import app.services.system.session as session_service_module

from app.services.memory.chat_history import ChatHistoryService
from app.services.system.session import SessionService


def _make_test_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal


def test_chat_history_filters_by_session_and_message_id():
    testing_session_local = _make_test_session()
    service = ChatHistoryService()
    now = utc_now_naive()

    with testing_session_local() as db:
        db.add_all(
            [
                ChatHistoryDB(user_id=1, session_id="session-a", role="user", content="u1", timestamp=now - timedelta(minutes=4)),
                ChatHistoryDB(user_id=1, session_id="session-a", role="ai", content="a1", timestamp=now - timedelta(minutes=3)),
                ChatHistoryDB(user_id=1, session_id="session-b", role="user", content="u2", timestamp=now - timedelta(minutes=2)),
                ChatHistoryDB(user_id=1, session_id="session-a", role="user", content="u3", timestamp=now - timedelta(minutes=1)),
            ]
        )
        db.commit()

        latest_session_a = service.get_recent_history_limit(
            1,
            limit=2,
            db=db,
            session_id="session-a",
        )
        assert [msg.content for msg in latest_session_a] == ["a1", "u3"]

        after_first = service.get_session_history_after_message(
            1,
            "session-a",
            after_message_id=latest_session_a[0].id - 1,
            db=db,
        )
        assert [msg.content for msg in after_first] == ["a1", "u3"]


@pytest.mark.asyncio
async def test_session_service_start_new_conversation_archives_previous(monkeypatch):
    storage: dict[str, str] = {}

    async def fake_get(key: str):
        return storage.get(key)

    async def fake_set(key: str, value, ttl=None):
        _ = ttl
        storage[key] = value

    async def fake_delete(key: str):
        storage.pop(key, None)

    monkeypatch.setattr(session_service_module.redis_client, "get", fake_get)
    monkeypatch.setattr(session_service_module.redis_client, "set", fake_set)
    monkeypatch.setattr(session_service_module.redis_client, "delete", fake_delete)

    service = SessionService()

    async def fake_last_session_from_db(_user_id: str):
        return None, None

    monkeypatch.setattr(service, "_get_last_session_from_db", fake_last_session_from_db)

    first_session_id = await service.get_active_conversation("1")
    first_meta = json.loads(storage[service._meta_key(first_session_id)])
    assert storage[service._active_key("1")] == first_session_id
    assert first_meta["status"] == "active"

    result = await service.start_new_conversation("1", end_current=True)
    second_session_id = result["session_id"]

    archived_meta = json.loads(storage[service._meta_key(first_session_id)])
    active_meta = json.loads(storage[service._meta_key(second_session_id)])

    assert result["previous_session_id"] == first_session_id
    assert storage[service._active_key("1")] == second_session_id
    assert archived_meta["status"] == "archived"
    assert archived_meta["ended_reason"] == "manual_boundary"
    assert active_meta["status"] == "active"
