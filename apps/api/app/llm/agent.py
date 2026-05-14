"""The central Planner Agent using OpenAI for schedule orchestration."""

from __future__ import annotations

import json
import logging
import re
import zoneinfo
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User
from app.schemas.assistant import (
    AssistantMessageRequest,
    AssistantMessageResponse,
    CalendarEventSnapshot,
    CreateEventInput,
    DeleteEventInput,
    DisplayAction,
    ExecutionPlan,
    FetchEventsInput,
    PendingCalendarAction,
    PendingActionFilters,
    PlanExecutionResult,
    PlanPreviewChange,
    RoutingDecision,
    SafetyAssessment,
)
from app.services.assistant.tools import AssistantToolRegistry
from app.llm.memory import AgentMemoryHandler
from app.llm.openai_params import completion_token_param
from app.llm.prompts import build_planner_prompt
from app.llm.tools import compact_tool_response, execute_tool_call, get_openai_tools

from app.services.assistant.state import ConversationStateStore
from app.services.assistant.memory import PlanningMemoryService
from app.services.subscriptions import FeatureName, PaywallError, commit_usage, refund_usage, reserve_usage
from app.llm.gemma import GemmaClient
import uuid

logger = logging.getLogger(__name__)

DAY_NAMES = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
MONTH_NAMES = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
CREATE_VERB_PATTERN = r"\b(add|create|schedule|sched|book|set\s+up|setup|put|make)\b"
CREATE_VERB_PREFIX_PATTERN = r"^\s*(add|create|schedule|sched|book|set\s+up|setup|put|make)\s+"
WEEKDAY_ALIASES = {
    "mon": "monday",
    "monday": "monday",
    "mond": "monday",
    "tue": "tuesday",
    "tues": "tuesday",
    "tuesday": "tuesday",
    "wed": "wednesday",
    "wedn": "wednesday",
    "weds": "wednesday",
    "wednes": "wednesday",
    "wensday": "wednesday",
    "wensdey": "wednesday",
    "wednesday": "wednesday",
    "thu": "thursday",
    "thur": "thursday",
    "thurs": "thursday",
    "thursday": "thursday",
    "fri": "friday",
    "friday": "friday",
    "sat": "saturday",
    "saturday": "saturday",
    "sun": "sunday",
    "sunday": "sunday",
}
NUMBER_WORDS = {
    "zero": 0,
    "oh": 0,
    "o": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
}
HOUR_WORD_PATTERN = (
    "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve"
)
MINUTE_WORD_PATTERN = (
    "a\\s+half|half|quarter|oh\\s+five|oh\\s+ten|"
    "five|ten|fifteen|twenty|twenty[-\\s]five|thirty|forty|forty[-\\s]five|fifty|fifty[-\\s]five"
)
TIME_TOKEN_PATTERN = r"(?:\d{1,2}(?::[0-5]\d)?\s*(?:am|pm)?|noon|midnight)"
AFFIRMATIVE_CREATE_REPLIES = {
    "sounds good",
    "that works",
    "works for me",
    "that sounds good",
}


@dataclass
class SimpleCalendarExtraction:
    intent: str = "unknown"
    title: str | None = None
    date: str | None = None
    date_value: datetime | None = None
    start_time: str | None = None
    end_time: str | None = None
    duration_minutes: int | None = None
    missing_fields: list[str] = field(default_factory=list)
    confidence: float = 0.0
    relative_time: str | None = None
    approximate_time: str | None = None
    old_time: str | None = None
    new_time: str | None = None
    requires_calendar_read: bool = False


