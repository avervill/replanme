"""Vision / schedule import route — authenticated."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.vision import ScheduleImportRequest, ScheduleImportResponse, ImportedEventPreview
from app.schemas.assistant import AssistantMessageRequest
from app.services.assistant import build_assistant_orchestrator
from app.services.subscriptions import (
    FeatureName,
    commit_usage,
    refund_usage,
    reset_active_billing_feature,
    reserve_usage,
    set_active_billing_feature,
)

router = APIRouter()

async def get_assistant_service():
    return await build_assistant_orchestrator()

@router.post("/import-preview", response_model=ScheduleImportResponse)
async def import_preview(
    payload: ScheduleImportRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    assistant=Depends(get_assistant_service),
) -> ScheduleImportResponse:
    reservation = await reserve_usage(db, user, FeatureName.IMAGE_TO_CALENDAR)
    token = set_active_billing_feature(FeatureName.IMAGE_TO_CALENDAR)
    prompt = payload.raw_text or f"Please parse this schedule image and create the events for me: {payload.image_url}"
    try:
        response = await assistant.handle_message(
            payload=AssistantMessageRequest(prompt=prompt, timezone=payload.timezone),
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
    
    events = []
    # If agent responded back with created_events memory or tools log, we extract it.
    for msg in response.memory.focus_windows: 
         pass # A proper mapper could go here. For now we just return the reply.
         
    return ScheduleImportResponse(
        source="raw_text" if payload.raw_text else "image_url",
        extracted_events=events,
        approval_required=False,
    )
