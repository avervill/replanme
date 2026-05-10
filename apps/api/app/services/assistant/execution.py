"""Execution, safety, retry, and rollback for assistant plans."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User
from app.schemas.assistant import (
    CalendarEventSnapshot,
    ExecutionLogEntry,
    ExecutionPlan,
    PlanExecutionResult,
    PlanPreviewChange,
    RiskLevel,
    RollbackOperation,
    SafetyAssessment,
    UserPlanningMemory,
)
from app.services.assistant.tools import AssistantToolRegistry
from app.services.subscriptions import (
    FeatureName,
    PaywallError,
    commit_usage,
    refund_usage,
    reserve_usage,
    should_skip_basic_ai_tool_usage,
)


class SafetyGuard:
    def assess(self, plan: ExecutionPlan, preview: list[PlanPreviewChange]) -> SafetyAssessment:
        mutating_steps = [
            step for step in plan.steps if step.action in AssistantToolRegistry.MUTATING_TOOLS
        ]
        impacted_events = len(preview)
        reasons: list[str] = []
        risk_level: RiskLevel = "low"

        if plan.requires_confirmation:
            reasons.append(plan.confirmation_reason or "Planner requested confirmation.")
            risk_level = "high"
        if any(step.action == "delete_event" for step in mutating_steps):
            reasons.append("Plan deletes calendar events.")
            risk_level = "high"
        if any(step.action == "duplicate_events" for step in mutating_steps):
            reasons.append("Plan duplicates calendar events across planning windows.")
            risk_level = "high"
        if any(step.action == "batch_move_events" for step in mutating_steps):
            reasons.append("Plan moves multiple calendar events.")
            risk_level = "high"
        if any(step.action == "batch_delete_events" for step in mutating_steps):
            reasons.append("Plan deletes multiple calendar events.")
            risk_level = "high"
        if impacted_events >= 5:
            reasons.append(f"Plan affects {impacted_events} events.")
            risk_level = "critical" if impacted_events >= 10 else "high"
        elif impacted_events >= 3 and risk_level == "low":
            reasons.append(f"Plan affects {impacted_events} events.")
            risk_level = "medium"

        return SafetyAssessment(
            requires_confirmation=bool(reasons),
            risk_level=risk_level,
            reasons=reasons,
            impacted_events=impacted_events,
        )


class ExecutionAgent:
    def __init__(self, tool_registry: AssistantToolRegistry):
        self.tool_registry = tool_registry

    async def preview(
        self,
        *,
        plan: ExecutionPlan,
        user: User,
        db: AsyncSession,
        memory: UserPlanningMemory,
    ) -> PlanExecutionResult:
        preview_changes: list[PlanPreviewChange] = []
        logs: list[ExecutionLogEntry] = []

        for step in plan.steps:
            payload = dict(step.payload)
            if step.action in AssistantToolRegistry.MUTATING_TOOLS:
                payload["dry_run"] = True
            result = await self.tool_registry.execute(
                tool_name=step.action,
                payload=payload,
                user=user,
                db=db,
                memory=memory,
            )
            preview_changes.extend(getattr(result, "preview", []))
            logs.append(
                ExecutionLogEntry(
                    step_id=step.id,
                    tool=step.action,
                    success=True,
                    details=step.purpose,
                )
            )

        return PlanExecutionResult(
            status="preview",
            executed_steps=0,
            preview=preview_changes,
            logs=logs,
            rollback_available=any(
                step.action in AssistantToolRegistry.MUTATING_TOOLS for step in plan.steps
            ),
        )

    async def execute(
        self,
        *,
        plan: ExecutionPlan,
        user: User,
        db: AsyncSession,
        memory: UserPlanningMemory,
        dry_run: bool = False,
    ) -> PlanExecutionResult:
        if dry_run:
            return await self.preview(plan=plan, user=user, db=db, memory=memory)

        rollback_stack: list[RollbackOperation] = []
        logs: list[ExecutionLogEntry] = []
        preview_changes: list[PlanPreviewChange] = []
        created_events: list[CalendarEventSnapshot] = []
        updated_events: list[CalendarEventSnapshot] = []
        deleted_events: list[CalendarEventSnapshot] = []

        try:
            for step in plan.steps:
                result = await self._run_with_retry(
                    tool_name=step.action,
                    payload=step.payload,
                    user=user,
                    db=db,
                    memory=memory,
                )
                preview_changes.extend(getattr(result, "preview", []))
                rollback_stack.extend(getattr(result, "rollback", []))
                created_events.extend(getattr(result, "created_events", []))
                updated_events.extend(
                    [event for event in [getattr(result, "updated_event", None), getattr(result, "moved_event", None)] if event]
                )
                deleted_events.extend(getattr(result, "deleted_events", []))
                logs.append(
                    ExecutionLogEntry(
                        step_id=step.id,
                        tool=step.action,
                        success=True,
                        details=step.purpose,
                    )
                )

            return PlanExecutionResult(
                status="completed",
                executed_steps=len(plan.steps),
                preview=preview_changes,
                logs=logs,
                rollback_available=bool(rollback_stack),
                created_events=created_events,
                updated_events=updated_events,
                deleted_events=deleted_events,
            )
        except Exception as exc:
            rollback_performed = False
            if rollback_stack:
                rollback_performed = await self._rollback(
                    rollback_stack=rollback_stack,
                    user=user,
                    db=db,
                    memory=memory,
                )
            logs.append(
                ExecutionLogEntry(
                    step_id="rollback" if rollback_performed else "failed",
                    tool="fetch_events",
                    success=False,
                    details=str(exc),
                )
            )
            return PlanExecutionResult(
                status="failed",
                executed_steps=len([entry for entry in logs if entry.success]),
                preview=preview_changes,
                logs=logs,
                rollback_performed=rollback_performed,
                rollback_available=bool(rollback_stack),
                error=str(exc),
                created_events=created_events,
                updated_events=updated_events,
                deleted_events=deleted_events,
            )

    async def _run_with_retry(
        self,
        *,
        tool_name: str,
        payload: dict[str, Any],
        user: User,
        db: AsyncSession,
        memory: UserPlanningMemory,
    ) -> BaseModel:
        last_error: Exception | None = None
        for attempt in range(1, settings.assistant_retry_attempts + 1):
            reservation = None
            try:
                if db is None:
                    reservation = None
                elif tool_name in AssistantToolRegistry.MUTATING_TOOLS and not should_skip_basic_ai_tool_usage():
                    reservation = await reserve_usage(db, user, FeatureName.BASIC_AI_ACTION)
                elif tool_name == "optimize_schedule" and not should_skip_basic_ai_tool_usage():
                    reservation = await reserve_usage(db, user, FeatureName.SMART_RESCHEDULING)
                result = await self.tool_registry.execute(
                    tool_name=tool_name,  # type: ignore[arg-type]
                    payload=payload,
                    user=user,
                    db=db,
                    memory=memory,
                )
                await commit_usage(db, reservation)
                return result
            except PaywallError:
                await refund_usage(db, reservation)
                raise
            except ValueError:
                await refund_usage(db, reservation)
                raise
            except Exception as exc:
                await refund_usage(db, reservation)
                last_error = exc
                if attempt >= settings.assistant_retry_attempts:
                    break
                await asyncio.sleep(0.25 * attempt)
        raise RuntimeError(f"{tool_name} failed after retries: {last_error}")

    async def _rollback(
        self,
        *,
        rollback_stack: list[RollbackOperation],
        user: User,
        db: AsyncSession,
        memory: UserPlanningMemory,
    ) -> bool:
        for operation in reversed(rollback_stack):
            payload = dict(operation.payload)
            await self.tool_registry.execute(
                tool_name=operation.action,
                payload=payload,
                user=user,
                db=db,
                memory=memory,
            )
        return True
