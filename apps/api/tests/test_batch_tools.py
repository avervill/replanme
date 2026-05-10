import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.schemas.assistant import BatchDeleteEventsInput, BatchMoveEventsInput, UserPlanningMemory
from app.services.assistant.tools import AssistantToolRegistry


def _google_event(event_id, title, start_at, end_at):
    return {
        "id": event_id,
        "summary": title,
        "start": {"dateTime": start_at.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": end_at.isoformat(), "timeZone": "UTC"},
        "status": "confirmed",
    }


def test_batch_move_dry_run_returns_preview_without_mutations(monkeypatch):
    start = datetime(2026, 5, 2, 9, tzinfo=UTC)
    events = [
        _google_event("evt-1", "Gym", start, start + timedelta(hours=1)),
        _google_event("evt-2", "Lunch", start + timedelta(hours=2), start + timedelta(hours=3)),
    ]
    update_calls = []

    async def fake_list_events(*args, **kwargs):
        return events

    async def fake_update_event(*args, **kwargs):
        update_calls.append(kwargs)
        return {}

    monkeypatch.setattr("app.services.assistant.tools.list_google_events_in_range", fake_list_events)
    monkeypatch.setattr("app.services.assistant.tools.update_google_event", fake_update_event)

    async def run():
        result = await AssistantToolRegistry().batch_move_events(
            BatchMoveEventsInput(
                start_at=start,
                end_at=start + timedelta(days=1),
                offset_minutes=120,
                query="Gym",
                dry_run=True,
            ),
            user=SimpleNamespace(id="user-1", timezone="UTC"),
            db=None,
            memory=UserPlanningMemory(),
        )

        assert result.count == 1
        assert result.metadata.executed is False
        assert update_calls == []
        assert result.moved_events[0].start_at == start + timedelta(hours=2)
        assert result.preview[0].proposed_start_at == start + timedelta(hours=2)

    asyncio.run(run())


def test_batch_move_execute_applies_offsets_and_generates_rollback(monkeypatch):
    start = datetime(2026, 5, 2, 9, tzinfo=UTC)
    events = [_google_event("evt-1", "Gym", start, start + timedelta(hours=1))]
    update_bodies = []

    async def fake_list_events(*args, **kwargs):
        return events

    async def fake_update_event(*args, **kwargs):
        update_bodies.append(kwargs["event_body"])
        return {}

    monkeypatch.setattr("app.services.assistant.tools.list_google_events_in_range", fake_list_events)
    monkeypatch.setattr("app.services.assistant.tools.update_google_event", fake_update_event)

    async def run():
        result = await AssistantToolRegistry().batch_move_events(
            BatchMoveEventsInput(
                start_at=start,
                end_at=start + timedelta(days=1),
                offset_minutes=30,
            ),
            user=SimpleNamespace(id="user-1", timezone="UTC"),
            db=None,
            memory=UserPlanningMemory(),
        )

        assert result.metadata.executed is True
        assert update_bodies[0]["start"]["dateTime"] == (start + timedelta(minutes=30)).isoformat()
        assert result.rollback[0].action == "edit_event"
        assert result.rollback[0].payload["event_id"] == "evt-1"

    asyncio.run(run())


def test_batch_delete_filters_by_query_and_time_and_generates_rollback(monkeypatch):
    day = datetime(2026, 5, 2, tzinfo=UTC)
    events = [
        _google_event("evt-1", "Gym", day.replace(hour=9), day.replace(hour=10)),
        _google_event("evt-2", "Gym", day.replace(hour=19), day.replace(hour=20)),
        _google_event("evt-3", "Dinner", day.replace(hour=19), day.replace(hour=20)),
    ]
    deleted_ids = []

    async def fake_list_events(*args, **kwargs):
        return events

    async def fake_delete_event(*args, **kwargs):
        deleted_ids.append(kwargs["event_id"])

    monkeypatch.setattr("app.services.assistant.tools.list_google_events_in_range", fake_list_events)
    monkeypatch.setattr("app.services.assistant.tools.delete_google_event", fake_delete_event)

    async def run():
        result = await AssistantToolRegistry().batch_delete_events(
            BatchDeleteEventsInput(
                start_at=day,
                end_at=day + timedelta(days=1),
                query="Gym",
                time_filter="evening",
            ),
            user=SimpleNamespace(id="user-1", timezone="UTC"),
            db=None,
            memory=UserPlanningMemory(),
        )

        assert result.count == 1
        assert deleted_ids == ["evt-2"]
        assert result.deleted_events[0].title == "Gym"
        assert result.rollback[0].action == "create_event"
        assert result.rollback[0].payload["title"] == "Gym"

    asyncio.run(run())


def test_batch_delete_treats_meetings_as_generic_calendar_events(monkeypatch):
    day = datetime(2026, 5, 4, tzinfo=UTC)
    events = [
        _google_event("evt-1", "DBMS final", day.replace(hour=11), day.replace(hour=13)),
        _google_event("evt-2", "Internship", day.replace(hour=15), day.replace(hour=17)),
    ]
    deleted_ids = []

    async def fake_list_events(*args, **kwargs):
        return events

    async def fake_delete_event(*args, **kwargs):
        deleted_ids.append(kwargs["event_id"])

    monkeypatch.setattr("app.services.assistant.tools.list_google_events_in_range", fake_list_events)
    monkeypatch.setattr("app.services.assistant.tools.delete_google_event", fake_delete_event)

    async def run():
        result = await AssistantToolRegistry().batch_delete_events(
            BatchDeleteEventsInput(
                start_at=day,
                end_at=day + timedelta(days=7),
                query="meetings",
            ),
            user=SimpleNamespace(id="user-1", timezone="UTC"),
            db=None,
            memory=UserPlanningMemory(),
        )

        assert result.count == 2
        assert deleted_ids == ["evt-1", "evt-2"]
        assert [event.title for event in result.deleted_events] == ["DBMS final", "Internship"]

    asyncio.run(run())
