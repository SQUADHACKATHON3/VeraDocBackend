"""
Optional Redis connection for caching, rate limits, etc.

Set ``REDIS_URL`` in the environment. If unset, ``get_redis()`` returns ``None``.
"""

from __future__ import annotations

import threading

import redis
from redis import Redis

from app.core.config import settings

_pool: redis.ConnectionPool | None = None
_client: Redis | None = None
_lock = threading.Lock()


def get_redis() -> Redis | None:
    """Shared Redis client, or ``None`` when ``REDIS_URL`` is not set."""
    global _pool, _client

    if not settings.redis_url:
        return None
    if _client is not None:
        return _client
    with _lock:
        if _client is not None:
            return _client
        _pool = redis.ConnectionPool.from_url(
            settings.redis_url,
            decode_responses=True,
            health_check_interval=30,
        )
        _client = Redis(connection_pool=_pool)
        return _client


def close_redis() -> None:
    """Close pool and client (call from app shutdown)."""
    global _pool, _client

    with _lock:
        if _client is not None:
            _client.close()
            _client = None
        if _pool is not None:
            _pool.disconnect()
            _pool = None
