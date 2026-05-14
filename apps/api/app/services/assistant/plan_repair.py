"""Plan repair helpers used after deterministic validation fails."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.core.config import settings
from app.llm.gemma import GemmaClient
from app.schemas.assistant import CalendarEventSnapshot, UserPlanningMemory
from app.services.assistant.plan_validator import validate_plan
from app.services.assistant.planner import deterministic_plan
from app.services.assistant.types import Constraint, CriticEvaluation, Deadline, ExtractedPlanningContext, FreeBlock, IntentClassification, PlanValidationResult, StructuredPlan


def _duration_minutes(start: str, end: str) -> int:
    return int((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() // 60)


def deterministic_repair(
    plan: StructuredPlan,
    *,
    free_blocks: list[FreeBlock],
    deadlines: list[Deadline] | None = None,
    constraints: list[Constraint] | None = None,
    critic: CriticEvaluation | None = None,
) -> StructuredPlan:
    if deadlines and (
        plan.total_planned_hours < (plan.inferred_target_hours or 0)
        or len({session.deadline_related_to for session in plan.sessions if session.deadline_related_to}) < len(deadlines)
        or len(plan.sessions) <= 1
    ):
        extracted = ExtractedPlanningContext(
            deadlines=deadlines,
            constraints=constraints or [],
            planning_window_start=plan.planning_window.start,
            planning_window_end=plan.planning_window.end,
            planning_window_days=max(1, (datetime.fromisoformat(plan.planning_window.end).date() - datetime.fromisoformat(plan.planning_window.start).date()).days + 1),
            target_hours=plan.inferred_target_hours,
            deadlines_count=len(deadlines),
            constraints_count=len(constraints or []),
        )
        return deterministic_plan(
            prompt="Repair weak exam preparation plan.",
            classification=IntentClassification(intent=plan.intent, requires_planning=True, requires_calendar_read=True, requires_user_confirmation=True),
            extracted=extracted,
            free_blocks=free_blocks,
            previous_state=None,
        )

    repaired = plan.model_copy(deep=True)
    if any(
        (datetime.fromisoformat(session.end) - datetime.fromisoformat(session.start)).total_seconds() / 3600 > 3
        for session in repaired.sessions
    ):
        split_sessions = []
        for session in repaired.sessions:
            start = datetime.fromisoformat(session.start)
            end = datetime.fromisoformat(session.end)
            if (end - start).total_seconds() / 3600 <= 3:
                split_sessions.append(session)
                continue
            cursor = start
            index = 1
            while cursor < end:
                chunk_end = min(cursor + timedelta(hours=2), end)
                if (chunk_end - cursor).total_seconds() / 60 < 45:
                    break
                split_sessions.append(
                    session.model_copy(
                        update={
                            "title": f"{session.title} ({index})",
                            "start": cursor.isoformat(),
                            "end": chunk_end.isoformat(),
                            "reason_short": "Split into a manageable study block with a break.",
                        }
                    )
                )
                index += 1
                cursor = chunk_end + timedelta(minutes=15)
        repaired.sessions = split_sessions
        repaired.total_planned_hours = round(
            sum(
                (datetime.fromisoformat(session.end) - datetime.fromisoformat(session.start)).total_seconds() / 3600
                for session in repaired.sessions
            ),
            2,
        )
        return repaired

    occupied: list[tuple[datetime, datetime]] = []
    blocks = sorted(free_blocks, key=lambda block: (block.start, -block.minutes))

    for session in repaired.sessions:
        start = datetime.fromisoformat(session.start)
        end = datetime.fromisoformat(session.end)
        duration = _duration_minutes(session.start, session.end)
        invalid_overlap = any(start < busy_end and busy_start < end for busy_start, busy_end in occupied)
        if end <= start or invalid_overlap:
            slot = next(
                (
                    block
                    for block in blocks
                    if block.minutes >= duration
                    and not any(
                        datetime.fromisoformat(block.start) < busy_end
                        and busy_start < datetime.fromisoformat(block.start) + (end - start)
                        for busy_start, busy_end in occupied
                    )
                ),
                None,
            )
            if slot:
                new_start = datetime.fromisoformat(slot.start)
                new_end = new_start + (end - start)
                session.start = new_start.isoformat()
                session.end = new_end.isoformat()
                start, end = new_start, new_end
        occupied.append((start, end))

    return repaired


class PlanRepairer:
    def __init__(self, client: object | None = None, gemma_client: GemmaClient | None = None):
        self.gemma = gemma_client or GemmaClient()

    async def repair(
        self,
        *,
        plan: StructuredPlan,
        validation: PlanValidationResult,
        free_blocks: list[FreeBlock],
        fixed_events: list[CalendarEventSnapshot],
        deadlines: list[Deadline],
        constraints: list[Constraint],
        memory: UserPlanningMemory,
        original_request: str | None = None,
        critic: CriticEvaluation | None = None,
    ) -> StructuredPlan:
        fallback = deterministic_repair(plan, free_blocks=free_blocks, deadlines=deadlines, constraints=constraints, critic=critic)
        fallback.intent = plan.intent
        fallback.version = plan.version
        fallback.supersedes_plan_id = plan.supersedes_plan_id
        fallback.status = plan.status
        fallback.requires_user_confirmation = True
        fallback.calendar_actions = []
        payload = {
            "plan": plan.model_dump(mode="json"),
            "validation_errors": [issue.model_dump() for issue in validation.issues],
            "critic": critic.model_dump(mode="json") if critic else None,
            "original_user_request": original_request,
            "free_blocks": [block.model_dump() for block in free_blocks[:80]],
            "deadlines": [deadline.model_dump() for deadline in deadlines],
            "constraints": [constraint.model_dump() for constraint in constraints],
            "deterministic_baseline": fallback.model_dump(mode="json"),
        }
        gemma_json = await self.gemma.generate_json(
            schema_name="StructuredPlanRepair",
            system_prompt=(
                "Repair the structured calendar plan using validation errors and critic instructions. "
                "Return JSON matching StructuredPlan. Keep calendar_actions empty. Use only provided free blocks "
                "and preserve the user's requested tasks."
            ),
            payload=payload,
            max_output_tokens=settings.planner_max_output_tokens,
        )
        if isinstance(gemma_json, dict):
            gemma_json.setdefault("plan_id", plan.plan_id)
            gemma_json.setdefault("status", plan.status)
            gemma_json.setdefault("version", plan.version)
            gemma_json.setdefault("created_at", plan.created_at)
            gemma_json.setdefault("requires_user_confirmation", True)
            gemma_json["calendar_actions"] = []
            try:
                repaired = StructuredPlan.model_validate(gemma_json)
            except Exception:
                repaired = None
            if repaired is not None:
                second = validate_plan(
                    repaired,
                    fixed_events=fixed_events,
                    deadlines=deadlines,
                    constraints=constraints,
                    memory=memory,
                    free_blocks=free_blocks,
                    inferred_target_hours=repaired.inferred_target_hours,
                )
                if second.valid:
                    return repaired
        return fallback
