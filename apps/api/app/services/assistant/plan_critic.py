"""AI critic for human-satisfaction planning quality."""

from __future__ import annotations

import json

from openai import AsyncOpenAI

from app.core.config import settings
from app.llm.openai_params import completion_token_param
from app.schemas.assistant import CalendarEventSnapshot, UserPlanningMemory
from app.services.assistant.cost_estimator import log_model_cost
from app.services.assistant.planner import available_deadline_hours, infer_target_hours
from app.services.assistant.types import Constraint, CriticEvaluation, Deadline, FreeBlock, RecurringTask, StructuredPlan


def deterministic_critic(
    *,
    user_request: str,
    plan: StructuredPlan,
    deadlines: list[Deadline],
    constraints: list[Constraint],
    fixed_events: list[CalendarEventSnapshot],
    free_blocks: list[FreeBlock],
    memory: UserPlanningMemory,
    recurring_tasks: list[RecurringTask] | None = None,
) -> CriticEvaluation:
    problems: list[str] = []
    instructions: list[str] = []

    if plan.calendar_actions:
        problems.append("Plan contains calendar actions before user confirmation.")
        instructions.append("Keep calendar_actions empty until the user confirms.")

    deadline_titles = {deadline.title.casefold(): deadline.title for deadline in deadlines}
    covered = {
        (session.deadline_related_to or session.subject or "").casefold()
        for session in plan.sessions
        if session.type == "study"
    }
    missing = [title for key, title in deadline_titles.items() if key not in covered]
    target = None
    available = None
    scarce_free_time = False
    if deadlines:
        target = plan.inferred_target_hours or infer_target_hours(
            deadlines=deadlines,
            planning_window_start=plan.planning_window.start,
            planning_window_days=max(1, (len({session.start[:10] for session in plan.sessions}) or 1)),
        )
        available = available_deadline_hours(free_blocks=free_blocks, deadlines=deadlines)
        scarce_free_time = available < target

    if missing and not scarce_free_time:
        problems.append("Plan does not cover: " + ", ".join(missing))
        instructions.append("Add preparation sessions for every exam/deadline before its deadline.")

    if deadlines:
        required = min(target, available) if available > 0 else target
        if plan.total_planned_hours + 0.01 < required:
            problems.append(
                f"Plan has only {plan.total_planned_hours:.1f} hours; a serious target is {target:.1f} hours."
            )
            instructions.append("Expand the plan across available free blocks until it approaches the inferred target hours.")

    if len(deadlines) > 1 and len(plan.sessions) <= 1:
        problems.append("Multi-exam plan has only one session.")
        instructions.append("Spread preparation across multiple days and include each subject.")

    for session in plan.sessions:
        from datetime import datetime

        duration_hours = (datetime.fromisoformat(session.end) - datetime.fromisoformat(session.start)).total_seconds() / 3600
        if duration_hours > 3:
            problems.append(f"{session.title} is {duration_hours:.1f} hours straight, which is overloaded.")
            instructions.append("Split long study sessions into shorter blocks with breaks.")
            break

    # --- Recurring task validation ---
    if recurring_tasks:
        from datetime import datetime as _dt
        for task in recurring_tasks:
            if task.category == "university":
                continue
            if task.category == "gym" and task.count:
                gym_count = sum(1 for s in plan.sessions if s.type == "gym")
                if gym_count < task.count:
                    problems.append(f"Plan has {gym_count} gym sessions but {task.count} were requested.")
                    instructions.append(f"Schedule {task.count} gym sessions across different days.")
            elif task.category == "cooking":
                cooking_days = len({_dt.fromisoformat(s.start).date().isoformat() for s in plan.sessions if s.type == "cooking"})
                window_days = max(1, (len({s.start[:10] for s in plan.sessions}) or 7))
                if cooking_days < window_days - 1:
                    problems.append(f"Cooking planned on {cooking_days} days but daily was requested.")
                    instructions.append("Add cooking sessions for every day in the planning window.")
            elif task.category == "project" and task.total_minutes:
                project_minutes = sum(
                    int((_dt.fromisoformat(s.end) - _dt.fromisoformat(s.start)).total_seconds() / 60)
                    for s in plan.sessions if s.type == "project"
                )
                if project_minutes < task.total_minutes * 0.8:
                    problems.append(f"Project work: {project_minutes / 60:.1f}h of {task.total_minutes / 60:.0f}h requested.")
                    instructions.append(f"Add more project work sessions to reach {task.total_minutes / 60:.0f}h total.")

        # Title quality: reject session titles that look like leftover user fragments
        import re as _re
        for session in plan.sessions:
            if _re.search(r'^(I\s+have|and\s+|I\s+need)', session.title, _re.IGNORECASE):
                problems.append(f"Session title '{session.title}' is a leftover user-message fragment.")
                instructions.append("Use clean titles like 'Gym session', 'Cooking', 'ML project deep work'.")
                break

    if deadlines and not problems:
        score = 8.5
        approved = True
        reason = "Plan is deadline-aware, covers all subjects, and is substantial enough."
        risk = "low"
    elif recurring_tasks and not problems:
        score = 8.5
        approved = True
        reason = "Plan covers all requested recurring tasks with appropriate scheduling."
        risk = "low"
    elif not problems:
        score = 8.0
        approved = True
        reason = "Plan is useful and actionable."
        risk = "low"
    else:
        score = max(2.0, 7.0 - len(problems) * 1.5)
        approved = score >= settings.min_critic_approval_score
        reason = problems[0]
        risk = "high" if score < 5 else "medium"

    return CriticEvaluation(
        approved=approved,
        score=score,
        main_reason=reason,
        problems=problems,
        repair_instructions=list(dict.fromkeys(instructions)),
        user_satisfaction_risk=risk,
    )


