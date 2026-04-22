import uuid
from datetime import UTC, datetime, timedelta

from app.schemas.calendar import CalendarEventCreate, CalendarEventResponse


def list_upcoming_events() -> list[CalendarEventResponse]:
    base = datetime.now(tz=UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return [
        CalendarEventResponse(
            id=uuid.uuid4(),
            title="Focus Sprint",
            description="Protected deep work block",
            start_at=base + timedelta(days=1, hours=9),
            end_at=base + timedelta(days=1, hours=11),
            timezone="UTC",
            location=None,
            reminders=[30],
            buffer_before_minutes=0,
            buffer_after_minutes=15,
            status="synced",
        ),
        CalendarEventResponse(
            id=uuid.uuid4(),
            title="Operations Catch-up",
            description="Admin tasks during lower-energy window",
            start_at=base + timedelta(days=1, hours=14),
            end_at=base + timedelta(days=1, hours=15),
            timezone="UTC",
            location=None,
            reminders=[10],
            buffer_before_minutes=10,
            buffer_after_minutes=0,
            status="synced",
        ),
    ]


def create_calendar_event(payload: CalendarEventCreate) -> CalendarEventResponse:
    return CalendarEventResponse(
        id=uuid.uuid4(),
        status="pending_approval",
        **payload.model_dump(),
    )
