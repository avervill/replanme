"""Production-oriented assistant orchestration.

This layer handles planning-first behavior with durable planning state, safe
confirmation, model routing, compact calendar context, validation, and credit
metadata. Non-planning calendar operations are delegated to the existing agent
so current calendar functionality stays intact.
"""

from __future__ import annotations

import logging
import uuid
import zoneinfo
from datetime import UTC, datetime
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.llm.agent import PlannerAgent as LegacyPlannerAgent
from app.llm.memory import AgentMemoryHandler
from app.models.user import User
from app.schemas.assistant import (
    AssistantMessageRequest,
    AssistantMessageResponse,
    CalendarEventSnapshot,
    CreateEventInput,
    DisplayAction,
    ExecutionPlan,
    PlanExecutionResult,
    PlanPreviewChange,
    RoutingDecision,
    SafetyAssessment,
)
from app.services.assistant.calendar_context import build_calendar_context
from app.services.assistant.constraint_extractor import ConstraintExtractor
from app.services.assistant.cost_estimator import estimate_credit_cost
from app.services.assistant.intent_classifier import IntentClassifier
from app.services.assistant.memory import PlanningMemoryService
from app.services.assistant.model_router import calculate_planning_complexity, select_planner_model
from app.services.assistant.plan_critic import PlanCritic
from app.services.assistant.plan_repair import PlanRepairer
from app.services.assistant.plan_validator import validate_plan
from app.services.assistant.planner import StructuredPlanner
from app.services.assistant.planning_state import build_planning_state, load_planning_state, save_planning_state
from app.services.assistant.state import ConversationStateStore
from app.services.assistant.tools import AssistantToolRegistry
from app.services.assistant.types import (
    ComplexityInput,
    IntentClassification,
    PlanningState,
    PlanValidationIssue,
    PlanValidationResult,
    PlanSession,
    StructuredPlan,
)

logger = logging.getLogger(__name__)


def _calendar_intent(intent: str) -> str:
    return {
        "create_single_event": "CREATE_EVENT",
        "delete_event": "DELETE_EVENT",
        "update_event": "UPDATE_EVENT",
        "move_event": "MOVE_EVENT",
        "duplicate_event": "DUPLICATE_EVENTS",
        "duplicate_period": "DUPLICATE_EVENTS",
        "generate_plan": "PLAN_PERIOD",
        "modify_existing_plan": "PLAN_PERIOD",
        "optimize_schedule": "OPTIMIZE_SCHEDULE",
        "confirm_plan_to_calendar": "CONFIRMATION_YES",
        "reject_plan": "CONFIRMATION_NO",
        "answer_question": "SEARCH_EVENTS",
    }.get(intent, "CHAT")


def _format_session(session: PlanSession) -> str:
    start = datetime.fromisoformat(session.start)
    end = datetime.fromisoformat(session.end)
    day = start.strftime("%A")
    return f"{day} {start.strftime('%H:%M')}-{end.strftime('%H:%M')}: {session.title}"


