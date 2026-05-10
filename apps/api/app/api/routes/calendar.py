"""Calendar event routes – authenticated, with Google Calendar integration."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.calendar import (
    CalendarEventCreate,
    CalendarEventResponse,
    CalendarEventUpdate,
    GoogleCalendarEvent,
)
from app.services.google_calendar import (
    create_google_event,
    delete_google_event,
    get_google_event,
    list_google_events,
    update_google_event,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# List events
# ---------------------------------------------------------------------------

@router.get("/events", response_model=list[GoogleCalendarEvent])
async def get_events(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List upcoming events from Google Calendar."""
    try:
        items = await list_google_events(user.id, db)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("Failed to list events: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch events from Google Calendar",
        ) from exc

    return [
        GoogleCalendarEvent(
            id=item.get("id", ""),
            title=item.get("summary", "Untitled"),
            description=item.get("description"),
            start=item.get("start", {}),
            end=item.get("end", {}),
            location=item.get("location"),
            status=item.get("status", "confirmed"),
            html_link=item.get("htmlLink"),
        )
        for item in items
    ]


# ---------------------------------------------------------------------------
# Create event
# ---------------------------------------------------------------------------

@router.post("/events", response_model=GoogleCalendarEvent)
async def create_event(
    payload: CalendarEventCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new event on Google Calendar."""
    event_body = {
        "summary": payload.title,
        "description": payload.description,
        "start": {
            "dateTime": payload.start_at.isoformat(),
            "timeZone": payload.timezone,
        },
        "end": {
            "dateTime": payload.end_at.isoformat(),
            "timeZone": payload.timezone,
        },
    }
    if payload.location:
        event_body["location"] = payload.location
    if payload.reminders:
        event_body["reminders"] = {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": m} for m in payload.reminders
            ],
        }

    try:
        result = await create_google_event(user.id, db, event_body=event_body)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    return GoogleCalendarEvent(
        id=result.get("id", ""),
        title=result.get("summary", "Untitled"),
        description=result.get("description"),
        start=result.get("start", {}),
        end=result.get("end", {}),
        location=result.get("location"),
        status=result.get("status", "confirmed"),
        html_link=result.get("htmlLink"),
    )


# ---------------------------------------------------------------------------
# Update event
# ---------------------------------------------------------------------------

@router.put("/events/{event_id}", response_model=GoogleCalendarEvent)
async def update_event(
    event_id: str,
    payload: CalendarEventUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing Google Calendar event."""
    event_body: dict = {}
    if payload.title is not None:
        event_body["summary"] = payload.title
    if payload.description is not None:
        event_body["description"] = payload.description
    if payload.start_at is not None:
        event_body["start"] = {
            "dateTime": payload.start_at.isoformat(),
            "timeZone": payload.timezone or "UTC",
        }
    if payload.end_at is not None:
        event_body["end"] = {
            "dateTime": payload.end_at.isoformat(),
            "timeZone": payload.timezone or "UTC",
        }
    if payload.location is not None:
        event_body["location"] = payload.location
    if payload.reminders is not None:
        event_body["reminders"] = {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": minutes} for minutes in payload.reminders
            ],
        }
    if payload.metadata is not None:
        event_body["extendedProperties"] = {"private": payload.metadata}

    try:
        await update_google_event(
            user.id, db, event_id=event_id, event_body=event_body
        )
        result = await get_google_event(user.id, db, event_id=event_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    return GoogleCalendarEvent(
        id=result.get("id", ""),
        title=result.get("summary", "Untitled"),
        description=result.get("description"),
        start=result.get("start", {}),
        end=result.get("end", {}),
        location=result.get("location"),
        status=result.get("status", "confirmed"),
        html_link=result.get("htmlLink"),
    )


# ---------------------------------------------------------------------------
# Delete event
# ---------------------------------------------------------------------------

@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_event(
    event_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a Google Calendar event."""
    try:
        await delete_google_event(user.id, db, event_id=event_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
