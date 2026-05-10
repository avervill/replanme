"""Structured planner model wrapper with deterministic fallback."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings
from app.llm.openai_params import completion_token_param
from app.services.assistant.cost_estimator import log_model_cost
from app.services.assistant.types import (
    Deadline,
    ExtractedPlanningContext,
    FreeBlock,
    IntentClassification,
    ModelSelection,
    PlanSession,
    PlanningState,
    PlanningWindow,
    RecurringTask,
    StructuredPlan,
)


def _hours(start: datetime, end: datetime) -> float:
    return round((end - start).total_seconds() / 3600, 2)


def _clean_session_title(raw: str) -> str:
    """Strip leftover user-message fragments from generated session titles."""
    import re as _re
    cleaned = _re.sub(r'^(I\s+have|and|I\s+need\s+to|I\s+need|I\s+want\s+to|I\s+want)\s+', '', raw, flags=_re.IGNORECASE)
    cleaned = _re.sub(r'\s+preparation$', '', cleaned, flags=_re.IGNORECASE)
    cleaned = cleaned.strip(' ,.')
    if not cleaned:
        return raw.strip()
    return cleaned[0].upper() + cleaned[1:] if cleaned else raw


def _block_bounds(block: FreeBlock) -> tuple[datetime, datetime]:
    return datetime.fromisoformat(block.start), datetime.fromisoformat(block.end)


def infer_target_hours(*, deadlines: list[Deadline], planning_window_start: str | None, planning_window_days: int) -> float:
    if not deadlines:
        return 10.0 if planning_window_days >= 7 else 4.0
    if len(deadlines) >= 3:
        return 18.0
    if len(deadlines) == 2:
        return 12.0

    first_due = datetime.fromisoformat(deadlines[0].due_at)
    if planning_window_start:
        start = datetime.fromisoformat(planning_window_start)
        days_until = max(1, (first_due.date() - start.date()).days + 1)
    else:
        days_until = planning_window_days
    if days_until <= 2:
        return 5.0
    if days_until <= 5:
        return 8.0
    return 6.0


def available_deadline_hours(*, free_blocks: list[FreeBlock], deadlines: list[Deadline]) -> float:
    if not deadlines:
        return round(sum(block.minutes for block in free_blocks) / 60, 2)
    latest_due = max(datetime.fromisoformat(deadline.due_at) for deadline in deadlines)
    return round(
        sum(block.minutes for block in free_blocks if datetime.fromisoformat(block.start) < latest_due) / 60,
        2,
    )


def _make_session(
    *,
    title: str,
    start: datetime,
    end: datetime,
    kind: str,
    related: str | None,
    reason: str,
) -> PlanSession:
    return PlanSession(
        title=title,
        subject=related,
        description=reason,
        start=start.isoformat(),
        end=end.isoformat(),
        type=kind,  # type: ignore[arg-type]
        priority="high" if kind == "study" else "medium",
        deadline_related_to=related,
        reason_short=reason,
    )


def _schedule_recurring_tasks(
    *,
    recurring_tasks: list[RecurringTask],
    free_blocks: list[FreeBlock],
    used_blocks: list[tuple[datetime, datetime]],
    planned_minutes_by_day: dict[str, int],
    planning_window_start: str,
    planning_window_end: str,
) -> list[PlanSession]:
    """Schedule general recurring tasks (gym, cooking, project) across free blocks."""
    sessions: list[PlanSession] = []
    w_start = datetime.fromisoformat(planning_window_start)
    w_end = datetime.fromisoformat(planning_window_end)
    num_days = max(1, (w_end.date() - w_start.date()).days + 1)

    def _is_free(start: datetime, end: datetime) -> bool:
        return not any(start < b_end and b_start < end for b_start, b_end in used_blocks)

    def _find_slot(target_day: datetime, duration_min: int, preferred_hour: int = 9, max_hour: int = 21) -> tuple[datetime, datetime] | None:
        """Find a free slot on a specific day."""
        day_blocks = [
            b for b in free_blocks
            if datetime.fromisoformat(b.start).date() == target_day.date()
            and b.minutes >= duration_min
        ]
        day_blocks.sort(key=lambda b: abs(datetime.fromisoformat(b.start).hour - preferred_hour))
        for block in day_blocks:
            bs, be = _block_bounds(block)
            cursor = bs
            while cursor + timedelta(minutes=duration_min) <= be:
                end = cursor + timedelta(minutes=duration_min)
                if _is_free(cursor, end) and cursor.hour >= 7 and end.hour <= max_hour:
                    return cursor, end
                cursor += timedelta(minutes=30)
        return None

    # Distribute days for the planning window
    all_days = [w_start + timedelta(days=i) for i in range(num_days)]

    for task in recurring_tasks:
        if task.category == "university":
            # University classes: don't schedule, they come from calendar as fixed events
            continue

        if task.category == "gym":
            count = task.count or 3
            # Spread gym across different days, prefer Mon/Wed/Fri or Tue/Thu/Sat
            gym_days = []
            if count <= len(all_days):
                step = max(1, len(all_days) // count)
                for i in range(count):
                    idx = min(i * step, len(all_days) - 1)
                    gym_days.append(all_days[idx])
            else:
                gym_days = all_days[:count]

            for day in gym_days:
                slot = _find_slot(day, task.duration_minutes, preferred_hour=8, max_hour=20)
                if slot:
                    start, end = slot
                    sessions.append(_make_session(
                        title=_clean_session_title(task.name),
                        start=start, end=end,
                        kind="gym", related=None,
                        reason="Gym session as requested.",
                    ))
                    used_blocks.append((start, end))
                    day_key = start.date().isoformat()
                    planned_minutes_by_day[day_key] = planned_minutes_by_day.get(day_key, 0) + task.duration_minutes

        elif task.category == "cooking":
            # Schedule cooking every day, prefer evening 19:00-21:00
            for day in all_days:
                slot = _find_slot(day, task.duration_minutes, preferred_hour=19, max_hour=22)
                if slot:
                    start, end = slot
                    sessions.append(_make_session(
                        title=_clean_session_title(task.name),
                        start=start, end=end,
                        kind="cooking", related=None,
                        reason="Daily cooking time.",
                    ))
                    used_blocks.append((start, end))
                    day_key = start.date().isoformat()
                    planned_minutes_by_day[day_key] = planned_minutes_by_day.get(day_key, 0) + task.duration_minutes

        elif task.category == "project" and task.total_minutes:
            # Distribute project work in 90-120 min chunks across free blocks
            remaining = task.total_minutes
            session_dur = task.duration_minutes
            # Spread across days
            blocks_sorted = sorted(
                [b for b in free_blocks if b.minutes >= 60],
                key=lambda b: (datetime.fromisoformat(b.start).date(), datetime.fromisoformat(b.start).hour),
            )
            for block in blocks_sorted:
                if remaining <= 0:
                    break
                bs, be = _block_bounds(block)
                cursor = bs
                while cursor + timedelta(minutes=60) <= be and remaining > 0:
                    dur = min(session_dur, remaining, int((be - cursor).total_seconds() // 60))
                    if dur < 45:
                        break
                    end = cursor + timedelta(minutes=dur)
                    if _is_free(cursor, end):
                        sessions.append(_make_session(
                            title=_clean_session_title(task.name),
                            start=cursor, end=end,
                            kind="project", related=None,
                            reason=f"{task.name} — focused work block.",
                        ))
                        used_blocks.append((cursor, end))
                        day_key = cursor.date().isoformat()
                        planned_minutes_by_day[day_key] = planned_minutes_by_day.get(day_key, 0) + dur
                        remaining -= dur
                        cursor = end + timedelta(minutes=15)
                    else:
                        cursor += timedelta(minutes=30)

        else:
            # Generic recurring task
            count = task.count or 1
            for i in range(min(count, len(all_days))):
                day = all_days[i % len(all_days)]
                slot = _find_slot(day, task.duration_minutes)
                if slot:
                    start, end = slot
                    sessions.append(_make_session(
                        title=_clean_session_title(task.name),
                        start=start, end=end,
                        kind="other", related=None,
                        reason=f"{task.name} as requested.",
                    ))
                    used_blocks.append((start, end))
                    day_key = start.date().isoformat()
                    planned_minutes_by_day[day_key] = planned_minutes_by_day.get(day_key, 0) + task.duration_minutes

    return sessions


def deterministic_plan(
    *,
    prompt: str,
    classification: IntentClassification,
    extracted: ExtractedPlanningContext,
    free_blocks: list[FreeBlock],
    previous_state: PlanningState | None,
) -> StructuredPlan:
    sessions: list[PlanSession] = []
    target_hours = extracted.target_hours
    has_recurring_tasks = bool(extracted.recurring_tasks and any(t.category != "university" for t in extracted.recurring_tasks))

    if target_hours is None:
        if has_recurring_tasks:
            # Calculate target from recurring tasks
            total = 0.0
            for t in extracted.recurring_tasks:
                if t.total_minutes:
                    total += t.total_minutes / 60
                elif t.count and t.category != "university":
                    total += (t.count * t.duration_minutes) / 60
            target_hours = max(total, 4.0)
        else:
            target_hours = infer_target_hours(
                deadlines=extracted.deadlines,
                planning_window_start=extracted.planning_window_start,
                planning_window_days=extracted.planning_window_days,
            )

    if classification.intent == "modify_existing_plan" and previous_state and previous_state.total_planned_hours:
        target_hours = max(target_hours, previous_state.total_planned_hours + 3.0)

    available_hours = available_deadline_hours(free_blocks=free_blocks, deadlines=extracted.deadlines)
    effective_target_hours = min(target_hours, available_hours) if available_hours > 0 else target_hours
    deadlines = sorted(extracted.deadlines, key=lambda deadline: deadline.due_at)
    remaining_minutes = int(effective_target_hours * 60) + (60 if deadlines and available_hours >= target_hours else 0)
    used_blocks: list[tuple[datetime, datetime]] = []
    planned_minutes_by_day: dict[str, int] = {}

    def add_study_sessions(deadline: Deadline, minutes: int, *, earliest: datetime | None = None, latest: datetime | None = None, reason: str | None = None) -> int:
        due = datetime.fromisoformat(deadline.due_at)
        latest = latest or due
        remaining = minutes
        eligible = [
            block
            for block in free_blocks
            if datetime.fromisoformat(block.start) < latest
            and (earliest is None or datetime.fromisoformat(block.end) > earliest)
            and block.minutes >= 45
        ]
        eligible.sort(key=lambda block: (datetime.fromisoformat(block.start).date(), datetime.fromisoformat(block.start).hour, -block.minutes))
        for block in eligible:
            if remaining <= 0:
                break
            block_start, block_end = _block_bounds(block)
            cursor = max(block_start, earliest) if earliest else block_start
            while cursor + timedelta(minutes=45) <= min(block_end, latest) and remaining > 0:
                duration = min(120, remaining, int((min(block_end, latest) - cursor).total_seconds() // 60))
                if duration < 45:
                    break
                day_key = cursor.date().isoformat()
                day_remaining = 240 - planned_minutes_by_day.get(day_key, 0)
                if day_remaining < 45:
                    break
                duration = min(duration, day_remaining)
                end = cursor + timedelta(minutes=duration)
                if any(cursor < busy_end and busy_start < end for busy_start, busy_end in used_blocks):
                    cursor += timedelta(minutes=30)
                    continue
                sessions.append(
                    _make_session(
                        title=_clean_session_title(f"{deadline.title} preparation"),
                        start=cursor,
                        end=end,
                        kind="study",
                        related=deadline.title,
                        reason=reason or f"Prepare before {deadline.title}.",
                    )
                )
                used_blocks.append((cursor, end))
                planned_minutes_by_day[day_key] = planned_minutes_by_day.get(day_key, 0) + duration
                remaining -= duration
                cursor = end + timedelta(minutes=15)
        return minutes - remaining

    if deadlines:
        if effective_target_hours < 3:
            add_study_sessions(deadlines[0], remaining_minutes, latest=datetime.fromisoformat(deadlines[0].due_at), reason="Best available preparation time before the nearest final.")
        elif len(deadlines) >= 2:
            first, second = deadlines[0], deadlines[1]
            first_due = datetime.fromisoformat(first.due_at)
            first_quota = int(remaining_minutes * 0.55)
            second_quota = remaining_minutes - first_quota
            pre_second = min(120, max(60, int(second_quota * 0.25)))
            used = add_study_sessions(first, first_quota, latest=first_due, reason=f"High priority before {first.title}.")
            used += add_study_sessions(second, pre_second, latest=first_due, reason=f"Secondary early start before {second.title}.")
            used += add_study_sessions(second, second_quota - pre_second, earliest=first_due, latest=datetime.fromisoformat(second.due_at), reason=f"Main review before {second.title}.")
            for extra in deadlines[2:]:
                used += add_study_sessions(extra, max(90, (remaining_minutes - used) // max(1, len(deadlines) - 2)), latest=datetime.fromisoformat(extra.due_at))
        else:
            add_study_sessions(deadlines[0], remaining_minutes, latest=datetime.fromisoformat(deadlines[0].due_at), reason=f"Prepare before {deadlines[0].title}.")

    # --- Schedule recurring tasks ---
    if extracted.recurring_tasks:
        recurring_sessions = _schedule_recurring_tasks(
            recurring_tasks=extracted.recurring_tasks,
            free_blocks=free_blocks,
            used_blocks=used_blocks,
            planned_minutes_by_day=planned_minutes_by_day,
            planning_window_start=extracted.planning_window_start or datetime.now().isoformat(),
            planning_window_end=extracted.planning_window_end or (datetime.now() + timedelta(days=7)).isoformat(),
        )
        sessions.extend(recurring_sessions)

    # If no deadlines AND no recurring tasks, fall back to generic blocks
    if not deadlines and not has_recurring_tasks:
        for block in free_blocks:
            if remaining_minutes <= 0:
                break
            start, block_end = _block_bounds(block)
            duration = min(90, remaining_minutes, block.minutes)
            if duration < 45:
                continue
            end = start + timedelta(minutes=duration)
            sessions.append(
                _make_session(
                    title="Focused planning block",
                    start=start,
                    end=end,
                    kind="work",
                    related=None,
                    reason="Placed in an available block.",
                )
            )
            remaining_minutes -= duration

    sessions.sort(key=lambda session: (session.start, session.end))
    total = sum(_hours(datetime.fromisoformat(session.start), datetime.fromisoformat(session.end)) for session in sessions)
    warnings: list[str] = []
    assumptions = [
        "Calendar events are treated as fixed unless you ask me to move them.",
        "Complex generated plans are drafts until you confirm calendar insertion.",
    ]
    if any(t.category == "university" for t in extracted.recurring_tasks):
        assumptions.append("University classes are read from your calendar or need your input for exact times.")
    if any(constraint.kind == "cooking" for constraint in extracted.constraints):
        assumptions.append("Assumed cooking takes 12:30-13:30 and 19:00-20:00 daily.")
    if available_hours < target_hours and deadlines:
        warnings.append(
            f"I found only {available_hours:.1f} free hours before the deadlines, below the {target_hours:.1f}-hour target."
        )

    # Build summary
    if has_recurring_tasks:
        parts = []
        for task in extracted.recurring_tasks:
            if task.category == "gym" and task.count:
                parts.append(f"{task.count} gym sessions")
            elif task.category == "cooking":
                parts.append("daily cooking")
            elif task.category == "project" and task.total_minutes:
                parts.append(f"{task.total_minutes / 60:.0f}h {task.name}")
        summary = f"Weekly plan with {', '.join(parts)}. Total: {total:.1f} planned hours."
    elif classification.intent == "modify_existing_plan":
        summary = f"Expanded the active plan to {total:.1f} planned hours and used additional available days."
    elif classification.intent == "optimize_schedule":
        summary = f"Built an optimized draft schedule with {total:.1f} planned hours."
    elif deadlines and total < target_hours and available_hours < target_hours:
        summary = f"I found only {available_hours:.1f} free hours before the finals, which is below the {target_hours:.1f}-hour preparation target."
    elif deadlines:
        summary = f"Built a {total:.1f}-hour plan across multiple days, prioritizing the nearest final first."
    else:
        summary = f"Built a draft plan with {total:.1f} planned hours."

    version = 1
    supersedes = None
    if classification.intent == "modify_existing_plan" and previous_state and previous_state.latest_plan:
        version = previous_state.latest_plan.version + 1
        supersedes = previous_state.latest_plan.plan_id

    window = PlanningWindow(
        start=extracted.planning_window_start or datetime.now().isoformat(),
        end=extracted.planning_window_end or (datetime.now() + timedelta(days=3)).isoformat(),
    )
    return StructuredPlan(
        plan_id=uuid.uuid4().hex,
        status="active_unconfirmed",
        version=version,
        supersedes_plan_id=supersedes,
        created_at=datetime.now(UTC).isoformat(),
        intent=classification.intent if classification.intent in {"generate_plan", "modify_existing_plan", "optimize_schedule"} else "generate_plan",
        summary=summary,
        planning_window=window,
        sessions=sessions,
        assumptions=assumptions,
        warnings=warnings if sessions else ["I could not find enough free time in the selected window."],
        total_planned_hours=total,
        inferred_target_hours=target_hours,
        requires_user_confirmation=True,
        calendar_actions=[],
    )


class StructuredPlanner:
    def __init__(self, client: AsyncOpenAI | None = None):
        self.client = client or AsyncOpenAI(api_key=settings.openai_api_key or "unused")

    async def generate(
        self,
        *,
        prompt: str,
        classification: IntentClassification,
        extracted: ExtractedPlanningContext,
        planning_state: PlanningState | None,
        fixed_events_summary: list[dict[str, Any]],
        free_blocks: list[FreeBlock],
        model_selection: ModelSelection,
    ) -> StructuredPlan:
        fallback = deterministic_plan(
            prompt=prompt,
            classification=classification,
            extracted=extracted,
            free_blocks=free_blocks,
            previous_state=planning_state,
        )
        if not settings.openai_api_key:
            return fallback

        payload = {
            "user_request": prompt,
            "intent": classification.intent,
            "planning_state_summary": planning_state.model_dump(mode="json") if planning_state else None,
            "deadlines": [deadline.model_dump() for deadline in extracted.deadlines],
            "constraints": [constraint.model_dump() for constraint in extracted.constraints],
            "inferred_target_hours": fallback.inferred_target_hours,
            "quality_rules": [
                "Exam plans must cover every deadline/subject before that deadline.",
                "Two exams in the same week should target at least 12 hours if free time exists.",
                "Do not show tiny one-session multi-exam plans unless calendar free time is truly scarce.",
            ],
            "fixed_events_summary": fixed_events_summary,
            "free_blocks": [block.model_dump() for block in free_blocks],
            "allowed_actions": ["draft_plan_only"],
            "calendar_mutation_rule": "calendar_actions must be empty until user confirmation",
            "compact_planning": model_selection.compact_planning,
        }
        log_model_cost(
            phase="planner",
            model=model_selection.model,
            input_payload=payload,
            max_output_tokens=model_selection.max_output_tokens,
        )
        response = await self.client.chat.completions.create(
            model=model_selection.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are replanme's structured planning engine. Return JSON only matching: "
                        "{plan_id,intent,summary,planning_window,sessions,assumptions,warnings,total_planned_hours,inferred_target_hours,"
                        "requires_user_confirmation,calendar_actions}. For complex plans calendar_actions must be [].\n"
                        "Each session should include subject for exam/deadline work.\n"
                        "ANTI-HALLUCINATION: Only schedule tasks explicitly requested by the user, found in the calendar, or listed as assumptions. "
                        "Do NOT invent subjects, exams, or tasks the user did not mention.\n"
                        "For recurring tasks (gym, cooking, project work), use clean human-readable titles like "
                        "'Gym session', 'Cooking', 'ML project deep work'. Never use leftover user-message fragments "
                        "like 'I have ICT preparation' or 'and Anatomy preparation'.\n"
                        "Spread sessions across the full planning window. Do not overload one day while leaving others empty."
                    ),
                },
                {"role": "user", "content": json.dumps(payload)},
            ],
            response_format={"type": "json_object"},
            **completion_token_param(model_selection.model, model_selection.max_output_tokens),
        )
        try:
            plan = StructuredPlan.model_validate_json(response.choices[0].message.content or "{}")
        except Exception:
            return fallback
        # Clean up session titles
        for session in plan.sessions:
            session.title = _clean_session_title(session.title)
        
        if classification.intent == "modify_existing_plan" and planning_state and planning_state.latest_plan:
            plan.version = planning_state.latest_plan.version + 1
            plan.supersedes_plan_id = planning_state.latest_plan.plan_id
        else:
            plan.version = 1
            plan.supersedes_plan_id = None
            
        plan.status = "active_unconfirmed"
        plan.created_at = datetime.now(UTC).isoformat()
        plan.requires_user_confirmation = True
        plan.calendar_actions = []
        return plan
