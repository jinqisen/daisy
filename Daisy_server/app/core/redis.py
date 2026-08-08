import asyncio
import json
import hashlib
import functools
import time
from pydantic import BaseModel, Field
from typing import Optional, Any, Callable, Union
import redis.asyncio as redis
import redis as sync_redis
import structlog
from arq import create_pool
from arq.connections import RedisSettings, ArqRedis
from .config import settings

logger = structlog.get_logger()

# 外部 Redis 的连接超时。默认(75s)会让配错地址表现为"启动卡住"而非报错。
REDIS_CONNECT_TIMEOUT_SEC = 5

# 嵌入模式下同步/异步 fakeredis 共享同一个内存服务器,保证跨 client 数据一致
# (例如 SSE 发布订阅、缓存、指标计数必须落在同一份内存上)。
_FAKE_SERVER = None


def _get_fake_server():
    global _FAKE_SERVER
    if _FAKE_SERVER is None:
        import fakeredis
        _FAKE_SERVER = fakeredis.FakeServer()
    return _FAKE_SERVER

class SyncRedisClient:
    """
    Synchronous Redis client for use in synchronous contexts (e.g. LLMService).
    """
    _instance = None

    def __init__(self):
        self.redis: Optional[sync_redis.Redis] = None
        self.enabled = False

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = SyncRedisClient()
        return cls._instance

    def connect(self):
        try:
            if settings.EMBEDDED_MODE:
                import fakeredis
                self.redis = fakeredis.FakeStrictRedis(
                    server=_get_fake_server(), decode_responses=True
                )
                self.enabled = True
                logger.info("Sync Redis (embedded fakeredis) ready.")
                return
            self.redis = sync_redis.from_url(
                f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
                password=settings.REDIS_PASSWORD,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=REDIS_CONNECT_TIMEOUT_SEC,
                socket_timeout=REDIS_CONNECT_TIMEOUT_SEC,
            )
            self.redis.ping()
            self.enabled = True
            logger.info("Sync Redis connected successfully.")
        except Exception as e:
            logger.warning(f"Failed to connect to Sync Redis: {e}. Sync operations will fallback or fail.")
            self.enabled = False

    def get(self, key: str) -> Any:
        if not self.enabled or not self.redis:
            return None
        try:
            data = self.redis.get(key)
            # Try to parse as JSON if it looks like one, otherwise return string
            if data:
                try:
                    return json.loads(data)
                except (json.JSONDecodeError, TypeError):
                    return data
            return None
        except Exception as e:
            logger.error(f"Sync Redis get error: {e}")
            return None
            
    def set(self, key: str, value: Any, ttl: int = None):
        if not self.enabled or not self.redis:
            return
        try:
            if isinstance(value, (dict, list)):
                data = json.dumps(value)
            else:
                data = str(value)
            self.redis.set(key, data, ex=ttl)
        except Exception as e:
            logger.error(f"Sync Redis set error: {e}")

# =============================================================================
# Step 3.1: Emotional State Model (Stored in Redis)
# =============================================================================

class EmotionalState(BaseModel):
    current_mood: str = "Neutral"
    intensity: int = Field(0, ge=0, le=100)
    last_update: float = Field(default_factory=time.time)
    decay_rate: int = 5 # Points per minute
    
    def apply_decay(self):
        """Apply time-based decay to intensity"""
        now = time.time()
        elapsed_minutes = (now - self.last_update) / 60.0
        if elapsed_minutes > 0:
            decay_amount = int(elapsed_minutes * self.decay_rate)
            self.intensity = max(0, self.intensity - decay_amount)
            self.last_update = now

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
                import fakeredis.aioredis
                self.redis = fakeredis.aioredis.FakeRedis(
                    server=_get_fake_server(), decode_responses=True
                )
                await self.redis.ping()
                self.enabled = True
                logger.info("Async Redis (embedded fakeredis) ready.")
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
                f"嵌入模式用进程内 fakeredis,不需要任何外部服务。"
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

    async def keys(self, pattern: str) -> list:
        if not self.enabled: return []
        try:
            return await self.redis.keys(pattern)
        except Exception as e:
            logger.error(f"Redis keys error: {e}")
            return []

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

    async def get_emotional_state(self, user_id: str) -> EmotionalState:
        """Fetch and decay emotional state"""
        key = f"user:{user_id}:emotional_state"
        data = await self.get(key)
        if data:
            try:
                state = EmotionalState(**json.loads(data))
                # Apply decay on read
                original_intensity = state.intensity
                state.apply_decay()
                if state.intensity != original_intensity:
                    # Update back to Redis if decayed
                    await self.set_emotional_state(user_id, state)
                return state
            except Exception as e:
                logger.error(f"Failed to parse emotional state: {e}")
        return EmotionalState()

    async def set_emotional_state(self, user_id: str, state: EmotionalState):
        """Save emotional state"""
        key = f"user:{user_id}:emotional_state"
        await self.set(key, state.model_dump_json(), ttl=86400) # 24h TTL

