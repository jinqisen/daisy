"""
本地启动不得被废弃的外部服务拖住。

实测:从源码启动要 **108 秒**,其中 89 秒纯粹是在等两个连不上的 Redis 超时 ——
`.env` 里还留着 `REDIS_HOST=172.22.1.251`,那是 Docker 时代的机器,早已不存在。
去 Docker 化时删掉了编排,却没清掉指向它的配置。

更糟的是表现形式:没有任何报错,只有一行 "Waiting for application startup" 挂着。
用户看到的就是"启动报错/卡死",完全无从判断。

两条防线:
  1. 本地默认走嵌入模式(进程内 fakeredis),压根不需要外部服务;
  2. 万一仍要连外部 Redis,必须快速失败并给出**能自解释**的提示,
     而不是走系统默认的 75 秒超时。
"""

import os
import re

import pytest

SERVER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestLocalDefaultsToEmbedded:

    def test_env_enables_embedded_mode(self):
        """
        本地开发默认嵌入模式。不设它就会去连早已不存在的远端 Redis,
        白等 75 秒才启动。
        """
        env = open(os.path.join(SERVER, ".env"), encoding="utf-8").read()
        active = [l for l in env.splitlines()
                  if l.strip() and not l.strip().startswith("#")]
        assert any(l.startswith("EMBEDDED_MODE=true") for l in active), \
            ".env 未启用嵌入模式 —— 本地启动会卡在连接外部 Redis 上"

    def test_no_active_stale_redis_host(self):
        """
        指向已下线机器的配置必须注释掉。留着它=给未来埋一个"启动莫名很慢"。
        """
        env = open(os.path.join(SERVER, ".env"), encoding="utf-8").read()
        active = [l for l in env.splitlines()
                  if l.strip() and not l.strip().startswith("#")]
        stale = [l for l in active if re.match(r"REDIS_HOST=\d+\.\d+\.\d+\.\d+", l)]
        assert not stale, f"仍配置了远端 Redis:{stale} —— 单机版不需要外部服务"


class TestRedisFailsFastWithReadableReason:

    def test_connect_timeout_is_bounded(self):
        """
        不设超时会走系统默认(实测 75 秒),表现为"启动卡住"而非报错 ——
        最难排查的那种失败。
        """
        from app.core.cache import REDIS_CONNECT_TIMEOUT_SEC

        assert 0 < REDIS_CONNECT_TIMEOUT_SEC <= 10, \
            f"连接超时 {REDIS_CONNECT_TIMEOUT_SEC}s 过长,启动会长时间无响应"

    def test_every_client_sets_timeout(self):
        """
        **每一个**真实 Redis 客户端都要设超时,漏一个就仍会卡住。

        原先写死"至少 2 个",因为当时有同步/异步两个客户端。后来同步客户端被删了
        (全库零使用者),这条断言就变成了在测**客户端数量**而不是它要守的性质。
        改成按实际的 from_url 调用数校验,以后增删客户端都不会误报或漏报。
        """
        # 连接逻辑现在分在 core/cache.py(缓存)与 core/task_queue.py(任务队列),
        # 两者曾同住一个名为 redis.py 的文件。
        src = "".join(
            open(os.path.join(SERVER, "app", "core", f), encoding="utf-8").read()
            for f in ("cache.py", "task_queue.py")
        )
        clients = src.count("from_url(")
        timeouts = src.count("socket_connect_timeout=REDIS_CONNECT_TIMEOUT_SEC")
        assert clients > 0, "没有找到任何 Redis 客户端构造点,这条测试已失效"
        assert timeouts >= clients, (
            f"{clients} 个 Redis 客户端里只有 {timeouts} 个设了连接超时,"
            f"其余会走 75 秒默认值,表现为启动卡住"
        )

    def test_error_message_points_at_embedded_mode(self):
        """
        绝大多数情况下根因是"忘了开 EMBEDDED_MODE",不是 Redis 真挂了。
        错误信息要能自解释,否则用户只能干瞪眼。
        """
        import inspect

        from app.core.cache import RedisClient

        src = inspect.getsource(RedisClient.connect)
        assert "EMBEDDED_MODE" in src, \
            "Redis 连接失败的提示没有指向真正的解法(开启嵌入模式)"


class TestEmbeddedModeNeedsNoExternalService:

    def test_embedded_clears_remote_hosts(self):
        """嵌入模式必须清空远程地址,否则仍会尝试连接。"""
        from app.core.config import Settings

        s = Settings(EMBEDDED_MODE=True, QDRANT_HOST="remote.example")
        assert s.QDRANT_HOST is None

    @pytest.mark.asyncio
    async def test_embedded_redis_connects_without_network(self, monkeypatch):
        """嵌入模式下 Redis 必须立刻可用(进程内 fakeredis),不依赖任何网络。"""
        from app.core import cache as redis_mod
        from app.core.config import settings

        monkeypatch.setattr(settings, "EMBEDDED_MODE", True)
        client = redis_mod.RedisClient()
        await client.connect()
        assert client.enabled is True
        await client.close()
