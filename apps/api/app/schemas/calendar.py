"""Calendar-related Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CalendarEventBase(BaseModel):
    title: str = Field(..., min_length=2)
    description: str | None = None
    start_at: datetime
    end_at: datetime
    timezone: str = "UTC"
    location: str | None = None
    reminders: list[int] = Field(default_factory=lambda: [15])
    buffer_before_minutes: int = 0
    buffer_after_minutes: int = 0


class CalendarEventCreate(CalendarEventBase):
    pass


class CalendarEventUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    timezone: str | None = None
    location: str | None = None
    reminders: list[int] | None = None
    metadata: dict[str, str] | None = None


class CalendarEventResponse(CalendarEventBase):
    id: uuid.UUID
    status: str = "pending_approval"


class GoogleCalendarEvent(BaseModel):
    """Normalized response from Google Calendar API."""

    id: str
    title: str
    description: str | None = None
    start: dict[str, Any] = Field(default_factory=dict)
    end: dict[str, Any] = Field(default_factory=dict)
    location: str | None = None
    status: str = "confirmed"
    html_link: str | None = None
