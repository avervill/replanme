"""Structured schemas for the multi-agent planning assistant."""

from __future__ import annotations

from datetime import datetime, time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

TaskComplexity = Literal["simple", "complex", "hybrid"]
CalendarIntent = Literal[
    "CREATE_EVENT",
    "DELETE_EVENT",
    "UPDATE_EVENT",
    "MOVE_EVENT",
    "DUPLICATE_EVENTS",
    "PLAN_PERIOD",
    "OPTIMIZE_SCHEDULE",
    "SEARCH_EVENTS",
    "CONFIRMATION_YES",
    "CONFIRMATION_NO",
    "CHAT",
    "UNKNOWN",
]
ToolName = Literal[
    "create_event",
    "edit_event",
    "delete_event",
    "duplicate_events",
    "fetch_events",
    "move_event",
    "find_free_slots",
    "summarize_schedule",
    "detect_conflicts",
    "optimize_schedule",
    "batch_move_events",
    "batch_delete_events",
    "parse_schedule_image",
]
ExecutionStatus = Literal[
    "preview",
    "awaiting_confirmation",
    "completed",
    "failed",
]
RiskLevel = Literal["low", "medium", "high", "critical"]
EnergyBand = Literal["low", "medium", "high"]
PendingActionStatus = Literal["draft", "awaiting_confirmation", "confirmed", "executed", "cancelled"]
PendingActionType = Literal[
    "create_event",
    "delete_event",
    "update_event",
    "move_event",
    "duplicate_events",
    "optimize_schedule",
    "search_events",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TimeWindow(StrictModel):
    start: time
    end: time
    label: str | None = None


class HabitPreference(StrictModel):
    title: str
    preferred_days: list[str] = Field(default_factory=list)
    preferred_band: EnergyBand = "medium"
    notes: str | None = None


class UserPlanningMemory(StrictModel):
    wake_time: time = time(hour=7, minute=30)
    sleep_time: time = time(hour=23, minute=30)
    workday_start: time = time(hour=9)
    workday_end: time = time(hour=18)
    focus_windows: list[TimeWindow] = Field(default_factory=list)
    avoid_windows: list[TimeWindow] = Field(default_factory=list)
    high_energy_windows: list[TimeWindow] = Field(default_factory=list)
    medium_energy_windows: list[TimeWindow] = Field(default_factory=list)
    low_energy_windows: list[TimeWindow] = Field(default_factory=list)
    recurring_habits: list[HabitPreference] = Field(default_factory=list)
    priorities: list[str] = Field(default_factory=list)
    task_categories: dict[str, str] = Field(default_factory=dict)
    scheduling_preferences: list[str] = Field(default_factory=list)
    preferred_break_minutes: int = Field(default=15, ge=5, le=120)
    max_focus_blocks_per_day: int = Field(default=3, ge=1, le=8)
    notes: list[str] = Field(default_factory=list)


class UserPlanningMemoryUpdate(StrictModel):
    wake_time: time | None = None
    sleep_time: time | None = None
    workday_start: time | None = None
    workday_end: time | None = None
    focus_windows: list[TimeWindow] | None = None
    avoid_windows: list[TimeWindow] | None = None
    high_energy_windows: list[TimeWindow] | None = None
    medium_energy_windows: list[TimeWindow] | None = None
    low_energy_windows: list[TimeWindow] | None = None
    recurring_habits: list[HabitPreference] | None = None
    priorities: list[str] | None = None
    task_categories: dict[str, str] | None = None
    scheduling_preferences: list[str] | None = None
    preferred_break_minutes: int | None = Field(default=None, ge=5, le=120)
    max_focus_blocks_per_day: int | None = Field(default=None, ge=1, le=8)
    notes: list[str] | None = None


class MemoryResponse(StrictModel):
    memory: UserPlanningMemory
    source: Literal["default", "stored", "updated"]


class CalendarEventSnapshot(StrictModel):
    id: str
    title: str
    description: str | None = None
    start_at: datetime
    end_at: datetime
    timezone: str = "UTC"
    location: str | None = None
    status: str = "confirmed"
    html_link: str | None = None


class ExtractedEntities(StrictModel):
    title: str | None = None
    date: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    source_date_range: str | None = None
    target_date_range: str | None = None
    recurrence: str | None = None
    participants: list[str] = Field(default_factory=list)
    location: str | None = None


class PendingActionFilters(StrictModel):
    title: str | None = None
    date: str | None = None
    time_range: str | None = None
    calendar_id: str | None = None


class PendingCalendarAction(StrictModel):
    id: str
    action: PendingActionType
    status: PendingActionStatus
    requires_confirmation: bool
    filters: PendingActionFilters | None = None
    target_event_ids: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class ConversationState(StrictModel):
    current_intent: CalendarIntent | None = None
    pending_action: PendingCalendarAction | None = None
    extracted_entities: ExtractedEntities | None = None
    last_assistant_question: str | None = None
    recently_referenced_events: list[CalendarEventSnapshot] = Field(default_factory=list)
    last_tool_result: dict[str, Any] | None = None
    awaiting_confirmation: bool = False
    confirmation_target: PendingCalendarAction | None = None
    session_id: str | None = None
    awaiting_selection: bool = False
    messages: list[dict[str, Any]] = Field(default_factory=list)
    # --- Advanced context tracking ---
    last_event_id: str | None = None
    last_event_title: str | None = None
    last_active_event_id: str | None = None
    user_constraints: list[str] = Field(default_factory=list)
    conflict_resolution_mode: bool = False
    planning_state: dict[str, Any] | None = None


class DisplayAction(StrictModel):
    kind: str
    summary: str


class CreateEventActionPayload(StrictModel):
    title: str
    start: str
    end: str | None = None
    duration_minutes: int | None = None
    location: str | None = None
    description: str | None = None


class DeleteEventActionPayload(StrictModel):
    event_ids: list[str]


class MoveEventActionPayload(StrictModel):
    event_id: str
    new_start: str
    new_end: str | None = None


class UpdateEventActionPayload(StrictModel):
    event_id: str
    title: str | None = None
    description: str | None = None
    start: str | None = None
    end: str | None = None
    timezone: str | None = None
    location: str | None = None
    reminders: list[int] | None = None
    metadata: dict[str, str] | None = None


class RangeValue(StrictModel):
    start: str
    end: str


class DuplicateEventsActionPayload(StrictModel):
    source_range: RangeValue
    target_range: RangeValue


class CreateEventAction(StrictModel):
    type: Literal["CREATE_EVENT"]
    payload: CreateEventActionPayload


class DeleteEventAction(StrictModel):
    type: Literal["DELETE_EVENT"]
    payload: DeleteEventActionPayload


class MoveEventAction(StrictModel):
    type: Literal["MOVE_EVENT"]
    payload: MoveEventActionPayload


class UpdateEventAction(StrictModel):
    type: Literal["UPDATE_EVENT"]
    payload: UpdateEventActionPayload


class DuplicateEventsAction(StrictModel):
    type: Literal["DUPLICATE_EVENTS"]
    payload: DuplicateEventsActionPayload


class ProposedCalendarEvent(StrictModel):
    title: str
    description: str | None = None
    start_at: datetime
    end_at: datetime
    timezone: str = "UTC"
    location: str | None = None


class FreeSlot(StrictModel):
    start_at: datetime
    end_at: datetime
    timezone: str
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    energy_band: EnergyBand = "medium"


class PlanPreviewChange(StrictModel):
    action: ToolName
    title: str
    details: str
    current_start_at: datetime | None = None
    proposed_start_at: datetime | None = None
    proposed_end_at: datetime | None = None


class RollbackOperation(StrictModel):
    action: Literal["create_event", "delete_event", "edit_event"]
    payload: dict[str, Any]


class ToolExecutionMetadata(StrictModel):
    tool: ToolName
    executed: bool = True
    dry_run: bool = False
    attempts: int = 1


class CreateEventInput(ProposedCalendarEvent):
    reminders: list[int] = Field(default_factory=lambda: [15])
    dry_run: bool = False
    allow_duplicate: bool = False


class CreateEventResult(StrictModel):
    success: bool
    metadata: ToolExecutionMetadata
    created_events: list[CalendarEventSnapshot] = Field(default_factory=list)
    preview: list[PlanPreviewChange] = Field(default_factory=list)
    rollback: list[RollbackOperation] = Field(default_factory=list)


class EditEventInput(StrictModel):
    event_id: str | None = None
    match_title: str | None = None
    title: str | None = None
    description: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    timezone: str | None = None
    location: str | None = None
    reminders: list[int] | None = None
    metadata: dict[str, str] | None = None
    dry_run: bool = False


class EditEventResult(StrictModel):
    success: bool
    metadata: ToolExecutionMetadata
    updated_event: CalendarEventSnapshot | None = None
    previous_event: CalendarEventSnapshot | None = None
    preview: list[PlanPreviewChange] = Field(default_factory=list)
    rollback: list[RollbackOperation] = Field(default_factory=list)


class DeleteEventInput(StrictModel):
    event_id: str | None = None
    match_title: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    delete_all_matches: bool = False
    dry_run: bool = False


class DeleteEventResult(StrictModel):
    success: bool
    metadata: ToolExecutionMetadata
    deleted_events: list[CalendarEventSnapshot] = Field(default_factory=list)
    preview: list[PlanPreviewChange] = Field(default_factory=list)
    rollback: list[RollbackOperation] = Field(default_factory=list)


class DuplicateEventsInput(StrictModel):
    source_start_at: datetime
    source_end_at: datetime
    target_start_at: datetime
    target_end_at: datetime | None = None
    title_contains: str | None = None
    move_to_evening_titles: list[str] = Field(default_factory=list)
    avoid_title_keywords: list[str] = Field(default_factory=list)
    dry_run: bool = False


class DuplicateEventsResult(StrictModel):
    success: bool
    metadata: ToolExecutionMetadata
    source_events: list[CalendarEventSnapshot] = Field(default_factory=list)
    duplicated_events: list[CalendarEventSnapshot] = Field(default_factory=list)
    preview: list[PlanPreviewChange] = Field(default_factory=list)
    rollback: list[RollbackOperation] = Field(default_factory=list)


class FetchEventsInput(StrictModel):
    start_at: datetime
    end_at: datetime
    query: str | None = None
    max_results: int = Field(default=250, ge=1, le=500)


class FetchEventsResult(StrictModel):
    success: bool
    metadata: ToolExecutionMetadata
    events: list[CalendarEventSnapshot] = Field(default_factory=list)
    count: int = 0


class MoveEventInput(StrictModel):
    event_id: str | None = None
    match_title: str | None = None
    new_start_at: datetime
    new_end_at: datetime | None = None
    timezone: str | None = None
    keep_duration: bool = True
    dry_run: bool = False


class MoveEventResult(StrictModel):
    success: bool
    metadata: ToolExecutionMetadata
    moved_event: CalendarEventSnapshot | None = None
    previous_event: CalendarEventSnapshot | None = None
    preview: list[PlanPreviewChange] = Field(default_factory=list)
    rollback: list[RollbackOperation] = Field(default_factory=list)


class FindFreeSlotsInput(StrictModel):
    start_at: datetime
    end_at: datetime
    slot_minutes: int = Field(default=60, ge=15, le=600)
    max_slots: int = Field(default=10, ge=1, le=30)
    preferred_band: EnergyBand | None = None
    working_hours_only: bool = True


class FindFreeSlotsResult(StrictModel):
    success: bool
    metadata: ToolExecutionMetadata
    slots: list[FreeSlot] = Field(default_factory=list)


class SummarizeScheduleInput(StrictModel):
    start_at: datetime
    end_at: datetime
    include_events: bool = False


class SummarizeScheduleResult(StrictModel):
    success: bool
    metadata: ToolExecutionMetadata
    summary: str
    busiest_day: str | None = None
    event_count: int = 0
    events: list[CalendarEventSnapshot] = Field(default_factory=list)


class ConflictItem(StrictModel):
    event_id: str | None = None
    title: str
    conflicting_event_id: str | None = None
    conflicting_with: str
    start_at: datetime
    end_at: datetime
    severity: RiskLevel = "medium"


class DetectConflictsInput(StrictModel):
    candidate_events: list[ProposedCalendarEvent] = Field(default_factory=list)
    start_at: datetime | None = None
    end_at: datetime | None = None


class DetectConflictsResult(StrictModel):
    success: bool
    metadata: ToolExecutionMetadata
    has_conflicts: bool
    conflicts: list[ConflictItem] = Field(default_factory=list)


class OptimizeScheduleInput(StrictModel):
    start_at: datetime
    end_at: datetime
    task_titles: list[str] = Field(default_factory=list)
    focus_only_titles: list[str] = Field(default_factory=list)
    preserve_meal_breaks: bool = True
    dry_run: bool = False


class BatchMoveEventsInput(StrictModel):
    """Move all events in a time range by an offset. Supports filtering by query."""
    start_at: datetime
    end_at: datetime
    offset_minutes: int = Field(description="Number of minutes to shift events. Positive = later, negative = earlier.")
    query: str | None = Field(default=None, description="Optional title filter to limit which events are moved.")
    dry_run: bool = False


class BatchMoveEventsResult(StrictModel):
    success: bool
    metadata: ToolExecutionMetadata
    moved_events: list[CalendarEventSnapshot] = Field(default_factory=list)
    count: int = 0
    preview: list[PlanPreviewChange] = Field(default_factory=list)
    rollback: list[RollbackOperation] = Field(default_factory=list)


class BatchDeleteEventsInput(StrictModel):
    """Delete all events in a time range. Supports filtering by query and time-of-day."""
    start_at: datetime
    end_at: datetime
    query: str | None = Field(default=None, description="Optional title filter to limit which events are deleted.")
    time_filter: str | None = Field(default=None, description="Optional time-of-day filter: 'morning', 'afternoon', 'evening'.")
    dry_run: bool = False


class BatchDeleteEventsResult(StrictModel):
    success: bool
    metadata: ToolExecutionMetadata
    deleted_events: list[CalendarEventSnapshot] = Field(default_factory=list)
    count: int = 0
    preview: list[PlanPreviewChange] = Field(default_factory=list)
    rollback: list[RollbackOperation] = Field(default_factory=list)


class ParseScheduleImageInput(StrictModel):
    attachment_id: str | None = None
    image_url: str | None = None


class ParseScheduleImageResult(StrictModel):
    success: bool
    metadata: ToolExecutionMetadata
    attachment_id: str | None = None
    extracted_text: str = ""
    subjects: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    schedule_structure: list[str] = Field(default_factory=list)


class OptimizationSuggestion(StrictModel):
    title: str
    current_start_at: datetime
    suggested_start_at: datetime
    suggested_end_at: datetime
    reason: str


class OptimizeScheduleResult(StrictModel):
    success: bool
    metadata: ToolExecutionMetadata
    suggestions: list[OptimizationSuggestion] = Field(default_factory=list)
    preview: list[PlanPreviewChange] = Field(default_factory=list)


class RoutingDecision(StrictModel):
    intent: CalendarIntent = "UNKNOWN"
    route: TaskComplexity
    selected_model: str
    confidence: float = Field(ge=0.0, le=1.0)
    complexity_score: float = Field(ge=0.0)
    use_calendar_context: bool = False
    use_memory: bool = True
    reason: str
    candidate_tools: list[ToolName] = Field(default_factory=list)
    low_cost_path: bool = False


class SimpleOperationBlueprint(StrictModel):
    route: Literal["simple"]
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    response_message: str
    requires_confirmation: bool = False
    clarification_question: str | None = None
    steps: list["PlanStep"] = Field(default_factory=list)


class MemoryWriteback(StrictModel):
    note: str
    update: UserPlanningMemoryUpdate


class PlanStep(StrictModel):
    id: str
    action: ToolName
    purpose: str
    payload: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    allow_failure: bool = False


class ExecutionPlan(StrictModel):
    goal: str
    summary: str
    selected_model: str
    route: TaskComplexity
    reasoning: str
    steps: list[PlanStep] = Field(default_factory=list)
    requires_confirmation: bool = False
    confirmation_reason: str | None = None
    memory_writebacks: list[MemoryWriteback] = Field(default_factory=list)
    response_message: str


class SafetyAssessment(StrictModel):
    requires_confirmation: bool
    risk_level: RiskLevel
    reasons: list[str] = Field(default_factory=list)
    impacted_events: int = 0


class ExecutionLogEntry(StrictModel):
    step_id: str
    tool: ToolName
    success: bool
    details: str


class PlanExecutionResult(StrictModel):
    status: ExecutionStatus
    executed_steps: int = 0
    preview: list[PlanPreviewChange] = Field(default_factory=list)
    logs: list[ExecutionLogEntry] = Field(default_factory=list)
    rollback_performed: bool = False
    rollback_available: bool = False
    error: str | None = None
    created_events: list[CalendarEventSnapshot] = Field(default_factory=list)
    updated_events: list[CalendarEventSnapshot] = Field(default_factory=list)
    deleted_events: list[CalendarEventSnapshot] = Field(default_factory=list)


class AssistantMessageRequest(StrictModel):
    prompt: str = ""
    timezone: str = "UTC"
    session_id: str | None = None
    preview: bool = True
    dry_run: bool = False
    confirm: bool = False
    confirmation_token: str | None = None
    attachments: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_prompt_requirements(self) -> "AssistantMessageRequest":
        if self.confirm and not self.confirmation_token:
            raise ValueError("confirmation_token is required when confirm=true")
        # Accept all short replies (yes/no/ok/later/move it/etc.) for natural follow-ups
        if not self.confirm and not self.prompt.strip():
            raise ValueError("prompt must not be empty")
        return self


class AssistantMessageResponse(StrictModel):
    session_id: str
    status: ExecutionStatus
    reply: str
    routing: RoutingDecision
    plan: ExecutionPlan
    safety: SafetyAssessment
    execution: PlanExecutionResult
    display_actions: list[DisplayAction] = Field(default_factory=list)
    referenced_events: list[CalendarEventSnapshot] = Field(default_factory=list)
    awaiting_confirmation: bool = False
    confirmation_token: str | None = None
    estimated_credit_cost: float = 0.0
    model_used: str | None = None
    complexity_score: float = 0.0
    credits: dict[str, int] | None = None
    memory: UserPlanningMemory


class RouterLLMDecision(StrictModel):
    route: TaskComplexity
    confidence: float = Field(ge=0.0, le=1.0)
    complexity_score: float = Field(ge=0.0)
    reason: str
    use_calendar_context: bool = False
    use_memory: bool = True
    candidate_tools: list[ToolName] = Field(default_factory=list)


class PlannerLLMOutput(StrictModel):
    goal: str
    summary: str
    reasoning: str
    steps: list[PlanStep] = Field(default_factory=list)
    requires_confirmation: bool = False
    confirmation_reason: str | None = None
    response_message: str
    memory_writebacks: list[MemoryWriteback] = Field(default_factory=list)


class ResponseFormattingPayload(StrictModel):
    reply: str


SimpleOperationBlueprint.model_rebuild()
