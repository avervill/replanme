"""Typed tool registry for calendar operations."""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.assistant import (
    BatchDeleteEventsInput,
    BatchDeleteEventsResult,
    BatchMoveEventsInput,
    BatchMoveEventsResult,
    CalendarEventSnapshot,
    ConflictItem,
    CreateEventInput,
    CreateEventResult,
    DeleteEventInput,
    DeleteEventResult,
    DetectConflictsInput,
    DetectConflictsResult,
    DuplicateEventsInput,
    DuplicateEventsResult,
    EditEventInput,
    EditEventResult,
    FetchEventsInput,
    FetchEventsResult,
    FindFreeSlotsInput,
    FindFreeSlotsResult,
    FreeSlot,
    MoveEventInput,
    MoveEventResult,
    OptimizationSuggestion,
    OptimizeScheduleInput,
    OptimizeScheduleResult,
    PlanPreviewChange,
    ProposedCalendarEvent,
    RollbackOperation,
    SummarizeScheduleInput,
    SummarizeScheduleResult,
    ToolExecutionMetadata,
    ToolName,
    UserPlanningMemory,
)
from app.services.google_calendar import (
    create_google_event,
    delete_google_event,
    get_google_event,
    list_google_events_in_range,
    update_google_event,
)
from app.services.subscriptions import FeatureName, refund_usage, reserve_usage

logger = logging.getLogger(__name__)


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _google_event_to_snapshot(item: dict[str, Any]) -> CalendarEventSnapshot:
    start = item.get("start", {})
    end = item.get("end", {})
    timezone = start.get("timeZone") or end.get("timeZone") or "UTC"

    start_value = start.get("dateTime") or f"{start.get('date')}T00:00:00+00:00"
    end_value = end.get("dateTime") or f"{end.get('date')}T00:00:00+00:00"

    return CalendarEventSnapshot(
        id=item.get("id", ""),
        title=item.get("summary", "Untitled"),
        description=item.get("description"),
        start_at=_ensure_aware(datetime.fromisoformat(start_value)),
        end_at=_ensure_aware(datetime.fromisoformat(end_value)),
        timezone=timezone,
        location=item.get("location"),
        status=item.get("status", "confirmed"),
        html_link=None, # explicitly strip link to stop AI hallucination outputs
    )


def _snapshot_to_google_body(event: ProposedCalendarEvent | CalendarEventSnapshot) -> dict[str, Any]:
    body = {
        "summary": event.title,
        "description": event.description,
        "start": {
            "dateTime": _ensure_aware(event.start_at).isoformat(),
            "timeZone": event.timezone,
        },
        "end": {
            "dateTime": _ensure_aware(event.end_at).isoformat(),
            "timeZone": event.timezone,
        },
    }
    if event.location:
        body["location"] = event.location
    return body


def _overlaps(
    left_start: datetime,
    left_end: datetime,
    right_start: datetime,
    right_end: datetime,
) -> bool:
    return left_start < right_end and right_start < left_end


def _contains_title(title: str, query: str) -> bool:
    return query.strip().casefold() in title.strip().casefold()


def _normalize_title_query(query: str | None) -> str | None:
    if query is None:
        return None

    normalized = " ".join(query.split()).casefold().strip(" .")
    generic_event_terms = {
        "appointment",
        "appointments",
        "calendar",
        "calendar event",
        "calendar events",
        "event",
        "events",
        "meeting",
        "meetings",
        "schedule",
        "scheduled events",
    }
    if normalized in generic_event_terms:
        return None
    return query


def _same_title(left: str, right: str) -> bool:
    return " ".join(left.split()).casefold() == " ".join(right.split()).casefold()