def format_plan_message(plan: StructuredPlan) -> str:
    lines = [plan.summary, "", "Plan:"]
    if plan.sessions:
        lines.extend(_format_session(session) for session in plan.sessions)
    else:
        lines.append("No schedulable sessions found in the selected window.")
    if plan.assumptions:
        lines.append("")
        lines.append("Assumptions:")
        lines.extend(f"- {assumption}" for assumption in plan.assumptions[:4])
    if plan.warnings:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in plan.warnings[:4])
    lines.append("")
    lines.append("Should I add this to your calendar?")
    return "\n".join(lines)


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
        self.client = AsyncOpenAI(api_key=settings.openai_api_key or "unused")
        self.intent_classifier = IntentClassifier(self.client)
        self.constraint_extractor = ConstraintExtractor(self.client)
        self.structured_planner = StructuredPlanner(self.client)
        self.repairer = PlanRepairer(self.client)
        self.critic = PlanCritic(self.client)
        self.legacy = LegacyPlannerAgent(
            state_store=state_store,
            memory_service=memory_service,
            tool_registry=tool_registry,
        )

    def _response(
        self,
        *,
        session_id: str,
        reply: str,
        memory: Any,
        classification: IntentClassification,
        selected_model: str,
        complexity_score: int,
        credit_cost: float,
        status: str = "completed",
        execution: PlanExecutionResult | None = None,
        requires_confirmation: bool = False,
        confirmation_token: str | None = None,
        display_actions: list[DisplayAction] | None = None,
    ) -> AssistantMessageResponse:
        return AssistantMessageResponse(
            session_id=session_id,
            status=status,  # type: ignore[arg-type]
            reply=reply,
            routing=RoutingDecision(
                intent=_calendar_intent(classification.intent),  # type: ignore[arg-type]
                route="complex" if classification.requires_planning else "simple",
                selected_model=selected_model,
                confidence=classification.confidence,
                complexity_score=complexity_score,
                use_calendar_context=classification.requires_calendar_read,
                use_memory=True,
                reason=classification.reason,
                low_cost_path=selected_model in {"backend", settings.intent_model, settings.simple_action_model},
            ),
            plan=ExecutionPlan(
                goal=classification.reason or reply,
                summary=reply[:500],
                selected_model=selected_model,
                route="complex" if classification.requires_planning else "simple",
                reasoning="Structured orchestration path.",
                requires_confirmation=requires_confirmation,
                confirmation_reason="Complex generated plans require confirmation before calendar insertion." if requires_confirmation else None,
                response_message=reply,
            ),
            safety=SafetyAssessment(
                requires_confirmation=requires_confirmation,
                risk_level="high" if requires_confirmation else "low",
            ),
            execution=execution or PlanExecutionResult(status=status),  # type: ignore[arg-type]
            display_actions=display_actions or [],
            awaiting_confirmation=requires_confirmation,
            confirmation_token=confirmation_token,
            estimated_credit_cost=credit_cost,
            model_used=selected_model,
            complexity_score=float(complexity_score),
            memory=memory,
        )

    async def _confirm_plan(
        self,
        *,
        session_id: str,
        payload: AssistantMessageRequest,
        user: User,
        db: AsyncSession,
        memory: Any,
        planning_state: PlanningState,
        classification: IntentClassification,
    ) -> AssistantMessageResponse:
        if not planning_state.latest_plan:
            reply = "I don't have an active draft plan to add yet."
            return self._response(
                session_id=session_id,
                reply=reply,
                memory=memory,
                classification=classification,
                selected_model="backend",
                complexity_score=0,
                credit_cost=0,
                execution=PlanExecutionResult(status="failed", error=reply),
            )
            
        plan = planning_state.latest_plan
        if plan.status == "applied_to_calendar":
            reply = "This plan was already added."
            return self._response(
                session_id=session_id,
                reply=reply,
                memory=memory,
                classification=classification,
                selected_model="backend",
                complexity_score=0,
                credit_cost=0,
                execution=PlanExecutionResult(status="completed", error=reply),
            )
            
        if plan.status == "superseded" or (payload.confirmation_token and payload.confirmation_token != plan.plan_id):
            logger.warning("assistant.confirm_plan_mismatch", extra={"token": payload.confirmation_token, "latest": plan.plan_id, "status": plan.status})
            reply = "I found multiple draft plans and could not safely determine which one to add. Please confirm the latest plan again."
            return self._response(
                session_id=session_id,
                reply=reply,
                memory=memory,
                classification=classification,
                selected_model="backend",
                complexity_score=0,
                credit_cost=0,
                execution=PlanExecutionResult(status="failed", error=reply),
            )
            
        if plan.status != "active_unconfirmed":
            reply = "This plan cannot be confirmed right now."
            return self._response(
                session_id=session_id,
                reply=reply,
                memory=memory,
                classification=classification,
                selected_model="backend",
                complexity_score=0,
                credit_cost=0,
                execution=PlanExecutionResult(status="failed", error=reply),
            )
            
        logger.info("assistant.plan_confirmation_received", extra={
            "user_message": payload.prompt,
            "resolved_plan_id": plan.plan_id,
            "plan_version": plan.version,
            "sessions_count": len(plan.sessions),
        })

        created: list[CalendarEventSnapshot] = []
        errors: list[str] = []
        for session in planning_state.latest_plan.sessions:
            try:
                result = await self.registry.create_event(
                    CreateEventInput(
                        title=session.title,
                        description=session.description or session.reason_short,
                        start_at=datetime.fromisoformat(session.start),
                        end_at=datetime.fromisoformat(session.end),
                        timezone=getattr(user, "timezone", "UTC") or "UTC",
                    ),
                    user=user,
                    db=db,
                    memory=memory,
                )
                created.extend(result.created_events)
            except Exception as exc:
                logger.warning("assistant.plan_create_event_failed", exc_info=True)
                errors.append(f"{session.title}: {exc}")

        planning_state.confirmed = bool(created)
        planning_state.requires_confirmation = False
        planning_state.active = False
        planning_state.created_calendar_event_ids = [event.id for event in created]
        if created:
            planning_state.latest_plan.status = "applied_to_calendar"
        planning_state.updated_at = datetime.now(UTC).isoformat()
        await save_planning_state(
            self.state_store,
            user_id=str(user.id),
            session_id=session_id,
            planning_state=planning_state,
        )

        if created:
            logger.info("assistant.calendar_events_created", extra={
                "plan_id": plan.plan_id,
                "created_count": len(created),
                "created_event_ids": [e.id for e in created],
            })

        reply = f"Added {len(created)} planned session{'s' if len(created) != 1 else ''} to your calendar."
        if errors:
            reply += f" {len(errors)} session{'s' if len(errors) != 1 else ''} could not be added."
        await AgentMemoryHandler(self.state_store, str(user.id), session_id).add_assistant_message(reply)
        return self._response(
            session_id=session_id,
            reply=reply,
            memory=memory,
            classification=classification,
            selected_model="backend",
            complexity_score=0,
            credit_cost=0.1 * len(created),
            execution=PlanExecutionResult(
                status="completed" if created else "failed",
                executed_steps=len(created),
                created_events=created,
                error="; ".join(errors[:3]) if errors and not created else None,
            ),
        )

    async def handle_message(
        self,
        *,
        payload: AssistantMessageRequest,
        user: User,
        db: AsyncSession,
    ) -> AssistantMessageResponse:
        session_id = payload.session_id or uuid.uuid4().hex
        timezone_str = payload.timezone or getattr(user, "timezone", "UTC") or "UTC"
        try:
            tz = zoneinfo.ZoneInfo(timezone_str)
        except Exception:
            tz = UTC
        now_local = datetime.now(tz)

        memory_response = await self.memory_service.get_memory(db, user)
        memory_handler = AgentMemoryHandler(self.state_store, str(user.id), session_id)
        planning_state = await load_planning_state(self.state_store, user_id=str(user.id), session_id=session_id)
        classification = await self.intent_classifier.classify(
            prompt=payload.prompt,
            planning_state=planning_state,
            attachments=payload.attachments,
        )

        if classification.intent == "reject_plan" and planning_state:
            planning_state.active = False
            planning_state.requires_confirmation = False
            if planning_state.latest_plan:
                planning_state.latest_plan.status = "rejected"
            planning_state.updated_at = datetime.now(UTC).isoformat()
            await save_planning_state(self.state_store, user_id=str(user.id), session_id=session_id, planning_state=planning_state)
            reply = "Okay, I won't add that plan to your calendar."
            await memory_handler.add_user_message(payload.prompt)
            await memory_handler.add_assistant_message(reply)
            return self._response(
                session_id=session_id,
                reply=reply,
                memory=memory_response.memory,
                classification=classification,
                selected_model="backend",
                complexity_score=0,
                credit_cost=0,
            )

        is_confirm = classification.intent == "confirm_plan_to_calendar" or payload.confirmation_token
        if is_confirm and planning_state and planning_state.latest_plan:
            await memory_handler.add_user_message(payload.prompt or "yes")
            return await self._confirm_plan(
                session_id=session_id,
                payload=payload,
                user=user,
                db=db,
                memory=memory_response.memory,
                planning_state=planning_state,
                classification=classification,
            )

        if not classification.requires_planning:
            response = await self.legacy.handle_message(payload=payload, user=user, db=db)
            if not isinstance(response.reply, str):
                response.reply = str(response.reply)
            response.model_used = response.model_used or response.routing.selected_model
            response.complexity_score = response.routing.complexity_score
            return response

        await memory_handler.add_user_message(payload.prompt)
        extracted = await self.constraint_extractor.extract(
            prompt=payload.prompt,
            now=now_local,
            planning_state=planning_state,
        )
        start_at = datetime.fromisoformat(extracted.planning_window_start or now_local.isoformat())
        end_at = datetime.fromisoformat(extracted.planning_window_end or now_local.isoformat())
        fixed_events, fixed_summary, free_blocks = await build_calendar_context(
            registry=self.registry,
            user=user,
            db=db,
            memory=memory_response.memory,
            start_at=start_at,
            end_at=end_at,
            constraints=extracted.constraints,
        )
        complexity_input = ComplexityInput(
            intent=classification.intent,
            planning_window_days=extracted.planning_window_days,
            fixed_events_count=len(fixed_events),
            constraints_count=extracted.constraints_count,
            deadlines_count=extracted.deadlines_count,
            requires_energy_optimization=extracted.requires_energy_optimization,
            requires_calendar_rewrite=extracted.requires_calendar_rewrite,
            has_previous_plan_revision=classification.intent == "modify_existing_plan" and bool(planning_state),
        )
        complexity_score = calculate_planning_complexity(complexity_input)
        selection = select_planner_model(complexity_score, user=user)
        plan = await self.structured_planner.generate(
            prompt=payload.prompt,
            classification=classification,
            extracted=extracted,
            planning_state=planning_state,
            fixed_events_summary=[event.model_dump(mode="json") for event in fixed_summary],
            free_blocks=free_blocks,
            model_selection=selection,
        )

        validation = PlanValidationResult(valid=True)
        critic_result = None
        critic_model_used = "none"
        repair_attempts = 0
        for attempt in range(settings.max_plan_repair_attempts + 1):
            validation = validate_plan(
                plan,
                fixed_events=fixed_events,
                deadlines=extracted.deadlines,
                constraints=extracted.constraints,
                memory=memory_response.memory,
                intense_mode="intense" in payload.prompt.casefold() or "more" in payload.prompt.casefold(),
                free_blocks=free_blocks,
                inferred_target_hours=plan.inferred_target_hours,
                recurring_tasks=extracted.recurring_tasks,
            )
            if (
                classification.intent == "modify_existing_plan"
                and planning_state
                and planning_state.total_planned_hours is not None
                and plan.total_planned_hours > planning_state.total_planned_hours
            ):
                remaining_issues = [issue for issue in validation.issues if issue.code != "insufficient_hours"]
                if len(remaining_issues) != len(validation.issues):
                    plan.warnings.append("Expanded the plan, but available calendar time may still be below the inferred target.")
                    validation = PlanValidationResult(valid=not remaining_issues, issues=remaining_issues)
            if not validation.valid:
                if attempt >= settings.max_plan_repair_attempts:
                    break
                repair_attempts += 1
                plan = await self.repairer.repair(
                    plan=plan,
                    validation=validation,
                    free_blocks=free_blocks,
                    fixed_events=fixed_events,
                    deadlines=extracted.deadlines,
                    constraints=extracted.constraints,
                    memory=memory_response.memory,
                    original_request=payload.prompt,
                )
                continue

            critic_result, critic_model_used = await self.critic.evaluate(
                user_request=payload.prompt,
                plan=plan,
                deadlines=extracted.deadlines,
                constraints=extracted.constraints,
                fixed_events=fixed_events,
                free_blocks=free_blocks,
                memory=memory_response.memory,
                complexity_score=complexity_score,
                recurring_tasks=extracted.recurring_tasks,
            )
            if critic_result.approved:
                break
            if attempt >= settings.max_plan_repair_attempts:
                break
            repair_attempts += 1
            plan = await self.repairer.repair(
                plan=plan,
                validation=PlanValidationResult(
                    valid=False,
                    issues=[
                        PlanValidationIssue(
                            code="critic_rejected",
                            message=critic_result.main_reason,
                        )
                    ],
                ),
                free_blocks=free_blocks,
                fixed_events=fixed_events,
                deadlines=extracted.deadlines,
                constraints=extracted.constraints,
                memory=memory_response.memory,
                original_request=payload.prompt,
                critic=critic_result,
            )

        if not validation.valid:
            reply = "I drafted a plan, but it still has scheduling conflicts, so I did not show or apply it. Try widening the planning window or freeing a few calendar blocks."
            await memory_handler.add_assistant_message(reply)
            return self._response(
                session_id=session_id,
                reply=reply,
                memory=memory_response.memory,
                classification=classification,
                selected_model=selection.model,
                complexity_score=complexity_score,
                credit_cost=estimate_credit_cost(classification.intent, complexity_score, selection.model).estimated_credit_cost,
                status="failed",
                execution=PlanExecutionResult(
                    status="failed",
                    error="; ".join(issue.message for issue in validation.issues[:4]),
                ),
            )

        if critic_result and not critic_result.approved:
            plan.warnings.insert(
                0,
                f"Quality critic still flagged this plan after {repair_attempts} repair attempt(s): {critic_result.main_reason}",
            )

        logger.info(
            "assistant.planning_quality_loop",
            extra={
                "planner_model_used": selection.model,
                "critic_model_used": critic_model_used,
                "validation_errors": [issue.code for issue in validation.issues],
                "critic_score": critic_result.score if critic_result else None,
                "critic_approved": critic_result.approved if critic_result else None,
                "repair_attempts": repair_attempts,
                "final_plan_total_hours": plan.total_planned_hours,
                "estimated_cost_usd": 0.0,
            },
        )

        if classification.intent == "modify_existing_plan" and planning_state and planning_state.latest_plan:
            logger.info("assistant.plan_superseded", extra={"old_plan_id": planning_state.latest_plan.plan_id, "new_plan_id": plan.plan_id})
            
        logger.info("assistant.plan_generated", extra={"plan_id": plan.plan_id, "version": plan.version, "supersedes_plan_id": plan.supersedes_plan_id, "status": plan.status, "sessions_count": len(plan.sessions), "total_hours": plan.total_planned_hours})

        next_state = build_planning_state(
            goal=planning_state.goal if planning_state and planning_state.goal else payload.prompt,
            latest_user_request=payload.prompt,
            latest_plan=plan,
            deadlines=extracted.deadlines,
            constraints=extracted.constraints,
            fixed_events_used=fixed_summary,
            free_blocks_used=free_blocks,
            target_hours=extracted.target_hours,
        )
        await save_planning_state(self.state_store, user_id=str(user.id), session_id=session_id, planning_state=next_state)
        reply = format_plan_message(plan)
        await memory_handler.add_assistant_message(reply)
        credit = estimate_credit_cost(classification.intent, complexity_score, selection.model)
        preview = [
            PlanPreviewChange(
                action="create_event",
                title=session.title,
                details=session.reason_short,
                proposed_start_at=datetime.fromisoformat(session.start),
                proposed_end_at=datetime.fromisoformat(session.end),
            )
            for session in plan.sessions
        ]
        return self._response(
            session_id=session_id,
            reply=reply,
            memory=memory_response.memory,
            classification=classification,
            selected_model=selection.model,
            complexity_score=complexity_score,
            credit_cost=credit.estimated_credit_cost,
            status="awaiting_confirmation",
            requires_confirmation=True,
            confirmation_token=plan.plan_id,
            display_actions=[DisplayAction(kind="ask_user", summary="Add this draft plan to calendar after confirmation.")],
            execution=PlanExecutionResult(
                status="awaiting_confirmation",
                preview=preview,
                rollback_available=False,
            ),
        )
