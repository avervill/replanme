from __future__ import annotations

from pydantic import BaseModel, Field


class AssistantMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
    timezone: str = Field(default="UTC", max_length=64)
    range_start: str | None = None
    range_end: str | None = None
