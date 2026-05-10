from __future__ import annotations

from enum import StrEnum


class PlanName(StrEnum):
    FREE = "free"
    PRO = "pro"
    ADMIN = "admin"


class SubscriptionStatus(StrEnum):
    NONE = "none"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"


class PaywallReason(StrEnum):
    NO_CREDITS = "NO_CREDITS"
    NOT_ENOUGH_CREDITS = "NOT_ENOUGH_CREDITS"
    FEATURE_LOCKED = "FEATURE_LOCKED"
    MONTHLY_LIMIT_REACHED = "MONTHLY_LIMIT_REACHED"
    SUBSCRIPTION_INACTIVE = "SUBSCRIPTION_INACTIVE"


FREE_SIGNUP_CREDITS = 20
FREE_WEEKLY_REFILL_CREDITS = 5
FREE_MAX_CREDITS = 30
PRO_MONTHLY_REFILL_CREDITS = 300
PRO_MAX_CREDITS = 300

CREDIT_COSTS: dict[str, int] = {
    "QUICK_ADD": 1,
    "SINGLE_EVENT_UPDATE": 1,
    "SINGLE_EVENT_DELETE": 1,
    "SINGLE_EVENT_MOVE": 1,
    "DUPLICATE_DAY": 2,
    "DUPLICATE_WEEK": 4,
    "OPTIMIZE_DAY": 3,
    "OPTIMIZE_WEEK": 5,
    "PLAN_DAY": 3,
    "PLAN_WEEK": 5,
    "PLAN_MONTH": 10,
    "IMAGE_TO_CALENDAR": 5,
    "VOICE_TO_CALENDAR": 2,
    "REGENERATE_PLAN": 2,
    "COMPLEX_MULTI_STEP_ACTION": 5,
}

LOW_CREDIT_THRESHOLD = 3