class PlanCritic:
    def __init__(self, client: AsyncOpenAI | None = None):
        self.client = client or AsyncOpenAI(api_key=settings.openai_api_key or "unused")

    async def evaluate(
        self,
        *,
        user_request: str,
        plan: StructuredPlan,
        deadlines: list[Deadline],
        constraints: list[Constraint],
        fixed_events: list[CalendarEventSnapshot],
        free_blocks: list[FreeBlock],
        memory: UserPlanningMemory,
        complexity_score: int,
        recurring_tasks: list[RecurringTask] | None = None,
    ) -> tuple[CriticEvaluation, str]:
        fallback = deterministic_critic(
            user_request=user_request,
            plan=plan,
            deadlines=deadlines,
            constraints=constraints,
            fixed_events=fixed_events,
            free_blocks=free_blocks,
            memory=memory,
            recurring_tasks=recurring_tasks,
        )
        model = settings.critic_model_hard if complexity_score > settings.planner_default_threshold else settings.critic_model
        if not settings.openai_api_key:
            return fallback, "deterministic"

        payload = {
            "user_request": user_request,
            "plan": plan.model_dump(mode="json"),
            "deadlines": [deadline.model_dump() for deadline in deadlines],
            "constraints": [constraint.model_dump() for constraint in constraints],
            "fixed_events_count": len(fixed_events),
            "free_blocks": [block.model_dump() for block in free_blocks[:80]],
            "deterministic_baseline": fallback.model_dump(mode="json"),
            "rubric": [
                "Does the plan satisfy the user's actual goal?",
                "Is it serious enough for the task?",
                "Are all exams/deadlines/tasks covered before deadlines?",
                "Is it realistic and not overloaded?",
                "Would a real user feel this is worth paying for?",
                "Is calendar insertion still waiting for confirmation?",
            ],
        }
        log_model_cost(
            phase="critic",
            model=model,
            input_payload=payload,
            max_output_tokens=settings.nano_max_output_tokens,
        )
        response = await self.client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a planning critic. Do not create or modify the plan. "
                        "Return JSON only with approved, score, main_reason, problems, "
                        "repair_instructions, user_satisfaction_risk."
                    ),
                },
                {"role": "user", "content": json.dumps(payload)},
            ],
            response_format={"type": "json_object"},
            **completion_token_param(model, settings.nano_max_output_tokens),
        )
        try:
            critic = CriticEvaluation.model_validate_json(response.choices[0].message.content or "{}")
        except Exception:
            return fallback, model
        if critic.score < settings.min_critic_approval_score:
            critic.approved = False
        return critic, model
