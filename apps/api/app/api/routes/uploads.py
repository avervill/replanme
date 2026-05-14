"""Temporary assistant upload and transcription endpoints."""

from __future__ import annotations

import uuid
import base64
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.uploads import UploadedFileResponse, UploadKind, VoiceTranscriptResponse
from app.services.assistant.model_params import completion_token_param
from app.services import analytics
from app.services.subscriptions import FeatureName, commit_usage, refund_usage, reserve_usage

router = APIRouter()

UPLOAD_ROOT = Path("tmp") / "assistant_uploads"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_AUDIO_BYTES = 25 * 1024 * 1024
MAX_TEXT_PREVIEW_CHARS = 1200
MAX_IMAGE_CONTEXT_TOKENS = 300
ALLOWED_CONTENT_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/csv",
    "audio/webm",
    "audio/mp4",
    "audio/mpeg",
    "audio/wav",
    "audio/ogg",
}


def _kind_for_content_type(content_type: str) -> UploadKind:
    if content_type.startswith("image/"):
        return "image"
    if content_type == "application/pdf":
        return "pdf"
    if content_type.startswith("text/"):
        return "text"
    if content_type.startswith("audio/"):
        return "audio"
    return "other"


def _safe_extension(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if len(suffix) > 12:
        return ""
    return suffix


async def _read_limited(file: UploadFile, max_bytes: int) -> bytes:
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File is too large. Max size is {max_bytes // (1024 * 1024)} MB.",
        )
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")
    return data


def _extract_openai_text(response: dict) -> str:
    choices = response.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    return str(content).strip()


async def _extract_image_context(data: bytes, content_type: str) -> str | None:
    if not settings.openai_api_key:
        return None
    encoded = base64.b64encode(data).decode("ascii")
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": settings.openai_model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": (
                                        "Extract readable schedule/calendar information from this uploaded image. "
                                        "Return concise text with event titles, days, dates, start/end times, and locations if visible."
                                    ),
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:{content_type};base64,{encoded}"},
                                },
                            ],
                        }
                    ],
                    **completion_token_param(settings.openai_model, MAX_IMAGE_CONTEXT_TOKENS),
                },
            )
            response.raise_for_status()
    except httpx.HTTPError:
        return None
    text = _extract_openai_text(response.json())
    return text or None


async def _build_response(*, file_id: str, filename: str, content_type: str, data: bytes) -> UploadedFileResponse:
    kind = _kind_for_content_type(content_type)
    text_preview = None
    if kind == "text":
        text_preview = data[:MAX_TEXT_PREVIEW_CHARS].decode("utf-8", errors="replace")
    elif kind == "image":
        text_preview = await _extract_image_context(data, content_type)
    return UploadedFileResponse(
        id=file_id,
        filename=filename,
        content_type=content_type,
        size_bytes=len(data),
        kind=kind,
        url=f"{settings.api_v1_prefix}/uploads/files/{file_id}",
        text_preview=text_preview,
    )


@router.post("", response_model=UploadedFileResponse)
async def upload_assistant_file(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UploadedFileResponse:
    content_type = (file.content_type or "application/octet-stream").lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported file type.")

    data = await _read_limited(file, MAX_AUDIO_BYTES if content_type.startswith("audio/") else MAX_UPLOAD_BYTES)
    try:
        file_id = f"{uuid.uuid4().hex}{_safe_extension(file.filename or '')}"
        user_dir = UPLOAD_ROOT / str(user.id)
        user_dir.mkdir(parents=True, exist_ok=True)
        (user_dir / file_id).write_bytes(data)

        return await _build_response(
            file_id=file_id,
            filename=file.filename or file_id,
            content_type=content_type,
            data=data,
        )
    except Exception:
        raise


@router.get("/files/{file_id}")
async def get_uploaded_file(
    file_id: str,
    user: User = Depends(get_current_user),
) -> FileResponse:
    safe_name = Path(file_id).name
    path = UPLOAD_ROOT / str(user.id) / safe_name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Uploaded file not found.")
    return FileResponse(path)


@router.post("/voice/transcribe", response_model=VoiceTranscriptResponse)
async def transcribe_voice_upload(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VoiceTranscriptResponse:
    content_type = (file.content_type or "application/octet-stream").lower()
    if not content_type.startswith("audio/"):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Upload an audio recording.")
    data = await _read_limited(file, MAX_AUDIO_BYTES)

    if not settings.openai_api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Voice transcription is not configured.")

    filename = file.filename or "recording.webm"
    reservation = await reserve_usage(db, user, FeatureName.VOICE_TO_CALENDAR)
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                data={"model": settings.whisper_model},
                files={"file": (filename, data, content_type)},
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        await refund_usage(db, reservation)
        detail = exc.response.json().get("error", {}).get("message", "Failed to transcribe audio.")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail) from exc
    except httpx.HTTPError as exc:
        await refund_usage(db, reservation)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to transcribe audio.") from exc
    except Exception:
        await refund_usage(db, reservation)
        raise

    transcript = str(response.json().get("text", "")).strip()
    if not transcript:
        await refund_usage(db, reservation)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No speech was detected.")
    await commit_usage(db, reservation)
    await analytics.track_event(
        db,
        user.id,
        "voice_prompt_used",
        {"source": "voice_transcription", "filename": filename},
        feature=FeatureName.VOICE_TO_CALENDAR,
    )
    await db.commit()
    return VoiceTranscriptResponse(transcript=transcript)
