"""In-memory recorded voice transcription. It never writes to Calendar."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from openai import AsyncOpenAI
from pydantic import BaseModel

from app.core.config import settings
from app.core.rate_limit import enforce_rate_limit
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter()
ALLOWED_AUDIO_TYPES = {"audio/webm", "audio/mp4", "audio/mpeg", "audio/wav", "audio/ogg", "audio/x-m4a"}
MAX_AUDIO_BYTES = 25 * 1024 * 1024


class TranscriptionResponse(BaseModel):
    transcript: str
    detected_language: str


@router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_voice(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
) -> TranscriptionResponse:
    await enforce_rate_limit(request, bucket="voice", identity=str(user.id))
    content_type = (file.content_type or "").casefold()
    if content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Upload a supported audio recording"
        )
    data = await file.read(MAX_AUDIO_BYTES + 1)
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Recording is empty")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Recording is too large")

    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
    )
    result = await client.audio.transcriptions.create(
        model=settings.transcription_model,
        file=(file.filename or "recording.webm", data, content_type),
        response_format="verbose_json",
    )
    transcript = str(getattr(result, "text", "")).strip()
    if not transcript:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No speech was detected")
    return TranscriptionResponse(
        transcript=transcript, detected_language=str(getattr(result, "language", "und") or "und")
    )
