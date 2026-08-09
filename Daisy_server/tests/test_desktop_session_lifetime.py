"""
桌面版会话与定时派发的两个「跑一阵子才暴露」的回归。

坑一:本地会话沿用了 server 部署的 30 分钟令牌有效期。桌面版没有服务端,
令牌从不离开本机,短 TTL 没有任何安全收益;但应用开着超过 30 分钟后,
所有请求变 401,前端只能拿着死令牌一直重试 —— 表现为满屏报错。

坑二:APScheduler 在独立线程里 asyncio.run() 新建事件循环派发任务。
嵌入模式下任务是进程内直接执行的,一碰到绑定在主循环上的 fakeredis 就报
"bound to a different event loop",主动对话检查每 15 分钟静默失败一次。
"""

import asyncio
from datetime import timedelta

import pytest
from jose import jwt

from app.api import auth as auth_api
from app.core import security
from app.core.config import settings
from app.core.scheduler import SchedulerManager


class TestLocalSessionTokenLifetime:

    def _exp_of(self, token: str) -> int:
        return jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )["exp"]

    def test_local_token_outlives_a_long_session(self):
        """
        核心回归:本地令牌必须远长于一次使用时长,否则用着用着就全 401。
        """
        token = security.create_access_token(
            subject="local",
            expires_delta=timedelta(days=auth_api.LOCAL_SESSION_TOKEN_DAYS),
        )
        import time
        remaining = self._exp_of(token) - time.time()
        assert remaining > 7 * 86400, \
            f"本地令牌仅剩 {remaining/3600:.1f} 小时,应用开久了会全部 401"

    def test_default_expiry_is_still_short_for_server_mode(self):
        """
        长效令牌只给本地会话,server 部署的登录令牌不受影响。
        断言字段默认值而非 settings 实例:后者会被本地 .env 覆盖,测不出真实默认。
        (打包版正是走这个默认值 —— 30 分钟,当初 401 刷屏的来源。)
        """
        default = type(settings).model_fields["ACCESS_TOKEN_EXPIRE_MINUTES"].default
        assert default <= 60


class TestEmbeddedDispatchUsesMainLoop:

    @pytest.mark.asyncio
    async def test_start_captures_running_loop(self):
        mgr = SchedulerManager()
        try:
            mgr.start()
            assert mgr._main_loop is asyncio.get_running_loop(), \
                "未记住主循环,嵌入模式派发会在新循环里碰到跨循环对象"
        finally:
            mgr.shutdown()

    def test_start_outside_async_does_not_crash(self):
        """非 async 上下文(测试/脚本)启动应回落而不是抛异常。"""
        mgr = SchedulerManager()
        try:
            mgr.start()
            assert mgr._main_loop is None
        finally:
            mgr.shutdown()

    @pytest.mark.asyncio
    async def test_embedded_dispatch_runs_on_main_loop(self, monkeypatch):
        """
        核心回归:调度线程触发时,任务协程必须落在主循环上执行。
        """
        monkeypatch.setattr(settings, "EMBEDDED_MODE", True)
        main_loop = asyncio.get_running_loop()
        seen = {}

        from app.core import task_queue as redis_mod

        class _Shim:
            async def enqueue_job(self, name, *a, **kw):
                seen["loop"] = asyncio.get_running_loop()
                seen["job"] = name

        monkeypatch.setattr(
            redis_mod._EmbeddedArqShim, "get_instance", classmethod(lambda cls: _Shim())
        )

        mgr = SchedulerManager()
        mgr._main_loop = main_loop
        # 模拟 APScheduler:在另一个线程里同步调用
        done = asyncio.Event()

        def _from_scheduler_thread():
            mgr._trigger_proactive_checks()
            main_loop.call_soon_threadsafe(done.set)

        import threading
        threading.Thread(target=_from_scheduler_thread, daemon=True).start()
        await asyncio.wait_for(done.wait(), timeout=10)

        assert seen.get("job") == "trigger_proactive_checks"
        assert seen["loop"] is main_loop, \
            "任务跑在了调度线程的新循环上 —— fakeredis 会报 bound to a different event loop"

    def test_embedded_dispatch_without_loop_is_silent(self, monkeypatch):
        """主循环不可用时应记日志返回,不能抛异常打断调度器。"""
        monkeypatch.setattr(settings, "EMBEDDED_MODE", True)
        mgr = SchedulerManager()
        mgr._main_loop = None
        mgr._trigger_proactive_checks()  # 不抛异常即通过
