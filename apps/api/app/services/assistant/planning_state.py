"""Persistent planning state helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from app.schemas.assistant import ConversationState
from app.services.assistant.state import ConversationStateStore
from app.services.assistant.types import (
    CompactCalendarEvent,
    Constraint,
    Deadline,
    FreeBlock,
    PlanningState,
    StructuredPlan,
)


async def load_planning_state(
    store: ConversationStateStore,
    *,
    user_id: str,
    session_id: str,
) -> PlanningState | None:
    state = await store.load(user_id=user_id, session_id=session_id)
    return PlanningState.model_validate(state.planning_state) if state.planning_state else None


async def save_planning_state(
    store: ConversationStateStore,
    *,
    user_id: str,
    session_id: str,
    planning_state: PlanningState,
) -> ConversationState:
    state = await store.load(user_id=user_id, session_id=session_id)
    state.planning_state = planning_state.model_dump(mode="json")
    await store.save(user_id=user_id, session_id=session_id, state=state)
    return state


def build_planning_state(
    *,
    goal: str,
    latest_user_request: str,
    latest_plan: StructuredPlan,
    deadlines: list[Deadline],
    constraints: list[Constraint],
    fixed_events_used: list[CompactCalendarEvent],
    free_blocks_used: list[FreeBlock],
    target_hours: float | None,
) -> PlanningState:
    return PlanningState(
        active=True,
        goal=goal,
        latest_user_request=latest_user_request,
        latest_assistant_plan_summary=latest_plan.summary,
        latest_plan=latest_plan,
        deadlines=deadlines,
        constraints=constraints,
        assumptions=latest_plan.assumptions,
        fixed_events_used=fixed_events_used,
        free_blocks_used=free_blocks_used,
        planning_window_start=latest_plan.planning_window.start,
        planning_window_end=latest_plan.planning_window.end,
        total_planned_hours=latest_plan.total_planned_hours,
        target_hours=target_hours,
        requires_confirmation=True,
        confirmed=False,
        created_calendar_event_ids=[],
        updated_at=datetime.now(UTC).isoformat(),
    )
