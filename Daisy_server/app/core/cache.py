"""
缓存客户端与缓存装饰器。

嵌入模式下由 `core/local_kv.py` 提供实现(进程内),server 部署用真 Redis。
调用方只认这里的 `redis_client` 门面,不需要知道背后是哪一种。

**这里只有缓存。** 后台任务派发在 `core/task_queue.py` —— 两者曾同住一个名为
redis.py 的文件,而找"任务怎么派发"的人不会想到去看 redis.py;
何况嵌入模式下这两件事都已不涉及 Redis,文件名本身就在误导。
"""

import functools
import hashlib
import json
from typing import Any, Callable, Optional

import redis.asyncio as redis
import structlog

from .config import settings

logger = structlog.get_logger()

# 外部 Redis 的连接超时。默认(75s)会让配错地址表现为"启动卡住"而非报错。
REDIS_CONNECT_TIMEOUT_SEC = 5

# 嵌入模式下不再使用 fakeredis,改为进程内实现(见 core/local_kv.py)。
# 同步与异步门面共享同一份数据,保证 SSE 广播、缓存看到一致的状态。
#
# 换掉 fakeredis 的理由:全部调用点里 33/48 是 get/set/delete,剩下是
# 1 次 publish、1 次 pipeline、1 次 keys、1 次 hgetall —— 我们在跑一个
# 网络缓存的仿真器来做字典的事。除了多一个依赖,它还制造了一个更贵的错觉:
# "它看起来像数据库,所以可以往里放长期数据" —— 而它重启即空,
# 主动关心的配额/冷却/作息和 SLO 指标都栽在这上面。

# 说明:这里原先有一个 EmotionalState 模型和 get/set_emotional_state 两个方法。
# 全库**没有任何地方写过** user:{uid}:emotional_state —— set 只在 get 内部的
# 衰减回写里被调用,而那要求键已存在。于是 get 永远返回默认对象,
# 且 pydantic 模型恒为真,调用方的 `if` 拦不住,结果每次生成都往提示词注入
# 「当前情感状态: Neutral (强度: 0)」—— 一个与事实相反且完全静默的信号。
# 真实情绪本就在图状态里(analyze 节点的 top_emotions),已改为直接使用。

