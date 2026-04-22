from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.calendar import GoogleCalendarEvent


class SuggestedAction(BaseModel):
    kind: Literal["create_event", "update_event", "protect_focus_block", "ask_user"]
    summary: str


class PlannerPromptRequest(BaseModel):
    prompt: str = Field(..., min_length=8)
    timeframe: Literal["week", "month", "year"] = "week"
    constraints: list[str] = Field(default_factory=list)


class PlannerPromptResponse(BaseModel):
    plan_summary: str
    actions: list[SuggestedAction]
    approval_required: bool = True


class CreateEventFromPromptRequest(BaseModel):
    prompt: str = Field(..., min_length=4)
    timezone: str = "UTC"


class ExtractedCalendarEvent(BaseModel):
    title: str
    description: str | None = None
    start_at: datetime
    end_at: datetime
    timezone: str = "UTC"
    location: str | None = None


class CreateEventFromPromptResponse(BaseModel):
    created: bool
    message: str
    event: GoogleCalendarEvent | None = None
    events: list[GoogleCalendarEvent] = Field(default_factory=list)
    extracted: ExtractedCalendarEvent | None = None
    extracted_events: list[ExtractedCalendarEvent] = Field(default_factory=list)
