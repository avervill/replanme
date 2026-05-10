"""Subscription and usage routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.subscription import UsageSummaryResponse
from app.services import analytics
from app.services.subscriptions import build_usage_summary

router = APIRouter()


@router.get("/usage", response_model=UsageSummaryResponse)
async def get_usage_summary(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    summary = await build_usage_summary(db, user)
    await db.commit()
    return summary


@router.post("/upgrade-clicked")
async def track_upgrade_clicked(
    payload: dict | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    source = str((payload or {}).get("source") or "unknown")
    await analytics.track_upgrade_clicked(db, user.id, source, payload or {})
    await db.commit()
    return {"ok": True}


@router.post("/onboarding-event")
async def track_onboarding_event(
    payload: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    event_name = str(payload.get("eventName") or "")
    if event_name not in {"onboarding_started", "onboarding_completed"}:
        return {"ok": False}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    await analytics.track_event(db, user.id, event_name, metadata)
    await db.commit()
    return {"ok": True}
