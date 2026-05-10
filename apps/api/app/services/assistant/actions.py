"""Typed internal calendar action execution."""

from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import TypeAdapter

from app.schemas.assistant import (
    CreateEventAction,
    CreateEventInput,
    DeleteEventAction,
    DeleteEventInput,
    DuplicateEventsAction,
    DuplicateEventsInput,
    EditEventInput,
    MoveEventAction,
    MoveEventInput,
    UpdateEventAction,
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

CalendarActionAdapter = TypeAdapter(
    CreateEventAction | DeleteEventAction | MoveEventAction | UpdateEventAction | DuplicateEventsAction
)


class CalendarActionExecutor:
    def __init__(self, tool_registry: AssistantToolRegistry):
        self.tool_registry = tool_registry

    async def execute(self, *, action_payload: dict, user, db, memory: UserPlanningMemory):
        action = CalendarActionAdapter.validate_python(action_payload)
        reservation = None
        if not should_skip_basic_ai_tool_usage():
            reservation = await reserve_usage(db, user, FeatureName.BASIC_AI_ACTION)

        try:
            result = await self._execute_reserved(action, user=user, db=db, memory=memory)
            await commit_usage(db, reservation)
            return result
        except PaywallError:
            await refund_usage(db, reservation)
            raise
        except Exception:
            await refund_usage(db, reservation)
            raise

    async def _execute_reserved(self, action, *, user, db, memory: UserPlanningMemory):
        if isinstance(action, CreateEventAction):
            start_at = datetime.fromisoformat(action.payload.start)
            if action.payload.end:
                end_at = datetime.fromisoformat(action.payload.end)
            else:
                end_at = start_at + timedelta(minutes=action.payload.duration_minutes or 60)
            return await self.tool_registry.create_event(
                CreateEventInput(
                    title=action.payload.title,
                    start_at=start_at,
                    end_at=end_at,
                    timezone=getattr(user, "timezone", "UTC") or "UTC",
                    location=action.payload.location,
                    description=action.payload.description,
                ),
                user=user,
                db=db,
                memory=memory,
            )

        if isinstance(action, DeleteEventAction):
            deleted = []
            for event_id in action.payload.event_ids:
                result = await self.tool_registry.delete_event(
                    DeleteEventInput(event_id=event_id),
                    user=user,
                    db=db,
                    memory=memory,
                )
                deleted.extend(result.deleted_events)
            return deleted

        if isinstance(action, MoveEventAction):
            return await self.tool_registry.move_event(
                MoveEventInput(
                    event_id=action.payload.event_id,
                    new_start_at=action.payload.new_start,
                    new_end_at=action.payload.new_end,
                    timezone=getattr(user, "timezone", "UTC") or "UTC",
                ),
                user=user,
                db=db,
                memory=memory,
            )

        if isinstance(action, UpdateEventAction):
            return await self.tool_registry.edit_event(
                EditEventInput(
                    event_id=action.payload.event_id,
                    title=action.payload.title,
                    description=action.payload.description,
                    start_at=datetime.fromisoformat(action.payload.start) if action.payload.start else None,
                    end_at=datetime.fromisoformat(action.payload.end) if action.payload.end else None,
                    timezone=action.payload.timezone or getattr(user, "timezone", "UTC") or "UTC",
                    location=action.payload.location,
                    reminders=action.payload.reminders,
                    metadata=action.payload.metadata,
                ),
                user=user,
                db=db,
                memory=memory,
            )

        return await self.tool_registry.duplicate_events(
            DuplicateEventsInput(
                source_start_at=action.payload.source_range.start,
                source_end_at=action.payload.source_range.end,
                target_start_at=action.payload.target_range.start,
                target_end_at=action.payload.target_range.end,
            ),
            user=user,
            db=db,
            memory=memory,
        )
