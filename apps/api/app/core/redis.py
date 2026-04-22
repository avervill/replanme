"""Redis async connection pool."""

from __future__ import annotations

import redis.asyncio as aioredis

from app.core.config import settings

_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Return a shared async Redis connection (lazy-init)."""
    global _pool
    if _pool is None:
        _pool = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
    return _pool


async def close_redis() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
