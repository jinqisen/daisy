"""
进程内缓存(替代 fakeredis)的行为契约。

为什么换掉 fakeredis:统计全部调用点后,48 次里 33 次是 get/set/delete,
其余是 1 次 publish、1 次 pipeline、1 次 keys、1 次 hgetall ——
我们在跑一个**网络缓存的仿真器**做字典的事。除了多一个依赖,它还制造了一个
更贵的错觉:"它看起来像数据库,所以可以往里放长期数据"。这轮修的四个缺陷
(主动关心的配额/冷却/作息、SLO 指标)全部源于这个错觉。

替换之所以此刻才安全:存储归位之后缓存里**只剩缓存**,没有持久数据依赖它。

这里逐条锁住实际用到的语义。用不到的 Redis 命令**故意不实现** ——
半实现的兼容层比没有更危险,它会让人以为可以随便用。
"""

import asyncio
import json
import threading

import pytest

from app.core.local_kv import LocalKVAsync, LocalKVSync, reset_for_tests


@pytest.fixture(autouse=True)
def clean():
    reset_for_tests()
    yield
    reset_for_tests()


def run(coro):
    return asyncio.run(coro)


class TestStringOps:

    def test_set_get_delete(self):
        async def go():
            r = LocalKVAsync()
            await r.set("k", "v")
            assert await r.get("k") == "v"
            assert await r.exists("k") == 1
            await r.delete("k")
            assert await r.get("k") is None
            assert await r.exists("k") == 0
        run(go())

    def test_values_are_strings(self):
        """decode_responses=True 的语义:取出来一律是 str,调用方自己 JSON 解码。"""
        async def go():
            r = LocalKVAsync()
            await r.set("n", 42)
            v = await r.get("n")
            assert v == "42" and isinstance(v, str)
        run(go())

    def test_ttl_expires(self):
        async def go():
            r = LocalKVAsync()
            await r.set("k", "v", ex=1)
            assert await r.get("k") == "v"
            await asyncio.sleep(1.05)
            assert await r.get("k") is None, "TTL 没有生效 —— 缓存会无限增长"
        run(go())

    def test_expire_on_existing_key(self):
        async def go():
            r = LocalKVAsync()
            await r.set("k", "v")
            assert await r.expire("k", 1) is True
            await asyncio.sleep(1.05)
            assert await r.get("k") is None
        run(go())

    def test_expire_on_missing_key_is_false(self):
        async def go():
            assert await LocalKVAsync().expire("nope", 10) is False
        run(go())

    def test_incr_preserves_ttl(self):
        """
        计数器自增不该把过期时间抹掉 —— 主动关心的每日配额就是
        "自增 + 到零点过期",抹掉 TTL 会让它永不复位。
        """
        async def go():
            r = LocalKVAsync()
            await r.set("c", 1, ex=1)
            await r.incr("c")
            assert await r.get("c") == "2"
            await asyncio.sleep(1.05)
            assert await r.get("c") is None, "自增把 TTL 抹掉了"
        run(go())


class TestHashOps:
    """budget.py 的执行预算账本用的是哈希。"""

    def test_hincrby_and_hgetall(self):
        async def go():
            r = LocalKVAsync()
            await r.hincrby("h", "a", 1)
            await r.hincrby("h", "a", 2)
            await r.hincrbyfloat("h", "cost", 0.5)
            got = await r.hgetall("h")
            assert got["a"] == "3"
            assert float(got["cost"]) == 0.5
        run(go())

    def test_hgetall_missing_returns_empty(self):
        async def go():
            assert await LocalKVAsync().hgetall("nope") == {}
        run(go())


class TestKeysPattern:
    """StateService.get_online_users 用 keys('user:*:online') 扫描。"""

    def test_glob_matching(self):
        async def go():
            r = LocalKVAsync()
            await r.set("user:a:online", "1")
            await r.set("user:b:online", "1")
            await r.set("user:a:last_active", "x")
            assert sorted(await r.keys("user:*:online")) == \
                ["user:a:online", "user:b:online"]
        run(go())

    def test_expired_keys_not_listed(self):
        async def go():
            r = LocalKVAsync()
            await r.set("user:a:online", "1", ex=1)
            await asyncio.sleep(1.05)
            assert await r.keys("user:*:online") == [], \
                "过期键仍出现在 keys() 里 —— 会把离线用户当成在线"
        run(go())


