"""
首次运行的角色卡流程测试。

设计要点(前端用 has_character_card 做全屏门禁):
  1. 未配置 LLM  → 不写卡,让前端显示"配置模型"引导(而非无限加载);
  2. 已配置 LLM  → 立即写入默认卡解除门禁,用户马上可用;
  3. 深度角色卡在后台异步升级,慢/失败/超时都不影响用户。

第 2、3 条是关键:深度生成是一次大 Prompt 的慢 LLM 调用(实测会挂住),
若让门禁等它,用户首次打开会长时间面对加载动画。
"""

import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import auth as auth_module
from app.models import CommonSettingsDB, UserDB
from app.models.base import Base


@pytest.fixture
def db_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def _seed_user(Session) -> int:
    with Session() as s:
        s.add(UserDB(username="newbie", hashed_password="x", is_active=True))
        s.flush()
        uid = s.query(UserDB).filter(UserDB.username == "newbie").first().id
        s.add(CommonSettingsDB(user_id=uid, name="Daisy"))
        s.commit()
        return uid


def _card_json(Session, uid):
    with Session() as s:
        row = s.query(CommonSettingsDB).filter(CommonSettingsDB.user_id == uid).first()
        return row.character_card_json


@pytest.fixture
def configured_llm(monkeypatch):
    """模拟已配置 LLM 密钥。"""
    monkeypatch.setattr(auth_module, "generate_deep_character_card", None, raising=False)
    import app.core.llm_config as llm_config
    monkeypatch.setattr(llm_config, "is_any_llm_configured", lambda: True)


@pytest.fixture
def unconfigured_llm(monkeypatch):
    import app.core.llm_config as llm_config
    monkeypatch.setattr(llm_config, "is_any_llm_configured", lambda: False)


def test_no_card_written_when_llm_unconfigured(db_factory, monkeypatch, unconfigured_llm):
    """
    未配置 LLM 时必须保持 character_card_json 为空 ——
    前端据此显示配置引导。若此时静默塞默认卡,用户会进入聊天后才发现发不出消息。
    """
    uid = _seed_user(db_factory)
    monkeypatch.setattr(auth_module, "SessionLocal", db_factory)

    called = {"deep": False}

    async def _should_not_run(*a, **k):
        called["deep"] = True
        return None
    monkeypatch.setattr(auth_module, "generate_deep_character_card", _should_not_run)

    asyncio.run(auth_module.generate_card_background(uid))

    assert not _card_json(db_factory, uid), "未配置 LLM 时不应写入任何角色卡"
    assert not called["deep"], "未配置 LLM 时不应发起深度生成(必然失败且浪费时间)"


def test_default_card_applied_immediately_when_configured(db_factory, monkeypatch, configured_llm):
    """
    已配置 LLM:即使深度生成很慢/失败,也必须先落默认卡解除门禁。
    这里让深度生成直接失败,验证用户仍拿到可用角色卡。
    """
    uid = _seed_user(db_factory)
    monkeypatch.setattr(auth_module, "SessionLocal", db_factory)

    async def _fail(*a, **k):
        return None
    monkeypatch.setattr(auth_module, "generate_deep_character_card", _fail)

    asyncio.run(auth_module.generate_card_background(uid))

    assert _card_json(db_factory, uid), (
        "已配置 LLM 时深度生成失败,仍应保留默认卡 —— 否则前端门禁永久阻塞"
    )


def test_slow_deep_generation_does_not_block(db_factory, monkeypatch, configured_llm):
    """深度生成超时不应影响用户:默认卡已生效,任务正常收尾。"""
    uid = _seed_user(db_factory)
    monkeypatch.setattr(auth_module, "SessionLocal", db_factory)
    monkeypatch.setattr(auth_module.settings, "DEEP_CARD_TIMEOUT_SEC", 1)

    async def _hang(*a, **k):
        await asyncio.sleep(30)  # 模拟挂住的 LLM 调用
        return None
    monkeypatch.setattr(auth_module, "generate_deep_character_card", _hang)

    # 不应抛异常,且应在超时上限附近返回
    asyncio.run(auth_module.generate_card_background(uid))
    assert _card_json(db_factory, uid), "超时后仍应保留默认卡"


def test_deep_card_upgrades_default(db_factory, monkeypatch, configured_llm):
    """深度生成成功时应覆盖默认卡(静默升级为更丰富的人格)。"""
    uid = _seed_user(db_factory)
    monkeypatch.setattr(auth_module, "SessionLocal", db_factory)

    class FakeCard:
        def model_dump(self):
            return {"name": "DeepPersona", "marker": "from-llm"}

    async def _ok(*a, **k):
        return FakeCard()
    monkeypatch.setattr(auth_module, "generate_deep_character_card", _ok)

    asyncio.run(auth_module.generate_card_background(uid))
    assert _card_json(db_factory, uid).get("marker") == "from-llm"


def test_default_card_loads_regardless_of_cwd(tmp_path, monkeypatch):
    """
    默认卡路径写的是相对 cwd 的 "./Daisy_server/assets/..." —— 只有从仓库根目录
    启动才成立。从 Daisy_server/ 启动或打包成冻结程序(cwd 不确定)时会找不到,
    表现为 "CRITICAL: Failed to load any character card"。
    """
    import os
    from app.services.persona.character_card import load_default_character_card

    monkeypatch.chdir(tmp_path)  # 一个绝无该资源的目录
    assert load_default_character_card() is not None, \
        "换个工作目录就加载不到默认角色卡 —— 打包版会直接卡在角色卡生成"
