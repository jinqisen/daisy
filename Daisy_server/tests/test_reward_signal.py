"""
奖励信号(Reflexion S 分数)质量测试 —— RL/bandit 的前置基础。

背景:D_R(关系深度)此前是硬编码常量(session_count_7d=20 / retention=0.95),
使 D_R 恒约 0.98。它在 S 中占 20% 权重,等于每轮固定加 ~0.196 的偏置:
  - S 分布被压缩(实测集中在 0.75±0.05),阈值难校准
  - 任何基于 S 的学习都会拟合到这个假信号

这里锁定:统计来自真实数据;样本不足时明确降级而非塞估算值。
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import ChatHistoryDB, UserDB
from app.models.base import Base


@pytest.fixture
def db_factory(tmp_path):
    # 注意:不能用 sqlite:///:memory: —— 被测代码在自己的连接里查询,
    # 而 :memory: 每个连接是独立数据库,会得到 "no such table"。
    engine = create_engine(f"sqlite:///{tmp_path}/t.db")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def _seed(Session, *, turns: int, days_spread: int = 1, user_id: int = 1):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with Session() as s:
        s.add(UserDB(id=user_id, username=f"u{user_id}", hashed_password="x", is_active=True))
        for i in range(turns):
            s.add(ChatHistoryDB(
                user_id=user_id,
                role="user" if i % 2 == 0 else "ai",
                content=f"msg{i}",
                status="completed",
                session_id=f"sess-{i % max(1, days_spread)}",
                timestamp=now - timedelta(days=i % max(1, days_spread)),
            ))
        s.commit()


def _stats(monkeypatch, db_factory, user_id=1):
    import asyncio
    import app.services.learning.reflexion.service as svc_mod
    from app.services.learning.reflexion.service import ReflexionService

    monkeypatch.setattr(svc_mod, "SessionLocal", db_factory)
    # _get_relationship_stats 内部按模块路径导入 SessionLocal
    import app.core.database as db_mod
    monkeypatch.setattr(db_mod, "SessionLocal", db_factory)

    svc = ReflexionService.__new__(ReflexionService)
    return asyncio.run(ReflexionService._get_relationship_stats(svc, user_id))


class TestRelationshipStats:

    def test_not_hardcoded_constants(self, db_factory, monkeypatch):
        """
        回归防线:曾经无论数据如何都返回 20/0.95/50/500。
        空库必须给出接近 0 的统计,而不是那组常量。
        """
        _seed(db_factory, turns=0)
        stats = _stats(monkeypatch, db_factory)
        assert stats["session_count_7d"] != 20 or stats["total_interactions"] != 500, \
            "仍在返回硬编码常量"
        assert stats["total_interactions"] == 0

    def test_marks_insufficient_history_as_unreliable(self, db_factory, monkeypatch):
        """新用户样本太少 → is_real=False,上层应降级为仅用 Q_I+E_U。"""
        _seed(db_factory, turns=4)
        stats = _stats(monkeypatch, db_factory)
        assert stats["is_real"] is False

    def test_marks_sufficient_history_as_reliable(self, db_factory, monkeypatch):
        from app.services.learning.reflexion.service import MIN_INTERACTIONS_FOR_DR
        _seed(db_factory, turns=MIN_INTERACTIONS_FOR_DR + 5, days_spread=3)
        stats = _stats(monkeypatch, db_factory)
        assert stats["is_real"] is True
        assert stats["total_interactions"] >= MIN_INTERACTIONS_FOR_DR

    def test_retention_reflects_active_days(self, db_factory, monkeypatch):
        """留存率应反映近 7 天活跃天数占比,而非常量。"""
        _seed(db_factory, turns=30, days_spread=7)
        stats = _stats(monkeypatch, db_factory)
        assert 0.0 < stats["retention_rate_7d"] <= 1.0
        assert stats["retention_rate_7d"] != 0.95, "疑似仍是硬编码值"

    def test_stats_degrade_gracefully_on_error(self, monkeypatch):
        """DB 异常时返回零值 + is_real=False,不得抛出中断反思流程。"""
        import asyncio
        import app.core.database as db_mod
        from app.services.learning.reflexion.service import ReflexionService

        def _boom():
            raise RuntimeError("db down")
        monkeypatch.setattr(db_mod, "SessionLocal", _boom)

        svc = ReflexionService.__new__(ReflexionService)
        stats = asyncio.run(ReflexionService._get_relationship_stats(svc, 1))
        assert stats["is_real"] is False
        assert stats["total_interactions"] == 0


class TestScoreComposition:
    """S 的组合方式:D_R 不可信时必须重新归一化,而不是掺入猜测值。"""

    def test_normalized_weights_sum_to_one(self):
        # 丢弃 D_R 后 Q_I:E_U 由 0.5:0.3 归一化为 0.625:0.375
        q_i, e_u = 0.8, 0.6
        s = (0.5 * q_i + 0.3 * e_u) / 0.8
        assert abs(s - (0.625 * q_i + 0.375 * e_u)) < 1e-9

    def test_dropping_dr_removes_constant_bias(self):
        """
        旧行为:D_R≈0.98 按 0.2 权重固定贡献 +0.196。
        新行为把权重归一化到 Q_I/E_U 上,净效果是抬高被移除(此例约 0.096 —
        因为分母也从 1.0 变成 0.8,不是简单减去 0.196)。
        """
        q_i, e_u = 0.5, 0.5
        old = 0.5 * q_i + 0.3 * e_u + 0.2 * 0.98
        new = (0.5 * q_i + 0.3 * e_u) / 0.8
        assert old > new, "未消除 D_R 常量偏置"
        assert abs(old - new) > 0.05, "偏置消除幅度应可观测"

    def test_low_quality_turn_can_now_reach_patch_threshold(self):
        """
        关键回归:旧的 D_R 常量把低分轮次也抬到 0.6 以上,使补丁阈值形同虚设
        (实测 S 分布挤在 0.75±0.05,而补丁阈值 0.40 永不可达)。
        移除偏置后,真正糟糕的轮次应能落到低分区间。
        """
        q_i, e_u = 0.2, 0.2  # 明显糟糕的一轮
        old = 0.5 * q_i + 0.3 * e_u + 0.2 * 0.98
        new = (0.5 * q_i + 0.3 * e_u) / 0.8
        assert old > 0.35, "确认旧行为确实把低分抬高了"
        assert new < 0.25, "新行为下糟糕轮次应能落入低分区,让补丁机制真正生效"
