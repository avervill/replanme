"""OpenAI function definitions and bridging for the assistant tools."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.schemas.assistant import (
    BatchDeleteEventsInput,
    BatchMoveEventsInput,
    CreateEventInput,
    DeleteEventInput,
    DetectConflictsInput,
    EditEventInput,
    FetchEventsInput,
    MoveEventInput,
    FindFreeSlotsInput,
    OptimizeScheduleInput,
    ParseScheduleImageInput,
    ParseScheduleImageResult,
    SummarizeScheduleInput,
    ToolExecutionMetadata,
)
from app.services.assistant.tools import AssistantToolRegistry
from app.services.subscriptions import (
    FeatureName,
    PaywallError,
    commit_usage,
    refund_usage,
    reserve_usage,
    should_skip_basic_ai_tool_usage,
)

logger = logging.getLogger(__name__)

# We select the core actions the PlannerAgent can invoke directly
TOOL_MODELS = {
    "create_event": CreateEventInput,
    "edit_event": EditEventInput,
    "delete_event": DeleteEventInput,
    "fetch_events": FetchEventsInput,
    "move_event": MoveEventInput,
    "find_free_slots": FindFreeSlotsInput,
    "detect_conflicts": DetectConflictsInput,
    "optimize_schedule": OptimizeScheduleInput,
    "summarize_schedule": SummarizeScheduleInput,
    "batch_move_events": BatchMoveEventsInput,
    "batch_delete_events": BatchDeleteEventsInput,
    "parse_schedule_image": ParseScheduleImageInput,
}

DEFAULT_TOOL_NAMES = tuple(TOOL_MODELS)
TOOL_SUMMARY_EVENT_KEYS = {
    "created_events",
    "duplicated_events",
    "deleted_events",
    "events",
}


def _compact_schema(value: Any) -> Any:
    """Remove schema decoration that helps docs more than tool calling."""
    if isinstance(value, dict):
        return {
            key: _compact_schema(item)
            for key, item in value.items()
            if key not in {"title", "description", "examples", "default"}
        }
    if isinstance(value, list):
        return [_compact_schema(item) for item in value]
    return value


def _format_event_summary(event: dict[str, Any]) -> str:
    event_id = str(event.get("id") or "?")
    title = str(event.get("title") or "Untitled")
    start = str(event.get("start_at") or "?")
    end = str(event.get("end_at") or "?")
    start_short = start.replace("T", " ")[:16]
    end_short = end.replace("T", " ")[11:16] if "T" in end else end[:16]
    return f"{event_id} | {title} | {start_short}-{end_short}"


def compact_tool_response(tool_name: str, raw_response: str, *, max_events: int = 8) -> str:
    """Persist a compact tool result in chat history instead of full JSON payloads."""
    try:
        payload = json.loads(raw_response)
    except json.JSONDecodeError:
        return raw_response[:800]

    if not isinstance(payload, dict):
        return raw_response[:800]
    if payload.get("error"):
        return json.dumps({"tool": tool_name, "error": payload["error"]})

    summary: dict[str, Any] = {
        "tool": tool_name,
        "success": payload.get("success", True),
    }
    for key in ("count", "event_count", "has_conflicts", "busiest_day", "summary"):
        if key in payload:
            summary[key] = payload[key]

    event_lines: list[str] = []
    for key in TOOL_SUMMARY_EVENT_KEYS:
        events = payload.get(key)
        if isinstance(events, list):
            event_lines.extend(
                _format_event_summary(event)
                for event in events[: max(0, max_events - len(event_lines))]
                if isinstance(event, dict)
            )
        if len(event_lines) >= max_events:
            break
    if event_lines:
        summary["events"] = event_lines

    for key in ("updated_event", "moved_event"):
        event = payload.get(key)
        if isinstance(event, dict):
            summary[key] = _format_event_summary(event)

    conflicts = payload.get("conflicts")
    if isinstance(conflicts, list):
        summary["conflicts"] = [
            {
                "event_id": item.get("event_id"),
                "title": item.get("title"),
                "with": item.get("conflicting_with"),
                "start": item.get("start_at"),
            }
            for item in conflicts[:max_events]
            if isinstance(item, dict)
        ]

    suggestions = payload.get("suggestions")
    if isinstance(suggestions, list):
        summary["suggestions"] = [
            {
                "title": item.get("title"),
                "from": item.get("current_start_at"),
                "to": item.get("suggested_start_at"),
            }
            for item in suggestions[:max_events]
            if isinstance(item, dict)
        ]

    if tool_name == "parse_schedule_image":
        summary["subjects"] = payload.get("subjects", [])[:8]
        summary["topics"] = payload.get("topics", [])[:8]
        summary["schedule_structure"] = payload.get("schedule_structure", [])[:8]

    return json.dumps(summary, ensure_ascii=True)


def _clean_title(value: str) -> str:
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        raise ValueError("title must not be empty")
    if len(cleaned) > 120:
        raise ValueError("title is too long")
    if re.search(r"([A-Za-z]:\\|/tmp/|\\tmp\\|https?://|data:image/)", cleaned):
        raise ValueError("title must be a human event title, not a path, URL, or raw file content")
    if cleaned.count("\n") or len(cleaned.split()) > 18:
        raise ValueError("title looks like raw pasted text; extract a concise event title first")
    return cleaned


def _validate_tool_args(tool_name: str, tool_args: dict[str, Any]) -> None:
    title = tool_args.get("title")
    if isinstance(title, str):
        tool_args["title"] = _clean_title(title)

    for start_key, end_key in (
        ("start_at", "end_at"),
        ("new_start_at", "new_end_at"),
        ("source_start_at", "source_end_at"),
        ("target_start_at", "target_end_at"),
    ):
        start = tool_args.get(start_key)
        end = tool_args.get(end_key)
        if start and end and str(end) <= str(start):
            raise ValueError(f"{end_key} must be after {start_key}")

    if tool_name in {"edit_event", "delete_event", "move_event"} and not (
        tool_args.get("event_id") or tool_args.get("match_title")
    ):
        raise ValueError("event_id is required for updates/deletes unless an explicit title search is requested")


def _parse_attachment_text(text: str) -> tuple[list[str], list[str], list[str]]:
    subjects: list[str] = []
    topics: list[str] = []
    structure: list[str] = []
    for raw_line in text.splitlines():
        line = " ".join(raw_line.strip(" -\t").split())
        if not line:
            continue
        lowered = line.casefold()
        if any(token in lowered for token in ("subject", "class", "course", "lesson")):
            subjects.append(line)
        elif any(token in lowered for token in ("topic", "chapter", "unit", "module")):
            topics.append(line)
        if re.search(r"\b(mon|tue|wed|thu|fri|sat|sun|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", lowered) or re.search(r"\b\d{1,2}:\d{2}\b", line):
            structure.append(line)

    if not subjects:
        subjects = [line for line in structure[:5]]
    if not topics:
        topics = [
            " ".join(line.split()[:12])
            for line in text.splitlines()
            if line.strip() and line.strip() not in structure
        ][:8]
    return subjects[:10], topics[:20], structure[:20]


def _execute_parse_schedule_image(tool_args: dict[str, Any], attachments: list[dict[str, Any]]) -> str:
    requested_id = tool_args.get("attachment_id")
    selected = None
    for attachment in attachments:
        if requested_id and attachment.get("id") != requested_id:
            continue
        if attachment.get("kind") == "image" or attachment.get("text_preview"):
            selected = attachment
            break
    if selected is None and attachments:
        selected = attachments[0]

    if not selected:
        return json.dumps({"error": "No uploaded image is available to parse."})

    text = str(selected.get("text_preview") or "").strip()
    if not text:
        return json.dumps({"error": "The uploaded image has no extracted text. Ask the user to re-upload a clearer image."})

    subjects, topics, structure = _parse_attachment_text(text)
    result = ParseScheduleImageResult(
        success=True,
        metadata=ToolExecutionMetadata(tool="parse_schedule_image", executed=True),
        attachment_id=selected.get("id"),
        extracted_text=text[:1000],
        subjects=subjects,
        topics=topics,
        schedule_structure=structure,
    )
    return json.dumps(result.model_dump(mode="json"))

def get_openai_tools(tool_names: list[str] | tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    """Generates the OpenAI tools payload dynamically from Pydantic schemas."""
    tools = []
    selected_names = tool_names or DEFAULT_TOOL_NAMES
    
    for name in selected_names:
        model = TOOL_MODELS.get(name)
        if model is None:
            logger.warning("Unknown OpenAI tool requested: %s", name)
            continue
        schema = _compact_schema(model.model_json_schema())
            
        tool = {
            "type": "function",
            "function": {
                "name": name,
                "description": schema.get("description", f"Executes {name} on the calendar."),
                "parameters": schema,
            }
        }
        tools.append(tool)
        
    return tools

async def execute_tool_call(
    registry: AssistantToolRegistry,
    tool_name: str,
    tool_args: dict[str, Any],
    user: Any,
    db: Any,
    memory: Any,
    user_timezone: str = "UTC",
    attachments: list[dict[str, Any]] | None = None,
) -> str:
    """Invokes the underlying AssistantToolRegistry based on OpenAI's request."""
    if tool_name not in TOOL_MODELS:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    logger.debug("planner.tool_call", extra={"tool_name": tool_name, "tool_args": tool_args})

    if tool_name == "parse_schedule_image":
        return _execute_parse_schedule_image(tool_args, attachments or [])

    input_model = TOOL_MODELS[tool_name]
    
    # Inject user timezone if the tool accepts a timezone field and AI didn't set one
    if "timezone" in input_model.model_fields and not tool_args.get("timezone"):
        tool_args["timezone"] = user_timezone
    
    try:
        _validate_tool_args(tool_name, tool_args)
        validated_input = input_model.model_validate(tool_args)
    except Exception as e:
        return json.dumps({"error": f"Validation error: {str(e)}"})

    reservation = None
    if db is not None:
        if (
            tool_name in AssistantToolRegistry.MUTATING_TOOLS
            and not getattr(validated_input, "dry_run", False)
            and not should_skip_basic_ai_tool_usage()
        ):
            reservation = await reserve_usage(db, user, FeatureName.BASIC_AI_ACTION)
        elif tool_name == "optimize_schedule" and not should_skip_basic_ai_tool_usage():
            reservation = await reserve_usage(db, user, FeatureName.SMART_RESCHEDULING)

    try:
        # E.g. registry.create_event(payload, user=..., db=..., memory=...)
        func = getattr(registry, tool_name)
        result = await func(validated_input, user=user, db=db, memory=memory)
        await commit_usage(db, reservation)
        # Returns a pydantic model (ToolExecutionResult), usually dump to json
        if hasattr(result, "model_dump"):
            return json.dumps(result.model_dump(mode="json"))
        return json.dumps(result)
    except PaywallError:
        await refund_usage(db, reservation)
        raise
    except Exception as e:
        await refund_usage(db, reservation)
        return json.dumps({"error": f"Execution error: {str(e)}"})
