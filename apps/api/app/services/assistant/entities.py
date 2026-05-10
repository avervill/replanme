"""Rule-first entity extraction and date parsing for calendar requests."""

from __future__ import annotations

import re
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.schemas.assistant import ExtractedEntities

WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

FILLER_WORDS = {
    "my",
    "the",
    "a",
    "an",
    "please",
    "event",
    "for",
    "to",
    "at",
    "on",
    "today",
    "tonight",
    "tomorrow",
    "this",
    "next",
    "week",
    "month",
    "all",
    "from",
    "into",
    "around",
    "cancelled",
    "canceled",
    "cancel",
    "delete",
    "remove",
    "add",
    "create",
    "schedule",
    "book",
    "set",
    "up",
    "put",
    "plan",
    "move",
    "duplicate",
    "make",
    "less",
    "packed",
}


def extract_entities(
    prompt: str,
    *,
    timezone: str,
    now: datetime,
) -> ExtractedEntities:
    clean_prompt = _strip_wrapping_quotes(prompt)
    lowered = clean_prompt.lower()
    entities = ExtractedEntities()

    target_day = _extract_date(lowered, timezone=timezone, now=now)
    if target_day:
        entities.date = target_day.date().isoformat()

    if "this week" in lowered:
        entities.source_date_range = "this week"
    if "next week" in lowered:
        if "from this week to next week" in lowered or "into next week" in lowered:
            entities.target_date_range = "next week"
        elif entities.source_date_range is None:
            entities.source_date_range = "next week"

    title = _extract_title_candidate(clean_prompt)
    if title:
        entities.title = title

    parsed_time = _extract_time(lowered, title=title)
    if parsed_time:
        entities.start_time = parsed_time

    duration = _extract_duration_minutes(lowered) or _default_duration_minutes(title or "")
    if duration:
        entities.duration_minutes = duration

    participants = _extract_participants(clean_prompt)
    if participants:
        entities.participants = participants

    return entities


def resolve_relative_day(label: str, *, timezone: str, now: datetime) -> datetime:
    tz = ZoneInfo(timezone)
    localized_now = now.astimezone(tz) if now.tzinfo else now.replace(tzinfo=UTC).astimezone(tz)
    current_day = localized_now.replace(hour=0, minute=0, second=0, microsecond=0)
    if label == "today":
        return current_day
    if label == "tomorrow":
        return current_day + timedelta(days=1)
    raise ValueError(f"Unsupported relative day: {label}")


def resolve_named_range(label: str, *, timezone: str, now: datetime) -> tuple[datetime, datetime]:
    tz = ZoneInfo(timezone)
    localized_now = now.astimezone(tz) if now.tzinfo else now.replace(tzinfo=UTC).astimezone(tz)
    current_day = localized_now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = current_day - timedelta(days=current_day.weekday())

    if label == "this week":
        start = week_start
        end = start + timedelta(days=7)
        return start, end
    if label == "next week":
        start = week_start + timedelta(days=7)
        end = start + timedelta(days=7)
        return start, end
    raise ValueError(f"Unsupported range label: {label}")


def build_event_datetimes(
    entities: ExtractedEntities,
    *,
    timezone: str,
    now: datetime,
    default_duration_minutes: int = 60,
) -> tuple[datetime, datetime] | None:
    if not entities.date or not entities.start_time:
        return None

    tz = ZoneInfo(timezone)
    target_date = datetime.fromisoformat(entities.date).date()
    hours, minutes = [int(value) for value in entities.start_time.split(":")]
    start = datetime.combine(target_date, time(hour=hours, minute=minutes), tzinfo=tz)
    duration = entities.duration_minutes or default_duration_minutes
    end = start + timedelta(minutes=duration)
    return start, end


def _strip_wrapping_quotes(value: str) -> str:
    return value.strip().strip(" \"'\u201c\u201d\u2018\u2019")


def _extract_date(prompt: str, *, timezone: str, now: datetime) -> datetime | None:
    if "today" in prompt or "tonight" in prompt:
        return resolve_relative_day("today", timezone=timezone, now=now)
    if "tomorrow" in prompt:
        return resolve_relative_day("tomorrow", timezone=timezone, now=now)

    tz = ZoneInfo(timezone)
    localized_now = now.astimezone(tz) if now.tzinfo else now.replace(tzinfo=UTC).astimezone(tz)
    current_day = localized_now.replace(hour=0, minute=0, second=0, microsecond=0)
    for name, weekday in WEEKDAYS.items():
        if re.search(rf"\bnext\s+{name}\b", prompt):
            days_ahead = (weekday - current_day.weekday()) % 7
            return current_day + timedelta(days=days_ahead or 7)
        if re.search(rf"\b{weeksafe(name)}\b", prompt):
            days_ahead = (weekday - current_day.weekday()) % 7
            return current_day + timedelta(days=days_ahead)
    return None


