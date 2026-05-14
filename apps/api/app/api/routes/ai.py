"""Multi-agent planning assistant routes."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.ai import (
    CreateEventFromPromptRequest,
    CreateEventFromPromptResponse,
    PlannerPromptRequest,
    PlannerPromptResponse,
    SuggestedAction,
)
from app.schemas.assistant import (
    AssistantMessageRequest,
    AssistantMessageResponse,
    MemoryResponse,
    UserPlanningMemoryUpdate,
)
from app.schemas.calendar import GoogleCalendarEvent
from app.services.assistant import build_assistant_orchestrator
from app.services import analytics
from app.services.assistant.memory import PlanningMemoryService
from app.services.subscriptions import (
    FeatureName,
    PaywallError,
    assert_feature_access,
    classify_prompt_feature_with_gemma,
    commit_usage,
    refund_usage,
    reset_active_billing_feature,
    reserve_usage,
    set_active_billing_feature,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def visible_chat_history_messages(stored_messages: list[dict]) -> list[dict[str, str]]:
    """Return only user-visible chat turns, hiding internal tool traffic."""
    messages: list[dict[str, str]] = []
    for idx, msg in enumerate(stored_messages):
        role = msg.get("role", "assistant")
        content = msg.get("content", "")
        if role not in {"user", "assistant"}:
            continue
        if role == "assistant" and msg.get("tool_calls"):
            continue
        if not isinstance(content, str) or not content.strip():
            continue
        messages.append({
            "id": f"history-{idx}",
            "role": role,
            "text": content,
        })
    return messages


async def get_assistant_service():
    return await build_assistant_orchestrator()


def _to_google_event(event) -> GoogleCalendarEvent:
    return GoogleCalendarEvent(
        id=event.id,
        title=event.title,
        description=event.description,
        start={"dateTime": event.start_at.isoformat(), "timeZone": event.timezone},
        end={"dateTime": event.end_at.isoformat(), "timeZone": event.timezone},
        location=event.location,
        status=event.status,
        html_link=event.html_link,
    )


@router.post("/assistant", response_model=AssistantMessageResponse)
async def assistant_message(
    payload: AssistantMessageRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    assistant=Depends(get_assistant_service),
) -> AssistantMessageResponse:
    has_image_attachment = any(
        attachment.get("kind") == "image" for attachment in payload.attachments
    )
    feature = await classify_prompt_feature_with_gemma(
        payload.prompt,
        has_image_attachment=has_image_attachment,
    )
    await analytics.track_event(db, user.id, "ai_prompt_submitted", {"sessionId": payload.session_id}, feature=feature)
    planning_request = await analytics.track_planning_request(
        db,
        user_id=user.id,
        prompt=payload.prompt,
        intent=None,
        feature=feature,
        estimated_credits=0,
    )
    started_at = time.perf_counter()
    reservation = None
    if feature == FeatureName.BASIC_AI_ACTION:
        await assert_feature_access(db, user, feature)
        planning_request.estimated_credits = 1
        db.add(planning_request)
        await db.flush()
    elif feature is not None:
        try:
            reservation = await reserve_usage(
                db,
                user,
                feature,
                related_planning_request_id=planning_request.id,
            )
            planning_request.estimated_credits = reservation.amount
            db.add(planning_request)
            await db.flush()
        except PaywallError:
            await analytics.update_planning_request(db, planning_request, status="blocked_by_paywall")
            await db.commit()
            raise

    token = set_active_billing_feature(feature if feature != FeatureName.BASIC_AI_ACTION else None)
    try:
        response = await assistant.handle_message(payload=payload, user=user, db=db)
        response.credits = None
        status_value = "failed"
        if response.status == "failed":
            await refund_usage(db, reservation)
            await analytics.update_planning_request(
                db,
                planning_request,
                status="failed",
                model_used=response.model_used,
                latency_ms=int((time.perf_counter() - started_at) * 1000),
                error_message=response.execution.error,
            )
            await analytics.track_event(db, user.id, "planning_failed", {"planningRequestId": str(planning_request.id)}, feature=feature)
            await db.commit()
        else:
            remaining = await commit_usage(db, reservation)
            if reservation and remaining is not None:
                response.credits = {"used": reservation.amount, "remaining": remaining}
            is_free_chat = reservation is None and response.routing.intent in {"CHAT", "SEARCH_EVENTS", "CONFIRMATION_YES", "CONFIRMATION_NO"}
            status_value = "cancelled" if is_free_chat else "draft_created" if response.status == "awaiting_confirmation" else "applied"
            await analytics.update_planning_request(
                db,
                planning_request,
                status=status_value,
                credits_used=reservation.amount if reservation else 0,
                model_used=response.model_used,
                latency_ms=int((time.perf_counter() - started_at) * 1000),
            )
            if status_value != "cancelled":
                await analytics.track_event(
                    db,
                    user.id,
                    "planning_draft_created" if status_value == "draft_created" else "planning_applied_to_calendar",
                    {"planningRequestId": str(planning_request.id)},
                    feature=feature,
                )
            await db.commit()
        return response
    except ValueError as exc:
        await refund_usage(db, reservation)
        await analytics.update_planning_request(db, planning_request, status="failed", error_message=str(exc))
        await db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PaywallError:
        await refund_usage(db, reservation)
        await analytics.update_planning_request(db, planning_request, status="blocked_by_paywall")
        await db.commit()
        raise
    except Exception as exc:
        await refund_usage(db, reservation)
        await analytics.update_planning_request(db, planning_request, status="failed", error_message=str(exc))
        await db.commit()
        logger.exception("Assistant orchestration failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Assistant orchestration failed",
        ) from exc
    finally:
        reset_active_billing_feature(token)


@router.get("/memory", response_model=MemoryResponse)
async def get_memory(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemoryResponse:
    return await PlanningMemoryService().get_memory(db, user)


@router.put("/memory", response_model=MemoryResponse)
async def update_memory(
    payload: UserPlanningMemoryUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemoryResponse:
    return await PlanningMemoryService().update_memory(db, user, payload)


@router.post("/plan", response_model=PlannerPromptResponse)
async def plan_life(
    payload: PlannerPromptRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    assistant=Depends(get_assistant_service),
) -> PlannerPromptResponse:
    feature = FeatureName.WEEKLY_PLANNING if payload.timeframe == "week" else FeatureName.MONTHLY_PLANNING
    reservation = await reserve_usage(db, user, feature)
    token = set_active_billing_feature(feature)
    try:
        response = await assistant.handle_message(
            payload=AssistantMessageRequest(
                prompt=payload.prompt,
                timezone=user.timezone or "UTC",
                preview=True,
                dry_run=True,
            ),
            user=user,
            db=db,
        )
    except Exception:
        await refund_usage(db, reservation)
        raise
    finally:
        reset_active_billing_feature(token)
    if response.status == "failed":
        await refund_usage(db, reservation)
    else:
        await commit_usage(db, reservation)
    return PlannerPromptResponse(
        plan_summary=response.reply,
        actions=[
            SuggestedAction(
                kind="ask_user" if response.safety.requires_confirmation else "protect_focus_block",
                summary=change.details,
            )
            for change in response.execution.preview[:5]
        ]
        or [
            SuggestedAction(
                kind="ask_user",
                summary=response.reply,
            )
        ],
        approval_required=response.safety.requires_confirmation,
    )


@router.post("/create-event", response_model=CreateEventFromPromptResponse)
async def create_event_from_prompt(
    payload: CreateEventFromPromptRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    assistant=Depends(get_assistant_service),
) -> CreateEventFromPromptResponse:
    await assert_feature_access(db, user, FeatureName.BASIC_AI_ACTION)
    response = await assistant.handle_message(
        payload=AssistantMessageRequest(
            prompt=payload.prompt,
            timezone=payload.timezone or user.timezone or "UTC",
            preview=False,
            dry_run=False,
        ),
        user=user,
        db=db,
    )

    if response.execution.created_events:
        events = [_to_google_event(event) for event in response.execution.created_events]
        return CreateEventFromPromptResponse(
            created=True,
            message=response.reply,
            event=events[0],
            events=events,
            extracted=None,
            extracted_events=[],
        )

    return CreateEventFromPromptResponse(
        created=False,
        message=response.reply,
        event=None,
        events=[],
        extracted=None,
        extracted_events=[],
    )


@router.get("/assistant/history")
async def get_chat_history(
    session_id: str,
    user: User = Depends(get_current_user),
    assistant=Depends(get_assistant_service),
):
    """Retrieve stored chat messages for a given session."""
    state = await assistant.state_store.load(user_id=str(user.id), session_id=session_id)
    messages = visible_chat_history_messages(state.messages)
    planning_active = False
    plan_summary = None
    if state.planning_state:
        planning_active = state.planning_state.get("active", False)
        plan_summary = state.planning_state.get("latest_assistant_plan_summary")
    return {
        "session_id": session_id,
        "messages": messages,
        "planning_active": planning_active,
        "plan_summary": plan_summary,
    }


@router.delete("/assistant/history")
async def clear_chat_history(
    session_id: str,
    user: User = Depends(get_current_user),
    assistant=Depends(get_assistant_service),
):
    """Clear chat history and planning state for a given session."""
    await assistant.state_store.clear(user_id=str(user.id), session_id=session_id)
    return {"session_id": session_id, "cleared": True}
