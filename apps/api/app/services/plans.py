"""Redis persistence and ownership checks for short-lived change plans."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status

from app.core.config import settings
from app.core.redis import get_redis
from app.schemas.plans import CalendarChangePlan


def _plan_key(plan_id: uuid.UUID) -> str:
    return f"plan:{plan_id}"


async def save_plan(plan: CalendarChangePlan, *, user_id: uuid.UUID) -> None:
    redis = await get_redis()
    payload = {"owner": str(user_id), "plan": plan.model_dump(mode="json")}
    await redis.set(_plan_key(plan.id), json.dumps(payload), ex=settings.plan_ttl_seconds)


async def load_plan(plan_id: uuid.UUID, *, user_id: uuid.UUID) -> CalendarChangePlan:
    redis = await get_redis()
    raw = await redis.get(_plan_key(plan_id))
    if not raw:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Plan expired or does not exist")
    payload = json.loads(raw)
    if payload.get("owner") != str(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    plan = CalendarChangePlan.model_validate(payload["plan"])
    if plan.expires_at <= datetime.now(UTC):
        plan.status = "expired"
        await save_plan(plan, user_id=user_id)
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Plan expired")
    return plan


async def claim_idempotency(*, user_id: uuid.UUID, key: str, plan_id: uuid.UUID) -> dict | None:
    redis = await get_redis()
    cache_key = f"idempotency:{user_id}:{key}"
    existing = await redis.get(cache_key)
    if existing:
        payload = json.loads(existing)
        if payload.get("plan_id") != str(plan_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Idempotency-Key was already used for another plan"
            )
        if payload.get("result") is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Plan application is already in progress")
        return payload["result"]
    claimed = await redis.set(
        cache_key,
        json.dumps({"plan_id": str(plan_id), "result": None}),
        ex=settings.session_ttl_seconds,
        nx=True,
    )
    if not claimed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Plan application is already in progress")
    return None


async def complete_idempotency(*, user_id: uuid.UUID, key: str, plan_id: uuid.UUID, result: dict) -> None:
    redis = await get_redis()
    await redis.set(
        f"idempotency:{user_id}:{key}",
        json.dumps({"plan_id": str(plan_id), "result": result}),
        ex=settings.session_ttl_seconds,
    )
