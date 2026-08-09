"""
(context, action, reward) 数据管线测试。

核心约束:**只记录,不改变线上行为**。任何记录失败都不得影响对话。
"""

import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.services.learning.rl_dataset import ACTION_SPACE, build_context_vector


@pytest.fixture
def db_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/rl.db")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


class TestContextVector:

    def test_low_dimensional(self):
        """
        单用户桌面场景样本稀疏(数百量级),context 维度必须远小于样本数,
        否则必然过拟合。刻意不用原始 28 维 GoEmotions。
        """
        ctx = build_context_vector({
            "ekman_scores": {"joy": .1, "sadness": .7, "anger": 0, "fear": .1,
                             "surprise": 0, "neutral": .1},
            "engagement_score": 72,
            "relationship_stage": "trust",
        })
        assert len(ctx) <= 10, f"context 维度 {len(ctx)} 过高,小样本下会过拟合"

    def test_engagement_normalized(self):
        ctx = build_context_vector({"engagement_score": 80, "ekman_scores": {}})
        assert 0.0 <= ctx["engagement"] <= 1.0

    def test_relationship_stage_encoded(self):
        a = build_context_vector({"relationship_stage": "acquaintance", "ekman_scores": {}})
        b = build_context_vector({"relationship_stage": "bond", "ekman_scores": {}})
        assert a["relationship"] != b["relationship"], "关系阶段未编码进 context"

    def test_handles_missing_fields(self):
        """状态字段缺失时不得抛异常(否则会中断对话)。"""
        ctx = build_context_vector({})
        assert isinstance(ctx, dict)


class TestPipeline:

    def _run(self, db_factory, monkeypatch, coro_fn):
        import app.core.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", db_factory)

        async def _main():
            from app.core.cache import redis_client
            from app.core.config import settings
            monkeypatch.setattr(settings, "EMBEDDED_MODE", True)
            await redis_client.connect()
            return await coro_fn()

        return asyncio.run(_main())

    def test_decision_reward_pairing(self, db_factory, monkeypatch):
        from app.models import RLSampleDB
        from app.services.learning.rl_dataset import record_decision, record_reward

        async def flow():
            await record_decision("s1", 1, {"emo_joy": 0.9}, "Ludus",
                                  {"Ludus": 0.7}, policy="llm")
            return await record_reward("s1", 0.85, True, {"Q_I": 0.9})

        assert self._run(db_factory, monkeypatch, flow) is True

        with db_factory() as s:
            rows = s.query(RLSampleDB).all()
            assert len(rows) == 1
            assert rows[0].action == "Ludus"
            assert rows[0].reward == pytest.approx(0.85)
            assert rows[0].policy == "llm", "必须记录产生数据的策略(离线评估需要)"

    def test_reward_without_decision_is_noop(self, db_factory, monkeypatch):
        """首轮或过期时没有暂存决策 —— 应安静返回 False,不得报错。"""
        from app.services.learning.rl_dataset import record_reward

        async def flow():
            return await record_reward("never-seen", 0.5)

        assert self._run(db_factory, monkeypatch, flow) is False

    def test_recording_failure_does_not_raise(self, monkeypatch):
        """
        记录失败绝不能影响对话主流程 —— 这是"只记录不干预"原则的底线。
        """
        from app.services.learning.rl_dataset import record_decision

        async def flow():
            # 未连接 Redis / 传入异常 session,均应被内部吞掉
            await record_decision("", 1, {}, "Storge")
            return "ok"

        assert asyncio.run(flow()) == "ok"


def test_action_space_matches_configured_dim():
    """动作空间需与 RL_ACTION_DIM 一致,否则模型输出无法映射到人格。"""
    from app.core.constants import RL_ACTION_DIM
    assert len(ACTION_SPACE) == RL_ACTION_DIM


def test_export_script_exists():
    from pathlib import Path
    assert (Path(__file__).resolve().parent.parent / "scripts" / "export_rl_dataset.py").exists()
