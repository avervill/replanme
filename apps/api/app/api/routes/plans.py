"""Explicit approval and idempotent execution of calendar change plans."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.calendar_action_audit import CalendarActionAudit
from app.models.user import User
from app.schemas.plans import (
    ApplyPlanResponse,
    CalendarChangePlan,
    CalendarChangePlanDraft,
    CreateChange,
    DeleteChange,
    UpdateChange,
)
from app.services.google_calendar import (
    create_google_event,
    delete_google_event,
    get_google_event,
    update_google_event,
)
from app.services.plans import claim_idempotency, complete_idempotency, load_plan, save_plan

router = APIRouter()


def _event_body(change: CreateChange | UpdateChange) -> dict:
    body: dict = {}
    if change.title is not None:
        body["summary"] = change.title
    if change.description is not None:
        body["description"] = change.description
    if change.location is not None:
        body["location"] = change.location
    if change.start_at is not None:
        body["start"] = {"dateTime": change.start_at.isoformat(), "timeZone": change.timezone or "UTC"}
    if change.end_at is not None:
        body["end"] = {"dateTime": change.end_at.isoformat(), "timeZone": change.timezone or "UTC"}
    return body


@router.put("/{plan_id}", response_model=CalendarChangePlan)
async def update_pending_plan(
    plan_id: uuid.UUID,
    payload: CalendarChangePlanDraft,
    user: User = Depends(get_current_user),
) -> CalendarChangePlan:
    plan = await load_plan(plan_id, user_id=user.id)
    if plan.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only pending plans can be edited")
    plan.summary = payload.summary
    plan.changes = payload.changes
    plan.conflicts = payload.conflicts
    plan.warnings = payload.warnings
    await save_plan(plan, user_id=user.id)
    return plan


@router.post("/{plan_id}/apply", response_model=ApplyPlanResponse)
async def apply_plan(
    plan_id: uuid.UUID,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=255),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApplyPlanResponse:
    plan = await load_plan(plan_id, user_id=user.id)
    cached = await claim_idempotency(user_id=user.id, key=idempotency_key, plan_id=plan_id)
    if cached:
        return ApplyPlanResponse.model_validate(cached)
    if plan.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Plan is already {plan.status}")
    if any(conflict.severity == "blocking" for conflict in plan.conflicts):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Resolve blocking conflicts before applying")

    plan.status = "applying"
    await save_plan(plan, user_id=user.id)
    applied_ids: list[str] = []
    rollback_stack: list[tuple[str, str, dict | None]] = []
    audits: list[CalendarActionAudit] = []

    try:
        for change in plan.changes:
            before = None
            after = None
            event_id = None
            if isinstance(change, CreateChange):
                after = await create_google_event(user.id, db, event_body=_event_body(change))
                event_id = after.get("id")
                rollback_stack.append(("delete", event_id, None))
            elif isinstance(change, UpdateChange):
                before = await get_google_event(user.id, db, event_id=change.event_id)
                after = await update_google_event(user.id, db, event_id=change.event_id, event_body=_event_body(change))
                event_id = change.event_id
                rollback_stack.append(("update", event_id, before))
            elif isinstance(change, DeleteChange):
                before = await get_google_event(user.id, db, event_id=change.event_id)
                await delete_google_event(user.id, db, event_id=change.event_id)
                event_id = change.event_id
                rollback_stack.append(("create", event_id, before))
            if event_id:
                applied_ids.append(event_id)
            audit = CalendarActionAudit(
                user_id=user.id,
                plan_id=plan.id,
                idempotency_key=idempotency_key,
                change_type=change.type,
                provider_event_id=event_id,
                status="applied",
                before_state=before,
                after_state=after,
            )
            db.add(audit)
            audits.append(audit)
        plan.status = "applied"
        await db.commit()
        await save_plan(plan, user_id=user.id)
        response = ApplyPlanResponse(plan=plan, applied_event_ids=applied_ids)
        await complete_idempotency(
            user_id=user.id, key=idempotency_key, plan_id=plan_id, result=response.model_dump(mode="json")
        )
        return response
    except Exception as exc:
        rolled_back = True
        for action, event_id, snapshot in reversed(rollback_stack):
            try:
                if action == "delete":
                    await delete_google_event(user.id, db, event_id=event_id)
                elif action == "update" and snapshot:
                    await update_google_event(user.id, db, event_id=event_id, event_body=snapshot)
                elif action == "create" and snapshot:
                    await create_google_event(user.id, db, event_body=snapshot)
            except Exception:
                rolled_back = False
        for audit in audits:
            audit.status = "rolled_back" if rolled_back else "rollback_failed"
        plan.status = "failed"
        await db.commit()
        await save_plan(plan, user_id=user.id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Calendar provider failed; completed changes were rolled back"
            if rolled_back
            else "Calendar provider failed and rollback needs attention",
        ) from exc
