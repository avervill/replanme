from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routes import plans as routes
from app.schemas.plans import CalendarChangePlan, CreateChange


class FakeDb:
    def __init__(self):
        self.rows = []
        self.commits = 0

    def add(self, row):
        self.rows.append(row)

    async def commit(self):
        self.commits += 1


def pending_plan(change_count: int = 1) -> CalendarChangePlan:
    changes = [
        CreateChange(
            type="create",
            client_ref=f"focus-{index}",
            title=f"Focus block {index}",
            start_at=datetime(2026, 8, 3, 10 + index, tzinfo=UTC),
            end_at=datetime(2026, 8, 3, 11 + index, tzinfo=UTC),
        )
        for index in range(change_count)
    ]
    return CalendarChangePlan(
        id=uuid.uuid4(),
        summary="Create focus time",
        changes=changes,
        expires_at=datetime.now(UTC) + timedelta(minutes=20),
    )


@pytest.mark.asyncio
async def test_apply_plan_executes_only_after_explicit_call(monkeypatch):
    plan = pending_plan()
    user = SimpleNamespace(id=uuid.uuid4())
    db = FakeDb()
    completed = {}
    monkeypatch.setattr(routes, "load_plan", lambda *args, **kwargs: _async_value(plan))
    monkeypatch.setattr(routes, "claim_idempotency", lambda **kwargs: _async_value(None))
    monkeypatch.setattr(routes, "save_plan", lambda *args, **kwargs: _async_value(None))
    monkeypatch.setattr(routes, "create_google_event", lambda *args, **kwargs: _async_value({"id": "g-1"}))

    async def complete(**kwargs):
        completed.update(kwargs["result"])

    monkeypatch.setattr(routes, "complete_idempotency", complete)
    response = await routes.apply_plan(
        plan_id=plan.id,
        idempotency_key="request-12345",
        user=user,
        db=db,
    )
    assert response.plan.status == "applied"
    assert response.applied_event_ids == ["g-1"]
    assert db.rows[0].status == "applied"
    assert completed["plan"]["status"] == "applied"


@pytest.mark.asyncio
async def test_provider_failure_rolls_back_completed_changes(monkeypatch):
    plan = pending_plan(change_count=2)
    user = SimpleNamespace(id=uuid.uuid4())
    db = FakeDb()
    calls = 0
    rolled_back = []
    monkeypatch.setattr(routes, "load_plan", lambda *args, **kwargs: _async_value(plan))
    monkeypatch.setattr(routes, "claim_idempotency", lambda **kwargs: _async_value(None))
    monkeypatch.setattr(routes, "save_plan", lambda *args, **kwargs: _async_value(None))

    async def create(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("provider unavailable")
        return {"id": "g-created"}

    async def delete(*args, **kwargs):
        rolled_back.append(kwargs["event_id"])

    monkeypatch.setattr(routes, "create_google_event", create)
    monkeypatch.setattr(routes, "delete_google_event", delete)
    with pytest.raises(HTTPException) as exc:
        await routes.apply_plan(
            plan_id=plan.id,
            idempotency_key="request-rollback",
            user=user,
            db=db,
        )
    assert exc.value.status_code == 502
    assert rolled_back == ["g-created"]
    assert plan.status == "failed"
    assert db.rows[0].status == "rolled_back"


async def _async_value(value):
    return value