class RedisClient:
    """
    Asynchronous Redis client for general application use.
    """
    _instance = None
    
    def __init__(self):
        self.redis: Optional[redis.Redis] = None
        self.enabled = False

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = RedisClient()
        return cls._instance

    async def connect(self):
        """
        Connect to Redis server.
        """
        try:
            if settings.EMBEDDED_MODE:
                from .local_kv import LocalKVAsync
                self.redis = LocalKVAsync()
                await self.redis.ping()
                self.enabled = True
                logger.info("缓存就绪(进程内实现,重启即清空 —— 只放缓存)。")
                return
            self.redis = redis.from_url(
                f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
                password=settings.REDIS_PASSWORD,
                encoding="utf-8",
                decode_responses=True,
                # 不设超时会走系统默认(实测 75 秒)。地址配错时启动会长时间"卡住"
                # 而非报错 —— 用户只看到 "Waiting for application startup",
                # 完全无法判断发生了什么。宁可快速失败并给出可读原因。
                socket_connect_timeout=REDIS_CONNECT_TIMEOUT_SEC,
                socket_timeout=REDIS_CONNECT_TIMEOUT_SEC,
            )
            # Ping to verify connection
            await self.redis.ping()
            self.enabled = True
            logger.info(f"Async Redis connected successfully to {settings.REDIS_HOST}:{settings.REDIS_PORT}")
        except Exception as e:
            # 这条提示要能自解释:项目已去 Docker,单机桌面版根本不需要外部 Redis。
            # 绝大多数情况下是"忘了开 EMBEDDED_MODE",而不是 Redis 真的挂了。
            logger.error(
                f"连接 Redis 失败({settings.REDIS_HOST}:{settings.REDIS_PORT}):{e}。"
                f"若在本机开发/单机运行,应设 EMBEDDED_MODE=true —— "
                f"嵌入模式用进程内缓存,不需要任何外部服务。"
            )
            self.enabled = False

    async def close(self):
        if self.redis:
            await self.redis.close()
            logger.info("Async Redis connection closed.")
            self.enabled = False

    # Wrapper methods to provide cleaner interface
    async def get(self, key: str) -> Any:
        if not self.enabled: return None
        try:
            return await self.redis.get(key)
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            return None
            
    async def set(self, key: str, value: Any, ttl: int = None):
        if not self.enabled: return
        try:
            await self.redis.set(key, value, ex=ttl)
        except Exception as e:
            logger.error(f"Redis set error: {e}")

    async def expire(self, key: str, ttl: int):
        if not self.enabled: return
        try:
            await self.redis.expire(key, ttl)
        except Exception as e:
            logger.error(f"Redis expire error: {e}")

    async def delete(self, key: str):
        if not self.enabled: return
        try:
            await self.redis.delete(key)
        except Exception as e:
            logger.error(f"Redis delete error: {e}")

    async def exists(self, key: str) -> int:
        if not self.enabled: return 0
        try:
            return await self.redis.exists(key)
        except Exception as e:
            logger.error(f"Redis exists error: {e}")
            return 0

    # 说明:原先这里有 keys(pattern)。它唯一的使用者 get_online_users() 从未被
    # 生产代码调用过,两者已一并移除。keys() 是 O(全部键) 的扫描,
    # 留一个没人用的扫描接口只会诱导后来者去用它。

    async def hincrby(self, key: str, field: str, amount: int = 1):
        if not self.enabled: return
        try:
            await self.redis.hincrby(key, field, amount)
        except Exception as e:
            logger.error(f"Redis hincrby error: {e}")

    async def hgetall(self, key: str) -> dict:
        if not self.enabled: return {}
        try:
            return await self.redis.hgetall(key)
        except Exception as e:
            logger.error(f"Redis hgetall error: {e}")
            return {}

# Global instance
redis_client = RedisClient.get_instance()

def cache_result(ttl: int = 3600, key_prefix: str = "", key_builder: Callable = None,
                 should_cache: Optional[Callable[[Any], bool]] = None):
    """
    Decorator to cache async function results in Redis.
    Uses function name and arguments to generate key.
    If key_builder is provided, it's used to generate the key part from arguments.

    should_cache(result) 返回 False 时只返回结果、不写缓存。用于"算出来了但不可信"
    的结果:情绪分析在翻译失败/模型报错时返回空字典,若照常缓存 24 小时,
    一次 LLM 抖动就会把这段文本钉死成"没有情绪",之后每轮都命中这个坏答案。
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            if not redis_client.enabled:
                return await func(*args, **kwargs)
                
            # Generate cache key
            if key_builder:
                try:
                    key_part = key_builder(*args, **kwargs)
                except Exception as e:
                     logger.warning(f"Key builder failed for {func.__name__}: {e}")
                     return await func(*args, **kwargs)
            else:
                arg_str = str(args) + str(sorted(kwargs.items()))
                key_part = hashlib.md5(arg_str.encode()).hexdigest()
            
            key = f"cache:{key_prefix}:{func.__name__}:{key_part}"
            
            # Try get from cache
            cached = await redis_client.get(key)
            if cached:
                try:
                    return json.loads(cached)
                except:
                    return cached
            
            # Call function
            result = await func(*args, **kwargs)
            
            # Cache result
            if result is not None:
                try:
                    if should_cache is not None and not should_cache(result):
                        return result
                    if isinstance(result, (dict, list, str, int, float, bool)):
                        val = json.dumps(result)
                        await redis_client.set(key, val, ttl=ttl)
                except Exception as e:
                    logger.warning(f"Failed to cache result for {func.__name__}: {e}")
            
            return result
        return wrapper
    return decorator