class TestPubSub:
    """SSE 是唯一使用者。这块出错的表现是"消息发出去了但前端收不到"。"""

    def test_subscribe_receives_published(self):
        async def go():
            r = LocalKVAsync()
            ps = r.pubsub()
            await ps.subscribe("chat:stream:u1")
            await r.publish("chat:stream:u1", json.dumps({"m": "hi"}))
            msg = await ps.get_message(ignore_subscribe_messages=True, timeout=1.0)
            assert msg and json.loads(msg["data"])["m"] == "hi"
        run(go())

    def test_channels_are_isolated(self):
        """串频道等于把消息发给了别的用户 —— 这是隐私问题,不只是 bug。"""
        async def go():
            r = LocalKVAsync()
            ps = r.pubsub()
            await ps.subscribe("chat:stream:u1")
            await r.publish("chat:stream:u2", "other")
            assert await ps.get_message(timeout=0.2) is None
        run(go())

    def test_publish_from_another_thread(self):
        """
        核心回归:主动关心由调度线程通过 run_coroutine_threadsafe 发布。
        用 asyncio.Queue 实现 pub/sub 在这条路径上是不安全的,
        所以实现里刻意用了带锁的 deque + 轮询。
        """
        async def go():
            r = LocalKVAsync()
            ps = r.pubsub()
            await ps.subscribe("chat:stream:u1")
            loop = asyncio.get_running_loop()

            def worker():
                fut = asyncio.run_coroutine_threadsafe(
                    r.publish("chat:stream:u1", "from-thread"), loop)
                fut.result(timeout=5)

            t = threading.Thread(target=worker)
            t.start()
            msg = await ps.get_message(ignore_subscribe_messages=True, timeout=2.0)
            t.join()
            assert msg and msg["data"] == "from-thread", \
                "跨线程发布丢消息 —— 主动关心的推送会静默失败"
        run(go())

    def test_timeout_returns_none_not_blocks(self):
        """SSE 循环每轮都要能返回,否则断连检测和心跳都会停摆。"""
        async def go():
            ps = LocalKVAsync().pubsub()
            await ps.subscribe("empty")
            assert await ps.get_message(timeout=0.1) is None
        run(go())

    def test_unsubscribe_stops_delivery(self):
        async def go():
            r = LocalKVAsync()
            ps = r.pubsub()
            await ps.subscribe("c")
            await ps.close()
            await r.publish("c", "x")
            assert await ps.get_message(timeout=0.1) is None
        run(go())


class TestPipeline:
    """budget.py:几个 hincrby 加一个 expire,一起提交。"""

    def test_buffered_then_executed(self):
        async def go():
            r = LocalKVAsync()
            p = r.pipeline()
            p.hincrby("ex:1", "llm_calls", 1)
            p.hincrby("ex:1", "in_tokens", 100)
            p.hincrbyfloat("ex:1", "cost_usd", 0.25)
            p.expire("ex:1", 60)
            assert await r.hgetall("ex:1") == {}, "命令在 execute 之前就生效了"
            await p.execute()
            got = await r.hgetall("ex:1")
            assert got["llm_calls"] == "1" and got["in_tokens"] == "100"
        run(go())


class TestSyncAndAsyncShareState:
    """
    同步门面在线程池里被调用,异步门面在事件循环里 —— 两者必须看到同一份数据,
    否则会出现"写进去了但读不到"这类最难查的问题。
    """

    def test_sync_sees_async_writes(self):
        async def go():
            await LocalKVAsync().set("shared", "v")
        run(go())
        assert LocalKVSync().get("shared") == "v"

    def test_async_sees_sync_writes(self):
        LocalKVSync().set("shared2", "v2")

        async def go():
            return await LocalKVAsync().get("shared2")
        assert run(go()) == "v2"


class TestFakeredisIsGone:

    def test_embedded_path_does_not_use_fakeredis(self):
        """
        连接分支里不能再出现 fakeredis,否则等于两套实现并存。
        """
        import inspect

        from app.core.redis import RedisClient, SyncRedisClient

        for fn in (RedisClient.connect, SyncRedisClient.connect):
            src = inspect.getsource(fn)
            assert "fakeredis" not in src, f"{fn.__qualname__} 仍在用 fakeredis"
            assert "LocalKV" in src
