"""Deterministic plan validation before display or calendar mutation."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time

from app.core.config import settings
from app.schemas.assistant import CalendarEventSnapshot, UserPlanningMemory
from app.services.assistant.planner import available_deadline_hours, infer_target_hours
from app.services.assistant.types import Constraint, Deadline, PlanValidationIssue, PlanValidationResult, RecurringTask, StructuredPlan


def _overlaps(left_start: datetime, left_end: datetime, right_start: datetime, right_end: datetime) -> bool:
    return left_start < right_end and right_start < left_end


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


def validate_plan(
    plan: StructuredPlan,
    *,
    fixed_events: list[CalendarEventSnapshot],
    deadlines: list[Deadline],
    constraints: list[Constraint],
    memory: UserPlanningMemory,
    intense_mode: bool = False,
    free_blocks: list | None = None,
    inferred_target_hours: float | None = None,
    recurring_tasks: list[RecurringTask] | None = None,
) -> PlanValidationResult:
    issues: list[PlanValidationIssue] = []
    parsed_sessions: list[tuple[datetime, datetime, str, str | None, str]] = []

    for session in plan.sessions:
        try:
            start = _parse(session.start)
            end = _parse(session.end)
        except Exception:
            issues.append(PlanValidationIssue(code="invalid_datetime", message="Session has invalid start or end.", session_title=session.title))
            continue
        if end <= start:
            issues.append(PlanValidationIssue(code="end_before_start", message="Session end must be after start.", session_title=session.title))
            continue
        parsed_sessions.append((start, end, session.type, session.deadline_related_to, session.title))

        if start.time() < memory.wake_time or end.time() > memory.sleep_time:
            issues.append(PlanValidationIssue(code="outside_waking_hours", message="Session is outside default waking hours.", session_title=session.title))

        for fixed in fixed_events:
            if _overlaps(start, end, fixed.start_at, fixed.end_at):
                issues.append(PlanValidationIssue(code="fixed_event_overlap", message=f"Session overlaps calendar event '{fixed.title}'.", session_title=session.title))

    ordered = sorted(parsed_sessions, key=lambda item: (item[0], item[1]))
    for index, left in enumerate(ordered):
        for right in ordered[index + 1:]:
            if right[0] >= left[1]:
                break
            if _overlaps(left[0], left[1], right[0], right[1]):
                issues.append(PlanValidationIssue(code="session_overlap", message=f"'{left[4]}' overlaps '{right[4]}'.", session_title=left[4]))

    deadline_by_title = {deadline.title.casefold(): _parse(deadline.due_at) for deadline in deadlines}
    covered_deadlines: set[str] = set()
    for start, end, session_type, related, title in parsed_sessions:
        if session_type != "study" or not related:
            continue
        deadline = deadline_by_title.get(related.casefold())
        if deadline and start < deadline:
            covered_deadlines.add(related.casefold())
        if deadline and start >= deadline:
            issues.append(PlanValidationIssue(code="after_deadline", message=f"Study session is after {related}.", session_title=title))

    scarce_free_time = False
    if deadlines and free_blocks is not None:
        window_days = 1
        if plan.planning_window.start and plan.planning_window.end:
            window_days = max(1, (_parse(plan.planning_window.end).date() - _parse(plan.planning_window.start).date()).days + 1)
        target_for_scarcity = inferred_target_hours or plan.inferred_target_hours or infer_target_hours(
            deadlines=deadlines,
            planning_window_start=plan.planning_window.start,
            planning_window_days=window_days,
        )
        scarce_free_time = available_deadline_hours(free_blocks=free_blocks, deadlines=deadlines) < target_for_scarcity

    for deadline in deadlines:
        if deadline.title.casefold() not in covered_deadlines and not scarce_free_time:
            issues.append(PlanValidationIssue(code="missing_deadline_coverage", message=f"No preparation session before {deadline.title}."))

    study_hours_by_day: dict[str, float] = defaultdict(float)
    for start, end, session_type, _, _ in parsed_sessions:
        if session_type == "study":
            study_hours_by_day[start.date().isoformat()] += (end - start).total_seconds() / 3600
    if not intense_mode:
        for day, hours in study_hours_by_day.items():
            if hours > settings.max_study_hours_per_day:
                issues.append(PlanValidationIssue(code="too_many_study_hours", message=f"{day} has {hours:.1f} study hours."))

    cooking_minutes = next((constraint.minutes_per_day for constraint in constraints if constraint.kind == "cooking"), None)
    if cooking_minutes:
        cooking_windows = [(time(hour=19), time(hour=min(23, 19 + max(1, (cooking_minutes - 60) // 60))))]
        if cooking_minutes >= 120:
            cooking_windows.insert(0, (time(hour=12, minute=30), time(hour=13, minute=30)))
        for start, end, _, _, title in parsed_sessions:
            for blocked_start, blocked_end in cooking_windows:
                if start.time() < blocked_end and end.time() > blocked_start:
                    issues.append(PlanValidationIssue(code="cooking_overlap", message="Session overlaps reserved cooking time.", session_title=title))

    if deadlines:
        window_days = 1
        if plan.planning_window.start and plan.planning_window.end:
            window_days = max(1, (_parse(plan.planning_window.end).date() - _parse(plan.planning_window.start).date()).days + 1)
        target = inferred_target_hours or plan.inferred_target_hours or infer_target_hours(
            deadlines=deadlines,
            planning_window_start=plan.planning_window.start,
            planning_window_days=window_days,
        )
        available = available_deadline_hours(free_blocks=free_blocks or [], deadlines=deadlines) if free_blocks is not None else target
        required = min(target, available) if available > 0 else target
        if plan.total_planned_hours + 0.5 < required:
            issues.append(
                PlanValidationIssue(
                    code="insufficient_hours",
                    message=f"Plan has {plan.total_planned_hours:.1f} hours; target is {target:.1f} hours.",
                )
            )
        if len(deadlines) > 1 and len({start.date().isoformat() for start, _, session_type, _, _ in parsed_sessions if session_type == "study"}) < 2 and required >= 3:
            issues.append(PlanValidationIssue(code="not_multi_day", message="Multi-exam plan should be spread across multiple days."))
        for start, end, session_type, _, title in parsed_sessions:
            if session_type == "study" and (end - start).total_seconds() / 3600 > 3:
                issues.append(PlanValidationIssue(code="session_too_long", message="Study session is too long without a break.", session_title=title))

    # --- Recurring task validation ---
    if recurring_tasks:
        import re as _re
        bad_title_patterns = [
            r'^I\s+have\b',
            r'^and\s+',
            r'^I\s+need\b',
        ]
        for session in plan.sessions:
            for pattern in bad_title_patterns:
                if _re.search(pattern, session.title, _re.IGNORECASE):
                    issues.append(PlanValidationIssue(
                        code="bad_title",
                        message=f"Session title '{session.title}' contains leftover user-message fragment.",
                        session_title=session.title,
                    ))
                    break

        # Build valid categories from the user request
        requested_categories = {t.category for t in recurring_tasks if t.category != "university"}
        session_types = {session.type for session in plan.sessions}

        for task in recurring_tasks:
            if task.category == "university":
                continue  # University classes handled separately

            if task.category == "gym":
                gym_count = sum(1 for s in plan.sessions if s.type == "gym")
                if task.count and gym_count < task.count:
                    issues.append(PlanValidationIssue(
                        code="missing_gym_sessions",
                        message=f"Plan has {gym_count} gym sessions but {task.count} were requested.",
                    ))

            elif task.category == "cooking":
                cooking_days = len({_parse(s.start).date().isoformat() for s in plan.sessions if s.type == "cooking"})
                window_days = 1
                if plan.planning_window.start and plan.planning_window.end:
                    window_days = max(1, (_parse(plan.planning_window.end).date() - _parse(plan.planning_window.start).date()).days + 1)
                if cooking_days < window_days - 1:  # allow 1 day tolerance
                    issues.append(PlanValidationIssue(
                        code="missing_cooking_days",
                        message=f"Cooking on {cooking_days}/{window_days} days; daily cooking was requested.",
                    ))

            elif task.category == "project" and task.total_minutes:
                project_minutes = sum(
                    int((_parse(s.end) - _parse(s.start)).total_seconds() / 60)
                    for s in plan.sessions
                    if s.type == "project"
                )
                if project_minutes < task.total_minutes * 0.8:  # 80% tolerance
                    issues.append(PlanValidationIssue(
                        code="insufficient_project_hours",
                        message=f"Project work has {project_minutes / 60:.1f}h but {task.total_minutes / 60:.0f}h were requested.",
                    ))

    return PlanValidationResult(valid=not issues, issues=issues)
