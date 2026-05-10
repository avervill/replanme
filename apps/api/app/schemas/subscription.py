from __future__ import annotations

from datetime import datetime
import uuid
from typing import Literal

from pydantic import BaseModel, Field


class UsageMetric(BaseModel):
    used: int
    limit: int | None = None
    allowed: bool = True


class UsageSummaryResponse(BaseModel):
    plan: Literal["free", "pro", "admin"]
    subscriptionStatus: str
    planningCredits: int = 0
    creditsLastRefilledAt: datetime | None = None
    lowCredits: bool = False
    periodStart: datetime | None = None
    periodEnd: datetime | None = None
    usage: dict[str, UsageMetric]


class AdminPlanUpdateRequest(BaseModel):
    plan: Literal["free", "pro", "admin"]
    subscriptionStatus: Literal["none", "active", "past_due", "cancelled", "inactive", "trialing", "canceled"] | None = Field(
        default=None
    )


class AdminCreditChangeRequest(BaseModel):
    amount: int
    reason: str = Field(min_length=1)


class AdminUserSummary(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None = None
    plan: str
    planning_credits: int
    is_admin: bool
    subscription_status: str
    has_google_calendar: bool = False
    total_planning_requests: int = 0
    total_credits_used: int = 0
    created_at: datetime


class AdminUserDetail(AdminUserSummary):
    credit_transactions: list[dict] = []
    planning_requests: list[dict] = []
