from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EnergyProfilePayload(BaseModel):
    peakFocusTime: str | list[str]
    lowEnergyTime: str | list[str]
    preferredWorkBlockLength: str | list[str]
    sleepPreference: str | list[str]


class OnboardingSaveRequest(BaseModel):
    role: str = Field(min_length=1, max_length=80)
    mainGoal: str | list[str]
    planningPain: str | list[str]
    energyProfile: EnergyProfilePayload
    calendarIntent: str = Field(min_length=1, max_length=160)
    firstPrompt: str = Field(min_length=1, max_length=4000)


class OnboardingStatusResponse(BaseModel):
    onboardingCompleted: bool
    onboardingSkipped: bool
    onboardingData: dict[str, Any] | None = None
