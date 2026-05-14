"""Lightweight planning constraint extraction."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from app.core.config import settings
from app.llm.gemma import GemmaClient
from app.services.assistant.types import Constraint, Deadline, ExtractedPlanningContext, PlanningState, RecurringTask

DAY_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def _next_weekday(now: datetime, weekday: int) -> datetime:
    delta = (weekday - now.weekday()) % 7
    if delta == 0:
        delta = 7
    return (now + timedelta(days=delta)).replace(hour=9, minute=0, second=0, microsecond=0)


def _extract_deadlines(prompt: str, now: datetime) -> list[Deadline]:
    deadlines: list[Deadline] = []

    def clean_title(value: str) -> str:
        title = " ".join(value.split()).strip(" ,.")
        title = re.sub(r"^(i\s+have|i\s+need\s+to\s+prepare\s+for|and)\s+", "", title, flags=re.IGNORECASE)
        title = re.sub(r"\b(finals?|exams?|deadline)$", "", title, flags=re.IGNORECASE).strip(" ,.")
        parts = re.split(r"\s+and\s+", title, flags=re.IGNORECASE)
        return (parts[-1] if parts else title).strip(" ,.") or title

    for match in re.finditer(
        r"\b(?P<title>[A-Za-z][A-Za-z0-9\s&-]{1,40}?)\s+(?:final|exam|deadline)\s+(?:on\s+)?(?P<day>monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        prompt,
        re.IGNORECASE,
    ):
        title = clean_title(match.group("title"))
        if not title:
            continue
        day = match.group("day").casefold()
        due = _next_weekday(now, DAY_INDEX[day])
        deadlines.append(Deadline(title=title, due_at=due.isoformat(), kind="exam" if "final" in match.group(0).casefold() or "exam" in match.group(0).casefold() else "deadline"))

    if any(word in prompt.casefold() for word in ("final", "exam", "deadline")):
        for match in re.finditer(
            r"\b(?P<title>[A-Z][A-Za-z0-9&-]{1,20})\s+on\s+(?P<day>monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
            prompt,
            re.IGNORECASE,
        ):
            title = clean_title(match.group("title"))
            if not title or title.casefold() in DAY_INDEX:
                continue
            day = match.group("day").casefold()
            due = _next_weekday(now, DAY_INDEX[day])
            if not any(existing.title.casefold() == title.casefold() for existing in deadlines):
                deadlines.append(Deadline(title=title, due_at=due.isoformat(), kind="exam"))

    if not deadlines:
        for day, index in DAY_INDEX.items():
            if re.search(rf"\b{day}\b", prompt, re.IGNORECASE) and any(word in prompt.casefold() for word in ("exam", "final", "deadline")):
                deadlines.append(Deadline(title=f"{day.title()} deadline", due_at=_next_weekday(now, index).isoformat(), kind="deadline"))

    return deadlines


def _extract_constraints(prompt: str) -> list[Constraint]:
    constraints: list[Constraint] = []
    for match in re.finditer(r"\b(?:spend|need|have)\s+(?P<hours>\d+(?:\.\d+)?)\s*hours?/?day\s+on\s+(?P<thing>[A-Za-z][A-Za-z\s-]+)", prompt, re.IGNORECASE):
        hours = float(match.group("hours"))
        thing = " ".join(match.group("thing").split()).strip(" .")
        constraints.append(Constraint(kind=thing.casefold(), value=f"{hours:g} hours/day on {thing}", minutes_per_day=int(hours * 60)))
    if "cooking" in prompt.casefold() and not any(c.kind == "cooking" for c in constraints):
        hour_match = re.search(r"(\d+(?:\.\d+)?)\s*hours?/?day.*cooking", prompt, re.IGNORECASE)
        minutes = int(float(hour_match.group(1)) * 60) if hour_match else 120
        constraints.append(Constraint(kind="cooking", value=f"{minutes // 60:g} hours/day on cooking", minutes_per_day=minutes))
    if re.search(r"\bcook\b", prompt, re.IGNORECASE) and not any(c.kind == "cooking" for c in constraints):
        hour_match = re.search(r"cook\s+(\d+(?:\.\d+)?)\s*hours?\s+(?:every\s+day|daily|a\s+day)", prompt, re.IGNORECASE)
        minutes = int(float(hour_match.group(1)) * 60) if hour_match else 120
        constraints.append(Constraint(kind="cooking", value=f"{minutes // 60:g} hours/day on cooking", minutes_per_day=minutes))
    if any(word in prompt.casefold() for word in ("sleep", "energy", "high energy", "low energy")):
        constraints.append(Constraint(kind="energy", value="Respect sleep and energy preferences."))
    return constraints


def _extract_recurring_tasks(prompt: str) -> list[RecurringTask]:
    """Extract general recurring tasks like gym, cooking, project work from the prompt."""
    tasks: list[RecurringTask] = []
    lower = prompt.lower()

    # Gym: "gym 3 times", "gym three times a week", "gym 3x"
    gym_match = re.search(
        r'\bgym\s+(\d+)\s*(?:times?|x|sessions?)\b',
        lower,
    )
    if not gym_match:
        gym_match = re.search(
            r'(\d+)\s*(?:times?|x|sessions?)\s+(?:at\s+(?:the\s+)?)?gym\b',
            lower,
        )
    if gym_match:
        count = int(gym_match.group(1))
        tasks.append(RecurringTask(
            name="Gym session",
            category="gym",
            frequency="weekly",
            count=count,
            duration_minutes=60,
        ))
    elif "gym" in lower and not gym_match:
        # Mentioned gym without a count, default to 3
        if re.search(r'\bgym\b', lower):
            tasks.append(RecurringTask(
                name="Gym session",
                category="gym",
                frequency="weekly",
                count=3,
                duration_minutes=60,
            ))

    # Cooking: "cooking every day", "cook daily", "cooking 2 hours a day"
    if re.search(r'\bcook(?:ing)?\b', lower):
        duration = 120  # default 2 hours
        dur_match = re.search(
            r'cook(?:ing)?\s+(\d+(?:\.\d+)?)\s*hours?\s*(?:a\s+day|daily|every\s+day|per\s+day)',
            lower,
        )
        if not dur_match:
            dur_match = re.search(
                r'(\d+(?:\.\d+)?)\s*hours?\s*(?:of\s+)?cook(?:ing)?',
                lower,
            )
        if dur_match:
            duration = int(float(dur_match.group(1)) * 60)
        tasks.append(RecurringTask(
            name="Cooking",
            category="cooking",
            frequency="daily",
            count=7,
            duration_minutes=duration,
        ))

    # Project work: "10 hours for my ML project", "need 10 hours for ML project"
    project_match = re.search(
        r'(\d+(?:\.\d+)?)\s*hours?\s+(?:for\s+(?:my\s+|the\s+)?|of\s+(?:my\s+|the\s+)?|on\s+(?:my\s+|the\s+)?)([A-Za-z][A-Za-z0-9\s-]{1,30}?)(?:\s+(?:project|work|study|research|assignment))?\s*[.,;]?\s*$',
        prompt,
        re.IGNORECASE | re.MULTILINE,
    )
    if not project_match:
        project_match = re.search(
            r'(\d+(?:\.\d+)?)\s*hours?\s+(?:for\s+(?:my\s+|the\s+)?|of\s+(?:my\s+|the\s+)?|on\s+(?:my\s+|the\s+)?)([A-Za-z][A-Za-z0-9\s-]{1,30}?)(?:\s+(?:project|work|study|research|assignment))?',
            prompt,
            re.IGNORECASE,
        )
    if project_match:
        hours = float(project_match.group(1))
        raw_name = project_match.group(2).strip().rstrip(".,;")
        # Clean up the name
        name = re.sub(r'\b(my|the|a|an)\b', '', raw_name, flags=re.IGNORECASE).strip()
        if name and name.casefold() not in ("cook", "cooking", "gym", "sleep"):
            tasks.append(RecurringTask(
                name=f"{name} deep work",
                category="project",
                frequency="total",
                total_minutes=int(hours * 60),
                duration_minutes=min(120, max(60, int(hours * 60 / max(1, int(hours / 1.5))))),
            ))

    # University classes: detect mention but don't create sessions (read from calendar or ask)
    if re.search(r'\buniversity\b|\buni\b|\bclass(?:es)?\b|\blecture', lower):
        if not any(t.category == "university" for t in tasks):
            tasks.append(RecurringTask(
                name="University class",
                category="university",
                frequency="weekly",
                count=0,  # 0 = read from calendar or ask
                duration_minutes=90,
            ))

    return tasks


def deterministic_extract(prompt: str, now: datetime, planning_state: PlanningState | None) -> ExtractedPlanningContext:
    deadlines = _extract_deadlines(prompt, now)
    constraints = _extract_constraints(prompt)
    recurring_tasks = _extract_recurring_tasks(prompt)

    if planning_state and planning_state.active:
        known_titles = {deadline.title.casefold() for deadline in deadlines}
        deadlines.extend(deadline for deadline in planning_state.deadlines if deadline.title.casefold() not in known_titles)
        known_constraints = {(constraint.kind, constraint.value) for constraint in constraints}
        constraints.extend(
            constraint
            for constraint in planning_state.constraints
            if (constraint.kind, constraint.value) not in known_constraints
        )

    window_start = now.replace(hour=7, minute=0, second=0, microsecond=0)
    if deadlines:
        latest = max(datetime.fromisoformat(deadline.due_at) for deadline in deadlines)
        window_end = latest.replace(hour=22, minute=0, second=0, microsecond=0)
    elif "month" in prompt.casefold():
        window_end = window_start + timedelta(days=30)
    elif "week" in prompt.casefold():
        window_end = window_start + timedelta(days=7)
    elif planning_state and planning_state.planning_window_end:
        window_end = datetime.fromisoformat(planning_state.planning_window_end)
    else:
        window_end = window_start + timedelta(days=3)

    if "other days" in prompt.casefold() and (window_end - window_start).days < 4:
        window_end = window_start + timedelta(days=5)

    target_hours = None
    for target_match in re.finditer(r"(\d+(?:\.\d+)?)\s+hours?", prompt, re.IGNORECASE):
        nearby = prompt[max(0, target_match.start() - 24): target_match.end() + 32].casefold()
        if any(word in nearby for word in ("cook", "cooking", "sleep", "gym", "work")):
            continue
        if any(word in nearby for word in ("study", "prepare", "preparation", "target", "revision", "review")):
            target_hours = float(target_match.group(1))
            break
    if planning_state and planning_state.total_planned_hours and any(phrase in prompt.casefold() for phrase in ("more", "not enough", "little", "intense")):
        target_hours = max(planning_state.total_planned_hours + 3.0, planning_state.total_planned_hours * 1.5)

    days = max(1, (window_end.date() - window_start.date()).days + 1)
    return ExtractedPlanningContext(
        deadlines=deadlines,
        constraints=constraints,
        recurring_tasks=recurring_tasks,
        planning_window_start=window_start.isoformat(),
        planning_window_end=window_end.isoformat(),
        planning_window_days=days,
        target_hours=target_hours,
        requires_energy_optimization=any(word in prompt.casefold() for word in ("energy", "optimize", "sleep")),
        requires_calendar_rewrite=any(phrase in prompt.casefold() for phrase in ("rebuild", "reorganize", "compress", "move around")),
        deadlines_count=len(deadlines),
        constraints_count=len(constraints),
    )


class ConstraintExtractor:
    def __init__(self, client: object | None = None, gemma_client: GemmaClient | None = None):
        self.gemma = gemma_client or GemmaClient()

    async def extract(self, *, prompt: str, now: datetime, planning_state: PlanningState | None) -> ExtractedPlanningContext:
        deterministic = deterministic_extract(prompt, now, planning_state)
        payload = {
            "message": prompt,
            "now": now.isoformat(),
            "existing_deadlines": [deadline.model_dump() for deadline in (planning_state.deadlines if planning_state else [])],
            "existing_constraints": [constraint.model_dump() for constraint in (planning_state.constraints if planning_state else [])],
            "existing_recurring_tasks": [task.model_dump() for task in (planning_state.latest_plan.sessions if planning_state and planning_state.latest_plan else [])],
            "deterministic_baseline": deterministic.model_dump(mode="json"),
        }
        gemma_json = await self.gemma.generate_json(
            schema_name="ExtractedPlanningContext",
            system_prompt=(
                "Extract planning context from the user's request. Return JSON matching ExtractedPlanningContext: "
                "deadlines, constraints, recurring_tasks, planning_window_start, planning_window_end, planning_window_days, "
                "target_hours, requires_energy_optimization, requires_calendar_rewrite, deadlines_count, constraints_count. "
                "Use ISO datetimes. Preserve explicitly mentioned subjects/tasks. Support English and Russian."
            ),
            payload=payload,
            max_output_tokens=settings.nano_max_output_tokens,
        )
        if isinstance(gemma_json, dict):
            try:
                extracted = ExtractedPlanningContext.model_validate(gemma_json)
            except Exception:
                extracted = None
            if extracted is not None:
                if not extracted.deadlines:
                    extracted.deadlines = deterministic.deadlines
                if not extracted.constraints:
                    extracted.constraints = deterministic.constraints
                if not extracted.recurring_tasks:
                    extracted.recurring_tasks = deterministic.recurring_tasks
                if not extracted.planning_window_start:
                    extracted.planning_window_start = deterministic.planning_window_start
                if not extracted.planning_window_end:
                    extracted.planning_window_end = deterministic.planning_window_end
                if extracted.planning_window_days <= 1:
                    extracted.planning_window_days = deterministic.planning_window_days
                extracted.deadlines_count = len(extracted.deadlines)
                extracted.constraints_count = len(extracted.constraints)
                return extracted

        return deterministic
