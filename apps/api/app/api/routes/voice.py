"""Voice-to-calendar route — authenticated."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.models.user import User
from app.schemas.voice import VoiceCommandRequest, VoiceCommandResponse
from app.services.voice import parse_voice_command

router = APIRouter()


@router.post("/commands/parse", response_model=VoiceCommandResponse)
async def parse_command(
    payload: VoiceCommandRequest,
    user: User = Depends(get_current_user),
) -> VoiceCommandResponse:
    return parse_voice_command(payload)
