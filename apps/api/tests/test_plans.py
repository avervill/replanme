from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.plans import CalendarChangePlan, CalendarChangePlanDraft, CreateChange, DeleteChange
from app.services import plans
from app.services.assistant.graph import approval_node, safety_node


def create_change() -> CreateChange:
    return CreateChange(
        type="create",
        client_ref="stats-review",
        title="Statistics review",
        start_at=datetime(2026, 8, 3, 10, tzinfo=UTC),
        end_at=datetime(2026, 8, 3, 11, 30, tzinfo=UTC),
        timezone="UTC",
    )


def test_change_rejects_invalid_range():
    with pytest.raises(ValidationError):
        CreateChange(
            type="create",
            client_ref="bad",
            title="Impossible",
            start_at=datetime(2026, 8, 3, 12, tzinfo=UTC),
            end_at=datetime(2026, 8, 3, 11, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_safety_warns_for_destructive_change():
    draft = CalendarChangePlanDraft(
        summary="Remove a duplicate",
        changes=[DeleteChange(type="delete", event_id="event-1", title="Duplicate", reason="Duplicate import")],
    )
    result = await safety_node({"draft": draft})
    assert "deletes" in result["draft"].warnings[0]


@pytest.mark.asyncio
async def test_approval_creates_pending_expiring_plan():
    draft = CalendarChangePlanDraft(summary="Add one focus block", changes=[create_change()])
    result = await approval_node({"draft": draft})
    assert result["plan"].status == "pending"
    assert result["plan"].expires_at > datetime.now(UTC)


@pytest.mark.asyncio
async def test_plan_store_enforces_ownership_and_idempotency(monkeypatch, fake_redis):
    monkeypatch.setattr(plans, "get_redis", lambda: _async_value(fake_redis))
    owner = uuid.uuid4()
    plan = CalendarChangePlan(
        id=uuid.uuid4(),
        summary="Add a focus block",
        changes=[create_change()],
        expires_at=datetime.now(UTC) + timedelta(minutes=20),
    )
    await plans.save_plan(plan, user_id=owner)
    loaded = await plans.load_plan(plan.id, user_id=owner)
    assert loaded.id == plan.id
    with pytest.raises(HTTPException) as exc:
        await plans.load_plan(plan.id, user_id=uuid.uuid4())
    assert exc.value.status_code == 404

    key = "request-12345"
    assert await plans.claim_idempotency(user_id=owner, key=key, plan_id=plan.id) is None
    with pytest.raises(HTTPException) as inflight:
        await plans.claim_idempotency(user_id=owner, key=key, plan_id=plan.id)
    assert inflight.value.status_code == 409
    await plans.complete_idempotency(user_id=owner, key=key, plan_id=plan.id, result={"ok": True})
    assert await plans.claim_idempotency(user_id=owner, key=key, plan_id=plan.id) == {"ok": True}


async def _async_value(value):
    return value