def weeksafe(name: str) -> str:
    return re.escape(name)


def _extract_duration_minutes(prompt: str) -> int | None:
    match = re.search(r"\bfor\s+(\d+(?:\.\d+)?)\s*(hours?|hrs?|h)\b", prompt)
    if match:
        return int(float(match.group(1)) * 60)
    match = re.search(r"\bfor\s+(\d{1,3})\s*(minutes?|mins?|m)\b", prompt)
    if match:
        return int(match.group(1))
    return None


def _extract_time(prompt: str, *, title: str | None) -> str | None:
    if "late tonight" in prompt:
        return "21:00"
    if "before bed" in prompt:
        return "22:00"
    if "tonight" in prompt:
        return "19:00"
    if "late evening" in prompt:
        return "20:00"
    if "evening" in prompt:
        return "18:00"
    if "late morning" in prompt:
        return "11:00"
    if "early morning" in prompt:
        return "07:00"
    if "morning" in prompt:
        return "09:00"
    if "around noon" in prompt or re.search(r"\bnoon\b", prompt):
        return "12:00"
    if "after lunch" in prompt:
        return "13:00"
    if "after work" in prompt:
        return "18:30"
    if "afternoon" in prompt:
        return "15:00"
    if title and title.lower().strip() == "lunch":
        return "12:00"

    match = re.search(
        r"(?:\bat\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b(?!\s*(?:hours?|hrs?|minutes?|mins?))",
        prompt,
    )
    if not match:
        return None

    hours = int(match.group(1))
    minutes = int(match.group(2) or 0)
    meridiem = match.group(3)
    context = f"{prompt} {title or ''}".lower()

    if meridiem == "pm" and hours < 12:
        hours += 12
    elif meridiem == "am" and hours == 12:
        hours = 0
    elif meridiem is None:
        if any(word in context for word in ("dinner", "tonight", "evening", "after work")) and 1 <= hours <= 11:
            hours += 12
        elif any(word in context for word in ("breakfast", "morning")):
            pass
        elif 1 <= hours <= 7:
            hours += 12
        elif hours == 8 and any(word in context for word in ("dinner", "evening")):
            hours = 20

    if hours > 23 or minutes > 59:
        return None
    return f"{hours:02d}:{minutes:02d}"


def _extract_title_candidate(prompt: str) -> str | None:
    clean = _strip_wrapping_quotes(prompt)
    clean = re.sub(r"^\s*(add|create|schedule|book|set\s+up|setup|plan|put|remind\s+me\s+to)\s+", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s+on\s+my\s+calendar\b", "", clean, flags=re.IGNORECASE)
    clean = re.split(
        r"\b(?:today|late tonight|tonight|tomorrow|next\s+\w+|monday|tuesday|wednesday|thursday|friday|saturday|sunday|at\s+\d|for\s+\d|around noon|after lunch|before bed|early morning|late morning|late evening|morning|noon|afternoon|evening|after work|cancelled|canceled|cancel|on\s+)",
        clean,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    clean = re.sub(r"^\s*(my|the|a|an)\s+", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s+", " ", clean).strip(" .")
    if clean:
        return clean.title()

    fallback = re.sub(r"[^\w\s]", " ", prompt)
    fallback = re.sub(r"\b\d{1,2}(:\d{2})?\s*(am|pm)?\b", " ", fallback, flags=re.IGNORECASE)
    tokens = [token for token in fallback.lower().split() if token not in FILLER_WORDS]
    if not tokens:
        return None
    return " ".join(tokens[:5]).strip().title()


def _extract_participants(prompt: str) -> list[str]:
    match = re.search(r"\bwith\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", prompt)
    if not match:
        return []
    return [match.group(1)]


def _default_duration_minutes(title: str) -> int | None:
    lowered = title.lower()
    if "study" in lowered:
        return 120
    if any(word in lowered for word in ("gym", "workout", "dinner", "lunch", "coffee", "appointment")):
        return 60
    return 60 if title else None
