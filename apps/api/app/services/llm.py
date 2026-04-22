"""LLM helpers for planning and calendar-event extraction."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.core.config import settings
from app.schemas.ai import (
    ExtractedCalendarEvent,
    PlannerPromptRequest,
    PlannerPromptResponse,
    SuggestedAction,
)

GOOGLE_GENERATE_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)


class EventCandidate(BaseModel):
    title: str
    description: str | None = None
    start_at: datetime
    end_at: datetime | None = None
    timezone: str | None = None
    location: str | None = None

    @field_validator("timezone")
    @classmethod
    def normalize_timezone(cls, value: str | None) -> str | None:
        if value:
            return value.strip()
        return value


class EventExtractionResult(BaseModel):
    can_create: bool = False
    clarification_question: str | None = None
    events: list[EventCandidate] = Field(default_factory=list)
    title: str | None = None
    description: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    timezone: str | None = None
    location: str | None = None

    @field_validator("timezone")
    @classmethod
    def normalize_timezone(cls, value: str | None) -> str | None:
        if value:
            return value.strip()
        return value


def build_planning_response(payload: PlannerPromptRequest) -> PlannerPromptResponse:
    timeframe_phrase = {
        "week": "this week",
        "month": "the upcoming month",
        "year": "the coming year",
    }[payload.timeframe]

    actions = [
        SuggestedAction(
            kind="protect_focus_block",
            summary="Reserve peak-focus windows for your highest-value work.",
        ),
        SuggestedAction(
            kind="create_event",
            summary="Draft new calendar events from the prompt and keep them pending approval.",
        ),
    ]

    if payload.constraints:
        actions.append(
            SuggestedAction(
                kind="ask_user",
                summary=f"Validate these constraints before sync: {', '.join(payload.constraints)}.",
            )
        )

    return PlannerPromptResponse(
        plan_summary=(
            f"Prepared an AI-assisted scheduling outline for {timeframe_phrase} based on: "
            f"'{payload.prompt}'."
        ),
        actions=actions,
        approval_required=True,
    )


def _resolve_timezone(timezone: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _build_extraction_prompt(prompt: str, timezone: str) -> str:
    tz = _resolve_timezone(timezone)
    now = datetime.now(tz)

    return f"""
You are an event extraction engine for a calendar app.

Current datetime: {now.isoformat()}
User timezone: {timezone}

Task:
Extract one or more Google Calendar events from the user's request.

Rules:
- Return only JSON.
- Return JSON with this exact shape:
  {{"can_create": boolean, "clarification_question": string|null, "events": [{{"title": string, "description": string|null, "start_at": string, "end_at": string, "timezone": string, "location": string|null}}]}}
- If the request lacks a clear title, date, or start time for any requested event, set can_create=false and ask one concise clarification_question.
- If the user requests multiple assignments/events, extract all of them into events.
- Do not duplicate the same event.
- Do not split one continuous time range into several events. For example, "Tuesday 13-19:00" is one event from 13:00 to 19:00.
- Resolve relative dates like today, tomorrow, next Monday, this Friday using Current datetime.
- If the user gives a start time but no duration, use 60 minutes.
- If the user gives a date without a year, use the next upcoming matching date.
- start_at and end_at must be ISO 8601 datetimes with timezone offset when can_create=true.
- timezone must be an IANA timezone string.
- Keep title short and human-readable.
- Put useful extra details in description.
- Do not use markdown fences.

User request:
{prompt}
""".strip()


def _extract_text(response: dict[str, Any]) -> str:
    candidates = response.get("candidates") or []
    for candidate in candidates:
        parts = candidate.get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts)
        if text.strip():
            return text.strip()
    return ""


def _parse_json_response(text: str) -> dict[str, Any]:
    clean = text.strip()
    if clean.startswith("```"):
        clean = clean.strip("`")
        if clean.startswith("json"):
            clean = clean[4:]
    start = clean.find("{")
    end = clean.rfind("}")
    if start >= 0 and end >= start:
        clean = clean[start : end + 1]
    return json.loads(clean)


async def extract_calendar_event_from_prompt(
    prompt: str,
    *,
    timezone: str,
) -> EventExtractionResult:
    """Use hosted Gemma through the Gemini API to extract calendar events."""
    if not settings.google_ai_api_key:
        raise ValueError("Missing GOOGLE_AI_API_KEY for AI event extraction")

    url = GOOGLE_GENERATE_URL.format(model=settings.gemma_model)
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": _build_extraction_prompt(prompt, timezone)}],
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
        },
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            params={"key": settings.google_ai_api_key},
            json=payload,
        )
        response.raise_for_status()

    text = _extract_text(response.json())
    if not text:
        raise ValueError("AI returned an empty response")

    try:
        return EventExtractionResult.model_validate(_parse_json_response(text))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError("AI returned an invalid event payload") from exc


def to_extracted_calendar_event(
    result: EventExtractionResult,
    *,
    fallback_timezone: str,
) -> ExtractedCalendarEvent:
    if not result.title or not result.start_at:
        raise ValueError("AI did not provide enough event data")

    end_at = result.end_at or result.start_at + timedelta(hours=1)
    timezone = result.timezone or fallback_timezone

    return ExtractedCalendarEvent(
        title=result.title,
        description=result.description,
        start_at=result.start_at,
        end_at=end_at,
        timezone=timezone,
        location=result.location,
    )


def to_extracted_calendar_events(
    result: EventExtractionResult,
    *,
    fallback_timezone: str,
) -> list[ExtractedCalendarEvent]:
    if result.events:
        extracted: list[ExtractedCalendarEvent] = []
        for event in result.events:
            end_at = event.end_at or event.start_at + timedelta(hours=1)
            extracted.append(
                ExtractedCalendarEvent(
                    title=event.title,
                    description=event.description,
                    start_at=event.start_at,
                    end_at=end_at,
                    timezone=event.timezone or fallback_timezone,
                    location=event.location,
                )
            )
        return extracted

    # Backward compatibility for older model responses while the prompt settles.
    return [to_extracted_calendar_event(result, fallback_timezone=fallback_timezone)]
