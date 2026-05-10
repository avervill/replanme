"""Typed planning orchestration models.

These are deliberately compact. They are safe to persist in conversation state
and safe to send to planner models after calendar preprocessing.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictPlanningModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


AssistantIntent = Literal[
    "simple_chat",
    "create_single_event",
    "delete_event",
    "update_event",
    "move_event",
    "duplicate_event",
    "duplicate_period",
    "generate_plan",
    "modify_existing_plan",
    "optimize_schedule",
    "confirm_plan_to_calendar",
    "reject_plan",
    "ask_clarification",
    "answer_question",
]

PlanningIntent = Literal["generate_plan", "modify_existing_plan", "optimize_schedule"]
PlanSessionType = Literal["study", "work", "gym", "break", "cooking", "project", "admin", "other"]
PlanPriority = Literal["low", "medium", "high"]
PlanningScope = Literal["whole_week", "whole_month", "single_day", "custom"]
PlanStatus = Literal["draft", "active_unconfirmed", "superseded", "rejected", "confirmed", "applied_to_calendar", "cancelled"]


class IntentClassification(StrictPlanningModel):
    intent: AssistantIntent
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    is_calendar_mutation: bool = False
    requires_planning: bool = False
    requires_calendar_read: bool = False
    requires_user_confirmation: bool = False
    complexity_hint: Literal["low", "medium", "high", "deep"] = "low"
    planning_scope: PlanningScope | None = None
    reason: str = ""


class Deadline(StrictPlanningModel):
    title: str
    due_at: str
    kind: str = "deadline"


class Constraint(StrictPlanningModel):
    kind: str
    value: str
    minutes_per_day: int | None = None


class RecurringTask(StrictPlanningModel):
    """A general recurring task extracted from the user's request (gym, cooking, project work, etc.)."""
    name: str
    category: Literal["gym", "cooking", "project", "study", "university", "other"] = "other"
    frequency: Literal["daily", "weekly", "total"] = "weekly"
    count: int | None = None       # e.g. gym 3 times → count=3
    duration_minutes: int = 60     # per session
    total_minutes: int | None = None  # for "total" frequency, e.g. 10 hours ML project = 600


class CompactCalendarEvent(StrictPlanningModel):
    id: str
    title: str
    start: str
    end: str
    timezone: str = "UTC"


class FreeBlock(StrictPlanningModel):
    start: str
    end: str
    minutes: int
    energy_band: Literal["low", "medium", "high"] = "medium"


class PlanSession(StrictPlanningModel):
    title: str
    subject: str | None = None
    description: str = ""
    start: str
    end: str
    type: PlanSessionType = "other"
    priority: PlanPriority = "medium"
    deadline_related_to: str | None = None
    reason_short: str = ""

    @field_validator("start", "end")
    @classmethod
    def validate_datetime(cls, value: str) -> str:
        datetime.fromisoformat(value)
        return value


class PlanningWindow(StrictPlanningModel):
    start: str
    end: str


class StructuredPlan(StrictPlanningModel):
    plan_id: str
    status: PlanStatus = "active_unconfirmed"
    version: int = 1
    supersedes_plan_id: str | None = None
    created_at: str = ""
    intent: PlanningIntent
    summary: str
    planning_window: PlanningWindow
    sessions: list[PlanSession] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    total_planned_hours: float = 0.0
    inferred_target_hours: float | None = None
    requires_user_confirmation: bool = True
    calendar_actions: list[dict[str, Any]] = Field(default_factory=list)


class PlanningState(StrictPlanningModel):
    active: bool = False
    goal: str = ""
    latest_user_request: str = ""
    latest_assistant_plan_summary: str = ""
    latest_plan: StructuredPlan | None = None
    deadlines: list[Deadline] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    fixed_events_used: list[CompactCalendarEvent] = Field(default_factory=list)
    free_blocks_used: list[FreeBlock] = Field(default_factory=list)
    planning_window_start: str = ""
    planning_window_end: str = ""
    total_planned_hours: float | None = None
    target_hours: float | None = None
    requires_confirmation: bool = True
    confirmed: bool = False
    created_calendar_event_ids: list[str] = Field(default_factory=list)
    updated_at: str = ""


class ExtractedPlanningContext(StrictPlanningModel):
    deadlines: list[Deadline] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    recurring_tasks: list[RecurringTask] = Field(default_factory=list)
    planning_window_start: str | None = None
    planning_window_end: str | None = None
    planning_window_days: int = 1
    target_hours: float | None = None
    requires_energy_optimization: bool = False
    requires_calendar_rewrite: bool = False
    deadlines_count: int = 0
    constraints_count: int = 0


class ComplexityInput(StrictPlanningModel):
    intent: AssistantIntent
    planning_window_days: int = 1
    fixed_events_count: int = 0
    constraints_count: int = 0
    deadlines_count: int = 0
    requires_energy_optimization: bool = False
    requires_calendar_rewrite: bool = False
    has_previous_plan_revision: bool = False


class ModelSelection(StrictPlanningModel):
    model: str
    tier: Literal["default", "hard", "deep"]
    max_input_tokens: int
    max_output_tokens: int
    complexity_score: int
    deep_planning_allowed: bool
    compact_planning: bool = False


class CreditEstimate(StrictPlanningModel):
    estimated_credit_cost: float
    model_used: str
    complexity_score: int
    reason: str


class PlanValidationIssue(StrictPlanningModel):
    code: str
    message: str
    session_title: str | None = None


class PlanValidationResult(StrictPlanningModel):
    valid: bool
    issues: list[PlanValidationIssue] = Field(default_factory=list)


class CriticEvaluation(StrictPlanningModel):
    approved: bool
    score: float = Field(ge=0.0, le=10.0)
    main_reason: str
    problems: list[str] = Field(default_factory=list)
    repair_instructions: list[str] = Field(default_factory=list)
    user_satisfaction_risk: Literal["low", "medium", "high"] = "medium"
