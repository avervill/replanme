"""Schemas for temporary assistant uploads and voice transcription."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


UploadKind = Literal["image", "pdf", "text", "audio", "other"]


class UploadedFileResponse(BaseModel):
    id: str
    filename: str
    content_type: str
    size_bytes: int
    kind: UploadKind
    url: str
    text_preview: str | None = None


class VoiceTranscriptResponse(BaseModel):
    transcript: str

