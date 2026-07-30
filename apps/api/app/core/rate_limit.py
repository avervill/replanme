"""Redis-backed fixed-window rate limits for user-facing AI endpoints."""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.core.redis import get_redis


async def enforce_rate_limit(request: Request, *, bucket: str, identity: str) -> None:
    redis = await get_redis()
    key = f"rate:{bucket}:{identity}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, settings.rate_limit_window_seconds)
    if count > settings.rate_limit_requests:
        retry_after = max(await redis.ttl(key), 1)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again shortly.",
            headers={"Retry-After": str(retry_after)},
        )