class AssistantToolRegistry:
    MUTATING_TOOLS: set[str] = {
        "create_event",
        "edit_event",
        "delete_event",
        "duplicate_events",
        "move_event",
        "batch_move_events",
        "batch_delete_events",
    }

    async def _reserve_basic_ai_action(self, *, payload: Any, user: User, db: AsyncSession | None):
        if getattr(payload, "dry_run", False) or db is None:
            return None
        return await reserve_usage(db, user, FeatureName.BASIC_AI_ACTION)

    async def _refund_basic_ai_action(self, db: AsyncSession | None, reservation: Any) -> None:
        if db is not None:
            await refund_usage(db, reservation)

    async def execute(
        self,
        *,
        tool_name: ToolName,
        payload: dict[str, Any],
        user: User,
        db: AsyncSession,
        memory: UserPlanningMemory,
    ) -> Any:
        handlers = {
            "create_event": (CreateEventInput, self.create_event),
            "edit_event": (EditEventInput, self.edit_event),
            "delete_event": (DeleteEventInput, self.delete_event),
            "duplicate_events": (DuplicateEventsInput, self.duplicate_events),
            "fetch_events": (FetchEventsInput, self.fetch_events),
            "move_event": (MoveEventInput, self.move_event),
            "find_free_slots": (FindFreeSlotsInput, self.find_free_slots),
            "summarize_schedule": (SummarizeScheduleInput, self.summarize_schedule),
            "detect_conflicts": (DetectConflictsInput, self.detect_conflicts),
            "optimize_schedule": (OptimizeScheduleInput, self.optimize_schedule),
            "batch_move_events": (BatchMoveEventsInput, self.batch_move_events),
            "batch_delete_events": (BatchDeleteEventsInput, self.batch_delete_events),
        }
        schema, handler = handlers[tool_name]
        return await handler(
            schema.model_validate(payload),
            user=user,
            db=db,
            memory=memory,
        )

    async def fetch_events(
        self,
        payload: FetchEventsInput,
        *,
        user: User,
        db: AsyncSession,
        memory: UserPlanningMemory,
    ) -> FetchEventsResult:
        items = await list_google_events_in_range(
            user.id,
            db,
            start_at=payload.start_at,
            end_at=payload.end_at,
            max_results=payload.max_results,
        )
        events = [_google_event_to_snapshot(item) for item in items]
        query = _normalize_title_query(payload.query)
        if query:
            events = [event for event in events if _contains_title(event.title, query)]
        logger.debug(
            "assistant.fetch_events",
            extra={
                "count": len(events),
                "start_at": payload.start_at.isoformat(),
                "end_at": payload.end_at.isoformat(),
                "query": query,
            },
        )
        return FetchEventsResult(
            success=True,
            metadata=ToolExecutionMetadata(tool="fetch_events", executed=True),
            events=events,
            count=len(events),
        )

    async def get_event(
        self,
        event_id: str,
        *,
        user: User,
        db: AsyncSession,
        memory: UserPlanningMemory,
    ) -> CalendarEventSnapshot:
        event = _google_event_to_snapshot(await get_google_event(user.id, db, event_id=event_id))
        if not event.id:
            raise ValueError("Event was not returned by calendar API")
        return event

    async def create_event(
        self,
        payload: CreateEventInput,
        *,
        user: User,
        db: AsyncSession,
        memory: UserPlanningMemory,
    ) -> CreateEventResult:
        existing = await self.fetch_events(
            FetchEventsInput(start_at=payload.start_at, end_at=payload.end_at),
            user=user,
            db=db,
            memory=memory,
        )
        duplicate = next(
            (
                event
                for event in existing.events
                if _same_title(event.title, payload.title)
                and event.start_at == payload.start_at
                and event.end_at == payload.end_at
            ),
            None,
        )
        if duplicate is not None:
            raise ValueError(
                f"This looks like a duplicate of '{duplicate.title}' ({duplicate.id}). Do you want to keep both?"
            )

        overlaps = [
            event
            for event in existing.events
            if _overlaps(payload.start_at, payload.end_at, event.start_at, event.end_at)
        ]
        conflict_details = ""
        if overlaps:
            conflict_details = " Overlaps with: " + ", ".join(
                f"{event.title} ({event.id}) at {event.start_at.isoformat()}" for event in overlaps[:5]
            )
        preview = [
            PlanPreviewChange(
                action="create_event",
                title=payload.title,
                details=f"Create a new calendar event.{conflict_details}",
                proposed_start_at=payload.start_at,
                proposed_end_at=payload.end_at,
            )
        ]
        if payload.dry_run:
            preview_event = CalendarEventSnapshot(
                id="preview:create_event",
                title=payload.title,
                description=payload.description,
                start_at=payload.start_at,
                end_at=payload.end_at,
                timezone=payload.timezone,
                location=payload.location,
                status="preview",
                html_link=None,
            )
            return CreateEventResult(
                success=True,
                metadata=ToolExecutionMetadata(
                    tool="create_event",
                    executed=False,
                    dry_run=True,
                ),
                created_events=[preview_event],
                preview=preview,
            )

        body = _snapshot_to_google_body(payload)
        body["reminders"] = {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": minutes} for minutes in payload.reminders],
        }
        created = _google_event_to_snapshot(await create_google_event(user.id, db, event_body=body))
        verified = await self.get_event(created.id, user=user, db=db, memory=memory)
        logger.debug(
            "assistant.create_event",
            extra={"event_id": verified.id, "title": verified.title, "overlap_count": len(overlaps)},
        )
        return CreateEventResult(
            success=True,
            metadata=ToolExecutionMetadata(tool="create_event", executed=True),
            created_events=[verified],
            preview=preview,
            rollback=[
                RollbackOperation(
                    action="delete_event",
                    payload={"event_id": verified.id},
                )
            ],
        )

    async def edit_event(
        self,
        payload: EditEventInput,
        *,
        user: User,
        db: AsyncSession,
        memory: UserPlanningMemory,
    ) -> EditEventResult:
        target = await self._resolve_single_event(
            user=user,
            db=db,
            event_id=payload.event_id,
            match_title=payload.match_title,
            start_at=payload.start_at,
            end_at=payload.end_at,
        )
        update_body: dict[str, Any] = {}
        if payload.title is not None:
            update_body["summary"] = payload.title
        if payload.description is not None:
            update_body["description"] = payload.description
        if payload.location is not None:
            update_body["location"] = payload.location
        if payload.reminders is not None:
            update_body["reminders"] = {
                "useDefault": False,
                "overrides": [{"method": "popup", "minutes": minutes} for minutes in payload.reminders],
            }
        if payload.metadata is not None:
            update_body["extendedProperties"] = {"private": payload.metadata}
        if payload.start_at is not None:
            update_body["start"] = {
                "dateTime": payload.start_at.isoformat(),
                "timeZone": payload.timezone or target.timezone,
            }
        if payload.end_at is not None:
            update_body["end"] = {
                "dateTime": payload.end_at.isoformat(),
                "timeZone": payload.timezone or target.timezone,
            }
        proposed_start = payload.start_at or target.start_at
        proposed_end = payload.end_at or target.end_at
        if proposed_end <= proposed_start:
            raise ValueError("Event end time must be after start time")

        move_conflicts: list[CalendarEventSnapshot] = []
        if proposed_start != target.start_at or proposed_end != target.end_at:
            move_conflicts = await self._find_overlaps_for_candidate(
                user=user,
                db=db,
                memory=memory,
                candidate_id=target.id,
                start_at=proposed_start,
                end_at=proposed_end,
            )
        preview = [
            PlanPreviewChange(
                action="edit_event",
                title=payload.title or target.title,
                details=self._mutation_details("Edit an existing calendar event.", move_conflicts),
                current_start_at=target.start_at,
                proposed_start_at=proposed_start,
                proposed_end_at=proposed_end,
            )
        ]
        if payload.dry_run:
            updated = target.model_copy(
                update={
                    "title": payload.title or target.title,
                    "description": payload.description if payload.description is not None else target.description,
                    "location": payload.location if payload.location is not None else target.location,
                    "start_at": proposed_start,
                    "end_at": proposed_end,
                    "timezone": payload.timezone or target.timezone,
                }
            )
            return EditEventResult(
                success=True,
                metadata=ToolExecutionMetadata(tool="edit_event", executed=False, dry_run=True),
                updated_event=updated,
                previous_event=target,
                preview=preview,
            )

        if move_conflicts:
            raise ValueError(
                "This update would create a conflict with "
                + ", ".join(f"{event.title} ({event.id})" for event in move_conflicts)
                + ". Please confirm or choose another time."
            )

        await update_google_event(user.id, db, event_id=target.id, event_body=update_body)
        updated = await self.get_event(target.id, user=user, db=db, memory=memory)
        logger.debug("assistant.edit_event", extra={"event_id": updated.id, "title": updated.title})
        return EditEventResult(
            success=True,
            metadata=ToolExecutionMetadata(tool="edit_event", executed=True),
            updated_event=updated,
            previous_event=target,
            preview=preview,
            rollback=[
                RollbackOperation(
                    action="edit_event",
                    payload={
                        "event_id": target.id,
                        "title": target.title,
                        "description": target.description,
                        "start_at": target.start_at.isoformat(),
                        "end_at": target.end_at.isoformat(),
                        "timezone": target.timezone,
                        "location": target.location,
                    },
                )
            ],
        )

    async def delete_event(
        self,
        payload: DeleteEventInput,
        *,
        user: User,
        db: AsyncSession,
        memory: UserPlanningMemory,
    ) -> DeleteEventResult:
        targets = await self._resolve_events(
            user=user,
            db=db,
            event_id=payload.event_id,
            match_title=payload.match_title,
            start_at=payload.start_at,
            end_at=payload.end_at,
        )
        if not payload.delete_all_matches and len(targets) > 1:
            raise ValueError("Delete matched multiple events; require confirmation or narrower targeting")

        preview = [
            PlanPreviewChange(
                action="delete_event",
                title=event.title,
                details="Delete a calendar event.",
                current_start_at=event.start_at,
            )
            for event in targets
        ]
        if payload.dry_run:
            return DeleteEventResult(
                success=True,
                metadata=ToolExecutionMetadata(tool="delete_event", executed=False, dry_run=True),
                deleted_events=targets,
                preview=preview,
                rollback=[],
            )

        for event in targets:
            await delete_google_event(user.id, db, event_id=event.id)
        logger.debug("assistant.delete_event", extra={"count": len(targets)})

        rollback = [
            RollbackOperation(
                action="create_event",
                payload={
                    "title": event.title,
                    "description": event.description,
                    "start_at": event.start_at.isoformat(),
                    "end_at": event.end_at.isoformat(),
                    "timezone": event.timezone,
                    "location": event.location,
                },
            )
            for event in targets
        ]
        return DeleteEventResult(
            success=True,
            metadata=ToolExecutionMetadata(tool="delete_event", executed=True),
            deleted_events=targets,
            preview=preview,
            rollback=rollback,
        )

    async def duplicate_events(
        self,
        payload: DuplicateEventsInput,
        *,
        user: User,
        db: AsyncSession,
        memory: UserPlanningMemory,
    ) -> DuplicateEventsResult:
        source_items = await list_google_events_in_range(
            user.id,
            db,
            start_at=payload.source_start_at,
            end_at=payload.source_end_at,
        )
        source_events = [_google_event_to_snapshot(item) for item in source_items]
        if payload.title_contains:
            source_events = [
                event for event in source_events if _contains_title(event.title, payload.title_contains)
            ]
        if payload.avoid_title_keywords:
            source_events = [
                event
                for event in source_events
                if not any(keyword.casefold() in event.title.casefold() for keyword in payload.avoid_title_keywords)
            ]

        day_offset = payload.target_start_at - payload.source_start_at
        target_existing = await list_google_events_in_range(
            user.id,
            db,
            start_at=payload.target_start_at,
            end_at=payload.target_end_at or (payload.target_start_at + (payload.source_end_at - payload.source_start_at)),
        )
        target_events = [_google_event_to_snapshot(item) for item in target_existing]

        duplicated: list[CalendarEventSnapshot] = []
        preview: list[PlanPreviewChange] = []
        rollback: list[RollbackOperation] = []
        evening_titles = [value.casefold() for value in payload.move_to_evening_titles]

        for event in source_events:
            new_start = event.start_at + day_offset
            new_end = event.end_at + day_offset
            if any(token in event.title.casefold() for token in evening_titles):
                duration = new_end - new_start
                new_start = self._find_evening_slot(
                    day=new_start.date(),
                    duration=duration,
                    timezone=event.timezone,
                    existing=target_events,
                )
                new_end = new_start + duration

            preview.append(
                PlanPreviewChange(
                    action="duplicate_events",
                    title=event.title,
                    details="Duplicate an event into a new planning window.",
                    current_start_at=event.start_at,
                    proposed_start_at=new_start,
                    proposed_end_at=new_end,
                )
            )

            if payload.dry_run:
                duplicated.append(
                    CalendarEventSnapshot(
                        id=f"preview:duplicate:{event.id}",
                        title=event.title,
                        description=event.description,
                        start_at=new_start,
                        end_at=new_end,
                        timezone=event.timezone,
                        location=event.location,
                        status="preview",
                        html_link=None,
                    )
                )
                continue

            created = _google_event_to_snapshot(
                await create_google_event(
                    user.id,
                    db,
                    event_body=_snapshot_to_google_body(
                        ProposedCalendarEvent(
                            title=event.title,
                            description=event.description,
                            start_at=new_start,
                            end_at=new_end,
                            timezone=event.timezone,
                            location=event.location,
                        )
                    ),
                )
            )
            duplicated.append(created)
            target_events.append(created)
            rollback.append(
                RollbackOperation(
                    action="delete_event",
                    payload={"event_id": created.id},
                )
            )

        return DuplicateEventsResult(
            success=True,
            metadata=ToolExecutionMetadata(
                tool="duplicate_events",
                executed=not payload.dry_run,
                dry_run=payload.dry_run,
            ),
            source_events=source_events,
            duplicated_events=duplicated,
            preview=preview,
            rollback=rollback,
        )

    async def move_event(
        self,
        payload: MoveEventInput,
        *,
        user: User,
        db: AsyncSession,
        memory: UserPlanningMemory,
    ) -> MoveEventResult:
        target = await self._resolve_single_event(
            user=user,
            db=db,
            event_id=payload.event_id,
            match_title=payload.match_title,
            start_at=payload.new_start_at,
            end_at=payload.new_end_at,
        )
        duration = target.end_at - target.start_at
        new_end = payload.new_end_at or (
            payload.new_start_at + duration if payload.keep_duration else target.end_at
        )
        if new_end <= payload.new_start_at:
            raise ValueError("Event end time must be after start time")
        move_conflicts = await self._find_overlaps_for_candidate(
            user=user,
            db=db,
            memory=memory,
            candidate_id=target.id,
            start_at=payload.new_start_at,
            end_at=new_end,
        )
        preview = [
            PlanPreviewChange(
                action="move_event",
                title=target.title,
                details=self._mutation_details("Move an existing event.", move_conflicts),
                current_start_at=target.start_at,
                proposed_start_at=payload.new_start_at,
                proposed_end_at=new_end,
            )
        ]

        if payload.dry_run:
            moved = target.model_copy(
                update={
                    "start_at": payload.new_start_at,
                    "end_at": new_end,
                    "timezone": payload.timezone or target.timezone,
                }
            )
            return MoveEventResult(
                success=True,
                metadata=ToolExecutionMetadata(tool="move_event", executed=False, dry_run=True),
                moved_event=moved,
                previous_event=target,
                preview=preview,
            )

        if move_conflicts:
            raise ValueError(
                "This move would create a conflict with "
                + ", ".join(f"{event.title} ({event.id})" for event in move_conflicts)
                + ". Please confirm or choose another time."
            )

        await update_google_event(
                user.id,
                db,
                event_id=target.id,
                event_body={
                    "start": {
                        "dateTime": payload.new_start_at.isoformat(),
                        "timeZone": payload.timezone or target.timezone,
                    },
                    "end": {
                        "dateTime": new_end.isoformat(),
                        "timeZone": payload.timezone or target.timezone,
                    },
                },
        )
        moved = await self.get_event(target.id, user=user, db=db, memory=memory)
        logger.debug("assistant.move_event", extra={"event_id": moved.id, "title": moved.title})
        return MoveEventResult(
            success=True,
            metadata=ToolExecutionMetadata(tool="move_event", executed=True),
            moved_event=moved,
            previous_event=target,
            preview=preview,
            rollback=[
                RollbackOperation(
                    action="edit_event",
                    payload={
                        "event_id": target.id,
                        "start_at": target.start_at.isoformat(),
                        "end_at": target.end_at.isoformat(),
                        "timezone": target.timezone,
                    },
                )
            ],
        )

    async def batch_move_events(
        self,
        payload: BatchMoveEventsInput,
        *,
        user: User,
        db: AsyncSession,
        memory: UserPlanningMemory,
    ) -> BatchMoveEventsResult:
        fetch = await self.fetch_events(
            FetchEventsInput(
                start_at=payload.start_at,
                end_at=payload.end_at,
                query=payload.query,
            ),
            user=user,
            db=db,
            memory=memory,
        )
        offset = timedelta(minutes=payload.offset_minutes)
        preview: list[PlanPreviewChange] = []
        moved_events: list[CalendarEventSnapshot] = []
        rollback: list[RollbackOperation] = []

        for event in fetch.events:
            new_start = event.start_at + offset
            new_end = event.end_at + offset
            preview.append(
                PlanPreviewChange(
                    action="batch_move_events",
                    title=event.title,
                    details=f"Move event by {payload.offset_minutes} minutes.",
                    current_start_at=event.start_at,
                    proposed_start_at=new_start,
                    proposed_end_at=new_end,
                )
            )

            moved = event.model_copy(
                update={
                    "start_at": new_start,
                    "end_at": new_end,
                }
            )
            moved_events.append(moved)

            if payload.dry_run:
                continue

        conflicts = await self._find_conflicts_after_batch_move(
            user=user,
            db=db,
            memory=memory,
            original_events=fetch.events,
            moved_events=moved_events,
            start_at=min([payload.start_at, *[event.start_at for event in moved_events]], default=payload.start_at),
            end_at=max([payload.end_at, *[event.end_at for event in moved_events]], default=payload.end_at),
        )
        if conflicts:
            detail = ", ".join(
                f"{conflict.title} ({conflict.event_id}) with {conflict.conflicting_with} ({conflict.conflicting_event_id})"
                for conflict in conflicts[:5]
            )
            if payload.dry_run:
                preview.append(
                    PlanPreviewChange(
                        action="batch_move_events",
                        title="Conflict warning",
                        details=f"Simulated batch move would create conflicts: {detail}",
                    )
                )
            else:
                raise ValueError(f"Batch move would create conflicts: {detail}. Please review before applying.")

        if payload.dry_run:
            return BatchMoveEventsResult(
                success=True,
                metadata=ToolExecutionMetadata(
                    tool="batch_move_events",
                    executed=False,
                    dry_run=True,
                ),
                moved_events=moved_events,
                count=len(moved_events),
                preview=preview,
                rollback=[],
            )

        for event, moved in zip(fetch.events, moved_events, strict=False):

            await update_google_event(
                user.id,
                db,
                event_id=event.id,
                event_body={
                    "start": {
                        "dateTime": moved.start_at.isoformat(),
                        "timeZone": event.timezone,
                    },
                    "end": {
                        "dateTime": moved.end_at.isoformat(),
                        "timeZone": event.timezone,
                    },
                },
            )
            rollback.append(
                RollbackOperation(
                    action="edit_event",
                    payload={
                        "event_id": event.id,
                        "start_at": event.start_at.isoformat(),
                        "end_at": event.end_at.isoformat(),
                        "timezone": event.timezone,
                    },
                )
            )
        logger.debug("assistant.batch_move_events", extra={"count": len(moved_events)})

        return BatchMoveEventsResult(
            success=True,
            metadata=ToolExecutionMetadata(
                tool="batch_move_events",
                executed=not payload.dry_run,
                dry_run=payload.dry_run,
            ),
            moved_events=moved_events,
            count=len(moved_events),
            preview=preview,
            rollback=rollback,
        )

    async def batch_delete_events(
        self,
        payload: BatchDeleteEventsInput,
        *,
        user: User,
        db: AsyncSession,
        memory: UserPlanningMemory,
    ) -> BatchDeleteEventsResult:
        fetch = await self.fetch_events(
            FetchEventsInput(
                start_at=payload.start_at,
                end_at=payload.end_at,
                query=payload.query,
            ),
            user=user,
            db=db,
            memory=memory,
        )
        targets = [
            event
            for event in fetch.events
            if self._matches_time_filter(event.start_at.time(), payload.time_filter)
        ]
        preview = [
            PlanPreviewChange(
                action="batch_delete_events",
                title=event.title,
                details="Delete event as part of a batch operation.",
                current_start_at=event.start_at,
            )
            for event in targets
        ]

        if not payload.dry_run:
            for event in targets:
                await delete_google_event(user.id, db, event_id=event.id)
            logger.debug("assistant.batch_delete_events", extra={"count": len(targets)})

        rollback = [] if payload.dry_run else [
            RollbackOperation(
                action="create_event",
                payload={
                    "title": event.title,
                    "description": event.description,
                    "start_at": event.start_at.isoformat(),
                    "end_at": event.end_at.isoformat(),
                    "timezone": event.timezone,
                    "location": event.location,
                },
            )
            for event in targets
        ]
        return BatchDeleteEventsResult(
            success=True,
            metadata=ToolExecutionMetadata(
                tool="batch_delete_events",
                executed=not payload.dry_run,
                dry_run=payload.dry_run,
            ),
            deleted_events=targets,
            count=len(targets),
            preview=preview,
            rollback=rollback,
        )

    async def find_free_slots(
        self,
        payload: FindFreeSlotsInput,
        *,
        user: User,
        db: AsyncSession,
        memory: UserPlanningMemory,
    ) -> FindFreeSlotsResult:
        fetch = await self.fetch_events(
            FetchEventsInput(start_at=payload.start_at, end_at=payload.end_at),
            user=user,
            db=db,
            memory=memory,
        )
        slot_duration = timedelta(minutes=payload.slot_minutes)
        events = sorted(fetch.events, key=lambda event: event.start_at)
        cursor = payload.start_at
        slots: list[FreeSlot] = []

        while cursor + slot_duration <= payload.end_at and len(slots) < payload.max_slots:
            day_start, day_end = self._working_window(cursor.date(), memory, payload.working_hours_only)
            if cursor < day_start:
                cursor = day_start
            if cursor + slot_duration > day_end:
                cursor = datetime.combine(
                    cursor.date() + timedelta(days=1),
                    time.min,
                    tzinfo=cursor.tzinfo,
                )
                continue

            blocking = next(
                (
                    event
                    for event in events
                    if _overlaps(cursor, cursor + slot_duration, event.start_at, event.end_at)
                ),
                None,
            )
            if blocking is None:
                slots.append(
                    FreeSlot(
                        start_at=cursor,
                        end_at=cursor + slot_duration,
                        timezone=user.timezone,
                        score=self._energy_score(cursor, memory, payload.preferred_band),
                        energy_band=self._classify_energy(cursor.time(), memory),
                    )
                )
                cursor += slot_duration + timedelta(minutes=memory.preferred_break_minutes)
            else:
                cursor = max(cursor + timedelta(minutes=15), blocking.end_at)

        return FindFreeSlotsResult(
            success=True,
            metadata=ToolExecutionMetadata(tool="find_free_slots", executed=True),
            slots=sorted(slots, key=lambda slot: slot.score, reverse=True),
        )

    async def summarize_schedule(
        self,
        payload: SummarizeScheduleInput,
        *,
        user: User,
        db: AsyncSession,
        memory: UserPlanningMemory,
    ) -> SummarizeScheduleResult:
        fetch = await self.fetch_events(
            FetchEventsInput(start_at=payload.start_at, end_at=payload.end_at),
            user=user,
            db=db,
            memory=memory,
        )
        by_day: Counter[str] = Counter(event.start_at.date().isoformat() for event in fetch.events)
        busiest = by_day.most_common(1)[0][0] if by_day else None
        summary = (
            f"You have {fetch.count} events scheduled between "
            f"{payload.start_at.date().isoformat()} and {payload.end_at.date().isoformat()}."
        )
        if busiest:
            summary += f" Busiest day: {busiest}."
        return SummarizeScheduleResult(
            success=True,
            metadata=ToolExecutionMetadata(tool="summarize_schedule", executed=True),
            summary=summary,
            busiest_day=busiest,
            event_count=fetch.count,
            events=fetch.events if payload.include_events else [],
        )

    async def detect_conflicts(
        self,
        payload: DetectConflictsInput,
        *,
        user: User,
        db: AsyncSession,
        memory: UserPlanningMemory,
    ) -> DetectConflictsResult:
        candidates = payload.candidate_events
        if not candidates and payload.start_at and payload.end_at:
            fetch = await self.fetch_events(
                FetchEventsInput(start_at=payload.start_at, end_at=payload.end_at),
                user=user,
                db=db,
                memory=memory,
            )
            conflicts = self._detect_all_conflicts(fetch.events)
            logger.debug("assistant.detect_conflicts", extra={"count": len(conflicts)})
            return DetectConflictsResult(
                success=True,
                metadata=ToolExecutionMetadata(tool="detect_conflicts", executed=True),
                has_conflicts=bool(conflicts),
                conflicts=conflicts,
            )

        start_at = payload.start_at or min(event.start_at for event in candidates)
        end_at = payload.end_at or max(event.end_at for event in candidates)
        fetch = await self.fetch_events(
            FetchEventsInput(start_at=start_at, end_at=end_at),
            user=user,
            db=db,
            memory=memory,
        )
        conflicts: list[ConflictItem] = []

        for candidate in candidates:
            for existing in fetch.events:
                if _overlaps(candidate.start_at, candidate.end_at, existing.start_at, existing.end_at):
                    conflicts.append(
                        ConflictItem(
                            event_id=None,
                            title=candidate.title,
                            conflicting_event_id=existing.id,
                            conflicting_with=existing.title,
                            start_at=max(candidate.start_at, existing.start_at),
                            end_at=min(candidate.end_at, existing.end_at),
                            severity="high",
                        )
            )

        logger.debug("assistant.detect_conflicts", extra={"count": len(conflicts)})
        return DetectConflictsResult(
            success=True,
            metadata=ToolExecutionMetadata(tool="detect_conflicts", executed=True),
            has_conflicts=bool(conflicts),
            conflicts=conflicts,
        )

    async def optimize_schedule(
        self,
        payload: OptimizeScheduleInput,
        *,
        user: User,
        db: AsyncSession,
        memory: UserPlanningMemory,
    ) -> OptimizeScheduleResult:
        fetch = await self.fetch_events(
            FetchEventsInput(start_at=payload.start_at, end_at=payload.end_at),
            user=user,
            db=db,
            memory=memory,
        )
        timeline = sorted(fetch.events, key=lambda event: (event.start_at, event.end_at))
        global_conflicts = self._detect_all_conflicts(timeline)
        movable = [
            event
            for event in timeline
            if not payload.task_titles or any(_contains_title(event.title, name) for name in payload.task_titles)
        ]
        suggestions: list[OptimizationSuggestion] = []
        preview: list[PlanPreviewChange] = []

        planned_events = timeline[:]
        for conflict in global_conflicts:
            if not conflict.event_id or not conflict.conflicting_event_id:
                continue
            left = next((event for event in planned_events if event.id == conflict.event_id), None)
            right = next((event for event in planned_events if event.id == conflict.conflicting_event_id), None)
            if left is None or right is None:
                continue
            target = right if right.start_at >= left.start_at else left
            duration = target.end_at - target.start_at
            slot_start = self._find_first_available_slot(
                target=target,
                events=planned_events,
                window_start=payload.start_at,
                window_end=payload.end_at,
                duration=duration,
            )
            if slot_start is None:
                continue
            suggested = target.model_copy(update={"start_at": slot_start, "end_at": slot_start + duration})
            planned_events = [
                suggested if event.id == target.id else event
                for event in planned_events
            ]
            suggestion = OptimizationSuggestion(
                title=target.title,
                current_start_at=target.start_at,
                suggested_start_at=suggested.start_at,
                suggested_end_at=suggested.end_at,
                reason="Resolve overlap with the smallest safe move found in the selected window.",
            )
            suggestions.append(suggestion)
            preview.append(
                PlanPreviewChange(
                    action="optimize_schedule",
                    title=target.title,
                    details=suggestion.reason,
                    current_start_at=target.start_at,
                    proposed_start_at=suggested.start_at,
                    proposed_end_at=suggested.end_at,
                )
            )

        free_slots = await self.find_free_slots(
            FindFreeSlotsInput(
                start_at=payload.start_at,
                end_at=payload.end_at,
                slot_minutes=90,
                max_slots=max(len(movable) * 2, 4),
                preferred_band="high",
            ),
            user=user,
            db=db,
            memory=memory,
        )

        for event in movable:
            desired_band = "high" if any(
                _contains_title(event.title, name) for name in payload.focus_only_titles
            ) else "medium"
            current_band = self._classify_energy(event.start_at.time(), memory)
            if desired_band == "high" and current_band == "high":
                continue

            duration = event.end_at - event.start_at
            slot = next(
                (
                    candidate
                    for candidate in free_slots.slots
                    if candidate.energy_band == desired_band
                    and candidate.end_at - candidate.start_at >= duration
                ),
                None,
            )
            if slot is None:
                continue

            suggestion = OptimizationSuggestion(
                title=event.title,
                current_start_at=event.start_at,
                suggested_start_at=slot.start_at,
                suggested_end_at=slot.start_at + duration,
                reason="Better energy fit and more balanced spacing.",
            )
            suggestions.append(suggestion)
            preview.append(
                PlanPreviewChange(
                    action="optimize_schedule",
                    title=event.title,
                    details=suggestion.reason,
                    current_start_at=event.start_at,
                    proposed_start_at=suggestion.suggested_start_at,
                    proposed_end_at=suggestion.suggested_end_at,
                )
            )

        return OptimizeScheduleResult(
            success=True,
            metadata=ToolExecutionMetadata(
                tool="optimize_schedule",
                executed=not payload.dry_run,
                dry_run=payload.dry_run,
            ),
            suggestions=suggestions,
            preview=preview,
        )

    async def _find_overlaps_for_candidate(
        self,
        *,
        user: User,
        db: AsyncSession,
        memory: UserPlanningMemory,
        candidate_id: str,
        start_at: datetime,
        end_at: datetime,
    ) -> list[CalendarEventSnapshot]:
        fetch = await self.fetch_events(
            FetchEventsInput(start_at=start_at, end_at=end_at),
            user=user,
            db=db,
            memory=memory,
        )
        return [
            event
            for event in fetch.events
            if event.id != candidate_id and _overlaps(start_at, end_at, event.start_at, event.end_at)
        ]

    async def _find_conflicts_after_batch_move(
        self,
        *,
        user: User,
        db: AsyncSession,
        memory: UserPlanningMemory,
        original_events: list[CalendarEventSnapshot],
        moved_events: list[CalendarEventSnapshot],
        start_at: datetime,
        end_at: datetime,
    ) -> list[ConflictItem]:
        moved_by_id = {event.id: event for event in moved_events}
        fetch = await self.fetch_events(
            FetchEventsInput(start_at=start_at, end_at=end_at),
            user=user,
            db=db,
            memory=memory,
        )
        simulated = [
            moved_by_id.get(event.id, event)
            for event in fetch.events
            if event.id not in {original.id for original in original_events} or event.id in moved_by_id
        ]
        for moved in moved_events:
            if all(event.id != moved.id for event in simulated):
                simulated.append(moved)
        return self._detect_all_conflicts(simulated)

    def _detect_all_conflicts(self, events: list[CalendarEventSnapshot]) -> list[ConflictItem]:
        conflicts: list[ConflictItem] = []
        ordered = sorted(events, key=lambda event: (event.start_at, event.end_at, event.id))
        for index, left in enumerate(ordered):
            for right in ordered[index + 1:]:
                if right.start_at >= left.end_at:
                    break
                if _overlaps(left.start_at, left.end_at, right.start_at, right.end_at):
                    conflicts.append(
                        ConflictItem(
                            event_id=left.id,
                            title=left.title,
                            conflicting_event_id=right.id,
                            conflicting_with=right.title,
                            start_at=max(left.start_at, right.start_at),
                            end_at=min(left.end_at, right.end_at),
                            severity="high",
                        )
                    )
        return conflicts

    def _find_first_available_slot(
        self,
        *,
        target: CalendarEventSnapshot,
        events: list[CalendarEventSnapshot],
        window_start: datetime,
        window_end: datetime,
        duration: timedelta,
    ) -> datetime | None:
        candidates: list[datetime] = [target.end_at]
        candidates.extend(event.end_at for event in events if event.id != target.id)
        candidates.extend(event.start_at - duration for event in events if event.id != target.id)
        valid_candidates = sorted(
            {
                candidate
                for candidate in candidates
                if window_start <= candidate and candidate + duration <= window_end
            },
            key=lambda candidate: abs((candidate - target.start_at).total_seconds()),
        )
        blocking_events = [event for event in events if event.id != target.id]
        for candidate in valid_candidates:
            if not any(
                _overlaps(candidate, candidate + duration, event.start_at, event.end_at)
                for event in blocking_events
            ):
                return candidate
        return None

    def _mutation_details(self, base: str, conflicts: list[CalendarEventSnapshot]) -> str:
        if not conflicts:
            return base
        return base + " Simulated conflict: " + ", ".join(
            f"{event.title} ({event.id}) at {event.start_at.isoformat()}" for event in conflicts
        )

    async def _resolve_single_event(
        self,
        *,
        user: User,
        db: AsyncSession,
        event_id: str | None,
        match_title: str | None,
        start_at: datetime | None,
        end_at: datetime | None,
    ) -> CalendarEventSnapshot:
        events = await self._resolve_events(
            user=user,
            db=db,
            event_id=event_id,
            match_title=match_title,
            start_at=start_at,
            end_at=end_at,
        )
        if len(events) != 1:
            raise ValueError("Expected exactly one target event")
        return events[0]

    async def _resolve_events(
        self,
        *,
        user: User,
        db: AsyncSession,
        event_id: str | None,
        match_title: str | None,
        start_at: datetime | None,
        end_at: datetime | None,
    ) -> list[CalendarEventSnapshot]:
        if event_id:
            return [_google_event_to_snapshot(await get_google_event(user.id, db, event_id=event_id))]

        if not match_title:
            raise ValueError("Event resolution requires event_id or match_title")

        lower_bound = start_at or datetime.now(UTC) - timedelta(days=30)
        upper_bound = end_at or datetime.now(UTC) + timedelta(days=60)
        items = await list_google_events_in_range(
            user.id,
            db,
            start_at=lower_bound,
            end_at=upper_bound,
        )
        matches = [
            _google_event_to_snapshot(item)
            for item in items
            if _contains_title(item.get("summary", ""), match_title)
        ]
        if not matches:
            raise ValueError(f"No calendar events matched '{match_title}'")
        return matches

    def _find_evening_slot(
        self,
        *,
        day: date,
        duration: timedelta,
        timezone: str,
        existing: list[CalendarEventSnapshot],
    ) -> datetime:
        cursor = datetime.combine(day, time(hour=18), tzinfo=UTC)
        cutoff = datetime.combine(day, time(hour=22), tzinfo=UTC)
        while cursor + duration <= cutoff:
            if not any(
                _overlaps(cursor, cursor + duration, event.start_at, event.end_at)
                for event in existing
            ):
                return cursor
            cursor += timedelta(minutes=30)
        return datetime.combine(day, time(hour=19), tzinfo=UTC)

    def _working_window(
        self,
        target_day: date,
        memory: UserPlanningMemory,
        working_hours_only: bool,
    ) -> tuple[datetime, datetime]:
        start_time = memory.workday_start if working_hours_only else memory.wake_time
        end_time = memory.workday_end if working_hours_only else memory.sleep_time
        return (
            datetime.combine(target_day, start_time, tzinfo=UTC),
            datetime.combine(target_day, end_time, tzinfo=UTC),
        )

    def _classify_energy(self, moment: time, memory: UserPlanningMemory) -> str:
        if any(window.start <= moment <= window.end for window in memory.high_energy_windows):
            return "high"
        if any(window.start <= moment <= window.end for window in memory.low_energy_windows):
            return "low"
        return "medium"

    def _matches_time_filter(self, moment: time, time_filter: str | None) -> bool:
        if not time_filter:
            return True
        normalized = time_filter.strip().casefold()
        if normalized == "morning":
            return time(hour=5) <= moment < time(hour=12)
        if normalized == "afternoon":
            return time(hour=12) <= moment < time(hour=18)
        if normalized == "evening":
            return time(hour=18) <= moment <= time(hour=23, minute=59, second=59)
        return True

    def _energy_score(
        self,
        slot_start: datetime,
        memory: UserPlanningMemory,
        preferred_band: str | None,
    ) -> float:
        band = self._classify_energy(slot_start.time(), memory)
        if preferred_band is None:
            return {"high": 0.9, "medium": 0.7, "low": 0.5}[band]
        if band == preferred_band:
            return 0.95
        if preferred_band == "high" and band == "medium":
            return 0.7
        if preferred_band == "medium" and band == "high":
            return 0.8
        return 0.45
