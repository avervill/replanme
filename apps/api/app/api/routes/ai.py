"""AI planning routes — authenticated."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.ai import (
    CreateEventFromPromptRequest,
    CreateEventFromPromptResponse,
    PlannerPromptRequest,
    PlannerPromptResponse,
)
from app.schemas.calendar import GoogleCalendarEvent
from app.services.google_calendar import create_google_event
from app.services.llm import (
    build_planning_response,
    extract_calendar_event_from_prompt,
    to_extracted_calendar_events,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _dedupe_extracted_events(events: list) -> list:
    seen: set[tuple[str, str, str, str | None]] = set()
    unique = []

    for event in events:
        key = (
            event.title.strip().casefold(),
            event.start_at.isoformat(),
            event.end_at.isoformat(),
            event.location.strip().casefold() if event.location else None,
        )
        if key in seen:
            continue

        seen.add(key)
        unique.append(event)

    return unique


@router.post("/plan", response_model=PlannerPromptResponse)
async def plan_life(
    payload: PlannerPromptRequest,
    user: User = Depends(get_current_user),
) -> PlannerPromptResponse:
    return build_planning_response(payload)


@router.post("/create-event", response_model=CreateEventFromPromptResponse)
async def create_event_from_prompt(
    payload: CreateEventFromPromptRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CreateEventFromPromptResponse:
    """Extract one event from natural language and create it in Google Calendar."""
    timezone = payload.timezone or user.timezone or "UTC"

    try:
        extraction = await extract_calendar_event_from_prompt(
            payload.prompt,
            timezone=timezone,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except httpx.HTTPStatusError as exc:
        logger.error("Gemma event extraction failed: %s", exc.response.text)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI event extraction failed",
        ) from exc
    except httpx.HTTPError as exc:
        logger.error("Gemma event extraction request failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI provider is unavailable",
        ) from exc

    if not extraction.can_create:
        return CreateEventFromPromptResponse(
            created=False,
            message=(
                extraction.clarification_question
                or "I need a date, time, and event title before I can add this to your calendar."
            ),
        )

    try:
        extracted_events = to_extracted_calendar_events(
            extraction,
            fallback_timezone=timezone,
        )
        extracted_events = _dedupe_extracted_events(extracted_events)
    except ValueError as exc:
        return CreateEventFromPromptResponse(
            created=False,
            message=str(exc),
        )

    events: list[GoogleCalendarEvent] = []
    try:
        for extracted in extracted_events:
            event_body = {
                "summary": extracted.title,
                "description": extracted.description,
                "start": {
                    "dateTime": extracted.start_at.isoformat(),
                    "timeZone": extracted.timezone,
                },
                "end": {
                    "dateTime": extracted.end_at.isoformat(),
                    "timeZone": extracted.timezone,
                },
                "reminders": {
                    "useDefault": False,
                    "overrides": [{"method": "popup", "minutes": 15}],
                },
            }

            if extracted.location:
                event_body["location"] = extracted.location

            result = await create_google_event(user.id, db, event_body=event_body)
            events.append(
                GoogleCalendarEvent(
                    id=result.get("id", ""),
                    title=result.get("summary", "Untitled"),
                    description=result.get("description"),
                    start=result.get("start", {}),
                    end=result.get("end", {}),
                    location=result.get("location"),
                    status=result.get("status", "confirmed"),
                    html_link=result.get("htmlLink"),
                )
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except httpx.HTTPError as exc:
        logger.error("Failed to create Google Calendar event from AI prompt: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to create event in Google Calendar",
        ) from exc

    event = events[0] if events else None
    count = len(events)
    message = (
        f"Created {count} events in your Google Calendar."
        if count != 1
        else f"Created '{event.title if event else 'event'}' in your Google Calendar."
    )

    return CreateEventFromPromptResponse(
        created=True,
        message=message,
        event=event,
        events=events,
        extracted=extracted_events[0] if extracted_events else None,
        extracted_events=extracted_events,
    )
