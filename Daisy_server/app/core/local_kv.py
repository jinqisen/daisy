"""
进程内的键值缓存与广播,替代嵌入模式下的 fakeredis。

为什么不继续用 fakeredis:统计全部调用点后,48 次里有 33 次是 get/set/delete,
其余是 1 次 publish、1 次 pipeline、1 次 keys、1 次 hgetall。也就是说我们在跑一个
**网络缓存的进程内仿真器**,来做一件字典就能做的事 —— 付出的是异步开销、
字符串序列化、一个额外依赖,以及"它看起来像个数据库所以可以放长期数据"的错觉
(这轮四个缺陷全部出在这个错觉上)。

这一步之所以现在才安全:早先配额、冷却、作息、指标都躺在 Redis 里,
换掉它等于同时搬迁数据。经过存储归位之后,**Redis 只剩缓存**,
没有任何持久数据依赖它,替换就成了纯粹的实现替换。

服务端部署仍然用真 Redis(多进程需要共享状态);这里只接管 EMBEDDED_MODE。
接口按**实际用到的**那部分实现,不追求兼容 Redis 全集 ——
用不到的方法不实现,才不会有人误以为它们能用。
"""

from __future__ import annotations

import asyncio
import fnmatch
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger()


class _Store:
    """
    带过期的键值存储。值为 str(对应 decode_responses=True)或 dict(哈希)。

    用锁保护:同步客户端可能在线程池里被调用,而异步客户端在事件循环里,
    两者共享同一份数据(SSE 广播、缓存必须看到同一份状态)。
    """

    def __init__(self) -> None:
        self._data: Dict[str, Tuple[Any, Optional[float]]] = {}
        self._lock = threading.RLock()

    # -- 内部 ----------------------------------------------------------------

    def _alive(self, key: str) -> bool:
        """惰性过期:读到才判断,不需要后台清理线程。"""
        item = self._data.get(key)
        if item is None:
            return False
        _, expires_at = item
        if expires_at is not None and time.time() >= expires_at:
            self._data.pop(key, None)
            return False
        return True

    def _get_raw(self, key: str) -> Any:
        with self._lock:
            return self._data[key][0] if self._alive(key) else None

    def _set_raw(self, key: str, value: Any, ttl: Optional[float]) -> None:
        with self._lock:
            self._data[key] = (value, (time.time() + ttl) if ttl else None)

    # -- 字符串 --------------------------------------------------------------

    def get(self, key: str) -> Optional[str]:
        v = self._get_raw(key)
        return v if isinstance(v, str) else None

    def set(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        self._set_raw(key, str(value), ex)
        return True

    def incrby(self, key: str, amount: int = 1) -> int:
        with self._lock:
            cur = int(self.get(key) or 0) + int(amount)
            ttl = self._remaining_ttl(key)
            self._set_raw(key, str(cur), ttl)
            return cur

    def incrbyfloat(self, key: str, amount: float) -> float:
        with self._lock:
            cur = float(self.get(key) or 0.0) + float(amount)
            ttl = self._remaining_ttl(key)
            self._set_raw(key, repr(cur), ttl)
            return cur

    def _remaining_ttl(self, key: str) -> Optional[float]:
        item = self._data.get(key)
        if not item or item[1] is None:
            return None
        remaining = item[1] - time.time()
        return remaining if remaining > 0 else None

    # -- 哈希 ----------------------------------------------------------------

    def _hash(self, key: str) -> Dict[str, str]:
        with self._lock:
            v = self._get_raw(key)
            if not isinstance(v, dict):
                v = {}
                self._set_raw(key, v, None)
            return v

    def hincrby(self, key: str, field: str, amount: int = 1) -> int:
        with self._lock:
            h = self._hash(key)
            h[field] = str(int(h.get(field, 0)) + int(amount))
            return int(h[field])

    def hincrbyfloat(self, key: str, field: str, amount: float) -> float:
        with self._lock:
            h = self._hash(key)
            h[field] = repr(float(h.get(field, 0.0)) + float(amount))
            return float(h[field])

    def hgetall(self, key: str) -> Dict[str, str]:
        with self._lock:
            v = self._get_raw(key)
            return dict(v) if isinstance(v, dict) else {}

    # -- 通用 ----------------------------------------------------------------

    def delete(self, *keys: str) -> int:
        with self._lock:
            return sum(1 for k in keys if self._data.pop(k, None) is not None)

    def exists(self, key: str) -> int:
        with self._lock:
            return 1 if self._alive(key) else 0

    def expire(self, key: str, ttl: int) -> bool:
        with self._lock:
            if not self._alive(key):
                return False
            value, _ = self._data[key]
            self._data[key] = (value, time.time() + ttl)
            return True

    def keys(self, pattern: str = "*") -> List[str]:
        with self._lock:
            # 顺带把过期项清掉 —— 这是唯一会全量遍历的操作,适合做清理
            for k in list(self._data):
                self._alive(k)
            return [k for k in self._data if fnmatch.fnmatch(k, pattern)]

    def flushall(self) -> None:
        with self._lock:
            self._data.clear()


class _Hub:
    """
    进程内广播。SSE 是唯一的使用者(chat:stream:{user_id})。

    刻意**不用 asyncio.Queue**:主动关心是由调度线程通过
    run_coroutine_threadsafe 发布的,跨线程/跨事件循环操作 asyncio 原语不安全。
    消费端本来就是 `get_message(timeout=1.0)` 轮询,用带锁的 deque 最简单也最稳。
    """

    def __init__(self) -> None:
        self._subs: Dict[str, List[Deque[str]]] = {}
        self._lock = threading.RLock()

    def register(self, channel: str) -> Deque[str]:
        with self._lock:
            q: Deque[str] = deque(maxlen=1000)
            self._subs.setdefault(channel, []).append(q)
            return q

    def unregister(self, channel: str, q: Deque[str]) -> None:
        with self._lock:
            lst = self._subs.get(channel, [])
            if q in lst:
                lst.remove(q)
            if not lst:
                self._subs.pop(channel, None)

    def publish(self, channel: str, message: str) -> int:
        with self._lock:
            queues = list(self._subs.get(channel, []))
        for q in queues:
            q.append(message)
        return len(queues)


class _PubSub:
    def __init__(self, hub: _Hub) -> None:
        self._hub = hub
        self._queues: Dict[str, Deque[str]] = {}

    async def subscribe(self, *channels: str) -> None:
        for ch in channels:
            if ch not in self._queues:
                self._queues[ch] = self._hub.register(ch)

    async def unsubscribe(self, *channels: str) -> None:
        for ch in list(channels or self._queues):
            q = self._queues.pop(ch, None)
            if q is not None:
                self._hub.unregister(ch, q)

    async def get_message(self, ignore_subscribe_messages: bool = True,
                          timeout: float = 0.0) -> Optional[Dict[str, Any]]:
        deadline = time.time() + max(timeout, 0.0)
        while True:
            for ch, q in self._queues.items():
                if q:
                    return {"type": "message", "channel": ch, "data": q.popleft()}
            if time.time() >= deadline:
                return None
            await asyncio.sleep(0.02)

    async def close(self) -> None:
        await self.unsubscribe()

    aclose = close


class _Pipeline:
    """
    只缓冲命令、execute 时依次执行。

    单进程内不存在网络往返,pipeline 的意义只剩"一组命令一起提交";
    这里按顺序执行即可(budget.py 是唯一使用者:几个 hincrby 加一个 expire)。
    """

    def __init__(self, store: _Store) -> None:
        self._store = store
        self._ops: List[Tuple[str, tuple]] = []

    def hincrby(self, key: str, field: str, amount: int = 1) -> "_Pipeline":
        self._ops.append(("hincrby", (key, field, amount)))
        return self

    def hincrbyfloat(self, key: str, field: str, amount: float) -> "_Pipeline":
        self._ops.append(("hincrbyfloat", (key, field, amount)))
        return self

    def expire(self, key: str, ttl: int) -> "_Pipeline":
        self._ops.append(("expire", (key, ttl)))
        return self

    def set(self, key: str, value: Any, ex: Optional[int] = None) -> "_Pipeline":
        self._ops.append(("set", (key, value, ex)))
        return self

    async def execute(self) -> List[Any]:
        results = []
        for name, args in self._ops:
            results.append(getattr(self._store, name)(*args))
        self._ops.clear()
        return results


# 进程内单例。曾经还有一个同步门面,随 SyncRedisClient 一并删除 ——
# 后者全库零使用者,而为它维护第二套接口只会让人以为存在同步路径
_STORE = _Store()
_HUB = _Hub()


class LocalKVAsync:
    """异步门面。方法名与 redis.asyncio 一致,便于原地替换。"""

    def __init__(self) -> None:
        self._store = _STORE
        self._hub = _HUB

    async def ping(self) -> bool:
        return True

    async def get(self, key: str) -> Optional[str]:
        return self._store.get(key)

    async def set(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        return self._store.set(key, value, ex)

    async def delete(self, *keys: str) -> int:
        return self._store.delete(*keys)

    async def exists(self, key: str) -> int:
        return self._store.exists(key)

    async def expire(self, key: str, ttl: int) -> bool:
        return self._store.expire(key, ttl)

    async def keys(self, pattern: str = "*") -> List[str]:
        return self._store.keys(pattern)

    async def incr(self, key: str) -> int:
        return self._store.incrby(key, 1)

    async def incrby(self, key: str, amount: int = 1) -> int:
        return self._store.incrby(key, amount)

    async def incrbyfloat(self, key: str, amount: float) -> float:
        return self._store.incrbyfloat(key, amount)

    async def hincrby(self, key: str, field: str, amount: int = 1) -> int:
        return self._store.hincrby(key, field, amount)

    async def hincrbyfloat(self, key: str, field: str, amount: float) -> float:
        return self._store.hincrbyfloat(key, field, amount)

    async def hgetall(self, key: str) -> Dict[str, str]:
        return self._store.hgetall(key)

    async def publish(self, channel: str, message: str) -> int:
        return self._hub.publish(channel, message)

    def pubsub(self) -> _PubSub:
        return _PubSub(self._hub)

    def pipeline(self) -> _Pipeline:
        return _Pipeline(self._store)

    async def flushall(self) -> None:
        self._store.flushall()

    async def close(self) -> None:
        return None

    aclose = close


def reset_for_tests() -> None:
    """清空全部状态。仅供测试使用。"""
    _STORE.flushall()
