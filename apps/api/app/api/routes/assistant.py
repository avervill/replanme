"""SSE assistant endpoint that returns proposals without calendar writes."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import enforce_rate_limit
from app.core.security import get_current_user
from app.models.energy_profile import PlanningProfile
from app.models.planning_request import PlanningRun
from app.models.user import User
from app.schemas.assistant_v1 import AssistantMessageRequest
from app.services.assistant.graph import planner_graph
from app.services.google_calendar import list_google_events_in_range
from app.services.plans import save_plan

router = APIRouter()


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"


@router.post("/messages")
async def assistant_messages(
    payload: AssistantMessageRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    await enforce_rate_limit(request, bucket="assistant", identity=str(user.id))

    async def stream():
        run = PlanningRun(user_id=user.id, prompt=payload.message, status="started")
        db.add(run)
        await db.flush()
        try:
            yield _sse("status", {"stage": "context", "message": "Reading your calendar and energy profile"})
            start = datetime.fromisoformat(payload.range_start) if payload.range_start else datetime.now(UTC)
            end = datetime.fromisoformat(payload.range_end) if payload.range_end else start + timedelta(days=14)
            events = await list_google_events_in_range(user.id, db, start_at=start, end_at=end)
            profile_result = await db.execute(select(PlanningProfile).where(PlanningProfile.user_id == user.id))
            profile = profile_result.scalar_one_or_none()

            yield _sse("status", {"stage": "plan", "message": "Building a safe proposal"})
            result = await planner_graph.ainvoke(
                {
                    "user_id": str(user.id),
                    "prompt": payload.message,
                    "timezone": payload.timezone,
                    "events": events,
                    "profile": {
                        "energy_windows": profile.energy_windows if profile else [],
                        "preferences": profile.preferences if profile else {},
                    },
                }
            )
            plan = result["plan"]
            await save_plan(plan, user_id=user.id)
            run.route = result.get("route")
            run.model_used = "gpt-5.6-terra"
            run.status = "awaiting_approval"
            run.plan_snapshot = plan.model_dump(mode="json")
            await db.commit()
            yield _sse("delta", {"text": result["summary"]})
            yield _sse("plan", plan.model_dump(mode="json"))
            yield _sse("done", {"status": "awaiting_approval"})
        except Exception as exc:
            run.status = "failed"
            run.error_message = type(exc).__name__
            await db.commit()
            yield _sse(
                "error",
                {
                    "code": "planning_failed",
                    "message": "I could not build a safe proposal. Your calendar was not changed.",
                },
            )
            yield _sse("done", {"status": "failed"})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
