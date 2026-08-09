"""
后台任务派发。

嵌入模式下不存在消息队列:`_EmbeddedArqShim` 直接在当前事件循环里以后台任务
调用目标函数(worker 并入后端进程,去掉独立 worker 与 broker)。
server 部署仍走 ARQ + Redis。

对调用方而言两者接口一致(`await pool.enqueue_job(name, *args)`),
所以 chat.py / scheduler 不需要感知模式差异。

这部分原先住在 `core/redis.py` —— 名字与内容不符,而嵌入模式下它根本不碰 Redis。
"""

import asyncio
from typing import Optional

import structlog
from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from .config import settings

logger = structlog.get_logger()


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
