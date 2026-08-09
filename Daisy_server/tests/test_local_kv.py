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
import time

import pytest

from app.core.local_kv import LocalKVAsync, reset_for_tests


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


class TestExpiredKeysAreReclaimed:
    """
    惰性过期(读到才判断)**会漏**:`cache_result` 的键是按参数做 md5 的,
    过期之后再也不会有人来读,于是每个失效条目都永久留在字典里。

    实测过:写 1000 个 1 秒过期的缓存键,过期后只读别的键,字典大小仍是 1000。
    fakeredis 自带主动过期,换成进程内实现时这层保障丢了 —— 这是替换引入的回归。
    """

    def test_expired_entries_do_not_accumulate(self):
        from app.core.local_kv import _STORE

        _STORE.flushall()
        for i in range(_STORE._SWEEP_EVERY_WRITES * 2):
            _STORE.set(f"cache:x:fn:{i:032x}", "v", ex=1)
        time.sleep(1.05)
        # 继续正常写入,应触发清扫
        for i in range(_STORE._SWEEP_EVERY_WRITES):
            _STORE.set(f"live:{i}", "v", ex=600)

        leftover = [k for k in _STORE._data if k.startswith("cache:x:")]
        assert not leftover, \
            f"{len(leftover)} 个过期缓存键没有回收 —— 长时间运行会持续吃内存"

    def test_unexpired_entries_survive_sweep(self):
        """清扫不能误伤未过期的键。"""
        from app.core.local_kv import _STORE

        _STORE.flushall()
        _STORE.set("keep", "v", ex=600)
        _STORE.set("forever", "v")          # 无 TTL
        for i in range(_STORE._SWEEP_EVERY_WRITES + 1):
            _STORE.set(f"tmp:{i}", "v", ex=600)
        assert _STORE.get("keep") == "v"
        assert _STORE.get("forever") == "v"


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


class TestFakeredisIsGone:

    def test_embedded_path_does_not_use_fakeredis(self):
        """
        连接分支里不能再出现 fakeredis,否则等于两套实现并存。
        """
        import inspect

        from app.core.cache import RedisClient

        src = inspect.getsource(RedisClient.connect)
        assert "fakeredis" not in src, "连接分支仍在用 fakeredis"
        assert "LocalKV" in src


class TestSetNxIsALock:
    """
    `nx=True`(SETNX)是**并发锁的原语**,chat_task 用 `lock:user:{id}` 保证
    同一用户同时只跑一个对话任务。

    第一版实现漏了这个参数,对话直接报
    `LocalKVAsync.set() got an unexpected keyword argument 'nx'`。
    它逃过了当时全部 428 个测试 —— 因为**没有一个测试真正跑过对话任务**,
    而我统计调用点时只数了 `set(` 出现的次数,没看参数。是启动应用才发现的。
    """

    def test_second_acquire_fails(self):
        async def go():
            r = LocalKVAsync()
            assert await r.set("lock:user:1", "1", nx=True, ex=600) is True
            assert await r.set("lock:user:1", "1", nx=True, ex=600) is False, \
                "锁能被重复获取 —— 同一用户会并发跑多个对话任务"
        run(go())

    def test_reacquire_after_release(self):
        async def go():
            r = LocalKVAsync()
            await r.set("lock:user:1", "1", nx=True, ex=600)
            await r.delete("lock:user:1")
            assert await r.set("lock:user:1", "1", nx=True, ex=600) is True, \
                "释放后拿不回锁 —— 用户会被永久挡住"
        run(go())

    def test_lock_expires(self):
        """任务崩溃时锁必须能自己过期,否则用户永远发不出消息。"""
        async def go():
            r = LocalKVAsync()
            await r.set("lock:user:1", "1", nx=True, ex=1)
            await asyncio.sleep(1.05)
            assert await r.set("lock:user:1", "1", nx=True, ex=600) is True
        run(go())

    def test_nx_does_not_affect_plain_set(self):
        """普通 set 仍要能覆盖已有值。"""
        async def go():
            r = LocalKVAsync()
            await r.set("k", "old")
            await r.set("k", "new")
            assert await r.get("k") == "new"
        run(go())

    def test_concurrent_acquire_only_one_wins(self):
        """
        检查与写入必须原子。分开做的话,两个并发请求可能同时判定"键不存在"
        而都拿到锁 —— 那正是这把锁要防的事。
        """
        from app.core.local_kv import _STORE

        _STORE.flushall()
        results, barrier = [], threading.Barrier(8)

        def worker():
            barrier.wait()
            results.append(_STORE.set("lock:user:1", "1", ex=600, nx=True))

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert sum(1 for r in results if r) == 1, \
            f"8 个并发请求里有 {sum(1 for r in results if r)} 个拿到了锁,应当只有 1 个"


class TestUsedKwargsAreSupported:
    """
    "只实现用到的接口"是对的,但**必须真的把用到的都实现** ——
    统计时要看参数,不能只数调用次数。这条测试直接扫源码里的实际调用。
    """

    def test_every_kwarg_at_call_sites_is_accepted(self):
        import ast
        import inspect
        import os

        server = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        used = set()
        for dp, _, fs in os.walk(os.path.join(server, "app")):
            if "__pycache__" in dp:
                continue
            for f in fs:
                if not f.endswith(".py"):
                    continue
                path = os.path.join(dp, f)
                tree = ast.parse(open(path, encoding="utf-8").read())
                for node in ast.walk(tree):
                    # 用 AST 而不是正则:第一版的 `[^)]*` 会跨进嵌套调用,
                    # 把 json.dumps(..., ensure_ascii=False) 的参数也算进来。
                    if not (isinstance(node, ast.Call)
                            and isinstance(node.func, ast.Attribute)
                            and node.func.attr == "set"):
                        continue
                    recv = ast.unparse(node.func.value)
                    if "redis" not in recv:
                        continue
                    used |= {kw.arg for kw in node.keywords if kw.arg}

        accepted = set(inspect.signature(LocalKVAsync.set).parameters)
        # 门面用 ttl=,底层用 ex= —— 两者都算已支持
        missing = used - accepted - {"ttl"}
        assert not missing, (
            f"调用点用了 {sorted(missing)},而 LocalKVAsync.set 不接受 —— "
            f"运行时会抛 TypeError,而测试可能完全覆盖不到"
        )
