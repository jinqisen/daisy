"""
Redis 测试工具:解决「全局 redis_client 连接绑定到已关闭事件循环」的串扰问题。

- probe_redis(): 用独立的一次性连接探测可用性,不触碰全局 redis_client。
- fresh_connect(): 在当前事件循环内重置并重连全局 redis_client;
  每个使用 asyncio.run 的测试都应先调用它,避免复用其他循环里创建的连接。
"""

import asyncio
from contextlib import asynccontextmanager


def probe_redis() -> bool:
    """独立连接探测本地 Redis 可用性(不污染全局 redis_client)。"""

    async def _probe() -> bool:
        try:
            import redis.asyncio as aioredis
            from app.core.config import settings
            client = aioredis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT,
                                    socket_connect_timeout=2)
            try:
                await client.ping()
                return True
            finally:
                await client.aclose()
        except Exception:
            return False

    return asyncio.run(_probe())


async def fresh_connect():
    """在当前事件循环内强制重建全局 redis_client 连接。"""
    from app.core.redis import redis_client
    try:
        if redis_client.redis is not None:
            await redis_client.redis.aclose()
    except Exception:
        pass
    redis_client.redis = None
    redis_client.enabled = False
    await redis_client.connect()
    return redis_client


@asynccontextmanager
async def fresh_redis():
    """
    fresh_connect 的上下文封装:退出时恢复 redis_client 为「未连接」状态,
    避免把连接留给其他默认按无 Redis 运行的测试(如 route 缓存测试)。
    """
    client = await fresh_connect()
    try:
        yield client
    finally:
        try:
            if client.redis is not None:
                await client.redis.aclose()
        except Exception:
            pass
        client.redis = None
        client.enabled = False
