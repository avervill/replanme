"""LangGraph-based assistant orchestration.

The public API shape stays stable while the implementation is a single graph
runtime where the cheap model is the first reasoning hop:

* gpt-4o-mini receives the user message first and chooses tools.
* gpt-5.4-mini is exposed as a delegate_to_smarter_model tool.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
import zoneinfo
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User
from app.schemas.assistant import (
    AssistantMessageRequest,
    AssistantMessageResponse,
    BatchDeleteEventsInput,
    BatchMoveEventsInput,
    CalendarEventSnapshot,
    CreateEventInput,
    CreateEventResult,
    DeleteEventInput,
    DetectConflictsInput,
    DisplayAction,
    DuplicateEventsInput,
    EditEventInput,
    ExecutionLogEntry,
    ExecutionPlan,
    FetchEventsInput,
    FindFreeSlotsInput,
    MoveEventInput,
    OptimizeScheduleInput,
    ParseScheduleImageInput,
    ParseScheduleImageResult,
    PlanExecutionResult,
    PlanPreviewChange,
    RoutingDecision,
    SafetyAssessment,
    SummarizeScheduleInput,
    ToolExecutionMetadata,
    ToolName,
)
from app.services.assistant.conversation_memory import AgentMemoryHandler
from app.services.assistant.memory import PlanningMemoryService
from app.services.assistant.state import ConversationStateStore
from app.services.assistant.tools import AssistantToolRegistry
from app.services.subscriptions import FeatureName, classify_prompt_feature

try:  # pragma: no cover - exercised only when optional deps are installed
    from langgraph.graph import END, START, StateGraph
except Exception:  # pragma: no cover - local test environment may not install deps
    END = "__end__"
    START = "__start__"
    StateGraph = None  # type: ignore[assignment]

try:  # pragma: no cover - exercised only when optional deps are installed
    from langchain_openai import ChatOpenAI
except Exception:  # pragma: no cover - local test environment may not install deps
    ChatOpenAI = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

CalendarIntentName = Literal[
    "simple_chat",
    "create_single_event",
    "delete_event",
    "update_event",
    "move_event",
    "duplicate_event",
    "generate_plan",
    "optimize_schedule",
    "answer_question",
    "confirm_plan_to_calendar",
    "reject_plan",
]

DELEGATE_TOOL = "delegate_to_smarter_model"

TOOL_MODELS: dict[str, type[BaseModel]] = {
    "create_event": CreateEventInput,
    "edit_event": EditEventInput,
    "delete_event": DeleteEventInput,
    "duplicate_events": DuplicateEventsInput,
    "fetch_events": FetchEventsInput,
    "move_event": MoveEventInput,
    "find_free_slots": FindFreeSlotsInput,
    "summarize_schedule": SummarizeScheduleInput,
    "detect_conflicts": DetectConflictsInput,
    "optimize_schedule": OptimizeScheduleInput,
    "batch_move_events": BatchMoveEventsInput,
    "batch_delete_events": BatchDeleteEventsInput,
    "parse_schedule_image": ParseScheduleImageInput,
}

MUTATING_TOOLS = {
    "create_event",
    "edit_event",
    "delete_event",
    "duplicate_events",
    "move_event",
    "batch_move_events",
    "batch_delete_events",
}

FRONTLINE_TOOLS: tuple[str, ...] = (
    "create_event",
    "fetch_events",
    "find_free_slots",
    "summarize_schedule",
    "parse_schedule_image",
    DELEGATE_TOOL,
)
COMPLEX_TOOLS: tuple[str, ...] = tuple(TOOL_MODELS)

YES_REPLIES = {"yes", "y", "ok", "okay", "sure", "confirm", "apply", "apply changes", "do it"}
NO_REPLIES = {"no", "n", "cancel", "stop", "don't", "dont", "do not", "reject"}


def _chat_model(model: str):
    if ChatOpenAI is None:
        return None
    base_kwargs = {"model": model, "api_key": settings.openai_api_key}
    try:
        return ChatOpenAI(
            **base_kwargs,
            timeout=settings.assistant_model_timeout_seconds,
            max_retries=1,
        )
    except TypeError as exc:
        if "timeout" not in str(exc) and "max_retries" not in str(exc):
            raise
        return ChatOpenAI(**base_kwargs)


class RouteDecision(BaseModel):
    intent: CalendarIntentName
    route: Literal["simple", "complex"]
    selected_model: str
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    complexity_score: float = Field(default=0.1, ge=0.0)
    reason: str
    candidate_tools: list[ToolName] = Field(default_factory=list)


class ToolCallPlan(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    id: str | None = None


class DelegateToSmarterModelInput(BaseModel):
    """Escalate complex calendar reasoning from the cheap frontline model."""

    task: str = Field(description="The user's full task, including relevant context from the conversation.")
    reason: str | None = Field(default=None, description="Why this needs deeper planning or optimization.")


class SmartModelResult(BaseModel):
    success: bool = True
    answer: str = ""
    intent: CalendarIntentName = "generate_plan"
    selected_model: str = Field(default_factory=lambda: settings.ai_complex_model)
    preview: list[PlanPreviewChange] = Field(default_factory=list)
    planned_tool_calls: list[dict[str, Any]] = Field(default_factory=list)


ALL_TOOL_MODELS: dict[str, type[BaseModel]] = {
    **TOOL_MODELS,
    DELEGATE_TOOL: DelegateToSmarterModelInput,
}


class AgentGraphState(TypedDict, total=False):
    payload: AssistantMessageRequest
    user: User
    db: AsyncSession
    session_id: str
    user_id: str
    timezone: str
    now: datetime
    memory: Any
    memory_handler: AgentMemoryHandler
    history: list[dict[str, Any]]
    conversation_state: Any
    planning_state: dict[str, Any] | None
    onboarding_profile: str
    route: RouteDecision
    selected_tools: tuple[str, ...]
    messages: list[dict[str, Any]]
    tool_calls: list[ToolCallPlan]
    tool_results: list[dict[str, Any]]
    planned_tool_calls: list[dict[str, Any]]
    answer: str
    response: AssistantMessageResponse
    loop_count: int
    delegated_to_smarter_model: bool


def _calendar_intent(intent: str) -> str:
    return {
        "create_single_event": "CREATE_EVENT",
        "delete_event": "DELETE_EVENT",
        "update_event": "UPDATE_EVENT",
        "move_event": "MOVE_EVENT",
        "duplicate_event": "DUPLICATE_EVENTS",
        "generate_plan": "PLAN_PERIOD",
        "optimize_schedule": "OPTIMIZE_SCHEDULE",
        "answer_question": "SEARCH_EVENTS",
        "confirm_plan_to_calendar": "CONFIRMATION_YES",
        "reject_plan": "CONFIRMATION_NO",
        "simple_chat": "CHAT",
    }.get(intent, "UNKNOWN")


def _compact_schema(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _compact_schema(item)
            for key, item in value.items()
            if key not in {"examples", "default"}
        }
    if isinstance(value, list):
        return [_compact_schema(item) for item in value]
    return value


def _tool_specs(tool_names: tuple[str, ...]) -> list[dict[str, Any]]:
    specs = []
    for name in tool_names:
        model = ALL_TOOL_MODELS[name]
        schema = _compact_schema(model.model_json_schema())
        specs.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": schema.get("description") or f"Execute {name} on the user's calendar.",
                    "parameters": schema,
                },
            }
        )
    return specs


def _prompt_norm(prompt: str) -> str:
    return re.sub(r"\s+", " ", prompt.strip().casefold())


def _is_yes(prompt: str) -> bool:
    normalized = _prompt_norm(prompt).strip(".! ")
    return normalized in YES_REPLIES or normalized.startswith(("yes ", "ok ", "okay ", "sure "))


def _is_no(prompt: str) -> bool:
    normalized = _prompt_norm(prompt).strip(".! ")
    return normalized in NO_REPLIES or normalized.startswith(("no ", "cancel "))


def _should_skip_frontline_for_planning(prompt: str) -> bool:
    return classify_prompt_feature(prompt) in {
        FeatureName.WEEKLY_PLANNING,
        FeatureName.MONTHLY_PLANNING,
    }


def _safe_zoneinfo(timezone: str):
    try:
        return zoneinfo.ZoneInfo(timezone)
    except Exception:
        return UTC


def _format_events(events: list[CalendarEventSnapshot]) -> str:
    if not events:
        return "I don't see any events in that window."
    lines = ["Here is what I found:"]
    for event in events[:12]:
        lines.append(f"- {event.title}: {event.start_at.strftime('%Y-%m-%d %H:%M')}-{event.end_at.strftime('%H:%M')}")
    return "\n".join(lines)


def _extract_text(message: Any) -> str:
    text = getattr(message, "text", None)
    if callable(text):
        value = text()
        if isinstance(value, str):
            return value
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in content)
    return str(content or "")


def _json_summary(value: Any, *, max_chars: int = 2000) -> str:
    try:
        if hasattr(value, "model_dump"):
            payload = value.model_dump(mode="json")
        else:
            payload = value
        return json.dumps(payload, ensure_ascii=True)[:max_chars]
    except Exception:
        return str(value)[:max_chars]


def _compact_cell(value: Any, *, max_chars: int = 120) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.replace("|", "/").split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _compact_dt(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else _compact_cell(value)


def _compact_events_context(events: list[CalendarEventSnapshot], *, count: int | None, timezone: str) -> str:
    total = count if count is not None else len(events)
    lines = [
        f"time zone: {timezone}",
        f"events count: {total}",
        "events:",
        "title | st_datetime | end_datetime | desc",
    ]
    if not events:
        lines.append("(none)")
        return "\n".join(lines)
    for event in events[:80]:
        lines.append(
            " | ".join(
                (
                    _compact_cell(event.title),
                    _compact_dt(event.start_at),
                    _compact_dt(event.end_at),
                    _compact_cell(event.description),
                )
            )
        )
    if total > len(events):
        lines.append(f"... {total - len(events)} more not shown")
    return "\n".join(lines)


def _compact_slots_context(value: Any, *, timezone: str) -> str:
    slots = list(getattr(value, "slots", []) or [])
    lines = [
        f"time zone: {timezone}",
        f"free slots count: {len(slots)}",
        "free slots:",
        "st_datetime | end_datetime | energy | score",
    ]
    if not slots:
        lines.append("(none)")
        return "\n".join(lines)
    for slot in slots[:80]:
        lines.append(
            " | ".join(
                (
                    _compact_dt(slot.start_at),
                    _compact_dt(slot.end_at),
                    _compact_cell(getattr(slot, "energy_band", "")),
                    _compact_cell(getattr(slot, "score", "")),
                )
            )
        )
    return "\n".join(lines)


def _compact_preview_context(value: Any, *, timezone: str) -> str:
    preview = _preview_from_payload(value)
    lines = [
        f"time zone: {timezone}",
        f"preview count: {len(preview)}",
        "preview:",
        "action | title | st_datetime | end_datetime | details",
    ]
    if not preview:
        lines.append("(none)")
        return "\n".join(lines)
    for item in preview[:80]:
        lines.append(
            " | ".join(
                (
                    _compact_cell(item.action),
                    _compact_cell(item.title),
                    _compact_dt(item.proposed_start_at or item.current_start_at or ""),
                    _compact_dt(item.proposed_end_at or ""),
                    _compact_cell(item.details),
                )
            )
        )
    return "\n".join(lines)


def _compact_tool_result(value: Any, *, timezone: str, max_chars: int = 6000) -> str:
    if isinstance(value, SmartModelResult):
        lines = [
            f"model: {value.selected_model}",
            f"success: {value.success}",
            f"intent: {value.intent}",
            f"planned tool calls count: {len(value.planned_tool_calls)}",
        ]
        if value.answer:
            lines.append(f"answer: {_compact_cell(value.answer, max_chars=1000)}")
        if value.preview:
            lines.append(_compact_preview_context(value, timezone=timezone))
        return "\n".join(lines)[:max_chars]

    if hasattr(value, "events"):
        events = list(getattr(value, "events", []) or [])
        count = getattr(value, "count", None)
        if count is None:
            count = getattr(value, "event_count", None)
        summary = getattr(value, "summary", None)
        header = f"summary: {_compact_cell(summary, max_chars=1000)}\n" if summary else ""
        return (header + _compact_events_context(events, count=count, timezone=timezone))[:max_chars]

    if hasattr(value, "slots"):
        return _compact_slots_context(value, timezone=timezone)[:max_chars]

    if _preview_from_payload(value):
        return _compact_preview_context(value, timezone=timezone)[:max_chars]

    return _json_summary(value, max_chars=max_chars)


def _localize_naive_datetimes(value: Any, tzinfo: Any) -> Any:
    if isinstance(value, datetime):
        return value.replace(tzinfo=tzinfo) if value.tzinfo is None else value
    if isinstance(value, BaseModel):
        updates = {
            name: _localize_naive_datetimes(getattr(value, name), tzinfo)
            for name in value.__class__.model_fields
        }
        return value.model_copy(update=updates)
    if isinstance(value, list):
        return [_localize_naive_datetimes(item, tzinfo) for item in value]
    if isinstance(value, tuple):
        return tuple(_localize_naive_datetimes(item, tzinfo) for item in value)
    if isinstance(value, dict):
        return {key: _localize_naive_datetimes(item, tzinfo) for key, item in value.items()}
    return value


def _infer_tzinfo(value: Any) -> Any | None:
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.tzinfo
    if isinstance(value, BaseModel):
        for name in value.__class__.model_fields:
            tzinfo = _infer_tzinfo(getattr(value, name))
            if tzinfo is not None:
                return tzinfo
    if isinstance(value, dict):
        for item in value.values():
            tzinfo = _infer_tzinfo(item)
            if tzinfo is not None:
                return tzinfo
    if isinstance(value, (list, tuple)):
        for item in value:
            tzinfo = _infer_tzinfo(item)
            if tzinfo is not None:
                return tzinfo
    return None


def _result_success(value: Any) -> bool:
    return bool(getattr(value, "success", True))


def _validation_error_message(tool_name: str, exc: ValidationError) -> str:
    missing = [str(error["loc"][-1]) for error in exc.errors() if error.get("type") == "missing" and error.get("loc")]
    if missing:
        return f"validation_error: {tool_name} is missing required field(s): {', '.join(missing)}. Ask the user for the missing details before calling this tool again."
    return f"validation_error: {tool_name} arguments are invalid: {exc}. Ask a clarification instead of retrying with guessed values."


def _is_duplicate_create_error(tool_name: str, exc: Exception) -> bool:
    return tool_name == "create_event" and "duplicate" in str(exc).casefold() and "keep both" in str(exc).casefold()


def _preview_from_payload(value: Any) -> list[PlanPreviewChange]:
    return list(getattr(value, "preview", []) or [])


def _key_value(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if value is None:
        return ""
    return str(value)


def _dedupe_preview(preview: list[PlanPreviewChange]) -> list[PlanPreviewChange]:
    seen: set[tuple[str, str, str, str]] = set()
    deduped: list[PlanPreviewChange] = []
    for item in preview:
        key = (
            item.action,
            item.title.strip().casefold(),
            _key_value(item.proposed_start_at or item.current_start_at),
            _key_value(item.proposed_end_at),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _tool_call_key(call: dict[str, Any]) -> tuple[str, str, str, str, str]:
    args = dict(call.get("args") or {})
    return (
        str(call.get("name") or ""),
        str(args.get("event_id") or args.get("match_title") or args.get("title") or "").strip().casefold(),
        _key_value(args.get("start_at") or args.get("new_start_at") or args.get("source_start_at")),
        _key_value(args.get("end_at") or args.get("new_end_at") or args.get("source_end_at")),
        str(args.get("query") or args.get("title_contains") or "").strip().casefold(),
    )


def _dedupe_tool_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for call in calls:
        key = _tool_call_key(call)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(call)
    return deduped


def _compact_onboarding_profile(data: Any) -> str:
    if not isinstance(data, dict) or not data:
        return ""

    def value_text(value: Any) -> str:
        if isinstance(value, list):
            return ", ".join(str(item) for item in value if item)
        return str(value) if value else ""

    energy = data.get("energyProfile") if isinstance(data.get("energyProfile"), dict) else {}
    lines = [
        "User planning preferences:",
        "Use these as persistent defaults unless the current request overrides them.",
    ]
    fields = [
        ("role", data.get("role")),
        ("main goal", data.get("mainGoal")),
        ("planning pain", data.get("planningPain")),
        ("peak focus", energy.get("peakFocusTime")),
        ("low energy", energy.get("lowEnergyTime")),
        ("work block", energy.get("preferredWorkBlockLength")),
        ("sleep", energy.get("sleepPreference")),
        ("calendar intent", data.get("calendarIntent")),
    ]
    for label, value in fields:
        text = value_text(value)
        if text:
            lines.append(f"- {label}: {text}")
    return "\n".join(lines)[:1200]


def _public_tool_names(tool_names: list[str] | tuple[str, ...]) -> list[ToolName]:
    return [name for name in tool_names if name in TOOL_MODELS]  # type: ignore[list-item]


def _initial_agent_route() -> RouteDecision:
    return RouteDecision(
        intent="simple_chat",
        route="simple",
        selected_model=settings.ai_simple_model,
        confidence=0.9,
        complexity_score=0.1,
        reason="Frontline model decides whether to answer, call calendar tools, or delegate to the smarter model.",
        candidate_tools=_public_tool_names(FRONTLINE_TOOLS),
    )


def _confirmation_route(intent: CalendarIntentName) -> RouteDecision:
    return RouteDecision(
        intent=intent,
        route="simple",
        selected_model="backend",
        confidence=1.0,
        complexity_score=0.0,
        reason="Backend confirmation token handling.",
    )


def _intent_from_tool_names(tool_names: list[str]) -> CalendarIntentName:
    names = set(tool_names)
    if "optimize_schedule" in names or "detect_conflicts" in names:
        return "optimize_schedule"
    if "batch_delete_events" in names or "delete_event" in names:
        return "delete_event"
    if "batch_move_events" in names or "move_event" in names:
        return "move_event"
    if "edit_event" in names:
        return "update_event"
    if "duplicate_events" in names:
        return "duplicate_event"
    if "create_event" in names:
        return "generate_plan" if len([name for name in tool_names if name == "create_event"]) > 1 else "create_single_event"
    if names & {"fetch_events", "find_free_slots", "summarize_schedule", "parse_schedule_image"}:
        return "answer_question"
    return "simple_chat"


class _FallbackGraph:
    def __init__(self, orchestrator: "AssistantOrchestrator"):
        self.orchestrator = orchestrator

    async def ainvoke(self, state: AgentGraphState) -> AgentGraphState:
        state = await self.orchestrator._load_context_node(state)
        if self.orchestrator._confirmation_condition(state) == "confirm":
            state = await self.orchestrator._confirmation_node(state)
            return state
        state = await self.orchestrator._prepare_frontline_agent_node(state)
        state = await self.orchestrator._agent_node(state)
        while self.orchestrator._agent_condition(state) == "tools":
            state = await self.orchestrator._tools_node(state)
            state = await self.orchestrator._agent_node(state)
        state = await self.orchestrator._finalize_node(state)
        return state


class AssistantOrchestrator:
    def __init__(
        self,
        *,
        state_store: ConversationStateStore,
        memory_service: PlanningMemoryService,
        tool_registry: AssistantToolRegistry,
    ):
        self.state_store = state_store
        self.memory_service = memory_service
        self.registry = tool_registry
        self.graph = self._compile_graph()

    def _compile_graph(self):
        if StateGraph is None:
            return _FallbackGraph(self)

        graph = StateGraph(AgentGraphState)
        graph.add_node("load_context", self._load_context_node)
        graph.add_node("confirmation", self._confirmation_node)
        graph.add_node("prepare_frontline_agent", self._prepare_frontline_agent_node)
        graph.add_node("agent", self._agent_node)
        graph.add_node("tools", self._tools_node)
        graph.add_node("finalize", self._finalize_node)
        graph.add_edge(START, "load_context")
        graph.add_conditional_edges("load_context", self._confirmation_condition, {"confirm": "confirmation", "prepare": "prepare_frontline_agent"})
        graph.add_edge("confirmation", END)
        graph.add_edge("prepare_frontline_agent", "agent")
        graph.add_conditional_edges("agent", self._agent_condition, {"tools": "tools", "finalize": "finalize"})
        graph.add_edge("tools", "agent")
        graph.add_edge("finalize", END)
        return graph.compile()

    async def handle_message(
        self,
        *,
        payload: AssistantMessageRequest,
        user: User,
        db: AsyncSession,
    ) -> AssistantMessageResponse:
        session_id = payload.session_id or uuid.uuid4().hex
        initial: AgentGraphState = {
            "payload": payload,
            "user": user,
            "db": db,
            "session_id": session_id,
            "loop_count": 0,
        }
        final = await self.graph.ainvoke(initial)
        response = final.get("response")
        if response is None:
            raise RuntimeError("Assistant graph finished without a response")
        return response

    async def _load_context_node(self, state: AgentGraphState) -> AgentGraphState:
        payload = state["payload"]
        user = state["user"]
        session_id = state["session_id"]
        timezone = payload.timezone or getattr(user, "timezone", "UTC") or "UTC"
        tzinfo = _safe_zoneinfo(timezone)
        memory_response = await self.memory_service.get_memory(state.get("db"), user)
        memory_handler = AgentMemoryHandler(self.state_store, str(user.id), session_id)
        conversation_state = await self.state_store.load(user_id=str(user.id), session_id=session_id)
        state.update(
            {
                "user_id": str(user.id),
                "timezone": timezone,
                "now": datetime.now(tzinfo),
                "memory": memory_response.memory,
                "memory_handler": memory_handler,
                "history": await memory_handler.get_history(),
                "conversation_state": conversation_state,
                "planning_state": conversation_state.planning_state,
                "onboarding_profile": _compact_onboarding_profile(getattr(user, "onboarding_data", None)),
            }
        )
        return state

    def _confirmation_condition(self, state: AgentGraphState) -> str:
        payload = state["payload"]
        planning_state = state.get("planning_state") or {}
        has_pending = bool(planning_state.get("active") and planning_state.get("status") in {"active_unconfirmed", "awaiting_confirmation"})
        if payload.confirm or payload.confirmation_token or (has_pending and (_is_yes(payload.prompt) or _is_no(payload.prompt))):
            return "confirm"
        return "prepare"

    async def _confirmation_node(self, state: AgentGraphState) -> AgentGraphState:
        payload = state["payload"]
        planning_state = state.get("planning_state") or {}
        memory_handler = state["memory_handler"]
        await memory_handler.add_user_message(payload.prompt or "yes")

        route = _confirmation_route("reject_plan" if _is_no(payload.prompt) else "confirm_plan_to_calendar")
        if _is_no(payload.prompt):
            planning_state["active"] = False
            planning_state["status"] = "rejected"
            await self._save_planning_state(state, planning_state)
            reply = "Okay, I won't apply those calendar changes."
            await memory_handler.add_assistant_message(reply)
            state["response"] = self._response(
                state=state,
                reply=reply,
                route=route,
                status="completed",
                execution=PlanExecutionResult(status="completed"),
            )
            return state

        token = payload.confirmation_token
        pending_token = planning_state.get("pending_token")
        if not planning_state or not planning_state.get("tool_calls"):
            reply = "I don't have an active draft to apply."
            await memory_handler.add_assistant_message(reply)
            state["response"] = self._response(
                state=state,
                reply=reply,
                route=route,
                status="failed",
                execution=PlanExecutionResult(status="failed", error=reply),
            )
            return state
        if token and pending_token and token != pending_token:
            reply = "I found a newer draft and could not safely apply this older confirmation."
            await memory_handler.add_assistant_message(reply)
            state["response"] = self._response(
                state=state,
                reply=reply,
                route=route,
                status="failed",
                execution=PlanExecutionResult(status="failed", error=reply),
            )
            return state
        if planning_state.get("status") == "applied_to_calendar":
            reply = "This plan was already added."
            await memory_handler.add_assistant_message(reply)
            state["response"] = self._response(
                state=state,
                reply=reply,
                route=route,
                status="completed",
                execution=PlanExecutionResult(status="completed"),
            )
            return state

        results = []
        errors = []
        for raw_call in planning_state.get("tool_calls", []):
            call = ToolCallPlan.model_validate(raw_call)
            try:
                results.append(await self._execute_tool(state, call.name, call.args, force_dry_run=False))
            except Exception as exc:
                logger.warning("assistant.confirmation_tool_failed", exc_info=True)
                errors.append(f"{call.name}: {exc}")

        execution = self._execution_from_results(results, status="completed" if not errors else "failed", error="; ".join(errors[:3]) or None)
        if errors:
            planning_state["status"] = "failed"
            planning_state["active"] = False
            await self._save_planning_state(state, planning_state)
            reply = "I couldn't apply those changes cleanly."
        else:
            planning_state["status"] = "applied_to_calendar"
            planning_state["active"] = False
            await self._save_planning_state(state, planning_state)
            created_count = len(execution.created_events)
            updated_count = len(execution.updated_events)
            deleted_count = len(execution.deleted_events)
            parts = []
            if created_count:
                parts.append(f"created {created_count}")
            if updated_count:
                parts.append(f"updated {updated_count}")
            if deleted_count:
                parts.append(f"deleted {deleted_count}")
            reply = "Applied changes: " + ", ".join(parts) + "." if parts else "Applied the draft changes."

        await memory_handler.add_assistant_message(reply)
        state["response"] = self._response(
            state=state,
            reply=reply,
            route=route,
            status=execution.status,
            execution=execution,
        )
        return state

    async def _prepare_frontline_agent_node(self, state: AgentGraphState) -> AgentGraphState:
        payload = state["payload"]
        route = _initial_agent_route()
        state["route"] = route
        state["selected_tools"] = FRONTLINE_TOOLS
        state["messages"] = self._build_messages(state)
        await state["memory_handler"].add_user_message(payload.prompt)
        if _should_skip_frontline_for_planning(payload.prompt):
            result = await self._delegate_to_smarter_model(
                state,
                DelegateToSmarterModelInput(
                    task=payload.prompt,
                    reason="The user asked for period planning, so route directly to the planner model.",
                ),
            )
            state["delegated_to_smarter_model"] = True
            state["answer"] = result.answer
            state["planned_tool_calls"] = result.planned_tool_calls
            state["tool_results"] = [
                {
                    "tool": DELEGATE_TOOL,
                    "result": result,
                    "success": result.success,
                    **({"error": result.answer} if not result.success and result.answer else {}),
                }
            ]
            state["route"] = RouteDecision(
                intent=result.intent,
                route="complex",
                selected_model=result.selected_model,
                confidence=0.9,
                complexity_score=6.0,
                reason="Period planning was routed directly to the planner model.",
                candidate_tools=_public_tool_names(COMPLEX_TOOLS),
            )
        return state

    async def _agent_node(self, state: AgentGraphState) -> AgentGraphState:
        if state.get("response") is not None:
            return state
        if state.get("delegated_to_smarter_model"):
            return state

        if not self._can_call_llm():
            state.setdefault("tool_results", []).append(
                {
                    "tool": "model",
                    "error": "OpenAI API key is not configured; the LLM agent cannot run.",
                    "success": False,
                }
            )
            return state

        route = state["route"]
        tool_specs = _tool_specs(state["selected_tools"])
        try:  # pragma: no cover - requires optional packages and API key
            llm = _chat_model(route.selected_model)
            if llm is None:
                raise RuntimeError("OpenAI chat model is not available.")
            message = await llm.bind_tools(tool_specs).ainvoke(state["messages"])
        except Exception as exc:
            logger.warning("assistant.llm_failed", exc_info=True)
            state.setdefault("tool_results", []).append({"tool": "model", "error": str(exc), "success": False})
            return state

        state["messages"].append(self._message_to_dict(message))
        tool_calls = []
        for item in getattr(message, "tool_calls", []) or []:
            name = item.get("name")
            if name in ALL_TOOL_MODELS:
                tool_calls.append(ToolCallPlan(name=name, args=item.get("args") or {}, id=item.get("id")))  # type: ignore[arg-type]
        if tool_calls:
            state["tool_calls"] = tool_calls
            return state
        state["tool_calls"] = []
        state["answer"] = _extract_text(message) or "Done."
        return state

    def _agent_condition(self, state: AgentGraphState) -> str:
        if state.get("tool_calls") and state.get("loop_count", 0) < 4:
            return "tools"
        return "finalize"

    def _update_route_from_tool_calls(self, state: AgentGraphState, calls: list[ToolCallPlan]) -> None:
        if not calls:
            return
        names = [call.name for call in calls]
        mutating_count = sum(1 for name in names if name in MUTATING_TOOLS)
        if DELEGATE_TOOL in names:
            state["route"] = RouteDecision(
                intent="generate_plan",
                route="complex",
                selected_model=settings.ai_complex_model,
                confidence=0.9,
                complexity_score=6.0,
                reason="The frontline model chose to delegate this request to the smarter model.",
                candidate_tools=_public_tool_names(COMPLEX_TOOLS),
            )
            state["selected_tools"] = COMPLEX_TOOLS
            return
        intent = _intent_from_tool_names(names)
        is_complex = mutating_count > 1 or any(name in {"edit_event", "delete_event", "duplicate_events", "move_event", "batch_move_events", "batch_delete_events"} for name in names)
        state["route"] = RouteDecision(
            intent=intent,
            route="complex" if is_complex else "simple",
            selected_model=state["route"].selected_model,
            confidence=0.85,
            complexity_score=5.0 if is_complex else 0.5,
            reason="Routing metadata derived from tools selected by the model.",
            candidate_tools=_public_tool_names(tuple(names)),
        )

    async def _tools_node(self, state: AgentGraphState) -> AgentGraphState:
        calls = state.pop("tool_calls", [])
        state["tool_calls"] = []
        self._update_route_from_tool_calls(state, calls)
        route = state["route"]
        results = []
        mutating_count = sum(1 for call in calls if call.name in MUTATING_TOOLS)
        for call in calls:
            try:
                force_dry_run = call.name in MUTATING_TOOLS and (route.route == "complex" or mutating_count > 1)
                result = await self._execute_tool(state, call.name, call.args, force_dry_run=force_dry_run)
                if call.name == DELEGATE_TOOL and isinstance(result, SmartModelResult):
                    state["delegated_to_smarter_model"] = True
                    state["answer"] = result.answer
                    state["planned_tool_calls"] = result.planned_tool_calls
                    state["route"] = RouteDecision(
                        intent=result.intent,
                        route="complex",
                        selected_model=result.selected_model,
                        confidence=0.9,
                        complexity_score=6.0,
                        reason="The frontline model delegated this request to the smarter model.",
                        candidate_tools=_public_tool_names(COMPLEX_TOOLS),
                    )
                success = _result_success(result)
                record = {"tool": call.name, "result": result, "success": success}
                if not success and getattr(result, "answer", None):
                    record["error"] = str(result.answer)
                results.append(record)
                state["messages"].append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id or f"tool-{call.name}",
                        "name": call.name,
                        "content": _compact_tool_result(result, timezone=state["timezone"]),
                    }
                )
            except ValidationError as exc:
                error = _validation_error_message(call.name, exc)
                logger.info("assistant.tool_validation_failed", extra={"tool": call.name, "error": error})
                results.append({"tool": call.name, "error": error, "success": False})
                state["messages"].append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id or f"tool-{call.name}",
                        "name": call.name,
                        "content": error,
                    }
                )
            except ValueError as exc:
                if _is_duplicate_create_error(call.name, exc):
                    logger.info("assistant.duplicate_create_requires_confirmation", extra={"tool": call.name})
                    result, pending_call = self._duplicate_create_confirmation(state, call, exc)
                    state["planned_tool_calls"] = [pending_call]
                    state["route"] = RouteDecision(
                        intent="create_single_event",
                        route="complex",
                        selected_model=state["route"].selected_model,
                        confidence=0.9,
                        complexity_score=5.0,
                        reason="Creating an exact duplicate needs explicit confirmation.",
                        candidate_tools=["create_event"],
                    )
                    results.append({"tool": call.name, "result": result, "success": False})
                    state["messages"].append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id or f"tool-{call.name}",
                            "name": call.name,
                            "content": _compact_tool_result(result, timezone=state["timezone"]),
                        }
                    )
                    continue
                logger.info("assistant.tool_rejected", extra={"tool": call.name, "error": str(exc)})
                results.append({"tool": call.name, "error": str(exc), "success": False})
                state["messages"].append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id or f"tool-{call.name}",
                        "name": call.name,
                        "content": json.dumps({"error": str(exc)}),
                    }
                )
            except Exception as exc:
                logger.warning("assistant.tool_failed", exc_info=True)
                results.append({"tool": call.name, "error": str(exc), "success": False})
                state["messages"].append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id or f"tool-{call.name}",
                        "name": call.name,
                        "content": json.dumps({"error": str(exc)}),
                    }
                )
        state.setdefault("tool_results", []).extend(results)
        state["loop_count"] = state.get("loop_count", 0) + 1
        return state

    async def _finalize_node(self, state: AgentGraphState) -> AgentGraphState:
        if state.get("response") is not None:
            return state

        route = state["route"]
        results = [item["result"] for item in state.get("tool_results", []) if item.get("result") is not None]
        errors = [str(item["error"]) for item in state.get("tool_results", []) if item.get("error")]

        if route.route == "complex" and results:
            preview = []
            pending_calls = list(state.get("planned_tool_calls", []) or [])
            for item in state.get("tool_results", []):
                if item.get("result") is not None:
                    preview.extend(_preview_from_payload(item["result"]))
            pending_calls.extend(
                [
                    ToolCallPlan(name=item["tool"], args=self._undry_args(item["tool"], item["result"])).model_dump(mode="json")
                    for item in state.get("tool_results", [])
                    if item.get("success") and item.get("tool") in MUTATING_TOOLS
                ]
            )
            preview = _dedupe_preview(preview)
            pending_calls = _dedupe_tool_calls(pending_calls)
            if not pending_calls and route.intent == "optimize_schedule":
                pending_calls = await self._pending_moves_from_optimization(state, results)
                pending_calls = _dedupe_tool_calls(pending_calls)
            if pending_calls:
                token = uuid.uuid4().hex
                await self._save_pending(
                    state,
                    token=token,
                    route=route,
                    tool_calls=pending_calls,
                    preview=preview,
                )
                reply = self._preview_reply(route, preview)
                await state["memory_handler"].add_assistant_message(reply)
                state["response"] = self._response(
                    state=state,
                    reply=reply,
                    route=route,
                    status="awaiting_confirmation",
                    execution=PlanExecutionResult(status="awaiting_confirmation", preview=preview),
                    requires_confirmation=True,
                    confirmation_token=token,
                    display_actions=[DisplayAction(kind="ask_user", summary="Apply this draft after confirmation.")],
                )
                return state

        execution = self._execution_from_results(results, status="failed" if errors else "completed", error="; ".join(errors[:3]) or None)
        reply = self._reply_from_results(route, results, errors) if errors else state.get("answer") or self._reply_from_results(route, results, errors)
        await state["memory_handler"].add_assistant_message(reply)
        state["response"] = self._response(
            state=state,
            reply=reply,
            route=route,
            status=execution.status,
            execution=execution,
        )
        return state

    async def _delegate_to_smarter_model(self, state: AgentGraphState, request: DelegateToSmarterModelInput) -> SmartModelResult:
        if not self._can_call_llm():
            return SmartModelResult(
                success=False,
                answer="The smarter model is not configured.",
                selected_model=settings.ai_complex_model,
            )

        messages = self._build_smart_model_messages(state, request)
        tool_specs = _tool_specs(COMPLEX_TOOLS)
        tool_records: list[dict[str, Any]] = []
        answer = ""
        try:  # pragma: no cover - external model call is exercised with fakes in tests
            llm = _chat_model(settings.ai_complex_model)
            if llm is None:
                raise RuntimeError("OpenAI chat model is not available.")
            for _ in range(max(1, settings.assistant_smart_model_iterations)):
                message = await llm.bind_tools(tool_specs).ainvoke(messages)
                messages.append(self._message_to_dict(message))
                calls = [
                    ToolCallPlan(name=item.get("name"), args=item.get("args") or {}, id=item.get("id"))  # type: ignore[arg-type]
                    for item in getattr(message, "tool_calls", []) or []
                    if item.get("name") in TOOL_MODELS
                ]
                if not calls:
                    answer = _extract_text(message)
                    break
                for call in calls:
                    try:
                        result = await self._execute_tool(state, call.name, call.args, force_dry_run=call.name in MUTATING_TOOLS)
                        tool_records.append({"tool": call.name, "result": result, "success": _result_success(result)})
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.id or f"smart-tool-{call.name}",
                                "name": call.name,
                                "content": _compact_tool_result(result, timezone=state["timezone"]),
                            }
                        )
                    except Exception as exc:
                        tool_records.append({"tool": call.name, "error": str(exc), "success": False})
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.id or f"smart-tool-{call.name}",
                                "name": call.name,
                                "content": json.dumps({"error": str(exc)}),
                            }
                        )
        except Exception as exc:
            logger.warning("assistant.smarter_model_failed", exc_info=True)
            return SmartModelResult(
                success=False,
                answer=f"I couldn't reach the smarter model: {exc}",
                selected_model=settings.ai_complex_model,
            )

        results = [item["result"] for item in tool_records if item.get("result") is not None]
        tool_names = [item["tool"] for item in tool_records if item.get("tool")]
        preview: list[PlanPreviewChange] = []
        pending_calls: list[dict[str, Any]] = []
        for item in tool_records:
            result = item.get("result")
            if result is None:
                continue
            preview.extend(_preview_from_payload(result))
            if item.get("success") and item.get("tool") in MUTATING_TOOLS:
                pending_calls.append(ToolCallPlan(name=item["tool"], args=self._undry_args(item["tool"], result)).model_dump(mode="json"))
        preview = _dedupe_preview(preview)
        pending_calls = _dedupe_tool_calls(pending_calls)
        if not pending_calls and _intent_from_tool_names(tool_names) == "optimize_schedule":
            pending_calls = await self._pending_moves_from_optimization(state, results)
            pending_calls = _dedupe_tool_calls(pending_calls)

        errors = [str(item["error"]) for item in tool_records if item.get("error")]
        intent = _intent_from_tool_names(tool_names)
        if pending_calls and intent == "create_single_event":
            intent = "generate_plan"
        return SmartModelResult(
            success=not errors,
            answer=answer,
            intent=intent,
            selected_model=settings.ai_complex_model,
            preview=preview,
            planned_tool_calls=pending_calls,
        )

    def _build_smart_model_messages(self, state: AgentGraphState, request: DelegateToSmarterModelInput) -> list[dict[str, Any]]:
        memory = state["memory"]
        reason = f" Delegation reason: {request.reason}." if request.reason else ""
        onboarding = f"\n{state['onboarding_profile']}" if state.get("onboarding_profile") else ""
        system = (
            "You are the smarter planning and optimization model for replanme. "
            "Use calendar tools to inspect availability and draft changes. "
            "For every calendar mutation, call tools with dry_run=true; the backend will handle user confirmation before applying anything. "
            "Do not ask the user to confirm inside this model call. "
            "If a tool returns validation_error or says a required field is missing, ask the user for that detail instead of retrying the same tool with guessed values. "
            f"Current local time: {state['now'].isoformat()} ({state['timezone']}). "
            f"User memory: wake {memory.wake_time}, sleep {memory.sleep_time}, work {memory.workday_start}-{memory.workday_end}."
            f"{onboarding}"
            f"{reason}"
        )
        messages = [{"role": "system", "content": system}]
        for message in state.get("history", []):
            if message.get("role") in {"user", "assistant"} and not message.get("tool_calls"):
                messages.append({"role": message["role"], "content": str(message.get("content") or "")})
        messages.append({"role": "user", "content": request.task or state["payload"].prompt})
        return messages

    async def _execute_tool(self, state: AgentGraphState, tool_name: str, tool_args: dict[str, Any], *, force_dry_run: bool) -> Any:
        if tool_name == DELEGATE_TOOL:
            request = DelegateToSmarterModelInput.model_validate(tool_args)
            return await self._delegate_to_smarter_model(state, request)
        if tool_name not in TOOL_MODELS:
            raise ValueError(f"Unknown tool: {tool_name}")
        if tool_name == "parse_schedule_image":
            return self._parse_schedule_image(tool_args, state["payload"].attachments)
        validated = self._validate_tool_args(state, tool_name, tool_args, force_dry_run=force_dry_run)
        handler = getattr(self.registry, tool_name)
        return await handler(validated, user=state["user"], db=state.get("db"), memory=state["memory"])

    def _validate_tool_args(self, state: AgentGraphState, tool_name: str, tool_args: dict[str, Any], *, force_dry_run: bool) -> BaseModel:
        model = TOOL_MODELS[tool_name]
        args = dict(tool_args)
        if "timezone" in model.model_fields and not args.get("timezone"):
            args["timezone"] = state["timezone"]
        if force_dry_run and tool_name in MUTATING_TOOLS and "dry_run" in model.model_fields:
            args["dry_run"] = True
        validated = model.model_validate(args)
        return _localize_naive_datetimes(validated, _infer_tzinfo(validated) or _safe_zoneinfo(state["timezone"]))

    def _duplicate_create_confirmation(self, state: AgentGraphState, call: ToolCallPlan, exc: Exception) -> tuple[CreateEventResult, dict[str, Any]]:
        payload = self._validate_tool_args(state, "create_event", call.args, force_dry_run=True)
        assert isinstance(payload, CreateEventInput)
        preview_event = CalendarEventSnapshot(
            id="preview:create_event_duplicate",
            title=payload.title,
            description=payload.description,
            start_at=payload.start_at,
            end_at=payload.end_at,
            timezone=payload.timezone,
            location=payload.location,
            status="preview",
            html_link=None,
        )
        result = CreateEventResult(
            success=True,
            metadata=ToolExecutionMetadata(tool="create_event", executed=False, dry_run=True),
            created_events=[preview_event],
            preview=[
                PlanPreviewChange(
                    action="create_event",
                    title=payload.title,
                    details=str(exc),
                    proposed_start_at=payload.start_at,
                    proposed_end_at=payload.end_at,
                )
            ],
        )
        pending_args = payload.model_dump(mode="json")
        pending_args["dry_run"] = False
        pending_args["allow_duplicate"] = True
        return result, ToolCallPlan(name="create_event", args=pending_args).model_dump(mode="json")

    def _parse_schedule_image(self, tool_args: dict[str, Any], attachments: list[dict[str, Any]]) -> ParseScheduleImageResult:
        requested_id = tool_args.get("attachment_id")
        selected = None
        for attachment in attachments or []:
            if requested_id and attachment.get("id") != requested_id:
                continue
            if attachment.get("kind") == "image" or attachment.get("text_preview"):
                selected = attachment
                break
        if selected is None and attachments:
            selected = attachments[0]
        text = str((selected or {}).get("text_preview") or "").strip()
        lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
        subjects = [line for line in lines if re.search(r"\b(subject|class|course|lesson)\b", line, re.IGNORECASE)]
        topics = [line for line in lines if re.search(r"\b(topic|chapter|unit|module)\b", line, re.IGNORECASE)]
        structure = [
            line
            for line in lines
            if re.search(r"\b(mon|tue|wed|thu|fri|sat|sun|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", line, re.IGNORECASE)
            or re.search(r"\b\d{1,2}:\d{2}\b", line)
        ]
        return ParseScheduleImageResult(
            success=bool(text),
            metadata=ToolExecutionMetadata(tool="parse_schedule_image", executed=True),
            attachment_id=(selected or {}).get("id"),
            extracted_text=text[:1000],
            subjects=subjects[:10] or structure[:5],
            topics=topics[:20],
            schedule_structure=structure[:20],
        )

    def _execution_from_results(self, results: list[Any], *, status: str, error: str | None = None) -> PlanExecutionResult:
        preview: list[PlanPreviewChange] = []
        created: list[CalendarEventSnapshot] = []
        updated: list[CalendarEventSnapshot] = []
        deleted: list[CalendarEventSnapshot] = []
        logs: list[ExecutionLogEntry] = []
        for index, result in enumerate(results, start=1):
            tool = getattr(getattr(result, "metadata", None), "tool", "fetch_events")
            success = _result_success(result)
            logs.append(ExecutionLogEntry(step_id=f"step-{index}", tool=tool, success=success, details=_json_summary(result, max_chars=500)))  # type: ignore[arg-type]
            preview.extend(_preview_from_payload(result))
            created.extend(list(getattr(result, "created_events", []) or []))
            duplicated = list(getattr(result, "duplicated_events", []) or [])
            created.extend(duplicated)
            for key in ("updated_event", "moved_event"):
                value = getattr(result, key, None)
                if value is not None:
                    updated.append(value)
            updated.extend(list(getattr(result, "moved_events", []) or []))
            deleted.extend(list(getattr(result, "deleted_events", []) or []))
        return PlanExecutionResult(
            status=status,  # type: ignore[arg-type]
            executed_steps=len(results),
            preview=preview,
            logs=logs,
            rollback_available=bool(created or updated or deleted),
            error=error,
            created_events=created,
            updated_events=updated,
            deleted_events=deleted,
        )

    def _reply_from_results(self, route: RouteDecision, results: list[Any], errors: list[str]) -> str:
        if errors:
            return f"I couldn't complete that: {errors[0]}"
        if route.intent == "answer_question":
            events = []
            for result in results:
                events.extend(list(getattr(result, "events", []) or []))
            return _format_events(events)
        execution = self._execution_from_results(results, status="completed")
        if execution.created_events:
            return f"Added {len(execution.created_events)} event{'s' if len(execution.created_events) != 1 else ''}."
        if execution.updated_events:
            return f"Updated {len(execution.updated_events)} event{'s' if len(execution.updated_events) != 1 else ''}."
        if execution.deleted_events:
            return f"Deleted {len(execution.deleted_events)} event{'s' if len(execution.deleted_events) != 1 else ''}."
        return "Done."

    def _preview_reply(self, route: RouteDecision, preview: list[PlanPreviewChange]) -> str:
        if not preview:
            return "I drafted calendar changes. Should I apply them?"
        label = "plan" if route.intent == "generate_plan" else "calendar changes"
        lines = [f"I drafted this {label}:", ""]
        for item in preview[:8]:
            when = item.proposed_start_at.strftime("%Y-%m-%d %H:%M") if item.proposed_start_at else "pending time"
            lines.append(f"- {item.title}: {when}")
        lines.append("")
        lines.append("Should I apply these changes to your calendar?")
        return "\n".join(lines)

    async def _pending_moves_from_optimization(self, state: AgentGraphState, results: list[Any]) -> list[dict[str, Any]]:
        pending = []
        for result in results:
            for suggestion in list(getattr(result, "suggestions", []) or []):
                fetch = await self._execute_tool(
                    state,
                    "fetch_events",
                    {
                        "start_at": suggestion.current_start_at.isoformat(),
                        "end_at": (suggestion.current_start_at + timedelta(minutes=1)).isoformat(),
                        "query": suggestion.title,
                        "max_results": 5,
                    },
                    force_dry_run=False,
                )
                event = next((item for item in getattr(fetch, "events", []) if item.title == suggestion.title), None)
                if event:
                    pending.append(
                        ToolCallPlan(
                            name="move_event",
                            args={
                                "event_id": event.id,
                                "new_start_at": suggestion.suggested_start_at.isoformat(),
                                "new_end_at": suggestion.suggested_end_at.isoformat(),
                                "timezone": state["timezone"],
                                "dry_run": False,
                            },
                        ).model_dump(mode="json")
                    )
        return pending

    def _undry_args(self, tool_name: str, result: Any) -> dict[str, Any]:
        preview = _preview_from_payload(result)
        if tool_name == "create_event" and getattr(result, "created_events", None):
            event = result.created_events[0]
            return {
                "title": event.title,
                "description": event.description,
                "start_at": event.start_at.isoformat(),
                "end_at": event.end_at.isoformat(),
                "timezone": event.timezone,
                "location": event.location,
                "dry_run": False,
            }
        if tool_name == "delete_event" and getattr(result, "deleted_events", None):
            first = result.deleted_events[0]
            return {"event_id": first.id, "delete_all_matches": False, "dry_run": False}
        if preview:
            first = preview[0]
            if tool_name == "move_event":
                return {
                    "match_title": first.title,
                    "new_start_at": first.proposed_start_at.isoformat() if first.proposed_start_at else None,
                    "new_end_at": first.proposed_end_at.isoformat() if first.proposed_end_at else None,
                    "timezone": "UTC",
                    "dry_run": False,
                }
        return {"dry_run": False}

    async def _save_pending(
        self,
        state: AgentGraphState,
        *,
        token: str,
        route: RouteDecision,
        tool_calls: list[dict[str, Any]],
        preview: list[PlanPreviewChange],
    ) -> None:
        pending = {
            "active": True,
            "kind": "langgraph_tool_batch",
            "status": "active_unconfirmed",
            "pending_token": token,
            "intent": route.intent,
            "route": route.route,
            "selected_model": route.selected_model,
            "tool_calls": tool_calls or state.get("planned_tool_calls", []),
            "preview": [item.model_dump(mode="json") for item in preview],
            "created_at": datetime.now(UTC).isoformat(),
        }
        await self._save_planning_state(state, pending)

    async def _save_planning_state(self, state: AgentGraphState, planning_state: dict[str, Any]) -> None:
        conversation_state = await self.state_store.load(user_id=state["user_id"], session_id=state["session_id"])
        conversation_state.planning_state = planning_state
        await self.state_store.save(user_id=state["user_id"], session_id=state["session_id"], state=conversation_state)

    def _build_messages(self, state: AgentGraphState) -> list[dict[str, Any]]:
        memory = state["memory"]
        onboarding = f"\n{state['onboarding_profile']}" if state.get("onboarding_profile") else ""
        system = (
            "You are replanme's frontline calendar agent running on the cheap model. "
            "You decide whether to answer directly, call safe calendar tools, or call delegate_to_smarter_model. "
            "Use delegate_to_smarter_model for multi-step planning, optimization, conflict resolution, batch changes, destructive changes, "
            "or any request where deeper reasoning would make the result better. "
            "Safe single event creation and calendar search can be handled directly with tools. "
            "Never claim existing calendar events without calling a calendar read tool first. "
            "If a tool returns validation_error or says a required field is missing, ask the user for that detail instead of retrying the same tool with guessed values. "
            "If a tool reports a duplicate event, ask whether to keep both instead of retrying. "
            f"Current local time: {state['now'].isoformat()} ({state['timezone']}). "
            f"User memory: wake {memory.wake_time}, sleep {memory.sleep_time}, work {memory.workday_start}-{memory.workday_end}."
            f"{onboarding}"
        )
        messages = [{"role": "system", "content": system}]
        for message in state.get("history", []):
            if message.get("role") in {"user", "assistant"} and not message.get("tool_calls"):
                messages.append({"role": message["role"], "content": str(message.get("content") or "")})
        messages.append({"role": "user", "content": state["payload"].prompt})
        return messages

    def _message_to_dict(self, message: Any) -> dict[str, Any]:
        if hasattr(message, "model_dump"):
            return message.model_dump(exclude_none=True)
        return {"role": "assistant", "content": _extract_text(message)}

    def _response(
        self,
        *,
        state: AgentGraphState,
        reply: str,
        route: RouteDecision,
        status: str,
        execution: PlanExecutionResult,
        requires_confirmation: bool = False,
        confirmation_token: str | None = None,
        display_actions: list[DisplayAction] | None = None,
    ) -> AssistantMessageResponse:
        risk = "high" if requires_confirmation or route.route == "complex" and route.intent in {"delete_event", "move_event", "optimize_schedule"} else "low"
        return AssistantMessageResponse(
            session_id=state["session_id"],
            status=status,  # type: ignore[arg-type]
            reply=str(reply),
            routing=RoutingDecision(
                intent=_calendar_intent(route.intent),  # type: ignore[arg-type]
                route=route.route,
                selected_model=route.selected_model,
                confidence=route.confidence,
                complexity_score=route.complexity_score,
                use_calendar_context=bool(route.candidate_tools),
                use_memory=True,
                reason=route.reason,
                candidate_tools=route.candidate_tools,
                low_cost_path=route.selected_model == settings.ai_simple_model,
            ),
            plan=ExecutionPlan(
                goal=route.reason,
                summary=reply[:500],
                selected_model=route.selected_model,
                route=route.route,
                reasoning="LangGraph routed and executed this request.",
                steps=[],
                requires_confirmation=requires_confirmation,
                confirmation_reason="Complex or risky calendar changes need confirmation." if requires_confirmation else None,
                response_message=reply,
            ),
            safety=SafetyAssessment(
                requires_confirmation=requires_confirmation,
                risk_level=risk,  # type: ignore[arg-type]
                impacted_events=len(execution.preview),
            ),
            execution=execution,
            display_actions=display_actions or [],
            awaiting_confirmation=requires_confirmation,
            confirmation_token=confirmation_token,
            estimated_credit_cost=3.0 if route.route == "complex" else 0.1 if route.intent == "create_single_event" else 0.0,
            model_used=route.selected_model,
            complexity_score=route.complexity_score,
            memory=state["memory"],
        )

    def _can_call_llm(self) -> bool:
        return bool(settings.openai_api_key and ChatOpenAI is not None)
