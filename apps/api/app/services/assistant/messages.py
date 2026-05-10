"""User-facing response formatting for the calendar assistant."""

from __future__ import annotations

import logging

from app.schemas.assistant import CalendarEventSnapshot, DisplayAction

logger = logging.getLogger(__name__)


def ensure_string_message(value: object) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, dict):
        logger.error("Non-string assistant message: %s", value)
        return "I completed the action, but had trouble formatting the response."
    return str(value)


def format_event_time(event: CalendarEventSnapshot) -> str:
    return event.start_at.strftime("%I:%M %p").lstrip("0")


def format_delete_confirmation(event: CalendarEventSnapshot, *, day_label: str) -> str:
    return (
        f'I found your "{event.title}" event scheduled for {day_label} at '
        f"{format_event_time(event)}. Do you want me to delete it?"
    )


def format_delete_success(event: CalendarEventSnapshot, *, day_label: str) -> str:
    return f'Done. Your {event.title.lower()} event for {day_label} has been removed.'


def format_multiple_matches(
    events: list[CalendarEventSnapshot],
    *,
    title: str,
    day_label: str,
    action_label: str = "delete",
) -> tuple[str, list[DisplayAction]]:
    lines = [f"I found {len(events)} {title.lower()}-related events {day_label}:"]
    actions: list[DisplayAction] = []
    for index, event in enumerate(events, start=1):
        summary = f"{index}. {event.title}, {format_event_time(event)}"
        lines.append(summary)
        actions.append(DisplayAction(kind="match_option", summary=summary))
    lines.append(f"Which one should I {action_label}?")
    return "\n".join(lines), actions


def format_no_match(title: str, *, scope_label: str, suggest_wider_range: bool) -> str:
    message = f"I couldn't find a {title.lower()} event for {scope_label}."
    if suggest_wider_range:
        message += " Want me to search this week?"
    return message


def format_create_success(event: CalendarEventSnapshot) -> str:
    day = event.start_at.strftime("%A").lower()
    return f'Done. I added "{event.title}" for {day} at {format_event_time(event)}.'


def format_update_success(event: CalendarEventSnapshot) -> str:
    day = event.start_at.strftime("%A").lower()
    return f'Done. I updated "{event.title}" for {day} at {format_event_time(event)}.'


def format_duplicate_confirmation(event_count: int, *, source_label: str, target_label: str) -> str:
    return (
        f"I found {event_count} events in {source_label}. "
        f"Do you want me to duplicate them into {target_label}?"
    )


def format_cancelled_action() -> str:
    return "Okay, I cancelled that action."


def format_no_pending_confirmation() -> str:
    return "I’m not holding a pending calendar action right now. Tell me what you want to change."
