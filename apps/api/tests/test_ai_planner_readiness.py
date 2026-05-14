"""Gated production-readiness checks for the AI calendar/planning assistant.

Run with:
    RUN_AI_READINESS=1 pytest apps/api/tests/test_ai_planner_readiness.py

The suite intentionally exercises real assistant orchestration with a mocked
calendar/tool layer. It is skipped by default so ordinary unit tests stay fast
and deterministic while this matrix acts as an acceptance gate for production
readiness.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from copy import deepcopy
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.core.config import settings
from app.schemas.assistant import (
    AssistantMessageRequest,
    BatchDeleteEventsInput,
    BatchDeleteEventsResult,
    BatchMoveEventsInput,
    BatchMoveEventsResult,
    CalendarEventSnapshot,
    ConflictItem,
    ConversationState,
    CreateEventInput,
    CreateEventResult,
    DeleteEventInput,
    DeleteEventResult,
    DetectConflictsInput,
    DetectConflictsResult,
    DuplicateEventsInput,
    DuplicateEventsResult,
    EditEventInput,
    EditEventResult,
    FetchEventsInput,
    FetchEventsResult,
    FindFreeSlotsInput,
    FindFreeSlotsResult,
    FreeSlot,
    MoveEventInput,
    MoveEventResult,
    OptimizeScheduleInput,
    OptimizeScheduleResult,
    OptimizationSuggestion,
    PlanPreviewChange,
    SummarizeScheduleInput,
    SummarizeScheduleResult,
    ToolExecutionMetadata,
    UserPlanningMemory,
)
from app.services.assistant.orchestrator import AssistantOrchestrator


pytestmark = [
    pytest.mark.ai_readiness,
    pytest.mark.skipif(
        os.getenv("RUN_AI_READINESS") != "1",
        reason="Set RUN_AI_READINESS=1 to run the gated AI production-readiness matrix.",
    ),
]


FIXED_NOW = datetime(2026, 5, 13, 12, 0, tzinfo=UTC)  # Wednesday
TODAY = FIXED_NOW.date()
TOMORROW = TODAY + timedelta(days=1)
THIS_WEEK_MONDAY = TODAY - timedelta(days=TODAY.weekday())
NEXT_WEEK_MONDAY = THIS_WEEK_MONDAY + timedelta(days=7)

RAW_OUTPUT_PATTERNS = [
    r"\[object Object\]",
    r"\bundefined\b",
    r"\bnull\b",
    r"Traceback \(most recent call last\)",
    r"\bValidationError\b",
    r"\bInternal Server Error\b",
    r"File \".+\", line \d+",
]


def _load_cases() -> list[dict[str, Any]]:
    path = Path(__file__).with_name("ai_readiness_cases.json")
    return json.loads(path.read_text(encoding="utf-8"))


AI_READINESS_CASES = _load_cases()


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = FIXED_NOW
        if tz is not None:
            return value.astimezone(tz)
        return value.replace(tzinfo=None)


class InMemoryStateStore:
    def __init__(self):
        self.states: dict[tuple[str, str], ConversationState] = {}

    async def load(self, *, user_id: str, session_id: str) -> ConversationState:
        key = (str(user_id), session_id)
        return self.states.get(key, ConversationState(session_id=session_id))

    async def save(self, *, user_id: str, session_id: str, state: ConversationState) -> None:
        self.states[(str(user_id), session_id)] = state


class FakeMemoryService:
    async def get_memory(self, db, user):
        return SimpleNamespace(memory=UserPlanningMemory())


def _at(day, hm: str) -> datetime:
    hour, minute = (int(part) for part in hm.split(":", 1))
    return datetime.combine(day, time(hour, minute), tzinfo=UTC)


def _day_for(label: str) -> Any:
    if label == "today":
        return TODAY
    if label == "tomorrow":
        return TOMORROW
    if label == "this_week_monday":
        return THIS_WEEK_MONDAY
    if label == "this_week_wednesday":
        return THIS_WEEK_MONDAY + timedelta(days=2)
    if label == "this_week_friday":
        return THIS_WEEK_MONDAY + timedelta(days=4)
    if label == "next_week_monday":
        return NEXT_WEEK_MONDAY
    if label == "next_week_wednesday":
        return NEXT_WEEK_MONDAY + timedelta(days=2)
    if label == "next_week_friday":
        return NEXT_WEEK_MONDAY + timedelta(days=4)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", label):
        return datetime.fromisoformat(label).date()
    raise AssertionError(f"Unknown day label: {label}")


def _event(
    event_id: str,
    title: str,
    day_label: str,
    start: str,
    end: str | None = None,
    *,
    location: str | None = None,
    description: str | None = None,
) -> CalendarEventSnapshot:
    day = _day_for(day_label)
    start_at = _at(day, start)
    end_at = _at(day, end) if end else start_at + timedelta(hours=1)
    return CalendarEventSnapshot(
        id=event_id,
        title=title,
        description=description,
        start_at=start_at,
        end_at=end_at,
        timezone="UTC",
        location=location,
        status="confirmed",
        html_link=None,
    )


def _fixture_events(name: str) -> list[CalendarEventSnapshot]:
    fixtures: dict[str, list[CalendarEventSnapshot]] = {
        "empty": [],
        "single_internship_today": [_event("evt-internship", "internship", "today", "10:00", "16:00")],
        "two_meetings_today": [
            _event("evt-team", "meeting with team", "today", "10:00", "11:00"),
            _event("evt-advisor", "meeting with advisor", "today", "15:00", "16:00"),
        ],
        "mixed_today": [
            _event("evt-math", "Math lecture", "today", "09:00", "10:00"),
            _event("evt-gym", "Gym", "today", "18:00", "19:00"),
            _event("evt-dinner", "Dinner", "today", "20:00", "21:00"),
        ],
        "dentist_tomorrow": [_event("evt-dentist", "Dentist", "tomorrow", "09:00", "10:00")],
        "class_tomorrow_afternoon": [_event("evt-class", "Class", "tomorrow", "14:00", "16:00")],
        "current_week_events": [
            _event("evt-math-week", "Math", "this_week_monday", "10:00", "11:30"),
            _event("evt-gym-week", "Gym", "this_week_wednesday", "18:00", "19:30"),
            _event("evt-sync-week", "Team sync", "this_week_friday", "15:00", "16:00"),
        ],
        "unoptimized_tomorrow": [
            _event("evt-deep", "Deep work", "tomorrow", "13:00", "15:00"),
            _event("evt-gym-tom", "Gym", "tomorrow", "09:00", "10:00"),
            _event("evt-admin", "Admin tasks", "tomorrow", "18:00", "19:00"),
        ],
        "tomorrow_events": [
            _event("evt-class-tom", "Class", "tomorrow", "09:00", "12:00"),
            _event("evt-meeting-tom", "Meeting", "tomorrow", "15:00", "16:00"),
        ],
        "class_and_meeting_tomorrow": [
            _event("evt-class-tom", "Class", "tomorrow", "09:00", "12:00"),
            _event("evt-meeting-tom", "Meeting", "tomorrow", "15:00", "16:00"),
        ],
        "boring_lecture_tomorrow": [_event("evt-lecture", "boring lecture", "tomorrow", "09:00", "10:00")],
        "work_tomorrow": [_event("evt-work", "Work", "tomorrow", "09:00", "17:00")],
        "two_events_tomorrow": [
            _event("evt-class", "Class", "tomorrow", "09:00", "10:00"),
            _event("evt-meeting", "Meeting", "tomorrow", "11:00", "12:00"),
        ],
        "many_events_tomorrow": [
            _event(f"evt-many-{idx}", f"Event {idx}", "tomorrow", f"{8 + idx:02d}:00", f"{9 + idx:02d}:00")
            for idx in range(8)
        ],
        "math_tomorrow": [_event("evt-math-dup", "Math", "tomorrow", "10:00", "11:00")],
        "ml_prep_tomorrow": [
            _event(
                "evt-ml-prep",
                "Machine Learning project defense preparation",
                "tomorrow",
                "18:00",
                "19:00",
            )
        ],
        "study_tomorrow_evening": [_event("evt-study-evening", "Study", "tomorrow", "20:00", "22:00")],
        "morning_busy_tomorrow": [_event("evt-morning-busy", "Morning class", "tomorrow", "08:00", "12:00")],
        "fully_booked_tomorrow": [
            _event(f"evt-full-{idx}", f"Busy block {idx}", "tomorrow", f"{8 + idx:02d}:00", f"{9 + idx:02d}:00")
            for idx in range(15)
        ],
        "normal_calendar": [
            _event("evt-class-normal", "Class", "tomorrow", "09:00", "12:00"),
            _event("evt-gym-normal", "Gym", "tomorrow", "18:00", "19:00"),
        ],
        "complex_academic_week": [
            _event("evt-fixed-mon", "Fixed class", "this_week_monday", "09:00", "12:00"),
            _event("evt-fixed-wed", "ML exam", "this_week_wednesday", "16:30", "18:00"),
            _event("evt-fixed-fri", "Seminar", "this_week_friday", "14:00", "16:00"),
        ],
    }
    if name not in fixtures:
        raise AssertionError(f"Unknown readiness fixture: {name}")
    return deepcopy(fixtures[name])


def _overlaps(a: CalendarEventSnapshot, b: CalendarEventSnapshot) -> bool:
    return a.start_at < b.end_at and b.start_at < a.end_at


def _title_matches(title: str, expected: dict[str, Any]) -> bool:
    title_folded = title.casefold()
    if "title_contains" in expected:
        return expected["title_contains"].casefold() in title_folded
    if "title_contains_any" in expected:
        return any(term.casefold() in title_folded for term in expected["title_contains_any"])
    return True


class ReadinessCalendarRegistry:
    MUTATING_TOOLS = {
        "create_event",
        "edit_event",
        "delete_event",
        "duplicate_events",
        "move_event",
        "batch_move_events",
        "batch_delete_events",
    }

    def __init__(self, events: list[CalendarEventSnapshot]):
        self.events = events
        self.created: list[CalendarEventSnapshot] = []
        self.updated: list[tuple[CalendarEventSnapshot, CalendarEventSnapshot]] = []
        self.deleted: list[CalendarEventSnapshot] = []
        self.duplicated: list[CalendarEventSnapshot] = []
        self.calls: list[tuple[str, Any]] = []
        self._next_id = 1

    async def execute(self, *, tool_name: str, payload: dict[str, Any], user, db, memory):
        schemas = {
            "create_event": CreateEventInput,
            "edit_event": EditEventInput,
            "delete_event": DeleteEventInput,
            "duplicate_events": DuplicateEventsInput,
            "fetch_events": FetchEventsInput,
            "move_event": MoveEventInput,
            "find_free_slots": FindFreeSlotsInput,
            "summarize_schedule": SummarizeScheduleInput,
            "detect_conflicts": DetectConflictsInput,
            "optimize_schedule": OptimizeScheduleInput,
            "batch_move_events": BatchMoveEventsInput,
            "batch_delete_events": BatchDeleteEventsInput,
        }
        model = schemas[tool_name].model_validate(payload)
        return await getattr(self, tool_name)(model, user=user, db=db, memory=memory)

    def all_mutations(self) -> list[Any]:
        return [*self.created, *self.updated, *self.deleted, *self.duplicated]

    async def fetch_events(self, payload: FetchEventsInput, *, user, db, memory) -> FetchEventsResult:
        self.calls.append(("fetch_events", payload))
        query = (payload.query or "").casefold().strip()
        events = [
            event
            for event in self.events
            if event.start_at < payload.end_at and payload.start_at < event.end_at
        ]
        if query:
            events = [event for event in events if query in event.title.casefold()]
        return FetchEventsResult(
            success=True,
            metadata=ToolExecutionMetadata(tool="fetch_events", executed=True),
            events=events[: payload.max_results],
            count=len(events),
        )

    async def create_event(self, payload: CreateEventInput, *, user, db, memory) -> CreateEventResult:
        self.calls.append(("create_event", payload))
        preview = [
            PlanPreviewChange(
                action="create_event",
                title=payload.title,
                details="Create a new calendar event.",
                proposed_start_at=payload.start_at,
                proposed_end_at=payload.end_at,
            )
        ]
        event = CalendarEventSnapshot(
            id=f"created-{self._next_id}",
            title=payload.title,
            description=payload.description,
            start_at=payload.start_at,
            end_at=payload.end_at,
            timezone=payload.timezone,
            location=payload.location,
            status="preview" if payload.dry_run else "confirmed",
            html_link=None,
        )
        self._next_id += 1
        if payload.dry_run:
            return CreateEventResult(
                success=True,
                metadata=ToolExecutionMetadata(tool="create_event", executed=False, dry_run=True),
                created_events=[event],
                preview=preview,
            )
        self.created.append(event)
        self.events.append(event)
        return CreateEventResult(
            success=True,
            metadata=ToolExecutionMetadata(tool="create_event", executed=True),
            created_events=[event],
            preview=preview,
        )

    async def edit_event(self, payload: EditEventInput, *, user, db, memory) -> EditEventResult:
        self.calls.append(("edit_event", payload))
        target = self._resolve_single(payload.event_id, payload.match_title, payload.start_at, payload.end_at)
        updated = target.model_copy(
            update={
                "title": payload.title or target.title,
                "description": payload.description if payload.description is not None else target.description,
                "location": payload.location if payload.location is not None else target.location,
                "start_at": payload.start_at or target.start_at,
                "end_at": payload.end_at or target.end_at,
                "timezone": payload.timezone or target.timezone,
            }
        )
        preview = [
            PlanPreviewChange(
                action="edit_event",
                title=updated.title,
                details="Edit an existing calendar event.",
                current_start_at=target.start_at,
                proposed_start_at=updated.start_at,
                proposed_end_at=updated.end_at,
            )
        ]
        if not payload.dry_run:
            self.events[self.events.index(target)] = updated
            self.updated.append((target, updated))
        return EditEventResult(
            success=True,
            metadata=ToolExecutionMetadata(tool="edit_event", executed=not payload.dry_run, dry_run=payload.dry_run),
            previous_event=target,
            updated_event=updated,
            preview=preview,
        )

    async def move_event(self, payload: MoveEventInput, *, user, db, memory) -> MoveEventResult:
        self.calls.append(("move_event", payload))
        target = self._resolve_single(payload.event_id, payload.match_title, None, None)
        duration = target.end_at - target.start_at
        new_end = payload.new_end_at or payload.new_start_at + duration
        moved = target.model_copy(
            update={
                "start_at": payload.new_start_at,
                "end_at": new_end,
                "timezone": payload.timezone or target.timezone,
            }
        )
        preview = [
            PlanPreviewChange(
                action="move_event",
                title=moved.title,
                details="Move an existing calendar event.",
                current_start_at=target.start_at,
                proposed_start_at=moved.start_at,
                proposed_end_at=moved.end_at,
            )
        ]
        if not payload.dry_run:
            self.events[self.events.index(target)] = moved
            self.updated.append((target, moved))
        return MoveEventResult(
            success=True,
            metadata=ToolExecutionMetadata(tool="move_event", executed=not payload.dry_run, dry_run=payload.dry_run),
            previous_event=target,
            moved_event=moved,
            preview=preview,
        )

    async def delete_event(self, payload: DeleteEventInput, *, user, db, memory) -> DeleteEventResult:
        self.calls.append(("delete_event", payload))
        targets = self._resolve_many(payload.event_id, payload.match_title, payload.start_at, payload.end_at)
        if not payload.delete_all_matches and len(targets) > 1:
            raise ValueError("Delete matched multiple events; require confirmation or narrower targeting")
        preview = [
            PlanPreviewChange(action="delete_event", title=event.title, details="Delete a calendar event.", current_start_at=event.start_at)
            for event in targets
        ]
        if not payload.dry_run:
            for event in targets:
                if event in self.events:
                    self.events.remove(event)
                self.deleted.append(event)
        return DeleteEventResult(
            success=True,
            metadata=ToolExecutionMetadata(tool="delete_event", executed=not payload.dry_run, dry_run=payload.dry_run),
            deleted_events=targets,
            preview=preview,
        )

    async def duplicate_events(self, payload: DuplicateEventsInput, *, user, db, memory) -> DuplicateEventsResult:
        self.calls.append(("duplicate_events", payload))
        source_events = [
            event
            for event in self.events
            if payload.source_start_at <= event.start_at < payload.source_end_at
            and (not payload.title_contains or payload.title_contains.casefold() in event.title.casefold())
        ]
        offset = payload.target_start_at - payload.source_start_at
        copies = [
            event.model_copy(
                update={
                    "id": f"copy-{event.id}",
                    "start_at": event.start_at + offset,
                    "end_at": event.end_at + offset,
                }
            )
            for event in source_events
        ]
        preview = [
            PlanPreviewChange(
                action="duplicate_events",
                title=event.title,
                details="Duplicate calendar event.",
                current_start_at=source.start_at,
                proposed_start_at=event.start_at,
                proposed_end_at=event.end_at,
            )
            for source, event in zip(source_events, copies, strict=False)
        ]
        if not payload.dry_run:
            self.events.extend(copies)
            self.duplicated.extend(copies)
        return DuplicateEventsResult(
            success=True,
            metadata=ToolExecutionMetadata(tool="duplicate_events", executed=not payload.dry_run, dry_run=payload.dry_run),
            source_events=source_events,
            duplicated_events=copies,
            preview=preview,
        )

    async def batch_move_events(self, payload: BatchMoveEventsInput, *, user, db, memory) -> BatchMoveEventsResult:
        self.calls.append(("batch_move_events", payload))
        targets = [
            event
            for event in self.events
            if payload.start_at <= event.start_at < payload.end_at
            and (not payload.query or payload.query.casefold() in event.title.casefold())
        ]
        moved = [
            event.model_copy(
                update={
                    "start_at": event.start_at + timedelta(minutes=payload.offset_minutes),
                    "end_at": event.end_at + timedelta(minutes=payload.offset_minutes),
                }
            )
            for event in targets
        ]
        preview = [
            PlanPreviewChange(
                action="batch_move_events",
                title=event.title,
                details="Move calendar event in batch.",
                current_start_at=target.start_at,
                proposed_start_at=event.start_at,
                proposed_end_at=event.end_at,
            )
            for target, event in zip(targets, moved, strict=False)
        ]
        if not payload.dry_run:
            for target, replacement in zip(targets, moved, strict=False):
                self.events[self.events.index(target)] = replacement
                self.updated.append((target, replacement))
        return BatchMoveEventsResult(
            success=True,
            metadata=ToolExecutionMetadata(tool="batch_move_events", executed=not payload.dry_run, dry_run=payload.dry_run),
            moved_events=moved,
            count=len(moved),
            preview=preview,
        )

    async def batch_delete_events(self, payload: BatchDeleteEventsInput, *, user, db, memory) -> BatchDeleteEventsResult:
        self.calls.append(("batch_delete_events", payload))
        targets = [
            event
            for event in self.events
            if payload.start_at <= event.start_at < payload.end_at
            and (not payload.query or payload.query.casefold() in event.title.casefold())
        ]
        preview = [
            PlanPreviewChange(action="batch_delete_events", title=event.title, details="Delete calendar event in batch.", current_start_at=event.start_at)
            for event in targets
        ]
        if not payload.dry_run:
            for event in targets:
                if event in self.events:
                    self.events.remove(event)
                self.deleted.append(event)
        return BatchDeleteEventsResult(
            success=True,
            metadata=ToolExecutionMetadata(tool="batch_delete_events", executed=not payload.dry_run, dry_run=payload.dry_run),
            deleted_events=targets,
            count=len(targets),
            preview=preview,
        )

    async def find_free_slots(self, payload: FindFreeSlotsInput, *, user, db, memory) -> FindFreeSlotsResult:
        self.calls.append(("find_free_slots", payload))
        events = sorted(
            [event for event in self.events if event.start_at < payload.end_at and payload.start_at < event.end_at],
            key=lambda event: event.start_at,
        )
        cursor = payload.start_at
        if payload.working_hours_only and cursor.hour < 8:
            cursor = cursor.replace(hour=8, minute=0, second=0, microsecond=0)
        slots: list[FreeSlot] = []
        for event in events:
            if cursor + timedelta(minutes=payload.slot_minutes) <= event.start_at:
                slots.append(FreeSlot(start_at=cursor, end_at=cursor + timedelta(minutes=payload.slot_minutes), timezone="UTC", score=0.8))
            cursor = max(cursor, event.end_at)
        if cursor + timedelta(minutes=payload.slot_minutes) <= payload.end_at and len(slots) < payload.max_slots:
            slots.append(FreeSlot(start_at=cursor, end_at=cursor + timedelta(minutes=payload.slot_minutes), timezone="UTC", score=0.8))
        return FindFreeSlotsResult(
            success=True,
            metadata=ToolExecutionMetadata(tool="find_free_slots", executed=True),
            slots=slots[: payload.max_slots],
        )

    async def summarize_schedule(self, payload: SummarizeScheduleInput, *, user, db, memory) -> SummarizeScheduleResult:
        self.calls.append(("summarize_schedule", payload))
        fetched = await self.fetch_events(
            FetchEventsInput(start_at=payload.start_at, end_at=payload.end_at),
            user=user,
            db=db,
            memory=memory,
        )
        titles = ", ".join(event.title for event in fetched.events[:8])
        return SummarizeScheduleResult(
            success=True,
            metadata=ToolExecutionMetadata(tool="summarize_schedule", executed=True),
            summary=f"{fetched.count} events: {titles}" if fetched.events else "No events.",
            event_count=fetched.count,
            events=fetched.events if payload.include_events else [],
        )

    async def detect_conflicts(self, payload: DetectConflictsInput, *, user, db, memory) -> DetectConflictsResult:
        self.calls.append(("detect_conflicts", payload))
        conflicts: list[ConflictItem] = []
        candidates = payload.candidate_events
        existing = self.events
        if payload.start_at and payload.end_at and not candidates:
            existing = [event for event in existing if event.start_at < payload.end_at and payload.start_at < event.end_at]
            for left, right in zip(existing, existing[1:], strict=False):
                if _overlaps(left, right):
                    conflicts.append(
                        ConflictItem(
                            event_id=left.id,
                            title=left.title,
                            conflicting_event_id=right.id,
                            conflicting_with=right.title,
                            start_at=max(left.start_at, right.start_at),
                            end_at=min(left.end_at, right.end_at),
                        )
                    )
        for candidate in candidates:
            for event in existing:
                if _overlaps(candidate, event):
                    conflicts.append(
                        ConflictItem(
                            event_id=None,
                            title=candidate.title,
                            conflicting_event_id=event.id,
                            conflicting_with=event.title,
                            start_at=max(candidate.start_at, event.start_at),
                            end_at=min(candidate.end_at, event.end_at),
                        )
                    )
        return DetectConflictsResult(
            success=True,
            metadata=ToolExecutionMetadata(tool="detect_conflicts", executed=True),
            has_conflicts=bool(conflicts),
            conflicts=conflicts,
        )

    async def optimize_schedule(self, payload: OptimizeScheduleInput, *, user, db, memory) -> OptimizeScheduleResult:
        self.calls.append(("optimize_schedule", payload))
        fetched = await self.fetch_events(
            FetchEventsInput(start_at=payload.start_at, end_at=payload.end_at),
            user=user,
            db=db,
            memory=memory,
        )
        suggestions = []
        for event in fetched.events:
            if "deep" in event.title.casefold():
                suggestions.append(
                    OptimizationSuggestion(
                        title=event.title,
                        current_start_at=event.start_at,
                        suggested_start_at=event.start_at.replace(hour=10, minute=0),
                        suggested_end_at=event.start_at.replace(hour=12, minute=0),
                        reason="Earlier focus window.",
                    )
                )
        preview = [
            PlanPreviewChange(
                action="move_event",
                title=suggestion.title,
                details=suggestion.reason,
                current_start_at=suggestion.current_start_at,
                proposed_start_at=suggestion.suggested_start_at,
                proposed_end_at=suggestion.suggested_end_at,
            )
            for suggestion in suggestions
        ]
        return OptimizeScheduleResult(
            success=True,
            metadata=ToolExecutionMetadata(tool="optimize_schedule", executed=False, dry_run=True),
            suggestions=suggestions,
            preview=preview,
        )

    def _resolve_many(
        self,
        event_id: str | None,
        match_title: str | None,
        start_at: datetime | None,
        end_at: datetime | None,
    ) -> list[CalendarEventSnapshot]:
        matches = self.events
        if event_id:
            matches = [event for event in matches if event.id == event_id]
        if match_title:
            matches = [event for event in matches if match_title.casefold() in event.title.casefold()]
        if start_at and end_at:
            matches = [event for event in matches if _overlaps(event, CalendarEventSnapshot(id="query", title="query", start_at=start_at, end_at=end_at))]
        elif start_at:
            matches = [event for event in matches if event.start_at.date() == start_at.date()]
        if not matches:
            raise ValueError("No matching event found")
        return matches

    def _resolve_single(
        self,
        event_id: str | None,
        match_title: str | None,
        start_at: datetime | None,
        end_at: datetime | None,
    ) -> CalendarEventSnapshot:
        matches = self._resolve_many(event_id, match_title, start_at, end_at)
        if len(matches) > 1:
            raise ValueError("Matched multiple events; ask for clarification")
        return matches[0]


def _patch_fixed_clock(monkeypatch) -> None:
    monkeypatch.setattr(settings, "openai_api_key", os.getenv("OPENAI_API_KEY", ""))
    monkeypatch.setattr(settings, "gemma_ai_api_key", os.getenv("GEMMA_AI_API_KEY", ""))
    for target in [
        "app.llm.agent.datetime",
        "app.services.assistant.orchestrator.datetime",
        "app.services.assistant.constraint_extractor.datetime",
        "app.services.assistant.planner.datetime",
        "app.services.assistant.planning_state.datetime",
    ]:
        monkeypatch.setattr(target, FixedDateTime)


def _assistant(registry: ReadinessCalendarRegistry) -> AssistantOrchestrator:
    return AssistantOrchestrator(
        state_store=InMemoryStateStore(),
        memory_service=FakeMemoryService(),
        tool_registry=registry,
    )


def _user():
    return SimpleNamespace(id="readiness-user", timezone="UTC", plan="pro")


async def _run_message(assistant: AssistantOrchestrator, prompt: str, *, session_id: str):
    return await assistant.handle_message(
        payload=AssistantMessageRequest(prompt=prompt, timezone="UTC", session_id=session_id, preview=False),
        user=_user(),
        db=None,
    )


def _response_intents(response) -> set[str]:
    return {
        response.routing.intent,
        response.plan.goal,
        response.plan.route,
        response.routing.reason,
    }


def _all_response_text(response) -> str:
    payload = response.model_dump(mode="json")
    return "\n".join(
        [
            str(response.reply),
            str(response.routing.reason),
            str(response.plan.summary),
            str(response.plan.goal),
            json.dumps(payload.get("display_actions", []), ensure_ascii=False),
        ]
    )


def assert_no_raw_internal_output(response) -> None:
    text = _all_response_text(response)
    assert isinstance(response.reply, str)
    assert not response.reply.strip().startswith("{"), "Assistant reply should not be raw JSON"
    for pattern in RAW_OUTPUT_PATTERNS:
        assert not re.search(pattern, text, flags=re.IGNORECASE), f"Raw/internal output leaked: {pattern}"


def assert_no_calendar_mutation(registry: ReadinessCalendarRegistry) -> None:
    assert registry.created == []
    assert registry.updated == []
    assert registry.deleted == []
    assert registry.duplicated == []


def _mutation_events_for_action(registry: ReadinessCalendarRegistry, action: str) -> list[CalendarEventSnapshot]:
    if action == "create":
        return registry.created
    if action == "delete":
        return registry.deleted
    if action == "update":
        return [updated for _, updated in registry.updated]
    if action == "duplicate":
        return registry.duplicated
    raise AssertionError(f"Unsupported mutation action: {action}")


def _preview_events(response) -> list[CalendarEventSnapshot]:
    previews = []
    for index, change in enumerate(response.execution.preview):
        if change.proposed_start_at and change.proposed_end_at:
            previews.append(
                CalendarEventSnapshot(
                    id=f"preview-{index}",
                    title=change.title,
                    start_at=change.proposed_start_at,
                    end_at=change.proposed_end_at,
                    timezone="UTC",
                    status="preview",
                )
            )
    return previews


def _matches_event(event: CalendarEventSnapshot, expected: dict[str, Any], initial_events: list[CalendarEventSnapshot]) -> bool:
    if not _title_matches(event.title, expected):
        return False
    if expected.get("date") and event.start_at.date() != _day_for(expected["date"]):
        return False
    if expected.get("start_time") and event.start_at.strftime("%H:%M") != expected["start_time"]:
        return False
    if expected.get("end_time") and event.end_at.strftime("%H:%M") != expected["end_time"]:
        return False
    if expected.get("duration_minutes") and int((event.end_at - event.start_at).total_seconds() // 60) != expected["duration_minutes"]:
        return False
    if expected.get("location_contains") and expected["location_contains"].casefold() not in (event.location or "").casefold():
        return False
    if expected.get("time_window"):
        start_label, end_label = expected["time_window"]
        start_minutes = event.start_at.hour * 60 + event.start_at.minute
        min_minutes = int(start_label[:2]) * 60 + int(start_label[3:])
        max_minutes = int(end_label[:2]) * 60 + int(end_label[3:])
        if not min_minutes <= start_minutes <= max_minutes:
            return False
    if expected.get("not_overlapping_title"):
        blockers = [item for item in initial_events if expected["not_overlapping_title"].casefold() in item.title.casefold()]
        if any(_overlaps(event, blocker) for blocker in blockers):
            return False
    return True


def assert_created_event(registry: ReadinessCalendarRegistry, expected: dict[str, Any], initial_events: list[CalendarEventSnapshot]) -> None:
    min_count = int(expected.get("min_count", 1))
    if "title_contains" not in expected and "title_contains_any" not in expected and min_count > 1:
        assert len(registry.created) >= min_count
        return
    matches = [event for event in registry.created if _matches_event(event, expected, initial_events)]
    assert len(matches) >= min_count, f"Expected created event not found: {expected}. Created: {registry.created}"


def assert_updated_event(registry: ReadinessCalendarRegistry, expected: dict[str, Any], initial_events: list[CalendarEventSnapshot]) -> None:
    matches = [event for _, event in registry.updated if _matches_event(event, expected, initial_events)]
    assert matches, f"Expected updated event not found: {expected}. Updated: {registry.updated}"


def assert_deleted_event(registry: ReadinessCalendarRegistry, expected: dict[str, Any], initial_events: list[CalendarEventSnapshot]) -> None:
    matches = [event for event in registry.deleted if _matches_event(event, expected, initial_events)]
    assert matches, f"Expected deleted event not found: {expected}. Deleted: {registry.deleted}"


def assert_needs_confirmation(response) -> None:
    assert (
        response.awaiting_confirmation
        or response.safety.requires_confirmation
        or response.status == "awaiting_confirmation"
        or response.confirmation_token
    ), "Expected response to require confirmation"


def assert_asks_clarification(response) -> None:
    text = response.reply.casefold()
    indicators = ["?", "which", "what", "when", "confirm", "уточ", "како", "когда"]
    assert any(indicator in text for indicator in indicators), f"Expected clarification question, got: {response.reply}"


def assert_draft_plan_only(response, registry: ReadinessCalendarRegistry) -> None:
    assert_needs_confirmation(response)
    assert response.execution.preview or "plan" in response.reply.casefold() or "draft" in response.reply.casefold()
    assert_no_calendar_mutation(registry)


def assert_no_conflicts(events: list[CalendarEventSnapshot]) -> None:
    for index, event in enumerate(events):
        for other in events[index + 1 :]:
            assert not _overlaps(event, other), f"Conflict detected between {event.title} and {other.title}"


def assert_within_time_window(event: CalendarEventSnapshot, start: str, end: str) -> None:
    start_minutes = int(start[:2]) * 60 + int(start[3:])
    end_minutes = int(end[:2]) * 60 + int(end[3:])
    value = event.start_at.hour * 60 + event.start_at.minute
    assert start_minutes <= value <= end_minutes


def assert_total_planned_duration(response, min_minutes: int) -> None:
    planned_minutes = sum(
        int((event.end_at - event.start_at).total_seconds() // 60)
        for event in [*_preview_events(response), *response.execution.created_events]
    )
    assert planned_minutes >= min_minutes, f"Expected at least {min_minutes} planned minutes, got {planned_minutes}"


def assert_preserves_metadata(previous: CalendarEventSnapshot, updated: CalendarEventSnapshot) -> None:
    assert updated.location == previous.location
    assert updated.description == previous.description
    assert updated.timezone == previous.timezone


def assert_no_duplicate_events(events: list[CalendarEventSnapshot]) -> None:
    seen = set()
    for event in events:
        key = (event.title.casefold(), event.start_at, event.end_at)
        assert key not in seen, f"Duplicate event found: {event.title} {event.start_at}"
        seen.add(key)


def _assert_response_terms(response, expected: dict[str, Any]) -> None:
    text = _all_response_text(response).casefold()
    for term in expected.get("expected_response_terms", []):
        assert term.casefold() in text, f"Expected response to mention {term!r}. Reply: {response.reply}"
    any_terms = expected.get("expected_response_terms_any", [])
    if any_terms:
        assert any(term.casefold() in text for term in any_terms), f"Expected one of {any_terms}. Reply: {response.reply}"
    for term in expected.get("forbidden_behavior", []):
        assert term.casefold() not in text, f"Forbidden response content {term!r}. Reply: {response.reply}"


def _assert_intent(response, expected: dict[str, Any]) -> None:
    compatible = set(expected.get("compatible_intents", []))
    compatible.add(expected["intent"])
    observed = _response_intents(response)
    observed_folded = {str(item).casefold() for item in observed}
    assert any(intent.casefold() in observed_folded for intent in compatible), (
        f"Expected intent compatible with {compatible}, got routing={response.routing.intent}, "
        f"reason={response.routing.reason!r}, goal={response.plan.goal!r}"
    )


def _assert_calendar_changes(
    response,
    registry: ReadinessCalendarRegistry,
    initial_events: list[CalendarEventSnapshot],
    expected: dict[str, Any],
) -> None:
    changes = expected.get("expected_calendar_changes", [])
    if not changes:
        assert_no_calendar_mutation(registry)
        return
    for change in changes:
        action = change["action"]
        if action == "create":
            assert_created_event(registry, change, initial_events)
        elif action == "delete":
            assert_deleted_event(registry, change, initial_events)
        elif action == "update":
            assert_updated_event(registry, change, initial_events)
        elif action == "create_or_preview":
            created_matches = [event for event in registry.created if _matches_event(event, change, initial_events)]
            preview_matches = [event for event in _preview_events(response) if _matches_event(event, change, initial_events)]
            assert created_matches or preview_matches, f"Expected created or preview event not found: {change}"
        else:
            raise AssertionError(f"Unsupported expected change action: {action}")


def _assert_case_result(response, registry: ReadinessCalendarRegistry, initial_events: list[CalendarEventSnapshot], expected: dict[str, Any]) -> None:
    assert_no_raw_internal_output(response)
    _assert_intent(response, expected)
    _assert_response_terms(response, expected)
    if expected.get("should_ask_clarification"):
        assert_asks_clarification(response)
    if expected.get("should_need_confirmation"):
        assert_needs_confirmation(response)
    if expected.get("should_create_draft_plan"):
        assert_draft_plan_only(response, registry)
    if expected.get("expected_min_planned_minutes"):
        assert_total_planned_duration(response, int(expected["expected_min_planned_minutes"]))
    _assert_calendar_changes(response, registry, initial_events, expected)
    assert_no_duplicate_events(registry.events)
    assert_no_conflicts([event for event in registry.events if event.status == "confirmed"])


@pytest.mark.parametrize("case", AI_READINESS_CASES, ids=lambda item: item["name"])
def test_ai_planning_assistant_production_readiness(case, monkeypatch):
    _patch_fixed_clock(monkeypatch)
    initial_events = _fixture_events(case["initial_calendar_state"])
    registry = ReadinessCalendarRegistry(deepcopy(initial_events))
    assistant = _assistant(registry)
    session_id = re.sub(r"[^a-z0-9]+", "-", case["name"].casefold()).strip("-")

    response = asyncio.run(_run_message(assistant, case["user_message"], session_id=session_id))
    if case.get("optional_followup"):
        assert_no_raw_internal_output(response)
        response = asyncio.run(_run_message(assistant, case["optional_followup"], session_id=session_id))

    _assert_case_result(response, registry, initial_events, case["expected_result"])
