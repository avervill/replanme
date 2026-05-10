from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics_event import AnalyticsEvent
from app.models.planning_request import PlanningRequest


async def track_event(
    db: AsyncSession,
    user_id: uuid.UUID | None,
    event_name: str,
    metadata: dict[str, Any] | None = None,
    *,
    feature: str | None = None,
) -> None:
    db.add(
        AnalyticsEvent(
            user_id=user_id,
            event_name=event_name,
            feature=feature,
            metadata_json=metadata or None,
        )
    )
    await db.flush()


async def track_paywall_shown(
    db: AsyncSession,
    user_id: uuid.UUID | None,
    feature: str | None,
    reason: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    await track_event(
        db,
        user_id,
        "paywall_shown",
        {"reason": reason, **(metadata or {})},
        feature=feature,
    )


async def track_upgrade_clicked(
    db: AsyncSession,
    user_id: uuid.UUID | None,
    source: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    await track_event(db, user_id, "upgrade_clicked", {"source": source, **(metadata or {})})


async def track_planning_request(
    db: AsyncSession,
    *,
    user_id: uuid.UUID | None,
    prompt: str | None,
    intent: str | None,
    feature: str | None,
    estimated_credits: int,
) -> PlanningRequest:
    request = PlanningRequest(
        user_id=user_id,
        prompt=prompt,
        intent=intent,
        feature=feature,
        estimated_credits=estimated_credits,
        status="started",
    )
    db.add(request)
    await db.flush()
    await track_event(
        db,
        user_id,
        "planning_request_started",
        {"planningRequestId": str(request.id), "estimatedCredits": estimated_credits},
        feature=feature,
    )
    return request


async def update_planning_request(
    db: AsyncSession,
    request: PlanningRequest | None,
    **values: Any,
) -> None:
    if request is None:
        return
    for key, value in values.items():
        if hasattr(request, key):
            setattr(request, key, value)
    db.add(request)
    await db.flush()
