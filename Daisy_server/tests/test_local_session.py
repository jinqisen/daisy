"""
桌面版免登录(本地会话)测试。

背景:原 /register 有白名单校验 —— 用户名不在 whitelist.json 即 403,
真实用户装了桌面版根本注册不了(这是"伪 C 端"的关键症状)。
本应用数据完全在用户本机,不存在服务端,不应要求注册/登录。

锁定:
  1. 嵌入模式下 /auth/local_session 自动建号并签发令牌(打开即用);
  2. 幂等 —— 反复调用复用同一本地用户,不会越建越多;
  3. 本地用户即拥有者(is_superuser),能看到设置页;
  4. server 部署模式下该端点必须不可用,避免绕过正常认证。
"""

import pytest
from fastapi import BackgroundTasks
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import auth as auth_module
from app.core.config import settings
from app.models import UserDB
from app.models.base import Base


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    with Session() as s:
        yield s


@pytest.fixture
def embedded(monkeypatch):
    monkeypatch.setattr(settings, "EMBEDDED_MODE", True)


@pytest.fixture
def no_card_gen(monkeypatch):
    """避免测试触发真实的角色卡后台生成。"""
    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(auth_module, "generate_card_background", _noop)


def test_local_session_creates_user_and_returns_token(db_session, embedded, no_card_gen):
    res = auth_module.local_session(BackgroundTasks(), db=db_session)
    assert res["access_token"]
    assert res["is_superuser"] is True, "本机用户即拥有者,应能访问设置页"

    users = db_session.query(UserDB).all()
    assert len(users) == 1
    assert users[0].username == auth_module.LOCAL_USER_NAME


def test_local_session_is_idempotent(db_session, embedded, no_card_gen):
    """反复打开应用不应不断创建新用户。"""
    for _ in range(3):
        auth_module.local_session(BackgroundTasks(), db=db_session)
    assert db_session.query(UserDB).count() == 1


def test_local_session_disabled_in_server_mode(db_session, monkeypatch, no_card_gen):
    """server 部署不得通过该端点绕过认证。"""
    monkeypatch.setattr(settings, "EMBEDDED_MODE", False)
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        auth_module.local_session(BackgroundTasks(), db=db_session)
    assert exc.value.status_code == 404
    assert db_session.query(UserDB).count() == 0


def test_existing_local_user_promoted_to_owner(db_session, embedded, no_card_gen, monkeypatch):
    """兼容早期版本创建的非 superuser 本地用户。"""
    from app.core import security
    db_session.add(UserDB(
        username=auth_module.LOCAL_USER_NAME,
        hashed_password=security.get_password_hash("x"),
        is_active=True,
        is_superuser=False,
    ))
    db_session.commit()

    res = auth_module.local_session(BackgroundTasks(), db=db_session)
    assert res["is_superuser"] is True
    assert db_session.query(UserDB).count() == 1
