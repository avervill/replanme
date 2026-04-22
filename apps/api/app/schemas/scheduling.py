from datetime import date, time
from typing import Literal

from pydantic import BaseModel, Field


class TaskInput(BaseModel):
    title: str
    estimated_minutes: int = Field(default=60, ge=15, le=480)
    intensity: Literal["low", "medium", "high"] = "medium"


class EnergyWindow(BaseModel):
    peak_start: time
    peak_end: time
    slump_start: time
    slump_end: time


class EnergySchedulingRequest(BaseModel):
    date: date
    timezone: str = "UTC"
    windows: EnergyWindow
    tasks: list[TaskInput]


class ScheduledTaskPreview(BaseModel):
    title: str
    starts_at: str
    ends_at: str
    assigned_energy: Literal["peak", "balanced", "slump"]


class EnergySchedulingResponse(BaseModel):
    scheduled: list[ScheduledTaskPreview]

