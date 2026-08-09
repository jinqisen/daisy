"""
SLO 指标必须跨重启有效。

原先 `metrics:llm:*` / `metrics:router:*` / `metrics:e2e:*` 都是 Redis 里
**不带 TTL** 的累加计数器。但嵌入模式的 Redis 是进程内 fakeredis,重启即空,
而这些恰恰是**累计量** —— 总调用数、总 token、总成本。后果:

  - 面板永远只反映"本次运行",重启即归零;
  - 成本统计基本没有意义(它本来就是要看长期花了多少钱)。

改为落 `metric_events` 事实表,聚合放到读取侧。顺带消掉了"计数器与事实不一致"
这个类别的隐患:没有计数器,只有事实。

依赖方向上沿用 trace_sink 的注入模式 —— 埋点在 core/workflow,而"存到哪张表"
是持久化关注点,core 直接 import 模型会让最底层反过来依赖 models(见 §依赖护栏)。
"""

import asyncio
import datetime
import os
import re

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.trace import MetricEventDB

SERVER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def metrics_db(monkeypatch):
    """
    内存库 + 注入 sink,**用完必须卸载**。

    sink 是进程级全局的。只装不卸的话,夹具退出后 monkeypatch 会把
    `store.SessionLocal` 还原成真实的那个,而 sink 仍然挂着 ——
    后续任何触发埋点的测试(比如跑一遍工作流图)就会把行写进
    开发机的真实数据库。实测每跑一次测试套件污染 2 行。

    这与当初"测试往仓库里的 server_config.json 写真值、密钥最终进了 .dmg"
    是同一类问题:**测试的副作用逃出了测试**。
    """
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    import app.core.database as database
    import app.core.metrics_sink as sink
    import app.services.system.metrics_store as store
    monkeypatch.setattr(database, "SessionLocal", Session)
    monkeypatch.setattr(store, "SessionLocal", Session)

    previous = sink._sink
    store.install()
    try:
        yield Session
    finally:
        sink.set_metrics_sink(previous) if previous else setattr(sink, "_sink", None)


class TestMetricsArePersisted:

    def test_llm_metric_lands_in_db(self, metrics_db):
        from app.core.metrics_sink import KIND_LLM, record_metric

        record_metric(kind=KIND_LLM, route="DEEP", model_name="deepseek-v3.2",
                      in_tokens=100, out_tokens=50, cost_usd=0.002)

        with metrics_db() as db:
            rows = db.query(MetricEventDB).all()
        assert len(rows) == 1
        assert rows[0].kind == "llm" and rows[0].in_tokens == 100

    def test_survives_redis_being_wiped(self, metrics_db):
        """
        核心回归:清空 Redis 不该影响任何指标 —— 它们已经不在那里了。
        这正是"重启即归零"的等价场景。
        """
        from app.core.metrics_sink import KIND_LLM, record_metric
        from app.core.cache import redis_client
        from app.services.system.metrics_store import summarize

        record_metric(kind=KIND_LLM, route="FAST", model_name="m",
                      in_tokens=10, out_tokens=5, cost_usd=0.1)

        async def _wipe():
            await redis_client.connect()
            if redis_client.redis:
                await redis_client.redis.flushall()
        asyncio.run(_wipe())

        assert summarize()["llm"]["count"] == 1, \
            "清空 Redis 后指标丢失 —— 说明真源仍在内存里"

    def test_sink_failure_does_not_raise(self, monkeypatch):
        """
        可观测性绝不能反过来拖垮主链路:埋点在对话热路径上,
        写失败必须静默,不能把异常抛回业务代码。
        """
        from app.core import metrics_sink

        def _boom(**kw):
            raise RuntimeError("disk full")
        monkeypatch.setattr(metrics_sink, "_sink", _boom)

        metrics_sink.record_metric(kind="llm")   # 不抛异常即通过

    def test_no_sink_installed_is_safe(self, monkeypatch):
        """未注入实现时静默丢弃,不能报错(测试/脚本场景常见)。"""
        from app.core import metrics_sink

        monkeypatch.setattr(metrics_sink, "_sink", None)
        metrics_sink.record_metric(kind="llm")