def _history_with_complete_tool_interactions(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replay stored history while dropping only broken tool-call fragments at the trim boundary."""
    replay: list[dict[str, Any]] = []
    index = 0
    while index < len(history):
        message = history[index]
        role = message.get("role")

        if role == "assistant" and message.get("tool_calls"):
            expected_ids = {
                tool_call.get("id")
                for tool_call in message.get("tool_calls", [])
                if tool_call.get("id")
            }
            group = [message]
            cursor = index + 1
            while cursor < len(history) and history[cursor].get("role") == "tool":
                tool_message = history[cursor]
                tool_call_id = tool_message.get("tool_call_id")
                if tool_call_id in expected_ids:
                    group.append(tool_message)
                    expected_ids.remove(tool_call_id)
                cursor += 1

            if not expected_ids:
                replay.extend(group)
            index = cursor
            continue

        if role == "tool":
            index += 1
            continue

        replay.append(message)
        index += 1

    return replay


def _extract_last_event_from_tool_result(tool_result: str) -> tuple[str | None, str | None]:
    try:
        payload = json.loads(tool_result)
    except json.JSONDecodeError:
        return None, None

    for key in ("created_events", "duplicated_events"):
        events = payload.get(key)
        if isinstance(events, list) and events:
            event = events[0]
            if isinstance(event, dict) and event.get("id") and event.get("title"):
                return event["id"], event["title"]

    for key in ("updated_event", "moved_event"):
        event = payload.get(key)
        if isinstance(event, dict) and event.get("id") and event.get("title"):
            return event["id"], event["title"]

    return None, None


def _looks_like_user_constraint(prompt: str) -> bool:
    normalized = prompt.strip().casefold()
    if not normalized:
        return False
    patterns = [
        r"\bi work\b",
        r"\bmy work hours\b",
        r"\bdon'?t schedule\b",
        r"\bdo not schedule\b",
        r"\bno events?\b",
        r"\bavoid scheduling\b",
        r"\bi prefer\b",
        r"\bprefer\b.*\b(morning|afternoon|evening|night|weekends?)\b",
    ]
    return any(re.search(pattern, normalized) for pattern in patterns)


def _looks_like_conflict_resolution(prompt: str) -> bool:
    normalized = prompt.strip().casefold()
    return any(phrase in normalized for phrase in ("fix conflicts", "resolve conflicts", "optimize", "free up time"))


def _classify_prompt_intent(prompt: str, attachments: list[dict[str, Any]]) -> str:
    normalized = prompt.strip().casefold()
    if attachments and _references_uploaded_image(prompt, attachments):
        return "image"
    if re.search(CREATE_VERB_PATTERN, normalized):
        return "create"
    if _looks_like_bare_event_create(prompt):
        return "create"
    if _looks_like_conflict_resolution(prompt):
        return "conflict"
    if any(phrase in normalized for phrase in ("plan my", "plan the", "study plan", "exam", "finals", "burned out", "burnt out")):
        return "planning"
    if any(word in normalized for word in ("delete", "remove", "clear")):
        return "delete"
    if any(word in normalized for word in ("move", "reschedule", "later", "earlier")):
        return "move"
    if any(word in normalized for word in ("rename", "edit", "update", "change")):
        return "update"
    if re.search(r"\b(what|show|list|find)\b", normalized) and any(
        token in normalized for token in ("calendar", "schedule", "events", "today", "tomorrow", "week")
    ):
        return "query"
    return "chat"


async def _classify_prompt_intent_with_gemma(prompt: str, attachments: list[dict[str, Any]]) -> str:
    baseline = _classify_prompt_intent(prompt, attachments)
    gemma_json = await GemmaClient().generate_json(
        schema_name="LegacyPromptIntent",
        system_prompt=(
            "Classify a calendar assistant prompt for tool routing. Return JSON with one key intent. "
            "intent must be one of create, query, delete, move, update, conflict, planning, image, chat. "
            "Use image only when the user references an uploaded image."
        ),
        payload={
            "message": prompt,
            "attachments_count": len(attachments or []),
            "has_image_reference": bool(attachments and _references_uploaded_image(prompt, attachments)),
            "deterministic_baseline": baseline,
        },
        max_output_tokens=settings.nano_max_output_tokens,
    )
    if isinstance(gemma_json, dict):
        intent = gemma_json.get("intent")
        if intent in {"create", "query", "delete", "move", "update", "conflict", "planning", "image", "chat"}:
            return str(intent)
    return baseline


def _select_tool_names(intent: str, must_parse_image: bool) -> tuple[str, ...]:
    tools_by_intent = {
        "create": ("fetch_events", "create_event", "detect_conflicts"),
        "query": ("fetch_events", "summarize_schedule"),
        "delete": ("fetch_events", "delete_event", "batch_delete_events"),
        "move": ("fetch_events", "move_event", "find_free_slots", "detect_conflicts", "batch_move_events"),
        "update": ("fetch_events", "edit_event"),
        "conflict": ("fetch_events", "detect_conflicts", "optimize_schedule", "find_free_slots", "move_event", "batch_move_events"),
        "planning": ("fetch_events", "find_free_slots", "create_event", "detect_conflicts", "summarize_schedule"),
        "image": ("parse_schedule_image", "fetch_events", "create_event", "find_free_slots"),
        "chat": (),
    }
    selected = list(tools_by_intent.get(intent, tools_by_intent["chat"]))
    if must_parse_image and "parse_schedule_image" not in selected:
        selected.insert(0, "parse_schedule_image")
    return tuple(dict.fromkeys(selected))


def _needs_date_rules(prompt: str, intent: str) -> bool:
    normalized = prompt.casefold()
    return intent != "chat" or any(
        token in normalized
        for token in (
            "today",
            "tomorrow",
            "week",
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
            "morning",
            "afternoon",
            "evening",
            "tonight",
        )
    )


def _compact_memory_payload(memory: Any) -> str:
    parts = [
        f"wake {memory.wake_time.strftime('%H:%M')}",
        f"sleep {memory.sleep_time.strftime('%H:%M')}",
        f"work {memory.workday_start.strftime('%H:%M')}-{memory.workday_end.strftime('%H:%M')}",
        f"break {memory.preferred_break_minutes}m",
    ]
    if memory.priorities:
        parts.append("priorities: " + ", ".join(memory.priorities[:5]))
    if memory.scheduling_preferences:
        parts.append("prefs: " + "; ".join(memory.scheduling_preferences[:5]))
    if memory.notes:
        parts.append("notes: " + "; ".join(memory.notes[:3]))
    return "; ".join(parts)


def _references_uploaded_image(prompt: str, attachments: list[dict[str, Any]]) -> bool:
    if not attachments:
        return False
    normalized = prompt.casefold()
    triggers = ("this is my schedule", "use the photo", "from image", "from the image", "topics from image", "curriculum on the photo", "photo", "image", "picture")
    return any(trigger in normalized for trigger in triggers)


def _build_attachment_context(attachments: list[dict[str, Any]]) -> str:
    if not attachments:
        return ""
    lines = ["Uploaded files:"]
    for attachment in attachments:
        lines.append(
            f"- id={attachment.get('id')} filename={attachment.get('filename')} "
            f"kind={attachment.get('kind')} content_type={attachment.get('content_type')}"
        )
        preview = str(attachment.get("text_preview") or "").strip()
        if preview:
            structured_lines = []
            for raw_line in preview.splitlines():
                line = " ".join(raw_line.split())
                if not line:
                    continue
                lowered = line.casefold()
                if (
                    re.search(r"\b\d{1,2}:\d{2}\b", line)
                    or any(day in lowered for day in DAY_NAMES)
                    or any(token in lowered for token in ("subject", "topic", "class", "course", "lesson"))
                ):
                    structured_lines.append(line[:140])
                if len(structured_lines) >= 10:
                    break
            compact_preview = "; ".join(structured_lines) or preview[:500]
            lines.append(f"  extracted_summary: {compact_preview[:800]}")
    return "\n".join(lines)


def _looks_like_existing_event_claim(answer: str) -> bool:
    normalized = answer.casefold()
    claim_patterns = [
        r"\balready\b.*\b(event|session|meeting|scheduled|calendar)\b",
        r"\bthere (is|are)\b.*\b(event|session|meeting|appointment)\b",
        r"\byou have\b.*\b(event|session|meeting|appointment|scheduled)\b",
        r"\bi found\b.*\b(event|session|meeting|appointment)\b",
        r"\bi see\b.*\b(event|session|meeting|appointment)\b",
    ]
    return any(re.search(pattern, normalized) for pattern in claim_patterns)


def _extract_deleted_event_ids(tool_name: str, tool_result: str) -> list[str]:
    if tool_name not in {"delete_event", "batch_delete_events"}:
        return []
    try:
        payload = json.loads(tool_result)
    except json.JSONDecodeError:
        return []
    deleted = payload.get("deleted_events")
    if not isinstance(deleted, list):
        return []
    return [event["id"] for event in deleted if isinstance(event, dict) and event.get("id")]


def _extract_tool_error(tool_result: str) -> str | None:
    try:
        payload = json.loads(tool_result)
    except json.JSONDecodeError:
        return None
    error = payload.get("error") if isinstance(payload, dict) else None
    return str(error) if error else None


def _friendly_tool_error(error: str, *, intent: str) -> str:
    normalized = error.casefold()
    if "title" in normalized:
        return "I need the event title. For example: `add project review on Wednesday at 16:30`."
    if "start_at" in normalized or "date" in normalized or "time" in normalized:
        return "I need a day and time. For example: `Wednesday at 16:30`."
    if "event_id is required" in normalized:
        return "I need to know which event to change. Try naming it or giving the day and time."
    if "no google calendar connection" in normalized:
        return "Connect Google Calendar first, then I can make calendar changes."
    if "duplicate" in normalized:
        return error
    if intent == "create":
        return "I couldn't create that event. Try: `add title on Wednesday at 16:30`."
    return f"I couldn't complete that: {error}"


def _strip_tool_json_from_reply(answer: str) -> str:
    visible_lines: list[str] = []
    for line in answer.splitlines():
        stripped = line.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict) and "tool" in payload:
                continue
        visible_lines.append(line)
    cleaned = "\n".join(visible_lines).strip()
    return cleaned or "Done."


def _is_use_previous_request_reply(prompt: str) -> bool:
    normalized = re.sub(r"[.!?\s]+$", "", prompt.strip().casefold())
    return normalized in {
        "that is it",
        "that's it",
        "thats it",
        "this is it",
        "use that",
        "use it",
        "same",
        "same title",
    }


def _latest_create_prompt_from_title_clarification(history: list[dict[str, Any]], now: datetime) -> str | None:
    if not history:
        return None
    last_assistant = next(
        (
            str(message.get("content") or "")
            for message in reversed(history)
            if message.get("role") == "assistant"
        ),
        "",
    ).casefold()
    if "title" not in last_assistant:
        return None

    for message in reversed(history):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if not isinstance(content, str):
            continue
        if (
            re.search(CREATE_VERB_PATTERN, content, re.IGNORECASE)
            and _parse_time_fragment(content)
            and _date_from_prompt(content, now)
            and _title_from_simple_create(content, now)
        ):
            return content
    return None


def _latest_title_from_schedule_clarification(history: list[dict[str, Any]]) -> str | None:
    for message in reversed(history):
        if message.get("role") != "assistant":
            continue
        content = message.get("content")
        if not isinstance(content, str):
            continue
        match = re.search(
            r"(?:when|which day|what time) should i schedule\s+(.+?)\??$",
            content.strip(),
            re.IGNORECASE,
        )
        if match:
            title = " ".join(match.group(1).strip(" .?\"'").split())
            return title[:120] or None
    return None


def _relative_day_from_token(token: str) -> tuple[str, int] | None:
    normalized = token.casefold().strip()
    if normalized == "today" or SequenceMatcher(None, normalized, "today").ratio() >= 0.84:
        return "today", 0
    if normalized == "tomorrow" or SequenceMatcher(None, normalized, "tomorrow").ratio() >= 0.78:
        return "tomorrow", 1
    return None


def _merge_schedule_clarification_reply(prompt: str, history: list[dict[str, Any]], now: datetime) -> str | None:
    title = _latest_title_from_schedule_clarification(history)
    if not title:
        return None
    extracted = _extract_simple_calendar_command(prompt, now)
    if not extracted.date_value and not extracted.start_time:
        return None
    merged = f"schedule {title} {prompt}"
    merged_extraction = _extract_simple_calendar_command(merged, now)
    if merged_extraction.intent == "create_single_event" and not merged_extraction.missing_fields:
        return merged
    return None


def _is_duration_context(prompt: str, start: int) -> bool:
    prefix = prompt[:start].casefold().rstrip()
    return bool(re.search(r"\b(for|during|duration)\s*$", prefix))


def _infer_unsuffixed_hour(hour: int) -> int:
    if 1 <= hour <= 7:
        return hour + 12
    return hour


def _coerce_time_parts(
    hour_text: str,
    minute_text: str | None,
    suffix: str | None,
    *,
    infer_meridiem: bool = True,
) -> tuple[int, int] | None:
    hour = int(hour_text)
    minute = int(minute_text or 0)
    suffix = (suffix or "").casefold()
    if suffix == "pm" and hour < 12:
        hour += 12
    elif suffix == "am" and hour == 12:
        hour = 0
    elif not suffix and infer_meridiem:
        hour = _infer_unsuffixed_hour(hour)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def _number_word_value(text: str) -> int | None:
    parts = [part for part in re.split(r"[\s-]+", text.casefold().strip()) if part and part != "and"]
    if not parts:
        return None
    total = 0
    for part in parts:
        value = NUMBER_WORDS.get(part)
        if value is None:
            return None
        total += value
    return total


def _coerce_spoken_time(hour_text: str, minute_text: str | None, suffix: str | None = None) -> tuple[int, int] | None:
    hour = _number_word_value(hour_text)
    if hour is None:
        return None

    minute = 0
    if minute_text:
        minute_text = minute_text.casefold().strip()
        if minute_text in {"half", "a half"}:
            minute = 30
        elif minute_text == "quarter":
            minute = 15
        else:
            parsed_minute = _number_word_value(minute_text)
            if parsed_minute is None:
                return None
            minute = parsed_minute

    return _coerce_time_parts(str(hour), str(minute), suffix)


def _find_time_fragment(prompt: str) -> tuple[int, int, tuple[int, int]] | None:
    spoken_patterns = [
        # half past two / quarter past four
        (rf"\b(half|quarter)\s+past\s+({HOUR_WORD_PATTERN})\s*(am|pm)?\b", "minute_first"),
        # two and a half / two thirty / two twenty pm
        (rf"\b(?:at\s+)?({HOUR_WORD_PATTERN})\s+(?:and\s+)?({MINUTE_WORD_PATTERN})\s*(am|pm)?\b", "hour_first"),
        # at two / two pm
        (rf"\b(?:at\s+)?({HOUR_WORD_PATTERN})\s*(am|pm)\b", "hour_only"),
        (rf"\bat\s+({HOUR_WORD_PATTERN})\b", "hour_only_no_suffix"),
    ]
    for pattern, mode in spoken_patterns:
        for match in re.finditer(pattern, prompt, re.IGNORECASE):
            if _is_duration_context(prompt, match.start()):
                continue
            if mode == "minute_first":
                minute_word, hour_word, suffix = match.groups()
                minute = "30" if minute_word.casefold() == "half" else "15"
                hour = _number_word_value(hour_word)
                parts = _coerce_time_parts(str(hour), minute, suffix) if hour is not None else None
            elif mode == "hour_only":
                hour_word, suffix = match.groups()
                parts = _coerce_spoken_time(hour_word, None, suffix)
            elif mode == "hour_only_no_suffix":
                hour_word = match.group(1)
                parts = _coerce_spoken_time(hour_word, None, None)
            else:
                hour_word, minute_word, suffix = match.groups()
                parts = _coerce_spoken_time(hour_word, minute_word, suffix)
            if parts is not None:
                return parts[0], parts[1], match.span()

    patterns = [
        # 4 30pm / at 4 30 pm
        (r"\b(?:at\s*)?(\d{1,2})\s+([0-5]\d)\s*(am|pm)\b", True),
        # 4pm / 4:30pm / at 4:30 pm
        (r"\b(?:at\s*)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", True),
        # 16:30 / at 16:30
        (r"\b(?:at\s*)?([01]?\d|2[0-3]):([0-5]\d)\b", False),
        # 16 30 / at 2 20
        (r"\b([01]?\d|2[0-3])\s+([0-5]\d)\b", True),
        # 1630
        (r"\b([01]\d|2[0-3])([0-5]\d)\b", False),
        # at 16
        (r"\bat\s+([01]?\d|2[0-3])\b", True),
    ]
    for pattern, infer_meridiem in patterns:
        match = re.search(pattern, prompt, re.IGNORECASE)
        if not match:
            continue
        if _is_duration_context(prompt, match.start()):
            continue
        groups = match.groups()
        if len(groups) == 1:
            parts = _coerce_time_parts(groups[0], None, None, infer_meridiem=infer_meridiem)
        elif len(groups) == 2:
            parts = _coerce_time_parts(groups[0], groups[1], None, infer_meridiem=infer_meridiem)
        else:
            parts = _coerce_time_parts(groups[0], groups[1], groups[2], infer_meridiem=infer_meridiem)
        if parts is not None:
            return parts[0], parts[1], match.span()
    return None


def _parse_time_fragment(prompt: str) -> tuple[int, int] | None:
    found = _find_time_fragment(prompt)
    if found is None:
        return None
    return found[0], found[1]


def _weekday_from_token(token: str) -> str | None:
    clean = re.sub(r"[^a-z]", "", token.casefold())
    if not clean:
        return None
    if clean in WEEKDAY_ALIASES:
        return WEEKDAY_ALIASES[clean]
    if len(clean) >= 3:
        for day in DAY_NAMES:
            if day.startswith(clean):
                return day
        best = max(DAY_NAMES, key=lambda day: SequenceMatcher(None, clean, day).ratio())
        if SequenceMatcher(None, clean, best).ratio() >= 0.72:
            return best
    return None


def _find_date_fragment(prompt: str, now: datetime) -> tuple[datetime, tuple[int, int]] | None:
    normalized = prompt.casefold()
    for pattern, offset in ((r"\btomorrow\b", 1), (r"\btoday\b", 0)):
        match = re.search(pattern, normalized)
        if match:
            return now + timedelta(days=offset), match.span()
    for match in re.finditer(r"\b[a-z]{4,10}\b", normalized):
        relative = _relative_day_from_token(match.group(0))
        if relative:
            return now + timedelta(days=relative[1]), match.span()

    iso_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", prompt)
    if iso_match:
        try:
            parsed = datetime.fromisoformat(iso_match.group(1))
            return parsed.replace(tzinfo=now.tzinfo), iso_match.span()
        except ValueError:
            return None

    month_match = re.search(
        r"\b("
        + "|".join(sorted(MONTH_NAMES, key=len, reverse=True))
        + r")\s+([0-3]?\d)(?:st|nd|rd|th)?(?:,\s*(20\d{2}))?\b",
        prompt,
        re.IGNORECASE,
    )
    if month_match:
        month = MONTH_NAMES[month_match.group(1).casefold()]
        day = int(month_match.group(2))
        year = int(month_match.group(3) or now.year)
        try:
            parsed = now.replace(year=year, month=month, day=day)
            if month_match.group(3) is None and parsed.date() < now.date():
                parsed = parsed.replace(year=year + 1)
            return parsed, month_match.span()
        except ValueError:
            return None

    for match in re.finditer(r"\b(next\s+)?([a-z]{3,10})\b", normalized):
        next_prefix, token = match.groups()
        day_name = _weekday_from_token(token)
        if not day_name:
            continue
        weekday = DAY_NAMES[day_name]
        days_ahead = (weekday - now.weekday()) % 7
        if next_prefix:
            days_ahead = days_ahead or 7
        return now + timedelta(days=days_ahead), match.span()
    return None


def _date_from_prompt(prompt: str, now: datetime) -> datetime | None:
    found = _find_date_fragment(prompt, now)
    if found is None:
        return None
    return found[0]


def _format_time_value(hour: int, minute: int) -> str:
    return f"{hour:02d}:{minute:02d}"


def _parse_time_token(token: str, *, infer_meridiem: bool = True) -> tuple[int, int] | None:
    normalized = " ".join(token.strip().casefold().split())
    if normalized == "noon":
        return 12, 0
    if normalized == "midnight":
        return 0, 0
    match = re.fullmatch(r"(\d{1,2})(?::([0-5]\d))?\s*(am|pm)?", normalized)
    if not match:
        return None
    return _coerce_time_parts(
        match.group(1),
        match.group(2),
        match.group(3),
        infer_meridiem=infer_meridiem,
    )


def _find_time_range(prompt: str) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]] | None:
    range_patterns = [
        rf"\bfrom\s+({TIME_TOKEN_PATTERN})\s*(?:to|until|-|–|—)\s*({TIME_TOKEN_PATTERN})\b",
        rf"\b({TIME_TOKEN_PATTERN})\s*(?:-|–|—)\s*({TIME_TOKEN_PATTERN})\b",
        rf"\b({TIME_TOKEN_PATTERN})\s*(?:to|until)\s*({TIME_TOKEN_PATTERN})\b",
    ]
    for pattern in range_patterns:
        match = re.search(pattern, prompt, re.IGNORECASE)
        if not match:
            continue
        left_raw, right_raw = match.group(1), match.group(2)
        left = _parse_time_token(left_raw)
        right = _parse_time_token(right_raw)
        if left is None or right is None:
            continue
        left_has_suffix = bool(re.search(r"\b(am|pm)\b", left_raw, re.IGNORECASE))
        right_has_suffix = bool(re.search(r"\b(am|pm)\b", right_raw, re.IGNORECASE))
        if left_has_suffix and not right_has_suffix:
            suffix = re.search(r"\b(am|pm)\b", left_raw, re.IGNORECASE)
            right = _parse_time_token(f"{right_raw} {suffix.group(1)}") if suffix else right
        if right is None:
            continue
        if right[0] < left[0] or (right[0] == left[0] and right[1] <= left[1]):
            if right[0] < 12:
                right = (right[0] + 12, right[1])
        return left, right, match.span()
    return None


def _find_date_expression(prompt: str, now: datetime) -> tuple[str, datetime, tuple[int, int]] | None:
    normalized = prompt.casefold()
    for pattern, label, offset in (
        (r"\btoday\b", "today", 0),
        (r"\btomorrow\b", "tomorrow", 1),
    ):
        match = re.search(pattern, normalized)
        if match:
            return label, now + timedelta(days=offset), match.span()
    for match in re.finditer(r"\b[a-z]{4,10}\b", normalized):
        relative = _relative_day_from_token(match.group(0))
        if relative:
            label, offset = relative
            return label, now + timedelta(days=offset), match.span()

    weekend = re.search(r"\bthis\s+weekend\b", normalized)
    if weekend:
        days_ahead = (5 - now.weekday()) % 7
        return "this weekend", now + timedelta(days=days_ahead), weekend.span()

    weekday_pattern = r"\b(?:(this|next)\s+|on\s+)?([a-z]{3,10})\b"
    for match in re.finditer(weekday_pattern, normalized):
        qualifier, token = match.groups()
        day_name = _weekday_from_token(token)
        if not day_name:
            continue
        weekday = DAY_NAMES[day_name]
        days_ahead = (weekday - now.weekday()) % 7
        if qualifier == "next":
            days_ahead = days_ahead or 7
        label = f"{qualifier} {day_name}" if qualifier else day_name
        return label, now + timedelta(days=days_ahead), match.span()

    iso_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", prompt)
    if iso_match:
        try:
            parsed = datetime.fromisoformat(iso_match.group(1)).replace(tzinfo=now.tzinfo)
            return iso_match.group(1), parsed, iso_match.span()
        except ValueError:
            return None
    month_match = re.search(
        r"\b("
        + "|".join(sorted(MONTH_NAMES, key=len, reverse=True))
        + r")\s+([0-3]?\d)(?:st|nd|rd|th)?(?:,\s*(20\d{2}))?\b",
        prompt,
        re.IGNORECASE,
    )
    if month_match:
        month = MONTH_NAMES[month_match.group(1).casefold()]
        day = int(month_match.group(2))
        year = int(month_match.group(3) or now.year)
        try:
            parsed = now.replace(year=year, month=month, day=day)
            if month_match.group(3) is None and parsed.date() < now.date():
                parsed = parsed.replace(year=year + 1)
            label = f"{month_match.group(1).casefold()} {day}"
            return label, parsed, month_match.span()
        except ValueError:
            return None
    return None


def _intent_from_calendar_prompt(prompt: str) -> str:
    normalized = prompt.casefold()
    if re.search(r"\b(move|reschedule)\b", normalized):
        return "move_event"
    if re.search(r"\b(delete|remove|clear)\b", normalized):
        return "delete_event"
    if re.search(r"\b(update|edit|rename|change)\b", normalized):
        return "update_event"
    if re.search(CREATE_VERB_PATTERN, normalized):
        return "create_single_event"
    if re.search(r"\b(?:i\s+)?(?:need|want|would\s+like)\s+to\s+(?:go\s+to|visit|attend)\b", normalized):
        return "create_single_event"
    if _looks_like_bare_event_create(prompt):
        return "create_single_event"
    if any(term in normalized for term in ("plan my", "prepare for", "study plan", "finals", "exam")):
        return "generate_plan"
    return "simple_chat"


def _looks_like_bare_event_create(prompt: str) -> bool:
    normalized = prompt.strip().casefold()
    if not normalized or "?" in normalized:
        return False
    if re.search(r"\b(what|when|where|who|why|how|show|list|find|do i|am i)\b", normalized):
        return False
    if re.search(r"\b(move|reschedule|delete|remove|clear|update|edit|rename|change)\b", normalized):
        return False

    time_fragment = _find_time_fragment(prompt)
    if not time_fragment:
        return False

    date_spans: list[tuple[int, int]] = []
    for match in re.finditer(r"\b(today|tomorrow|20\d{2}-\d{2}-\d{2})\b", prompt, re.IGNORECASE):
        date_spans.append(match.span())
    month_pattern = (
        r"\b("
        + "|".join(sorted(MONTH_NAMES, key=len, reverse=True))
        + r")\s+([0-3]?\d)(?:st|nd|rd|th)?(?:,\s*(20\d{2}))?\b"
    )
    for match in re.finditer(month_pattern, prompt, re.IGNORECASE):
        date_spans.append(match.span())
    for match in re.finditer(r"\b(?:(?:this|next|on)\s+)?([a-z]{3,10})\b", prompt, re.IGNORECASE):
        if _weekday_from_token(match.group(1)):
            date_spans.append(match.span())

    if not date_spans:
        return False

    title = _clean_extracted_title(
        prompt,
        intent="create_single_event",
        spans_to_remove=[time_fragment[2], *date_spans],
    )
    return bool(title and len(title.split()) <= 18)


def _remove_spans(text: str, spans: list[tuple[int, int]]) -> str:
    if not spans:
        return text
    cleaned: list[str] = []
    cursor = 0
    for start, end in sorted(spans):
        cleaned.append(text[cursor:start])
        cleaned.append(" ")
        cursor = max(cursor, end)
    cleaned.append(text[cursor:])
    return "".join(cleaned)


def _clean_extracted_title(prompt: str, *, intent: str, spans_to_remove: list[tuple[int, int]]) -> str | None:
    title = _remove_spans(prompt, spans_to_remove)
    title = re.sub(CREATE_VERB_PREFIX_PATTERN, "", title, flags=re.IGNORECASE)
    title = re.sub(r"^\s*(?:i\s+)?(?:need|want|would\s+like)\s+to\s+(?:go\s+to|visit|attend)\s+(?:the\s+)?", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^\s*back\s+", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^\s*(move|reschedule|delete|remove|clear|update|edit|rename|change)\s+", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\b(?:from|to|until|at|on|for|this|next)\s*$", " ", title, flags=re.IGNORECASE)
    title = re.sub(r"\bfor\s+\d+(?:\.\d+)?\s*(hours?|hrs?|h|minutes?|mins?|m)\b", " ", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+", " ", title).strip(" .,-")
    if intent == "move_event":
        title = re.sub(r"\b(?:from|to)\b.*$", "", title, flags=re.IGNORECASE).strip(" .,-")
    return title[:120] or None


def _extract_simple_calendar_command(prompt: str, now: datetime) -> SimpleCalendarExtraction:
    intent = _intent_from_calendar_prompt(prompt)
    extraction = SimpleCalendarExtraction(intent=intent, confidence=0.65)
    spans_to_remove: list[tuple[int, int]] = []

    date_expr = _find_date_expression(prompt, now)
    if date_expr:
        extraction.date, extraction.date_value, date_span = date_expr
        spans_to_remove.append(date_span)

    relative_match = re.search(r"\bafter\s+(?:my\s+)?([a-z\s]+?)(?=\s+(?:today|tomorrow|this|next|on\b|$))", prompt, re.IGNORECASE)
    if relative_match:
        relative = " ".join(relative_match.group(1).split())
        extraction.relative_time = f"after {relative.replace('my ', '')}"
        extraction.requires_calendar_read = True
        spans_to_remove.append(relative_match.span())
    elif re.search(r"\bafter\s+lunch\b", prompt, re.IGNORECASE):
        relative_match = re.search(r"\bafter\s+lunch\b", prompt, re.IGNORECASE)
        extraction.relative_time = "after_lunch"
        spans_to_remove.append(relative_match.span())

    approximate_match = re.search(r"\b(morning|afternoon|evening|tonight)\b", prompt, re.IGNORECASE)
    if approximate_match and extraction.start_time is None:
        extraction.approximate_time = approximate_match.group(1).casefold()
        spans_to_remove.append(approximate_match.span())

    if intent == "move_event":
        move_match = re.search(rf"\bfrom\s+({TIME_TOKEN_PATTERN})\s+to\s+({TIME_TOKEN_PATTERN})\b", prompt, re.IGNORECASE)
        if move_match:
            old_time = _parse_time_token(move_match.group(1))
            new_time = _parse_time_token(move_match.group(2))
            if old_time:
                extraction.old_time = _format_time_value(*old_time)
            if new_time:
                extraction.new_time = _format_time_value(*new_time)
                extraction.start_time = extraction.new_time
            spans_to_remove.append(move_match.span())
    else:
        time_range = _find_time_range(prompt)
        if time_range:
            start, end, time_span = time_range
            extraction.start_time = _format_time_value(*start)
            extraction.end_time = _format_time_value(*end)
            start_minutes = start[0] * 60 + start[1]
            end_minutes = end[0] * 60 + end[1]
            extraction.duration_minutes = end_minutes - start_minutes
            spans_to_remove.append(time_span)

    if extraction.start_time is None and intent != "delete_event":
        time_fragment = _find_time_fragment(prompt)
        if time_fragment:
            extraction.start_time = _format_time_value(time_fragment[0], time_fragment[1])
            extraction.duration_minutes = _duration_minutes_from_prompt(prompt) or 60
            spans_to_remove.append(time_fragment[2])

    duration = _duration_minutes_from_prompt(prompt)
    if duration is not None:
        extraction.duration_minutes = duration

    extraction.title = _clean_extracted_title(prompt, intent=intent, spans_to_remove=spans_to_remove)

    missing: list[str] = []
    if intent in {"create_single_event", "move_event", "delete_event", "update_event"}:
        if not extraction.title:
            missing.append("title")
        if not extraction.date:
            missing.append("date")
    if intent == "create_single_event":
        if not extraction.start_time and not extraction.relative_time and not extraction.approximate_time:
            missing.append("start_time")
        # replanme defaults single start-time commands to one hour, so end_time
        # is not missing when start_time exists and duration was defaulted.
        if extraction.start_time and extraction.end_time is None and extraction.duration_minutes is None:
            extraction.duration_minutes = 60
    if intent == "move_event" and not extraction.new_time:
        missing.append("start_time")

    extraction.missing_fields = missing
    if intent == "create_single_event" and not missing:
        extraction.confidence = 0.95 if extraction.end_time else 0.88
    elif intent in {"move_event", "delete_event"} and not missing:
        extraction.confidence = 0.9
    return extraction


def _simple_extraction_from_mapping(data: dict[str, Any], fallback: SimpleCalendarExtraction) -> SimpleCalendarExtraction | None:
    intent = data.get("intent")
    if intent not in {"create_single_event", "move_event", "delete_event", "update_event", "unknown"}:
        return None

    date_value = None
    raw_date_value = data.get("date_value")
    if isinstance(raw_date_value, str) and raw_date_value:
        try:
            date_value = datetime.fromisoformat(raw_date_value)
        except ValueError:
            date_value = None
    if date_value is None and data.get("date") == fallback.date:
        date_value = fallback.date_value

    extraction = SimpleCalendarExtraction(
        intent=str(intent),
        title=str(data["title"]).strip()[:120] if data.get("title") else None,
        date=str(data["date"]).strip()[:80] if data.get("date") else None,
        date_value=date_value,
        start_time=str(data["start_time"]).strip() if data.get("start_time") else None,
        end_time=str(data["end_time"]).strip() if data.get("end_time") else None,
        duration_minutes=int(data["duration_minutes"]) if isinstance(data.get("duration_minutes"), int) else None,
        missing_fields=[str(item) for item in data.get("missing_fields", []) if isinstance(item, str)],
        confidence=float(data.get("confidence", 0.8) or 0.8),
        relative_time=str(data["relative_time"]).strip() if data.get("relative_time") else None,
        approximate_time=str(data["approximate_time"]).strip() if data.get("approximate_time") else None,
        old_time=str(data["old_time"]).strip() if data.get("old_time") else None,
        new_time=str(data["new_time"]).strip() if data.get("new_time") else None,
        requires_calendar_read=bool(data.get("requires_calendar_read", False)),
    )

    missing: list[str] = []
    if extraction.intent in {"create_single_event", "move_event", "delete_event", "update_event"}:
        if not extraction.title:
            missing.append("title")
        if not extraction.date or not extraction.date_value:
            missing.append("date")
    if extraction.intent == "create_single_event":
        if not extraction.start_time and not extraction.relative_time and not extraction.approximate_time:
            missing.append("start_time")
        if extraction.start_time and extraction.end_time is None and extraction.duration_minutes is None:
            extraction.duration_minutes = 60
    if extraction.intent == "move_event" and not extraction.new_time:
        missing.append("start_time")
    extraction.missing_fields = missing
    return extraction


async def _extract_simple_calendar_command_with_gemma(prompt: str, now: datetime) -> SimpleCalendarExtraction:
    fallback = _extract_simple_calendar_command(prompt, now)
    gemma_json = await GemmaClient().generate_json(
        schema_name="SimpleCalendarExtraction",
        system_prompt=(
            "Extract a simple calendar command. Return JSON matching SimpleCalendarExtraction with keys "
            "intent, title, date, date_value, start_time, end_time, duration_minutes, missing_fields, confidence, "
            "relative_time, approximate_time, old_time, new_time, requires_calendar_read. "
            "date_value must be an ISO datetime in the user's timezone when a date is known. "
            "Use null for unknown optional fields."
        ),
        payload={
            "message": prompt,
            "now": now.isoformat(),
            "timezone": str(now.tzinfo) if now.tzinfo else "UTC",
            "deterministic_baseline": {
                **fallback.__dict__,
                "date_value": fallback.date_value.isoformat() if fallback.date_value else None,
            },
        },
        max_output_tokens=settings.nano_max_output_tokens,
    )
    if isinstance(gemma_json, dict):
        parsed = _simple_extraction_from_mapping(gemma_json, fallback)
        if parsed is not None:
            return parsed
    return fallback


def _duration_minutes_from_prompt(prompt: str) -> int | None:
    match = re.search(r"\bfor\s+(\d+(?:\.\d+)?)\s*(hours?|hrs?|h)\b", prompt, re.IGNORECASE)
    if match:
        return int(float(match.group(1)) * 60)
    match = re.search(r"\bfor\s+(\d+)\s*(minutes?|mins?|m)\b", prompt, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _log_simple_extraction(
    *,
    extraction: SimpleCalendarExtraction,
    raw_user_message: str,
    clarification_question: str | None = None,
    reason_for_clarification: str | None = None,
) -> None:
    logger.info(
        "assistant.simple_event_extraction",
        extra={
            "raw_user_message": raw_user_message,
            "detected_intent": extraction.intent,
            "extracted_title": extraction.title,
            "extracted_date": extraction.date,
            "extracted_start_time": extraction.start_time,
            "extracted_end_time": extraction.end_time,
            "missing_fields": extraction.missing_fields,
            "clarification_question": clarification_question,
            "reason_for_clarification": reason_for_clarification,
        },
    )


def _duration_from_prompt(prompt: str) -> timedelta:
    minutes = _duration_minutes_from_prompt(prompt)
    if minutes is not None:
        return timedelta(minutes=minutes)
    return timedelta(hours=1)


def _title_from_simple_create(prompt: str, now: datetime | None = None) -> str | None:
    if now is not None:
        extracted = _extract_simple_calendar_command(prompt, now)
        if extracted.intent == "create_single_event" and extracted.title:
            return extracted.title

    title = prompt.strip()
    time_fragment = _find_time_fragment(title)
    if time_fragment:
        start, end = time_fragment[2]
        title = f"{title[:start]} {title[end:]}"
    if now is not None:
        date_fragment = _find_date_fragment(title, now)
        if date_fragment:
            start, end = date_fragment[1]
            prefix = title[:start]
            prefix = re.sub(r"\b(on|for)\s*$", " ", prefix, flags=re.IGNORECASE)
            title = f"{prefix} {title[end:]}"
    else:
        title = re.sub(r"\b(on\s+)?(next\s+)?([a-z]{3,10})\b", lambda m: " " if _weekday_from_token(m.group(3)) else m.group(0), title, flags=re.IGNORECASE)
        title = re.sub(r"\b(on\s+)?(today|tomorrow|20\d{2}-\d{2}-\d{2})\b", " ", title, flags=re.IGNORECASE)
    title = re.sub(CREATE_VERB_PREFIX_PATTERN, "", title, flags=re.IGNORECASE)
    title = re.sub(r"\bfor\s+\d+(?:\.\d+)?\s*(hours?|hrs?|h|minutes?|mins?|m)\b", " ", title, flags=re.IGNORECASE)
    title = " ".join(title.split())
    title = re.sub(r"\b(on|for|at)$", "", title, flags=re.IGNORECASE).strip(" .,-")
    return title[:120] or None


def _format_event_time(start: datetime, end: datetime) -> str:
    if start.date() == end.date():
        return f"{start.strftime('%a %Y-%m-%d %H:%M')}-{end.strftime('%H:%M')}"
    return f"{start.strftime('%Y-%m-%d %H:%M')} to {end.strftime('%Y-%m-%d %H:%M')}"


def _format_event_list(events: list[Any]) -> str:
    if not events:
        return "I don't see any events in that range."
    lines = [f"{event.title} ({_format_event_time(event.start_at, event.end_at)})" for event in events[:8]]
    suffix = f" Plus {len(events) - 8} more." if len(events) > 8 else ""
    return "You have: " + "; ".join(lines) + "." + suffix


def _is_confirmation_yes(prompt: str) -> bool:
    normalized = re.sub(r"[.!?\s]+$", "", prompt.strip().casefold())
    return normalized in AFFIRMATIVE_CREATE_REPLIES or normalized in {
        "yes",
        "y",
        "yeah",
        "yep",
        "ok",
        "okay",
        "sure",
        "confirm",
        "confirmed",
        "apply",
        "apply changes",
        "do it",
        "go ahead",
        "please do",
    }


def _is_confirmation_no(prompt: str) -> bool:
    normalized = re.sub(r"[.!?\s]+$", "", prompt.strip().casefold())
    return normalized in {"no", "nope", "cancel", "stop", "don't", "do not", "never mind", "nevermind", "another time", "not that time"}


def _looks_like_time_suggestion_request(prompt: str) -> bool:
    normalized = prompt.casefold()
    return any(
        phrase in normalized
        for phrase in (
            "suggest",
            "you choose",
            "you pick",
            "i dont know",
            "i don't know",
            "not sure",
            "maybe afternoon",
            "myabe affternoon",
            "afternoon",
            "morning",
            "evening",
        )
    )


def _suggested_hour_from_prompt(prompt: str) -> int:
    normalized = prompt.casefold()
    if "morning" in normalized:
        return 9
    if "evening" in normalized:
        return 18
    return 15


def _human_date_label(value: datetime, now: datetime) -> str:
    if value.date() == (now + timedelta(days=1)).date():
        return "tomorrow"
    if value.date() == now.date():
        return "today"
    return value.strftime("%A %Y-%m-%d")


def _pending_create_missing(payload: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not str(payload.get("title") or "").strip():
        missing.append("title")
    if not str(payload.get("start_at") or "").strip():
        missing.append("start_at")
    if not str(payload.get("end_at") or "").strip():
        missing.append("end_at")
    return missing


def _pending_payload_from_extraction(extracted: SimpleCalendarExtraction, timezone: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": extracted.title,
        "timezone": timezone,
        "duration_minutes": extracted.duration_minutes or 60,
        "date": extracted.date,
        "date_value": extracted.date_value.isoformat() if extracted.date_value else None,
    }
    if extracted.date_value and extracted.start_time:
        start_hour, start_minute = [int(part) for part in extracted.start_time.split(":")]
        start_at = extracted.date_value.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
        if extracted.end_time:
            end_hour, end_minute = [int(part) for part in extracted.end_time.split(":")]
            end_at = extracted.date_value.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
            if end_at <= start_at:
                end_at += timedelta(hours=12)
        else:
            end_at = start_at + timedelta(minutes=extracted.duration_minutes or 60)
        payload["start_at"] = start_at.isoformat()
        payload["end_at"] = end_at.isoformat()
    return payload


def _pending_action_for_create(payload: dict[str, Any], *, requires_confirmation: bool, status: str = "awaiting_confirmation") -> PendingCalendarAction:
    return PendingCalendarAction(
        id=uuid.uuid4().hex,
        action="create_event",
        status=status,  # type: ignore[arg-type]
        requires_confirmation=requires_confirmation,
        filters=PendingActionFilters(
            title=payload.get("title"),
            date=payload.get("date"),
            time_range=f"{payload.get('start_at')}..{payload.get('end_at')}" if payload.get("start_at") and payload.get("end_at") else None,
        ),
        payload=payload,
        created_at=datetime.now(UTC).isoformat(),
    )


def _format_date_for_user(value: datetime) -> str:
    return f"{value.strftime('%B')} {value.day}, {value.year}"


def _bulk_delete_range_from_prompt(prompt: str, now: datetime) -> tuple[datetime, datetime, str] | None:
    normalized = prompt.casefold()
    if "this week" in normalized:
        start = datetime.combine(
            (now - timedelta(days=now.weekday())).date(),
            datetime.min.time(),
            tzinfo=now.tzinfo,
        )
        end = start + timedelta(days=7)
        label = f"{_format_date_for_user(start)} through {_format_date_for_user(end - timedelta(days=1))}"
        return start, end, label
    if "today" in normalized:
        start = datetime.combine(now.date(), datetime.min.time(), tzinfo=now.tzinfo)
        end = start + timedelta(days=1)
        label = _format_date_for_user(start)
        return start, end, label
    if "tomorrow" in normalized:
        start = datetime.combine((now + timedelta(days=1)).date(), datetime.min.time(), tzinfo=now.tzinfo)
        end = start + timedelta(days=1)
        label = _format_date_for_user(start)
        return start, end, label
    return None


def _looks_like_bulk_delete_request(prompt: str, now: datetime) -> bool:
    normalized = prompt.casefold()
    if _bulk_delete_range_from_prompt(prompt, now) is None:
        return False
    if not re.search(r"\b(delete|remove|clear)\b", normalized):
        return False
    has_bulk_term = bool(re.search(r"\b(all|every|entire|whole)\b", normalized)) or "clear" in normalized
    has_calendar_noun = bool(
        re.search(
            r"\b(appointments?|calendar|classes|events?|meetings?|schedule|scheduled|tasks?)\b",
            normalized,
        )
    )
    return has_bulk_term and has_calendar_noun


def _preview_event_titles(events: list[CalendarEventSnapshot], *, limit: int = 6) -> str:
    titles = [event.title for event in events[:limit]]
    if len(events) > limit:
        titles.append(f"{len(events) - limit} more")
    return ", ".join(titles)


class PlannerAgent:
    def __init__(
        self,
        state_store: ConversationStateStore,
        memory_service: PlanningMemoryService,
        tool_registry: AssistantToolRegistry,
    ):
        self.state_store = state_store
        self.memory_service = memory_service
        self.registry = tool_registry
        self.client = AsyncOpenAI(api_key=settings.openai_api_key or "unused")

    def _base_response(
        self,
        *,
        session_id: str,
        reply: str,
        memory: Any,
        intent: str,
        route_reason: str,
        execution: PlanExecutionResult | None = None,
    ) -> AssistantMessageResponse:
        return AssistantMessageResponse(
            session_id=session_id,
            status=execution.status if execution else "completed",
            reply=reply,
            routing=RoutingDecision(
                intent="CREATE_EVENT" if intent == "create" else "SEARCH_EVENTS" if intent == "query" else "CHAT",
                route="simple",
                selected_model="backend",
                confidence=0.95,
                complexity_score=0.05,
                reason=route_reason,
                low_cost_path=True,
            ),
            plan=ExecutionPlan(
                goal=reply,
                summary=route_reason,
                selected_model="backend",
                route="simple",
                reasoning="Handled by deterministic low-token path.",
                response_message=reply,
            ),
            safety=SafetyAssessment(
                requires_confirmation=False,
                risk_level="low",
            ),
            execution=execution or PlanExecutionResult(status="completed"),
            memory=memory,
        )

    def _calendar_response(
        self,
        *,
        session_id: str,
        reply: str,
        memory: Any,
        intent: str,
        reason: str,
        execution: PlanExecutionResult,
        requires_confirmation: bool = False,
        risk_level: str = "low",
        display_actions: list[DisplayAction] | None = None,
        referenced_events: list[CalendarEventSnapshot] | None = None,
        awaiting_confirmation: bool = False,
        confirmation_token: str | None = None,
    ) -> AssistantMessageResponse:
        return AssistantMessageResponse(
            session_id=session_id,
            status=execution.status,
            reply=reply,
            routing=RoutingDecision(
                intent=intent,
                route="simple",
                selected_model="backend",
                confidence=0.98,
                complexity_score=0.15,
                reason=reason,
                low_cost_path=True,
            ),
            plan=ExecutionPlan(
                goal=reply,
                summary=reason,
                selected_model="backend",
                route="simple",
                reasoning="Handled by deterministic calendar safety path.",
                response_message=reply,
                requires_confirmation=requires_confirmation,
                confirmation_reason=reply if requires_confirmation else None,
            ),
            safety=SafetyAssessment(
                requires_confirmation=requires_confirmation,
                risk_level=risk_level,
                impacted_events=len(referenced_events or []),
            ),
            execution=execution,
            display_actions=display_actions or [],
            referenced_events=referenced_events or [],
            awaiting_confirmation=awaiting_confirmation,
            confirmation_token=confirmation_token,
            memory=memory,
        )

    async def _try_pending_confirmation(
        self,
        *,
        prompt: str,
        confirm: bool,
        confirmation_token: str | None,
        session_id: str,
        user: User,
        db: AsyncSession,
        memory_response: Any,
        memory_handler: AgentMemoryHandler,
    ) -> AssistantMessageResponse | None:
        state = await self.state_store.load(user_id=str(user.id), session_id=session_id)
        pending = state.confirmation_target or state.pending_action
        if not (state.awaiting_confirmation and pending):
            return None
        if confirmation_token and confirmation_token != pending.id:
            return None

        if not confirm and not (_is_confirmation_yes(prompt) or _is_confirmation_no(prompt)):
            return None

        await memory_handler.add_user_message(prompt or "confirmed")

        if _is_confirmation_no(prompt):
            pending.status = "cancelled"
            state.pending_action = None
            state.confirmation_target = None
            state.awaiting_confirmation = False
            await self.state_store.save(user_id=str(user.id), session_id=session_id, state=state)
            reply = "Okay, I won't schedule that." if pending.action == "create_event" else "Okay, I won't delete anything."
            await memory_handler.add_assistant_message(reply)
            return self._calendar_response(
                session_id=session_id,
                reply=reply,
                memory=memory_response.memory,
                intent="CONFIRMATION_NO",
                reason="Cancelled pending calendar action.",
                execution=PlanExecutionResult(status="completed"),
            )

        if pending.action == "create_event":
            return await self._execute_pending_create(
                state=state,
                pending=pending,
                session_id=session_id,
                user=user,
                db=db,
                memory_response=memory_response,
                memory_handler=memory_handler,
            )

        if pending.action != "delete_event":
            return None

        reservation = await reserve_usage(db, user, FeatureName.BASIC_AI_ACTION) if db is not None else None
        deleted_events: list[CalendarEventSnapshot] = []
        errors: list[str] = []
        try:
            for event_id in pending.target_event_ids:
                try:
                    result = await self.registry.delete_event(
                        DeleteEventInput(event_id=event_id),
                        user=user,
                        db=db,
                        memory=memory_response.memory,
                    )
                    deleted_events.extend(result.deleted_events)
                except Exception as exc:  # keep deleting the rest of the confirmed batch
                    logger.warning("assistant.confirmed_delete_failed", exc_info=True)
                    errors.append(event_id)
        except Exception:
            await refund_usage(db, reservation)
            raise

        pending.status = "executed" if deleted_events else "cancelled"
        state.pending_action = None
        state.confirmation_target = None
        state.awaiting_confirmation = False
        state.recently_referenced_events = []
        await self.state_store.save(user_id=str(user.id), session_id=session_id, state=state)
        for event in deleted_events:
            await memory_handler.clear_last_event(event.id)

        if not deleted_events:
            await refund_usage(db, reservation)
            reply = "I could not find those events anymore, so nothing was deleted."
            status = "failed"
        else:
            await commit_usage(db, reservation)
            names = _preview_event_titles(deleted_events)
            reply = f"Deleted {len(deleted_events)} event{'s' if len(deleted_events) != 1 else ''}: {names}."
            if errors:
                reply += f" I could not delete {len(errors)} event{'s' if len(errors) != 1 else ''} that may have changed."
            status = "completed"

        await memory_handler.add_assistant_message(reply)
        return self._calendar_response(
            session_id=session_id,
            reply=reply,
            memory=memory_response.memory,
            intent="CONFIRMATION_YES",
            reason="Executed confirmed bulk delete.",
            execution=PlanExecutionResult(
                status=status,
                executed_steps=len(deleted_events),
                rollback_available=bool(deleted_events),
                deleted_events=deleted_events,
                error=None if deleted_events else reply,
            ),
            referenced_events=deleted_events,
        )

    async def _execute_pending_create(
        self,
        *,
        state: Any,
        pending: PendingCalendarAction,
        session_id: str,
        user: User,
        db: AsyncSession,
        memory_response: Any,
        memory_handler: AgentMemoryHandler,
    ) -> AssistantMessageResponse:
        payload = dict(pending.payload or {})
        missing = _pending_create_missing(payload)
        if missing:
            pending.status = "draft"
            pending.requires_confirmation = False
            state.pending_action = pending
            state.confirmation_target = None
            state.awaiting_confirmation = False
            await self.state_store.save(user_id=str(user.id), session_id=session_id, state=state)
            if "title" in missing:
                reply = "What should I call the event?"
            elif "start_at" in missing:
                reply = f"What time should I schedule {payload.get('title') or 'it'}?"
            else:
                reply = f"How long should {payload.get('title') or 'it'} be?"
            await memory_handler.add_assistant_message(reply)
            return self._calendar_response(
                session_id=session_id,
                reply=reply,
                memory=memory_response.memory,
                intent="CREATE_EVENT",
                reason="Pending create action is missing required fields.",
                execution=PlanExecutionResult(status="completed"),
            )

        title = str(payload["title"]).strip()
        start_at = datetime.fromisoformat(str(payload["start_at"]))
        end_at = datetime.fromisoformat(str(payload["end_at"]))
        timezone_value = str(payload.get("timezone") or getattr(user, "timezone", "UTC") or "UTC")
        reservation = await reserve_usage(db, user, FeatureName.BASIC_AI_ACTION) if db is not None else None
        try:
            result = await self.registry.create_event(
                CreateEventInput(
                    title=title,
                    start_at=start_at,
                    end_at=end_at,
                    timezone=timezone_value,
                ),
                user=user,
                db=db,
                memory=memory_response.memory,
            )
        except PaywallError:
            await refund_usage(db, reservation)
            raise
        except ValueError as exc:
            await refund_usage(db, reservation)
            reply = str(exc)
            await memory_handler.add_assistant_message(reply)
            return self._calendar_response(
                session_id=session_id,
                reply=reply,
                memory=memory_response.memory,
                intent="CREATE_EVENT",
                reason="Pending create action hit a calendar validation guard.",
                execution=PlanExecutionResult(status="completed", error=reply),
            )
        except Exception:
            await refund_usage(db, reservation)
            raise

        await commit_usage(db, reservation)
        pending.status = "executed"
        state.pending_action = None
        state.confirmation_target = None
        state.awaiting_confirmation = False
        await self.state_store.save(user_id=str(user.id), session_id=session_id, state=state)

        event = result.created_events[0] if result.created_events else None
        if event:
            await memory_handler.update_last_event(event.id, event.title)
        reply = f"Scheduled: {title} {start_at.strftime('%a %Y-%m-%d')} {start_at.strftime('%H:%M')}-{end_at.strftime('%H:%M')}."
        await memory_handler.add_assistant_message(reply)
        return self._base_response(
            session_id=session_id,
            reply=reply,
            memory=memory_response.memory,
            intent="create",
            route_reason="Executed confirmed pending create action.",
            execution=PlanExecutionResult(
                status="completed",
                executed_steps=1,
                preview=result.preview,
                rollback_available=bool(result.rollback),
                created_events=result.created_events,
            ),
        )

    async def _save_pending_create_draft(
        self,
        *,
        session_id: str,
        user: User,
        extracted: SimpleCalendarExtraction,
        timezone_str: str,
    ) -> None:
        payload = _pending_payload_from_extraction(extracted, timezone_str)
        action = _pending_action_for_create(payload, requires_confirmation=False, status="draft")
        state = await self.state_store.load(user_id=str(user.id), session_id=session_id)
        state.current_intent = "CREATE_EVENT"
        state.pending_action = action
        state.confirmation_target = None
        state.awaiting_confirmation = False
        await self.state_store.save(user_id=str(user.id), session_id=session_id, state=state)

    async def _latest_pending_create_context(
        self,
        *,
        session_id: str,
        user: User,
        history: list[dict[str, Any]],
        now_local: datetime,
        timezone_str: str,
    ) -> tuple[Any, PendingCalendarAction] | None:
        state = await self.state_store.load(user_id=str(user.id), session_id=session_id)
        pending = state.pending_action if state.pending_action and state.pending_action.action == "create_event" else None
        if pending:
            return state, pending
        for message in reversed(history):
            if message.get("role") != "user":
                continue
            content = message.get("content")
            if not isinstance(content, str):
                continue
            extracted = await _extract_simple_calendar_command_with_gemma(content, now_local)
            if extracted.intent == "create_single_event" and (extracted.title or extracted.date_value):
                payload = _pending_payload_from_extraction(extracted, timezone_str)
                pending = _pending_action_for_create(payload, requires_confirmation=False, status="draft")
                state.pending_action = pending
                state.current_intent = "CREATE_EVENT"
                await self.state_store.save(user_id=str(user.id), session_id=session_id, state=state)
                return state, pending
        return None

    async def _try_pending_create_time_suggestion(
        self,
        *,
        prompt: str,
        history: list[dict[str, Any]],
        session_id: str,
        timezone_str: str,
        now_local: datetime,
        user: User,
        memory_response: Any,
        memory_handler: AgentMemoryHandler,
    ) -> AssistantMessageResponse | None:
        if not _looks_like_time_suggestion_request(prompt):
            return None
        context = await self._latest_pending_create_context(
            session_id=session_id,
            user=user,
            history=history,
            now_local=now_local,
            timezone_str=timezone_str,
        )
        if not context:
            return None
        state, pending = context
        payload = dict(pending.payload or {})
        title = str(payload.get("title") or "").strip()
        date_raw = payload.get("date_value")
        if not title or not date_raw:
            return None
        date_value = datetime.fromisoformat(str(date_raw))
        start_at = date_value.replace(hour=_suggested_hour_from_prompt(prompt), minute=0, second=0, microsecond=0)
        end_at = start_at + timedelta(minutes=int(payload.get("duration_minutes") or 60))
        payload.update(
            {
                "title": title,
                "start_at": start_at.isoformat(),
                "end_at": end_at.isoformat(),
                "timezone": timezone_str,
                "date": payload.get("date") or _human_date_label(start_at, now_local),
                "date_value": date_value.isoformat(),
                "duration_minutes": int(payload.get("duration_minutes") or 60),
            }
        )
        action = _pending_action_for_create(payload, requires_confirmation=True, status="awaiting_confirmation")
        state.pending_action = action
        state.confirmation_target = action
        state.awaiting_confirmation = True
        state.current_intent = "CREATE_EVENT"
        await self.state_store.save(user_id=str(user.id), session_id=session_id, state=state)

        await memory_handler.add_user_message(prompt)
        date_label = _human_date_label(start_at, now_local)
        reply = f"Let's schedule {title} {date_label} at {start_at.strftime('%H:%M')}. Does that sound good?"
        await memory_handler.add_assistant_message(reply)
        preview = [
            PlanPreviewChange(
                action="create_event",
                title=title,
                details="Create event after confirmation.",
                proposed_start_at=start_at,
                proposed_end_at=end_at,
            )
        ]
        return self._calendar_response(
            session_id=session_id,
            reply=reply,
            memory=memory_response.memory,
            intent="CREATE_EVENT",
            reason="Suggested a concrete time for a pending create request.",
            execution=PlanExecutionResult(status="awaiting_confirmation", preview=preview),
            requires_confirmation=True,
            display_actions=[DisplayAction(kind="ask_user", summary=f"Schedule {title} at {start_at.strftime('%H:%M')}.")],
            awaiting_confirmation=True,
            confirmation_token=action.id,
        )

    async def _try_pending_create_field_reply(
        self,
        *,
        prompt: str,
        session_id: str,
        timezone_str: str,
        now_local: datetime,
        user: User,
        db: AsyncSession,
        memory_response: Any,
        memory_handler: AgentMemoryHandler,
    ) -> AssistantMessageResponse | None:
        state = await self.state_store.load(user_id=str(user.id), session_id=session_id)
        pending = state.pending_action if state.pending_action and state.pending_action.action == "create_event" else None
        if not pending or state.awaiting_confirmation:
            return None
        payload = dict(pending.payload or {})
        missing = _pending_create_missing(payload)
        if not missing:
            return None
        if "title" in missing and prompt.strip() and not _find_time_fragment(prompt):
            payload["title"] = " ".join(prompt.strip(" .").split())[:120]
        if "start_at" in missing:
            title = payload.get("title") or "event"
            merged = f"schedule {title} {prompt}"
            if payload.get("date"):
                merged = f"{merged} {payload['date']}"
            extracted = await _extract_simple_calendar_command_with_gemma(merged, now_local)
            if extracted.date_value and extracted.start_time:
                payload.update(_pending_payload_from_extraction(extracted, timezone_str))
                if payload.get("title") == "event" and title != "event":
                    payload["title"] = title
        pending.payload = payload
        pending.filters = PendingActionFilters(
            title=payload.get("title"),
            date=payload.get("date"),
            time_range=f"{payload.get('start_at')}..{payload.get('end_at')}" if payload.get("start_at") and payload.get("end_at") else None,
        )
        state.pending_action = pending
        await self.state_store.save(user_id=str(user.id), session_id=session_id, state=state)
        if _pending_create_missing(payload):
            return None
        await memory_handler.add_user_message(prompt)
        return await self._execute_pending_create(
            state=state,
            pending=pending,
            session_id=session_id,
            user=user,
            db=db,
            memory_response=memory_response,
            memory_handler=memory_handler,
        )

    async def _try_bulk_delete_confirmation(
        self,
        *,
        prompt: str,
        session_id: str,
        now_local: datetime,
        user: User,
        db: AsyncSession,
        memory_response: Any,
        memory_handler: AgentMemoryHandler,
    ) -> AssistantMessageResponse | None:
        date_range = _bulk_delete_range_from_prompt(prompt, now_local)
        if date_range is None or not _looks_like_bulk_delete_request(prompt, now_local):
            return None

        await memory_handler.add_user_message(prompt)
        start_at, end_at, date_label = date_range
        result = await self.registry.fetch_events(
            FetchEventsInput(start_at=start_at, end_at=end_at, max_results=500),
            user=user,
            db=db,
            memory=memory_response.memory,
        )
        events = result.events
        if not events:
            reply = f"I don't see any calendar events from {date_label}, so there's nothing to delete."
            await memory_handler.add_assistant_message(reply)
            return self._calendar_response(
                session_id=session_id,
                reply=reply,
                memory=memory_response.memory,
                intent="DELETE_EVENT",
                reason="Bulk delete request found no matching events.",
                execution=PlanExecutionResult(status="completed", executed_steps=1),
            )

        action = PendingCalendarAction(
            id=uuid.uuid4().hex,
            action="delete_event",
            status="awaiting_confirmation",
            requires_confirmation=True,
            filters=PendingActionFilters(date=date_label),
            target_event_ids=[event.id for event in events],
            payload={
                "start_at": start_at.isoformat(),
                "end_at": end_at.isoformat(),
                "date_label": date_label,
            },
            created_at=datetime.now(UTC).isoformat(),
        )
        state = await self.state_store.load(user_id=str(user.id), session_id=session_id)
        state.current_intent = "DELETE_EVENT"
        state.pending_action = action
        state.confirmation_target = action
        state.awaiting_confirmation = True
        state.recently_referenced_events = events[:10]
        await self.state_store.save(user_id=str(user.id), session_id=session_id, state=state)

        names = _preview_event_titles(events)
        reply = f"I found {len(events)} calendar event{'s' if len(events) != 1 else ''} from {date_label}: {names}. Delete all of them?"
        await memory_handler.add_assistant_message(reply)
        preview = [
            PlanPreviewChange(
                action="batch_delete_events",
                title=event.title,
                details="Delete event after confirmation.",
                current_start_at=event.start_at,
            )
            for event in events
        ]
        return self._calendar_response(
            session_id=session_id,
            reply=reply,
            memory=memory_response.memory,
            intent="DELETE_EVENT",
            reason="Prepared bulk delete and requested confirmation.",
            execution=PlanExecutionResult(
                status="awaiting_confirmation",
                executed_steps=1,
                preview=preview,
            ),
            requires_confirmation=True,
            risk_level="high",
            display_actions=[
                DisplayAction(
                    kind="ask_user",
                    summary=f"Delete {len(events)} events from {date_label}.",
                )
            ],
            referenced_events=events,
            awaiting_confirmation=True,
            confirmation_token=action.id,
        )

    async def _try_simple_create(
        self,
        *,
        prompt: str,
        session_id: str,
        timezone_str: str,
        now_local: datetime,
        user: User,
        db: AsyncSession,
        memory_response: Any,
        memory_handler: AgentMemoryHandler,
        history_message: str | None = None,
    ) -> AssistantMessageResponse | None:
        extracted = await _extract_simple_calendar_command_with_gemma(prompt, now_local)
        _log_simple_extraction(extraction=extracted, raw_user_message=prompt)
        if extracted.intent != "create_single_event":
            return None
        if extracted.missing_fields or not (extracted.date_value and extracted.title and extracted.start_time):
            return None

        await memory_handler.add_user_message(history_message or prompt)
        start_hour, start_minute = [int(part) for part in extracted.start_time.split(":")]
        start_at = extracted.date_value.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
        if extracted.end_time:
            end_hour, end_minute = [int(part) for part in extracted.end_time.split(":")]
            end_at = extracted.date_value.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
            if end_at <= start_at:
                end_at += timedelta(hours=12)
        else:
            end_at = start_at + timedelta(minutes=extracted.duration_minutes or 60)
        reservation = await reserve_usage(db, user, FeatureName.BASIC_AI_ACTION)
        try:
            result = await self.registry.create_event(
                CreateEventInput(
                    title=extracted.title,
                    start_at=start_at,
                    end_at=end_at,
                    timezone=timezone_str,
                ),
                user=user,
                db=db,
                memory=memory_response.memory,
            )
        except PaywallError:
            await refund_usage(db, reservation)
            raise
        except ValueError as exc:
            await refund_usage(db, reservation)
            reply = str(exc)
            await memory_handler.add_assistant_message(reply)
            return self._base_response(
                session_id=session_id,
                reply=reply,
                memory=memory_response.memory,
                intent="create",
                route_reason="Simple create hit a calendar validation guard.",
                execution=PlanExecutionResult(status="completed", error=reply),
            )
        except Exception:
            await refund_usage(db, reservation)
            raise

        event = result.created_events[0] if result.created_events else None
        await commit_usage(db, reservation)
        if event:
            await memory_handler.update_last_event(event.id, event.title)
        detail = result.preview[0].details if result.preview else ""
        overlap_note = " It overlaps with an existing event." if "Overlaps with:" in detail else ""
        reply = f"Scheduled: {extracted.title} {start_at.strftime('%a %Y-%m-%d')} {start_at.strftime('%H:%M')}-{end_at.strftime('%H:%M')}.{overlap_note}"
        await memory_handler.add_assistant_message(reply)
        return self._base_response(
            session_id=session_id,
            reply=reply,
            memory=memory_response.memory,
            intent="create",
            route_reason="Handled simple complete create without LLM.",
            execution=PlanExecutionResult(
                status="completed",
                executed_steps=1,
                preview=result.preview,
                rollback_available=bool(result.rollback),
                created_events=result.created_events,
            ),
        )

    async def _try_simple_create_clarification(
        self,
        *,
        prompt: str,
        session_id: str,
        timezone_str: str,
        now_local: datetime,
        user: User,
        memory_response: Any,
        memory_handler: AgentMemoryHandler,
    ) -> AssistantMessageResponse | None:
        extracted = await _extract_simple_calendar_command_with_gemma(prompt, now_local)
        if extracted.intent != "create_single_event":
            return None

        if not extracted.missing_fields:
            _log_simple_extraction(extraction=extracted, raw_user_message=prompt)
            return None

        await memory_handler.add_user_message(prompt)
        await self._save_pending_create_draft(
            session_id=session_id,
            user=user,
            extracted=extracted,
            timezone_str=timezone_str,
        )
        if "title" in extracted.missing_fields:
            reply = "What should I call the event?"
            reason = "title missing"
        elif "date" in extracted.missing_fields and "start_time" in extracted.missing_fields:
            reply = f"When should I schedule {extracted.title}?"
            reason = "date and start_time missing"
        elif "date" in extracted.missing_fields:
            reply = f"Which day should I schedule {extracted.title}?"
            reason = "date missing"
        else:
            reply = f"What time should I schedule {extracted.title}?"
            reason = "start_time missing"

        _log_simple_extraction(
            extraction=extracted,
            raw_user_message=prompt,
            clarification_question=reply,
            reason_for_clarification=reason,
        )
        await memory_handler.add_assistant_message(reply)
        return self._calendar_response(
            session_id=session_id,
            reply=reply,
            memory=memory_response.memory,
            intent="CREATE_EVENT",
            reason="Missing required event fields.",
            execution=PlanExecutionResult(status="completed"),
        )

    async def _try_simple_query(
        self,
        *,
        prompt: str,
        session_id: str,
        now_local: datetime,
        user: User,
        db: AsyncSession,
        memory_response: Any,
        memory_handler: AgentMemoryHandler,
    ) -> AssistantMessageResponse | None:
        normalized = prompt.casefold()
        if not re.search(r"\b(what|show|list)\b", normalized):
            return None
        if "tomorrow" in normalized:
            day = now_local.date() + timedelta(days=1)
        elif "today" in normalized:
            day = now_local.date()
        else:
            return None

        await memory_handler.add_user_message(prompt)
        start_at = datetime.combine(day, datetime.min.time(), tzinfo=now_local.tzinfo)
        end_at = start_at + timedelta(days=1)
        result = await self.registry.fetch_events(
            FetchEventsInput(start_at=start_at, end_at=end_at, max_results=20),
            user=user,
            db=db,
            memory=memory_response.memory,
        )
        reply = _format_event_list(result.events)
        await memory_handler.add_assistant_message(reply)
        return self._base_response(
            session_id=session_id,
            reply=reply,
            memory=memory_response.memory,
            intent="query",
            route_reason="Handled simple day query without LLM.",
            execution=PlanExecutionResult(status="completed", executed_steps=1),
        )

    async def handle_message(
        self,
        *,
        payload: AssistantMessageRequest,
        user: User,
        db: AsyncSession,
    ) -> AssistantMessageResponse:
        session_id = payload.session_id or uuid.uuid4().hex
        memory_handler = AgentMemoryHandler(self.state_store, user.id, session_id)
        if _looks_like_user_constraint(payload.prompt):
            await memory_handler.add_user_constraint(payload.prompt.strip())
        if _looks_like_conflict_resolution(payload.prompt):
            await memory_handler.set_conflict_mode(True)
        
        # Load structured user memory preferences
        memory_response = await self.memory_service.get_memory(db, user)
        memory_payload = _compact_memory_payload(memory_response.memory)
        last_event_id, last_event_title = await memory_handler.get_last_event()
        user_constraints = await memory_handler.get_user_constraints()
        conflict_mode = await memory_handler.get_conflict_mode()
        attachment_context = _build_attachment_context(payload.attachments)
        must_parse_image = _references_uploaded_image(payload.prompt, payload.attachments)
        intent = await _classify_prompt_intent_with_gemma(payload.prompt, payload.attachments)
        
        timezone_str = payload.timezone or getattr(user, "timezone", "UTC") or "UTC"
        try:
            tz = zoneinfo.ZoneInfo(timezone_str)
        except Exception:
            tz = UTC
            
        now_local = datetime.now(tz)
        history = await memory_handler.get_history()

        pending_response = await self._try_pending_confirmation(
            prompt=payload.prompt,
            confirm=payload.confirm,
            confirmation_token=payload.confirmation_token,
            session_id=session_id,
            user=user,
            db=db,
            memory_response=memory_response,
            memory_handler=memory_handler,
        )
        if pending_response:
            return pending_response

        if not payload.attachments and not payload.dry_run and not payload.preview:
            pending_field_response = await self._try_pending_create_field_reply(
                prompt=payload.prompt,
                session_id=session_id,
                timezone_str=timezone_str,
                now_local=now_local,
                user=user,
                db=db,
                memory_response=memory_response,
                memory_handler=memory_handler,
            )
            if pending_field_response:
                return pending_field_response

            suggested_time_response = await self._try_pending_create_time_suggestion(
                prompt=payload.prompt,
                history=history,
                session_id=session_id,
                timezone_str=timezone_str,
                now_local=now_local,
                user=user,
                memory_response=memory_response,
                memory_handler=memory_handler,
            )
            if suggested_time_response:
                return suggested_time_response

            merged_create_prompt = _merge_schedule_clarification_reply(payload.prompt, history, now_local)
            if merged_create_prompt:
                simple_response = await self._try_simple_create(
                    prompt=merged_create_prompt,
                    session_id=session_id,
                    timezone_str=timezone_str,
                    now_local=now_local,
                    user=user,
                    db=db,
                    memory_response=memory_response,
                    memory_handler=memory_handler,
                    history_message=payload.prompt,
                )
                if simple_response:
                    return simple_response

            if _is_use_previous_request_reply(payload.prompt):
                previous_create_prompt = _latest_create_prompt_from_title_clarification(history, now_local)
                if previous_create_prompt:
                    simple_response = await self._try_simple_create(
                        prompt=previous_create_prompt,
                        session_id=session_id,
                        timezone_str=timezone_str,
                        now_local=now_local,
                        user=user,
                        db=db,
                        memory_response=memory_response,
                        memory_handler=memory_handler,
                        history_message=payload.prompt,
                    )
                    if simple_response:
                        return simple_response

            bulk_delete_response = await self._try_bulk_delete_confirmation(
                prompt=payload.prompt,
                session_id=session_id,
                now_local=now_local,
                user=user,
                db=db,
                memory_response=memory_response,
                memory_handler=memory_handler,
            )
            if bulk_delete_response:
                return bulk_delete_response

        if not payload.attachments and not payload.dry_run and not payload.preview:
            simple_response = await self._try_simple_create(
                prompt=payload.prompt,
                session_id=session_id,
                timezone_str=timezone_str,
                now_local=now_local,
                user=user,
                db=db,
                memory_response=memory_response,
                memory_handler=memory_handler,
            )
            if simple_response:
                return simple_response

            clarification_response = await self._try_simple_create_clarification(
                prompt=payload.prompt,
                session_id=session_id,
                timezone_str=timezone_str,
                now_local=now_local,
                user=user,
                memory_response=memory_response,
                memory_handler=memory_handler,
            )
            if clarification_response:
                return clarification_response

            simple_response = await self._try_simple_query(
                prompt=payload.prompt,
                session_id=session_id,
                now_local=now_local,
                user=user,
                db=db,
                memory_response=memory_response,
                memory_handler=memory_handler,
            )
            if simple_response:
                return simple_response
        
        system_prompt = build_planner_prompt(
            now=now_local,
            timezone=timezone_str,
            memory_payload=memory_payload,
            calendar_context="",
            last_event_id=last_event_id,
            last_event_title=last_event_title,
            user_constraints=user_constraints,
            conflict_mode=conflict_mode,
            include_date_rules=_needs_date_rules(payload.prompt, intent),
            include_planning_rules=intent == "planning",
            include_image_rules=must_parse_image,
        )

        messages = [{"role": "system", "content": system_prompt}]
        if attachment_context:
            messages.append({"role": "system", "content": attachment_context})
        if must_parse_image:
            messages.append({
                "role": "system",
                "content": "The user referenced an uploaded image. You must call parse_schedule_image before planning from it.",
            })
        messages.extend(_history_with_complete_tool_interactions(history))
        
        content = payload.prompt
        messages.append({"role": "user", "content": content})
        await memory_handler.add_user_message(content)

        selected_tools = _select_tool_names(intent, must_parse_image)
        tools = get_openai_tools(selected_tools)
        current_turn_calendar_truth = False
        max_cycles = 4 if intent in {"planning", "conflict", "image"} else 3
        response_tokens = 650 if intent in {"planning", "conflict", "image"} else 320
        last_tool_error: str | None = None
        repeated_tool_errors = 0

        for cycle in range(max_cycles):
            request_kwargs: dict[str, Any] = {
                "model": settings.openai_model,
                "messages": messages,
                **completion_token_param(settings.openai_model, response_tokens),
            }
            if tools:
                request_kwargs["tools"] = tools
                request_kwargs["tool_choice"] = "auto"
            response = await self.client.chat.completions.create(
                **request_kwargs,
            )
            if response.usage:
                logger.info(
                    "planner.token_usage",
                    extra={
                        "input_tokens": response.usage.prompt_tokens,
                        "output_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens,
                        "intent": intent,
                        "tool_count": len(tools),
                    },
                )
            
            message = response.choices[0].message
            msg_dict = message.model_dump(exclude_none=True)
            messages.append(msg_dict)
            
            if not message.tool_calls:
                answer = _strip_tool_json_from_reply(message.content or "I have processed your request.")
                if _looks_like_existing_event_claim(answer) and not current_turn_calendar_truth:
                    messages.append({
                        "role": "system",
                        "content": (
                            "You made a claim about existing calendar events without a fresh calendar tool result in this turn. "
                            "Call fetch_events first. If no events are returned, say: \"I don't see any events at that time.\""
                        ),
                    })
                    continue
                await memory_handler.add_assistant_message(answer)
                
                return AssistantMessageResponse(
                    session_id=session_id,
                    status="completed",
                    reply=answer,
                    routing=RoutingDecision(
                        intent="CHAT",
                        route="simple",
                        selected_model=settings.openai_model,
                        confidence=1.0,
                        complexity_score=0.1,
                        reason="Planner completed tool loop"
                    ),
                    plan=ExecutionPlan(
                        goal="Chat completed",
                        summary="Agent replied directly.",
                        selected_model=settings.openai_model,
                        route="simple",
                        reasoning="Direct LLM completion",
                        response_message=answer
                    ),
                    safety=SafetyAssessment(
                        requires_confirmation=False,
                        risk_level="low",
                    ),
                    execution=PlanExecutionResult(
                        status="completed"
                    ),
                    memory=memory_response.memory
                )

            await memory_handler.add_tool_call(msg_dict)

            # Process tool calls
            latest_event_context: tuple[str, str] | None = None
            cycle_errors: list[str] = []
            for tcall in message.tool_calls:
                args = json.loads(tcall.function.arguments)
                tool_res = await execute_tool_call(
                     registry=self.registry,
                     tool_name=tcall.function.name,
                     tool_args=args,
                     user=user,
                     db=db,
                     memory=memory_response.memory,
                     user_timezone=timezone_str,
                     attachments=payload.attachments,
                )
                if tcall.function.name in {
                    "fetch_events",
                    "summarize_schedule",
                    "detect_conflicts",
                    "optimize_schedule",
                    "create_event",
                    "edit_event",
                    "move_event",
                    "delete_event",
                    "batch_move_events",
                    "batch_delete_events",
                }:
                    current_turn_calendar_truth = True
                
                tool_msg = {
                    "role": "tool",
                    "tool_call_id": tcall.id,
                    "name": tcall.function.name,
                    "content": tool_res,
                }
                messages.append(tool_msg)
                await memory_handler.add_tool_response(
                    tcall.id,
                    tcall.function.name,
                    compact_tool_response(tcall.function.name, tool_res),
                )
                tool_error = _extract_tool_error(tool_res)
                if tool_error:
                    cycle_errors.append(tool_error)
                event_id, event_title = _extract_last_event_from_tool_result(tool_res)
                if event_id and event_title:
                    await memory_handler.update_last_event(event_id, event_title)
                    latest_event_context = (event_id, event_title)
                for deleted_id in _extract_deleted_event_ids(tcall.function.name, tool_res):
                    await memory_handler.clear_last_event(deleted_id)

            if latest_event_context:
                event_id, event_title = latest_event_context
                messages.append({
                    "role": "system",
                    "content": f"[Context: Last event = '{event_title}' (id: {event_id})]",
                })
            if cycle_errors and len(cycle_errors) == len(message.tool_calls):
                current_error = cycle_errors[-1]
                repeated_tool_errors = repeated_tool_errors + 1 if current_error == last_tool_error else 1
                last_tool_error = current_error
                if repeated_tool_errors >= 2 or cycle == max_cycles - 1:
                    answer = _friendly_tool_error(current_error, intent=intent)
                    await memory_handler.add_assistant_message(answer)
                    return self._calendar_response(
                        session_id=session_id,
                        reply=answer,
                        memory=memory_response.memory,
                        intent="CREATE_EVENT" if intent == "create" else "CHAT",
                        reason="Stopped repeated invalid tool calls.",
                        execution=PlanExecutionResult(status="completed", error=current_error),
                    )

        fallback_msg = (
            "I couldn't finish that cleanly. Try a direct format like "
            "`add title on Wednesday at 16:30`, or name the exact event to change."
        )
        await memory_handler.add_assistant_message(fallback_msg)
        return AssistantMessageResponse(
            session_id=session_id,
            status="failed",
            reply=fallback_msg,
            routing=RoutingDecision(
                intent="UNKNOWN",
                route="simple",
                selected_model=settings.openai_model,
                confidence=0.0,
                complexity_score=1.0,
                reason="Max tool loop reached"
            ),
            plan=ExecutionPlan(
                goal="Failure",
                summary="Aborted after max tool cycles",
                selected_model=settings.openai_model,
                route="simple",
                reasoning="Agent ran out of iterations.",
                response_message=fallback_msg
            ),
            safety=SafetyAssessment(
                requires_confirmation=False,
                risk_level="low",
            ),
            execution=PlanExecutionResult(
                status="failed",
                error="Exceeded max planning depth"
            ),
            memory=memory_response.memory
        )