# Global instance
redis_client = RedisClient.get_instance()
sync_redis_client = SyncRedisClient.get_instance()

class _EmbeddedArqShim:
    """
    嵌入模式下替代 ARQ 连接池:enqueue_job 不进消息队列,而是在当前事件循环内
    以后台任务直接调用对应任务函数(worker 并入后端,去掉独立 worker 与 broker)。
    对调用方保持与 ArqRedis 相同的 async enqueue_job 接口,故 chat.py / scheduler
    无需感知模式差异。
    """
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = _EmbeddedArqShim()
        return cls._instance

    def _resolve(self, name: str):
        # 走注册表而非直接 import tasks —— core 是最底层,不应认识上层模块。
        # 任务在 app/tasks/__init__.py 被导入时自行登记(见 core/job_registry.py)。
        from .job_registry import resolve_job
        return resolve_job(name)

    async def enqueue_job(self, name: str, *args, **kwargs):
        fn = self._resolve(name)
        if fn is None:
            logger.error(f"EmbeddedArqShim: unknown job '{name}'")
            return None

        # 任务函数签名为 (ctx, *args);ctx.redis 提供同款 enqueue_job 以支持任务内再分发
        async def _runner():
            try:
                await fn({"redis": self}, *args)
            except Exception as e:
                logger.error(f"EmbeddedArqShim: job '{name}' failed: {e}", exc_info=True)

        asyncio.create_task(_runner())
        return None

    async def close(self):
        return None


class ARQClient:
    """
    Manages ARQ Redis connection pool.
    """
    _pool: Optional[ArqRedis] = None

    @classmethod
    async def get_pool(cls) -> ArqRedis:
        if settings.EMBEDDED_MODE:
            return _EmbeddedArqShim.get_instance()
        if cls._pool is None:
             try:
                 cls._pool = await create_pool(
                    RedisSettings(
                        host=settings.REDIS_HOST,
                        port=settings.REDIS_PORT,
                        database=settings.REDIS_DB,
                        password=settings.REDIS_PASSWORD
                    )
                )
                 logger.info("ARQ Redis Pool created.")
             except Exception as e:
                 logger.error(f"Failed to create ARQ Redis Pool: {e}")
                 raise e
        return cls._pool

    @classmethod
    async def close(cls):
        if cls._pool:
            await cls._pool.close()
            cls._pool = None
            logger.info("ARQ Redis Pool closed.")

async def get_arq_pool() -> ArqRedis:
    """
    Dependency to get ARQ Redis pool.
    """
    return await ARQClient.get_pool()

def cache_result(ttl: int = 3600, key_prefix: str = "", key_builder: Callable = None):
    """
    Decorator to cache async function results in Redis.
    Uses function name and arguments to generate key.
    If key_builder is provided, it's used to generate the key part from arguments.
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
                    if isinstance(result, (dict, list, str, int, float, bool)):
                        val = json.dumps(result)
                        await redis_client.set(key, val, ttl=ttl)
                except Exception as e:
                    logger.warning(f"Failed to cache result for {func.__name__}: {e}")
            
            return result
        return wrapper
    return decorator