class TestAggregation:

    def _seed(self, Session):
        from app.core.metrics_sink import KIND_E2E, KIND_LLM, KIND_ROUTER, record_metric

        record_metric(kind=KIND_LLM, route="DEEP", model_name="a",
                      in_tokens=100, out_tokens=20, cost_usd=0.01)
        record_metric(kind=KIND_LLM, route="DEEP", model_name="b",
                      in_tokens=200, out_tokens=40, cost_usd=0.02)
        record_metric(kind=KIND_ROUTER, route="FAST", duration_ms=12)
        record_metric(kind=KIND_ROUTER, route="DEEP", duration_ms=340)
        record_metric(kind=KIND_E2E, route="DEEP", duration_ms=28000)

    def test_sums_and_groupings(self, metrics_db):
        from app.services.system.metrics_store import summarize

        self._seed(metrics_db)
        agg = summarize()

        assert agg["llm"]["count"] == 2
        assert agg["llm"]["sum_in"] == 300
        assert abs(agg["llm"]["sum_cost"] - 0.03) < 1e-9
        assert agg["llm"]["by_model"] == {"a": 1, "b": 1}
        assert agg["router"]["count"] == 2
        assert agg["router"]["by_route"] == {"FAST": 1, "DEEP": 1}
        assert agg["e2e"]["count"] == 1

    def test_histogram_buckets_populated(self, metrics_db):
        """
        分桶原先在**写入侧**做,读取侧再读回来。那样写入和读取各持一套阈值,
        改了一边就会悄悄漂移。现在统一在读取侧分桶。
        """
        from app.services.system.metrics_store import summarize

        self._seed(metrics_db)
        assert sum(summarize()["router"]["hist"].values()) == 2

    def test_slo_endpoint_shape_unchanged(self, metrics_db):
        """
        换存储不该让前端改代码 —— 响应结构必须与改造前逐字段一致。
        """
        from app.api.metrics import get_slo_metrics

        self._seed(metrics_db)
        out = asyncio.run(get_slo_metrics())

        assert set(out) == {"router", "e2e", "llm", "fast_hit_rate"}
        for k in ("count", "avg_ms", "by_route", "hist"):
            assert k in out["router"], f"router 缺字段 {k}"
        for k in ("count", "avg_in_tokens", "sum_in_tokens", "sum_cost_usd",
                  "by_route", "by_model", "est_chars_per_token"):
            assert k in out["llm"], f"llm 缺字段 {k}"
        assert out["fast_hit_rate"] == 0.5

    def test_slo_no_longer_requires_redis(self, metrics_db):
        """
        原先 Redis 不可用时接口直接 503。指标已落库,不该再有这个依赖。
        """
        src = open(os.path.join(SERVER, "app", "api", "metrics.py"),
                   encoding="utf-8").read()
        # 只看可执行代码 —— 文档字符串里会提到 Redis(那正是在解释这次改动)
        code = re.sub(r'"""[\s\S]*?"""', "", src)
        code = "\n".join(l for l in code.splitlines()
                         if not l.strip().startswith("#"))
        assert "redis_client" not in code, "SLO 接口仍在读 Redis"
        assert "HTTPException" not in code, \
            "SLO 接口仍会因 Redis 不可用而 503 —— 指标已落库,不该有这个依赖"


class TestRetention:
    """一行一次调用,不设上限这张表会无限增长。"""

    def test_purge_removes_old_only(self, metrics_db):
        from app.services.system.metrics_store import purge_old

        with metrics_db() as db:
            db.add(MetricEventDB(kind="llm",
                                 timestamp=datetime.datetime.utcnow() - datetime.timedelta(days=200)))
            db.add(MetricEventDB(kind="llm", timestamp=datetime.datetime.utcnow()))
            db.commit()

        assert purge_old(days=90) == 1
        with metrics_db() as db:
            assert db.query(MetricEventDB).count() == 1


class TestDependencyDirection:
    """
    core 不能 import models —— 那会让最底层反过来依赖持久化层,形成环。
    这正是 trace_sink / metrics_sink 这层间接存在的理由。
    """

    def test_core_does_not_import_models(self):
        src = open(os.path.join(SERVER, "app", "core", "metrics_sink.py"),
                   encoding="utf-8").read()
        assert not re.search(r"from\s+.*models|import\s+.*models", src), \
            "core/metrics_sink.py 直接依赖了 models —— 应通过注入获得实现"

    def test_sink_is_installed_at_startup(self):
        """没注入的话指标会被静默丢弃,而且不会有任何报错。"""
        src = open(os.path.join(SERVER, "app", "main.py"), encoding="utf-8").read()
        assert "install_metrics_store" in src, "启动时未注入指标落库实现"


class TestNoLeftoverCounters:

    def test_redis_metric_counters_removed(self):
        """
        残留任何一处旧计数器,就会出现"两套数各说各话"。
        """
        import subprocess

        out = subprocess.run(
            ["grep", "-rn", "-e", "metrics:llm:", "-e", "metrics:router:",
             "-e", "metrics:e2e:", os.path.join(SERVER, "app")],
            capture_output=True, text=True,
        ).stdout
        assert not out.strip(), f"仍有 Redis 指标计数器:\n{out}"


class TestTestsDoNotTouchRealDatabase:
    """
    测试的副作用必须留在测试里。

    这条护栏来自一次实测:加了指标落库之后,跑一次测试套件就往开发机的
    `Daisy_server/sqlite.db` 写 2 行 —— 因为启动烟测会把 sink 等**进程级全局
    实现**装到真实数据库上,之后任何触发埋点的用例都会写真库。

    项目在这个类别上已经付过一次代价:测试往仓库里的 server_config.json
    写了真值,密钥最终随 .dmg 分发了出去。所以宁可一刀切。
    """

    def test_db_path_is_isolated(self):
        import app.core.database as database

        assert "daisy-tests-" in database.DB_PATH, (
            f"测试用的是真实数据库 {database.DB_PATH} —— "
            f"conftest.py 里的 DAISY_DB_PATH 隔离没生效"
        )

    def test_conftest_sets_env_before_imports(self):
        """
        必须在模块导入期设置。放进 fixture 就晚了 ——
        core/database.py 在 import 时就已经据此建好了 engine。
        """
        src = open(os.path.join(SERVER, "tests", "conftest.py"), encoding="utf-8").read()
        code = re.sub(r'"""[\s\S]*?"""', "", src)
        assert "DAISY_DB_PATH" in code
        assert "def " not in code, \
            "隔离逻辑被包进了函数 —— 那会晚于 app 模块导入,不起作用"
