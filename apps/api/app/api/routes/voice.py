"""Voice-to-calendar route — authenticated."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.voice import VoiceCommandRequest, VoiceCommandResponse
from app.schemas.assistant import AssistantMessageRequest
from app.services.assistant import build_assistant_orchestrator
from app.services import analytics
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

@router.post("/commands/parse", response_model=VoiceCommandResponse)
async def parse_command(
    payload: VoiceCommandRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    assistant=Depends(get_assistant_service),
) -> VoiceCommandResponse:
    # Use the central planner agent to parse the spoken transcript
    reservation = await reserve_usage(db, user, FeatureName.VOICE_TO_CALENDAR)
    token = set_active_billing_feature(FeatureName.VOICE_TO_CALENDAR)
    try:
        response = await assistant.handle_message(
            payload=AssistantMessageRequest(
                prompt=payload.transcript,
                timezone=payload.timezone,
                session_id=None,
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
        await analytics.track_event(
            db,
            user.id,
            "voice_prompt_used",
            {"source": "voice_command"},
            feature=FeatureName.VOICE_TO_CALENDAR,
        )
        await db.commit()
    
    intent = "clarify"
    if response.status == "completed":
        intent = "book_event" # Default if it actually succeeded creating/booking
        
    return VoiceCommandResponse(
        intent=intent,
        summary=response.reply,
        suggested_buffer_minutes=15,
    )
