"""
用户头像字段 + 老库自动补列的回归。

背景:界面上原先只有「角色头像」(AI 的),用户自己的气泡头像写死成绿底小人,
没有任何自定义入口 —— 用户反馈"换头像功能遗漏"指的就是这个。

新增 user_avatar_path 字段带出一个更要命的问题:项目没有 Alembic,
create_all 只建**不存在的表**,不会给已存在的表加列。桌面版升级安装会保留用户的
sqlite.db —— 老库缺这一列,第一次查询就 "no such column",且没有自愈路径。
"""

import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.agents.daisy.config import CommonSettings
from app.models.user import CommonSettingsDB


class TestUserAvatarField:

    def test_model_has_separate_user_avatar(self):
        """两个头像必须是独立字段 —— 复用同一个会导致改了 AI 头像连带改掉自己的。"""
        cols = {c.name for c in CommonSettingsDB.__table__.columns}
        assert "avatar_path" in cols
        assert "user_avatar_path" in cols

    def test_schema_exposes_user_avatar(self):
        """接口 schema 必须带上,否则前端存了也读不回来。"""
        assert "user_avatar_path" in CommonSettings.model_fields

    def test_user_avatar_defaults_to_none(self):
        assert CommonSettings(name="x").user_avatar_path is None

    def test_config_route_maps_both_avatars(self):
        """读写两端都要映射 —— 只加字段不接线是最常见的漏法。"""
        import inspect as _inspect
        from app.api.routers import config as config_router

        read = _inspect.getsource(config_router.get_common_settings)
        write = _inspect.getsource(config_router.update_common_settings)
        assert "user_avatar_path" in read, "读接口未返回用户头像"
        assert "user_avatar_path" in write, "写接口未保存用户头像"


class TestAdditiveMigration:
    """老库必须能被自动补列,否则升级安装即崩。"""

    def _legacy_db(self, tmp_path):
        """造一个缺 user_avatar_path 的老库。"""
        db = tmp_path / "legacy.db"
        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE common_settings ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  user_id INTEGER,"
            "  name VARCHAR,"
            "  avatar_path TEXT"
            ")"
        )
        conn.execute(
            "INSERT INTO common_settings (user_id, name, avatar_path) "
            "VALUES (1, '静雯', '/static/uploads/avatars/a.png')"
        )
        conn.commit()
        conn.close()
        return db

    def test_missing_column_is_added(self, tmp_path, monkeypatch):
        db = self._legacy_db(tmp_path)
        engine = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})

        from app.services.system import schema_bootstrap as db_mod
        monkeypatch.setattr(db_mod, "engine", engine)

        before = {c["name"] for c in inspect(engine).get_columns("common_settings")}
        assert "user_avatar_path" not in before, "前置条件不成立:老库不该有这一列"

        db_mod._add_missing_columns()

        after = {c["name"] for c in inspect(engine).get_columns("common_settings")}
        assert "user_avatar_path" in after, \
            "老库未补上新列 —— 升级安装后第一次查询就会 no such column"

    def test_existing_rows_survive(self, tmp_path, monkeypatch):
        """补列不能丢数据:用户的角色头像、名字都得在。"""
        db = self._legacy_db(tmp_path)
        engine = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})

        from app.services.system import schema_bootstrap as db_mod
        monkeypatch.setattr(db_mod, "engine", engine)
        db_mod._add_missing_columns()

        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT name, avatar_path, user_avatar_path FROM common_settings WHERE user_id=1"
            )).fetchone()
        assert row[0] == "静雯"
        assert row[1] == "/static/uploads/avatars/a.png"
        assert row[2] is None, "新列对老数据应为空,而不是被塞进旧值"

    def test_is_idempotent(self, tmp_path, monkeypatch):
        """重复启动会反复调用,第二次不得报 duplicate column。"""
        db = self._legacy_db(tmp_path)
        engine = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})

        from app.services.system import schema_bootstrap as db_mod
        monkeypatch.setattr(db_mod, "engine", engine)
        db_mod._add_missing_columns()
        db_mod._add_missing_columns()  # 不抛异常即通过

    def test_ignores_tables_that_do_not_exist_yet(self, tmp_path, monkeypatch):
        """全新库由 create_all 建好,补列逻辑不该对不存在的表做任何事。"""
        db = tmp_path / "fresh.db"
        engine = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})

        from app.services.system import schema_bootstrap as db_mod
        monkeypatch.setattr(db_mod, "engine", engine)
        db_mod._add_missing_columns()  # 空库,不抛异常即通过


class TestUserAvatarRoundTrip:
    """字段要能真正存进去再读出来。"""

    def test_persists_through_db(self, tmp_path):
        from app.models.base import Base

        engine = create_engine(f"sqlite:///{tmp_path/'t.db'}",
                               connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)

        with Session() as s:
            s.add(CommonSettingsDB(
                user_id=1, name="静雯",
                avatar_path="/static/uploads/avatars/ai.png",
                user_avatar_path="/static/uploads/avatars/me.png",
            ))
            s.commit()

        with Session() as s:
            row = s.query(CommonSettingsDB).filter_by(user_id=1).first()
            assert row.user_avatar_path == "/static/uploads/avatars/me.png"
            assert row.avatar_path == "/static/uploads/avatars/ai.png"
