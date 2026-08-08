from __future__ import annotations

from typing import Optional
import socket

import redis as redis_sync
import redis.asyncio as redis_async

from ..core.config import settings


_client: Optional[redis_sync.Redis] = None
_async_client: Optional[redis_async.Redis] = None


def _is_tcp_open(host: str, port: int, timeout_sec: float = 0.35) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_sec):
            return True
    except OSError:
        return False


def _resolve_redis_host(host: str, port: int) -> str:
    if _is_tcp_open(host, port):
        return host
    if host not in {"localhost", "127.0.0.1"} and _is_tcp_open("localhost", port):
        return "localhost"
    return host


def get_redis_client() -> redis_sync.Redis:
    global _client
    if _client is None:
        host = _resolve_redis_host(settings.REDIS_HOST, settings.REDIS_PORT)
        _client = redis_sync.Redis(
            host=host,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=2,
            retry_on_timeout=True,
        )
    return _client


def get_async_redis_client() -> redis_async.Redis:
    global _async_client
    if _async_client is None:
        host = _resolve_redis_host(settings.REDIS_HOST, settings.REDIS_PORT)
        _async_client = redis_async.Redis(
            host=host,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=2,
            retry_on_timeout=True,
        )
    return _async_client


redis_client = get_redis_client()
async_redis_client = get_async_redis_client()
