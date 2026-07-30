from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class CreateChange(BaseModel):
    type: Literal["create"]
    client_ref: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=250)
    start_at: datetime
    end_at: datetime
    timezone: str = "UTC"
    description: str | None = Field(default=None, max_length=2000)
    location: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_range(self):
        if self.start_at >= self.end_at:
            raise ValueError("start_at must be before end_at")
        return self


class UpdateChange(BaseModel):
    type: Literal["update"]
    event_id: str = Field(min_length=1, max_length=500)
    title: str | None = Field(default=None, max_length=250)
    start_at: datetime | None = None
    end_at: datetime | None = None
    timezone: str | None = None
    description: str | None = Field(default=None, max_length=2000)
    location: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_range(self):
        if self.start_at and self.end_at and self.start_at >= self.end_at:
            raise ValueError("start_at must be before end_at")
        return self


class DeleteChange(BaseModel):
    type: Literal["delete"]
    event_id: str = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=250)
    reason: str = Field(min_length=1, max_length=500)


CalendarChange = Annotated[CreateChange | UpdateChange | DeleteChange, Field(discriminator="type")]


class CalendarConflict(BaseModel):
    change_ref: str
    event_id: str | None = None
    summary: str
    severity: Literal["info", "warning", "blocking"] = "warning"


class CalendarChangePlanDraft(BaseModel):
    summary: str = Field(min_length=1, max_length=1000)
    changes: list[CalendarChange] = Field(default_factory=list, max_length=20)
    conflicts: list[CalendarConflict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CalendarChangePlan(CalendarChangePlanDraft):
    id: uuid.UUID
    status: Literal["pending", "applying", "applied", "expired", "failed", "cancelled"] = "pending"
    expires_at: datetime


class ApplyPlanResponse(BaseModel):
    plan: CalendarChangePlan
    applied_event_ids: list[str] = Field(default_factory=list)
    rolled_back: bool = False
