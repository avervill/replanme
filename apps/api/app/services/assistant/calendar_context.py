"""Deterministic calendar window selection and free-block preprocessing."""

from __future__ import annotations

from datetime import datetime, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.assistant import CalendarEventSnapshot, FetchEventsInput, UserPlanningMemory
from app.services.assistant.tools import AssistantToolRegistry
from app.services.assistant.types import CompactCalendarEvent, Constraint, FreeBlock


def compact_event(event: CalendarEventSnapshot) -> CompactCalendarEvent:
    return CompactCalendarEvent(
        id=event.id,
        title=event.title,
        start=event.start_at.isoformat(),
        end=event.end_at.isoformat(),
        timezone=event.timezone,
    )


def _overlaps(left_start: datetime, left_end: datetime, right_start: datetime, right_end: datetime) -> bool:
    return left_start < right_end and right_start < left_end


def _constraint_blocks(day: datetime, constraints: list[Constraint], tzinfo) -> list[tuple[datetime, datetime, str]]:
    blocks: list[tuple[datetime, datetime, str]] = []
    for constraint in constraints:
        if constraint.kind == "cooking" and constraint.minutes_per_day:
            if constraint.minutes_per_day >= 120:
                lunch = datetime.combine(day.date(), time(hour=12, minute=30), tzinfo=tzinfo)
                dinner = datetime.combine(day.date(), time(hour=19), tzinfo=tzinfo)
                blocks.append((lunch, lunch + timedelta(minutes=60), "Cooking"))
                blocks.append((dinner, dinner + timedelta(minutes=constraint.minutes_per_day - 60), "Cooking"))
            else:
                start = datetime.combine(day.date(), time(hour=19), tzinfo=tzinfo)
                blocks.append((start, start + timedelta(minutes=constraint.minutes_per_day), "Cooking"))
    return blocks


def compute_free_blocks(
    *,
    start_at: datetime,
    end_at: datetime,
    fixed_events: list[CalendarEventSnapshot],
    constraints: list[Constraint],
    memory: UserPlanningMemory,
    min_minutes: int = 30,
) -> list[FreeBlock]:
    tzinfo = start_at.tzinfo
    busy: list[tuple[datetime, datetime, str]] = [
        (event.start_at, event.end_at, event.title) for event in fixed_events
    ]
    cursor_day = start_at.replace(hour=0, minute=0, second=0, microsecond=0)
    last_day = end_at.replace(hour=0, minute=0, second=0, microsecond=0)
    while cursor_day <= last_day:
        busy.extend(_constraint_blocks(cursor_day, constraints, tzinfo))
        cursor_day += timedelta(days=1)

    busy.sort(key=lambda item: (item[0], item[1]))
    merged: list[tuple[datetime, datetime, str]] = []
    for block in busy:
        if not merged or block[0] > merged[-1][1]:
            merged.append(block)
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], block[1]), merged[-1][2])

    free: list[FreeBlock] = []
    day = start_at.replace(hour=0, minute=0, second=0, microsecond=0)
    while day < end_at:
        day_start = max(datetime.combine(day.date(), memory.wake_time, tzinfo=tzinfo), start_at)
        day_end = min(datetime.combine(day.date(), memory.sleep_time, tzinfo=tzinfo), end_at)
        cursor = day_start
        for busy_start, busy_end, _ in merged:
            if busy_end <= day_start or busy_start >= day_end:
                continue
            if cursor < busy_start and int((busy_start - cursor).total_seconds() // 60) >= min_minutes:
                free.append(
                    FreeBlock(
                        start=cursor.isoformat(),
                        end=busy_start.isoformat(),
                        minutes=int((busy_start - cursor).total_seconds() // 60),
                        energy_band="high" if cursor.hour < 12 else "medium",
                    )
                )
            cursor = max(cursor, busy_end)
        if cursor < day_end and int((day_end - cursor).total_seconds() // 60) >= min_minutes:
            free.append(
                FreeBlock(
                    start=cursor.isoformat(),
                    end=day_end.isoformat(),
                    minutes=int((day_end - cursor).total_seconds() // 60),
                    energy_band="high" if cursor.hour < 12 else "medium",
                )
            )
        day += timedelta(days=1)
    return free


async def build_calendar_context(
    *,
    registry: AssistantToolRegistry,
    user: User,
    db: AsyncSession,
    memory: UserPlanningMemory,
    start_at: datetime,
    end_at: datetime,
    constraints: list[Constraint],
    max_events: int = 250,
) -> tuple[list[CalendarEventSnapshot], list[CompactCalendarEvent], list[FreeBlock]]:
    fetched = await registry.fetch_events(
        FetchEventsInput(start_at=start_at, end_at=end_at, max_results=max_events),
        user=user,
        db=db,
        memory=memory,
    )
    events = sorted(fetched.events, key=lambda event: (event.start_at, event.end_at))
    free_blocks = compute_free_blocks(
        start_at=start_at,
        end_at=end_at,
        fixed_events=events,
        constraints=constraints,
        memory=memory,
    )
    return events, [compact_event(event) for event in events[:80]], free_blocks[:120]
