import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.llm.agent import (
    _classify_prompt_intent,
    _date_from_prompt,
    _extract_simple_calendar_command,
    _latest_create_prompt_from_title_clarification,
    _merge_schedule_clarification_reply,
    _parse_time_fragment,
    _strip_tool_json_from_reply,
    _title_from_simple_create,
)
from app.llm.tools import execute_tool_call
from app.schemas.assistant import (
    CreateEventInput,
    DetectConflictsInput,
    MoveEventInput,
    UserPlanningMemory,
)
from app.services.assistant.tools import AssistantToolRegistry


def _google_event(event_id, title, start_at, end_at):
    return {
        "id": event_id,
        "summary": title,
        "start": {"dateTime": start_at.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": end_at.isoformat(), "timeZone": "UTC"},
        "status": "confirmed",
    }


def test_create_rejects_exact_duplicate_before_mutation(monkeypatch):
    start = datetime(2026, 5, 4, 19, tzinfo=UTC)
    existing = [_google_event("evt-1", "Gym", start, start + timedelta(hours=1))]
    created = []

    async def fake_list_events(*args, **kwargs):
        return existing

    async def fake_create_event(*args, **kwargs):
        created.append(kwargs["event_body"])
        return _google_event("evt-2", "Gym", start, start + timedelta(hours=1))

    monkeypatch.setattr("app.services.assistant.tools.list_google_events_in_range", fake_list_events)
    monkeypatch.setattr("app.services.assistant.tools.create_google_event", fake_create_event)

    async def run():
        with pytest.raises(ValueError, match="duplicate"):
            await AssistantToolRegistry().create_event(
                CreateEventInput(
                    title="Gym",
                    start_at=start,
                    end_at=start + timedelta(hours=1),
                    timezone="UTC",
                ),
                user=SimpleNamespace(id="user-1", timezone="UTC"),
                db=None,
                memory=UserPlanningMemory(),
            )

    asyncio.run(run())
    assert created == []


def test_detect_conflicts_fetches_range_and_detects_all_overlaps(monkeypatch):
    start = datetime(2026, 5, 4, 9, tzinfo=UTC)
    events = [
        _google_event("evt-1", "Study", start, start + timedelta(hours=2)),
        _google_event("evt-2", "Gym", start + timedelta(hours=1), start + timedelta(hours=3)),
        _google_event("evt-3", "Call", start + timedelta(hours=2, minutes=30), start + timedelta(hours=4)),
    ]

    async def fake_list_events(*args, **kwargs):
        return events

    monkeypatch.setattr("app.services.assistant.tools.list_google_events_in_range", fake_list_events)

    async def run():
        result = await AssistantToolRegistry().detect_conflicts(
            DetectConflictsInput(start_at=start, end_at=start + timedelta(hours=5)),
            user=SimpleNamespace(id="user-1", timezone="UTC"),
            db=None,
            memory=UserPlanningMemory(),
        )

        assert result.has_conflicts is True
        assert len(result.conflicts) == 2
        assert {conflict.event_id for conflict in result.conflicts} == {"evt-1", "evt-2"}
        assert {conflict.conflicting_event_id for conflict in result.conflicts} == {"evt-2", "evt-3"}

    asyncio.run(run())


def test_move_event_refuses_to_create_new_conflict(monkeypatch):
    original = datetime(2026, 5, 4, 9, tzinfo=UTC)
    target = _google_event("evt-1", "Study", original, original + timedelta(hours=1))
    blocking_start = datetime(2026, 5, 4, 12, tzinfo=UTC)
    blocker = _google_event("evt-2", "Gym", blocking_start, blocking_start + timedelta(hours=1))
    updates = []

    async def fake_get_event(*args, **kwargs):
        return target

    async def fake_list_events(*args, **kwargs):
        return [blocker]

    async def fake_update_event(*args, **kwargs):
        updates.append(kwargs["event_body"])
        return target

    monkeypatch.setattr("app.services.assistant.tools.get_google_event", fake_get_event)
    monkeypatch.setattr("app.services.assistant.tools.list_google_events_in_range", fake_list_events)
    monkeypatch.setattr("app.services.assistant.tools.update_google_event", fake_update_event)

    async def run():
        with pytest.raises(ValueError, match="create a conflict"):
            await AssistantToolRegistry().move_event(
                MoveEventInput(
                    event_id="evt-1",
                    new_start_at=blocking_start,
                    new_end_at=blocking_start + timedelta(hours=1),
                    timezone="UTC",
                ),
                user=SimpleNamespace(id="user-1", timezone="UTC"),
                db=None,
                memory=UserPlanningMemory(),
            )

    asyncio.run(run())
    assert updates == []


def test_parse_schedule_image_tool_uses_uploaded_image_text():
    attachments = [
        {
            "id": "img-1",
            "filename": "schedule.png",
            "kind": "image",
            "text_preview": "Monday 09:00 Math\nTopic: Derivatives\nWednesday 10:00 Physics",
        }
    ]

    async def run():
        raw = await execute_tool_call(
            registry=AssistantToolRegistry(),
            tool_name="parse_schedule_image",
            tool_args={"attachment_id": "img-1"},
            user=SimpleNamespace(id="user-1", timezone="UTC"),
            db=None,
            memory=UserPlanningMemory(),
            attachments=attachments,
        )
        result = json.loads(raw)

        assert result["success"] is True
        assert result["attachment_id"] == "img-1"
        assert "Derivatives" in result["extracted_text"]
        assert result["schedule_structure"]

    asyncio.run(run())


def test_simple_create_parser_handles_space_separated_24h_time():
    now = datetime(2026, 5, 10, 12, tzinfo=UTC)
    prompt = "add regression final defence on wednesday 16 30"

    assert _parse_time_fragment(prompt) == (16, 30)
    assert _date_from_prompt(prompt, now).date().isoformat() == "2026-05-13"
    assert _title_from_simple_create(prompt, now) == "regression final defence"


def test_simple_create_parser_handles_shorthand_typos_and_human_times():
    now = datetime(2026, 5, 10, 12, tzinfo=UTC)
    cases = [
        ("sched ml final defence on wednes at 2 20", (14, 20), "2026-05-13", "ml final defence"),
        ("schedule stats final wedn 14 30", (14, 30), "2026-05-13", "stats final"),
        ("book project review wensdey two and a half", (14, 30), "2026-05-13", "project review"),
        ("make advising call next wed at half past two", (14, 30), "2026-05-13", "advising call"),
    ]

    for prompt, expected_time, expected_date, expected_title in cases:
        assert _parse_time_fragment(prompt) == expected_time
        assert _date_from_prompt(prompt, now).date().isoformat() == expected_date
        assert _title_from_simple_create(prompt, now) == expected_title


def test_title_clarification_can_reuse_previous_create_prompt():
    now = datetime(2026, 5, 10, 12, tzinfo=UTC)
    history = [
        {"role": "user", "content": "add regression final defence on wednesday 16 30"},
        {
            "role": "assistant",
            "content": "It seems I need a title for the event. What should the title be?",
        },
    ]

    assert _latest_create_prompt_from_title_clarification(history, now) == history[0]["content"]


def test_structured_extraction_parses_this_friday_time_range():
    now = datetime(2026, 5, 10, 12, tzinfo=UTC)
    result = _extract_simple_calendar_command("Schedule math class this Friday from 10 to 12", now)

    assert result.intent == "create_single_event"
    assert result.title == "math class"
    assert result.date == "this friday"
    assert result.start_time == "10:00"
    assert result.end_time == "12:00"
    assert result.duration_minutes == 120
    assert result.missing_fields == []


def test_structured_extraction_parses_single_start_time_with_default_duration():
    now = datetime(2026, 5, 10, 12, tzinfo=UTC)
    result = _extract_simple_calendar_command("Add gym tomorrow at 6pm", now)

    assert result.intent == "create_single_event"
    assert result.title == "gym"
    assert result.date == "tomorrow"
    assert result.start_time == "18:00"
    assert result.end_time is None
    assert result.duration_minutes == 60
    assert result.missing_fields == []


def test_structured_extraction_treats_bare_title_day_time_as_create():
    now = datetime(2026, 5, 13, 12, tzinfo=UTC)
    result = _extract_simple_calendar_command("ml final project defence wednesday 14:20", now)

    assert _classify_prompt_intent("ml final project defence wednesday 14:20", []) == "create"
    assert result.intent == "create_single_event"
    assert result.title == "ml final project defence"
    assert result.date == "wednesday"
    assert result.start_time == "14:20"
    assert result.missing_fields == []


def test_structured_extraction_parses_month_day_follow_up_and_back_title():
    now = datetime(2026, 5, 13, 12, tzinfo=UTC)
    result = _extract_simple_calendar_command("sched back ml final project defence to may 13 14:20", now)

    assert _classify_prompt_intent("ml final project defence may 13 14:20", []) == "create"
    assert result.intent == "create_single_event"
    assert result.title == "ml final project defence"
    assert result.date == "may 13"
    assert result.date_value.date().isoformat() == "2026-05-13"
    assert result.start_time == "14:20"
    assert result.missing_fields == []


def test_schedule_time_clarification_merges_previous_title():
    now = datetime(2026, 5, 13, 12, tzinfo=UTC)
    history = [
        {"role": "user", "content": "sched back ml final project defence"},
        {"role": "assistant", "content": "When should I schedule ml final project defence?"},
    ]

    merged = _merge_schedule_clarification_reply("to may 13 14:20", history, now)

    assert merged == "schedule ml final project defence to may 13 14:20"
    result = _extract_simple_calendar_command(merged, now)
    assert result.title == "ml final project defence"
    assert result.start_time == "14:20"
    assert result.missing_fields == []


def test_tool_json_is_removed_from_assistant_reply():
    answer = (
        '{"tool": "delete_event", "success": true, "events": ["evt | Title"]}\n\n'
        'The event was deleted.'
    )

    assert _strip_tool_json_from_reply(answer) == "The event was deleted."


def test_structured_extraction_parses_next_monday_24h_time():
    now = datetime(2026, 5, 10, 12, tzinfo=UTC)
    result = _extract_simple_calendar_command("Put dentist appointment next Monday at 15:30", now)

    assert result.intent == "create_single_event"
    assert result.title == "dentist appointment"
    assert result.date == "next monday"
    assert result.start_time == "15:30"
    assert result.missing_fields == []


def test_structured_extraction_parses_weekday_dash_range_without_title_pollution():
    now = datetime(2026, 5, 10, 12, tzinfo=UTC)
    result = _extract_simple_calendar_command("Schedule biology lecture on Friday 9-11", now)

    assert result.intent == "create_single_event"
    assert result.title == "biology lecture"
    assert result.date == "friday"
    assert result.start_time == "09:00"
    assert result.end_time == "11:00"
    assert result.missing_fields == []


def test_structured_extraction_parses_relative_after_calendar_anchor():
    now = datetime(2026, 5, 10, 12, tzinfo=UTC)
    result = _extract_simple_calendar_command("Add lunch with Dan after my morning lecture tomorrow", now)

    assert result.intent == "create_single_event"
    assert result.title == "lunch with Dan"
    assert result.date == "tomorrow"
    assert result.relative_time == "after morning lecture"
    assert result.requires_calendar_read is True


def test_structured_extraction_parses_move_old_and_new_time():
    now = datetime(2026, 5, 10, 12, tzinfo=UTC)
    result = _extract_simple_calendar_command("Move gym from 6pm to 8pm tomorrow", now)

    assert result.intent == "move_event"
    assert result.title == "gym"
    assert result.date == "tomorrow"
    assert result.old_time == "18:00"
    assert result.new_time == "20:00"
    assert result.missing_fields == []


def test_structured_extraction_parses_delete_title_and_date():
    now = datetime(2026, 5, 10, 12, tzinfo=UTC)
    result = _extract_simple_calendar_command("Delete internship today", now)

    assert result.intent == "delete_event"
    assert result.title == "internship"
    assert result.date == "today"
    assert result.missing_fields == []
