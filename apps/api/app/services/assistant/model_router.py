"""Configurable model routing and deterministic complexity scoring."""

from __future__ import annotations

from app.core.config import settings
from app.services.assistant.types import ComplexityInput, ModelSelection
from app.services.subscriptions import PlanName, get_user_plan


def calculate_planning_complexity(input: ComplexityInput) -> int:
    score = 0

    if input.intent == "generate_plan":
        score += 2
    if input.intent == "modify_existing_plan":
        score += 2
    if input.intent == "optimize_schedule":
        score += 4

    if input.planning_window_days > 3:
        score += 2
    if input.planning_window_days > 7:
        score += 3
    if input.planning_window_days > 14:
        score += 5

    if input.fixed_events_count > 5:
        score += 1
    if input.fixed_events_count > 10:
        score += 2
    if input.fixed_events_count > 20:
        score += 4

    if input.constraints_count > 3:
        score += 1
    if input.constraints_count > 6:
        score += 2
    if input.constraints_count > 10:
        score += 4

    if input.deadlines_count > 1:
        score += 1
    if input.deadlines_count > 3:
        score += 2

    if input.requires_energy_optimization:
        score += 3
    if input.requires_calendar_rewrite:
        score += 4
    if input.has_previous_plan_revision:
        score += 2

    return score


def deep_planning_allowed(user: object) -> bool:
    return bool(settings.enable_deep_planning and get_user_plan(user) == PlanName.PRO)


def select_planner_model(score: int, *, user: object) -> ModelSelection:
    allow_deep = deep_planning_allowed(user)
    if score <= settings.planner_default_threshold:
        return ModelSelection(
            model=settings.default_planner_model,
            tier="default",
            max_input_tokens=settings.planner_max_input_tokens,
            max_output_tokens=settings.planner_max_output_tokens,
            complexity_score=score,
            deep_planning_allowed=allow_deep,
        )
    if score <= settings.planner_hard_threshold:
        return ModelSelection(
            model=settings.hard_planner_model,
            tier="hard",
            max_input_tokens=settings.hard_planner_max_input_tokens,
            max_output_tokens=settings.hard_planner_max_output_tokens,
            complexity_score=score,
            deep_planning_allowed=allow_deep,
        )
    if allow_deep:
        return ModelSelection(
            model=settings.deep_planner_model,
            tier="deep",
            max_input_tokens=settings.deep_planner_max_input_tokens,
            max_output_tokens=settings.deep_planner_max_output_tokens,
            complexity_score=score,
            deep_planning_allowed=True,
        )
    return ModelSelection(
        model=settings.hard_planner_model,
        tier="hard",
        max_input_tokens=settings.hard_planner_max_input_tokens,
        max_output_tokens=settings.hard_planner_max_output_tokens,
        complexity_score=score,
        deep_planning_allowed=False,
        compact_planning=True,
    )

