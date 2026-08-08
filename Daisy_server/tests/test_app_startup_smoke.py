"""
应用启动冒烟测试 —— 真正跑一遍 lifespan。

为什么必须有它:重构后 292 个测试全绿,打包版却**启动即崩**:

    app/main.py: for route in app.routes:
    AttributeError: module 'app' has no attribute 'routes'

原因是 lifespan 里写了 `import app.tasks`,把名字 `app` 绑到了顶层包,
遮蔽了同名的 FastAPI 实例。这类错误单元测试永远发现不了 —— 它们只 import 模块、
调用函数,**从不启动应用**。

覆盖上的真空比单个 bug 更值得修:任何只在 lifespan 中出现的问题
(启动顺序、资源初始化、名字遮蔽)此前都无人把守。
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """在隔离数据目录里真正启动一次应用(会执行完整 lifespan)。"""
    import os

    data_dir = tmp_path_factory.mktemp("startup")
    os.environ["DAISY_DATA_DIR"] = str(data_dir)
    os.environ["DAISY_DB_PATH"] = str(data_dir / "t.db")
    os.environ["EMBEDDED_MODE"] = "true"

    from app.main import app

    with TestClient(app) as c:   # __enter__ 触发 lifespan
        yield c


class TestLifespanCompletes:

    def test_app_starts(self, client):
        """
        能走到这里就说明 lifespan 完整跑通了 —— 上面那个遮蔽 bug 会让
        TestClient(app).__enter__ 直接抛异常。
        """
        assert client.get("/health").status_code == 200

    def test_routes_are_registered(self, client):
        """
        lifespan 末尾会遍历 app.routes 打印路由。名字被遮蔽时正是死在这一步。
        """
        from app.main import app

        paths = {getattr(r, "path", "") for r in app.routes}
        for expected in ("/health", "/api/auth/local_session", "/api/config/common"):
            assert expected in paths, f"路由未注册: {expected}"


class TestBackgroundJobsRegistered:
    """
    任务注册发生在 lifespan 内(见 core/job_registry.py)。
    若那句导入写错,分发时会查不到任务 —— 表现为"消息发出去没人处理"。
    """

    def test_jobs_registered_after_startup(self, client):
        from app.core.job_registry import registered_jobs

        jobs = registered_jobs()
        for name in ("chat_task", "proactive_check_task", "trigger_proactive_checks"):
            assert name in jobs, f"后台任务未注册: {name}"

    def test_resolve_returns_callable(self, client):
        from app.core.job_registry import resolve_job

        assert callable(resolve_job("chat_task"))


class TestTraceSinkInstalled:
    """LLM 轨迹落库实现由 lifespan 注入(core 只持接口)。漏注入则轨迹静默丢失。"""

    def test_sink_installed(self, client):
        from app.core import trace_sink

        assert trace_sink._sink is not None, "轨迹 sink 未注入,LLM 调用轨迹会全部丢失"


class TestNoNameShadowingInMain:
    """
    静态兜底:main.py 里不得出现 `import app.xxx` —— 它会把 `app` 绑到顶层包,
    遮蔽 FastAPI 实例。用 `from . import xxx` 代替。
    """

    def test_no_absolute_app_import(self):
        import inspect
        import re

        from app import main

        src = open(inspect.getsourcefile(main), encoding="utf-8").read()
        code = "\n".join(
            l for l in src.splitlines() if not l.strip().startswith("#")
        )
        hits = re.findall(r"^\s*import app\b.*$", code, re.M)
        assert not hits, (
            f"main.py 中出现绝对导入 {hits} —— 会遮蔽同名的 FastAPI 实例 app,"
            f"导致 app.routes 报 AttributeError。请改用 `from . import xxx`。"
        )
