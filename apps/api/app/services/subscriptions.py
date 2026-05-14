"""Plan helpers and compatibility wrappers for credit-based billing."""

from __future__ import annotations

import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.core.config import settings
from app.llm.gemma import GemmaClient
from app.services import analytics
from app.services.billing_config import PlanName, SubscriptionStatus
from app.services.credits import CreditReservation, maybe_refill_credits, spend_credits
from app.services.paywall import (
    build_paywall_response,
    check_feature_access as check_credit_access,
    estimate_credits_for_action,
    feature_cost,
    normalize_plan,
    normalize_subscription_status,
)


class FeatureName(str):
    BASIC_AI_ACTION = "BASIC_AI_ACTION"
    WEEKLY_PLANNING = "WEEKLY_PLANNING"
    MONTHLY_PLANNING = "MONTHLY_PLANNING"
    IMAGE_TO_CALENDAR = "IMAGE_TO_CALENDAR"
    VOICE_TO_CALENDAR = "VOICE_TO_CALENDAR"
    ENERGY_SCHEDULING = "ENERGY_SCHEDULING"
    SMART_RESCHEDULING = "SMART_RESCHEDULING"
    RECURRING_AI_PLANNING = "RECURRING_AI_PLANNING"


ACTIVE_BILLING_FEATURE: ContextVar[str | None] = ContextVar("ACTIVE_BILLING_FEATURE", default=None)


def _feature_value(feature: str | FeatureName | None) -> str | None:
    if feature is None:
        return None
    return str(feature)


def classify_prompt_feature(prompt: str, *, has_image_attachment: bool = False) -> str | None:
    normalized = " ".join(prompt.casefold().split())

    if has_image_attachment or any(
        phrase in normalized
        for phrase in ("from image", "from the image", "schedule image", "schedule photo", "photo to calendar")
    ):
        return FeatureName.IMAGE_TO_CALENDAR

    if any(phrase in normalized for phrase in ("voice", "spoken", "recording", "audio to calendar")):
        return FeatureName.VOICE_TO_CALENDAR

    if any(phrase in normalized for phrase in ("energy level", "energy levels", "high energy", "low energy", "energy-based")):
        return FeatureName.ENERGY_SCHEDULING

    if any(
        phrase in normalized
        for phrase in (
            "missed tasks",
            "unfinished tasks",
            "smart reschedule",
            "fix conflicts",
            "resolve conflicts",
            "optimize my schedule",
            "optimize schedule",
        )
    ):
        return FeatureName.SMART_RESCHEDULING

    if any(phrase in normalized for phrase in ("recurring ai", "every sunday", "automatically plan", "plan next week automatically")):
        return FeatureName.RECURRING_AI_PLANNING

    planning_verbs = ("plan", "build", "organize", "schedule")
    if "month" in normalized and any(verb in normalized for verb in planning_verbs):
        return FeatureName.MONTHLY_PLANNING

    if "week" in normalized and any(verb in normalized for verb in planning_verbs):
        return FeatureName.WEEKLY_PLANNING

    if any(
        verb in normalized
        for verb in (
            "add ",
            "create ",
            "book ",
            "delete ",
            "remove ",
            "move ",
            "duplicate ",
            "edit ",
            "update ",
            "rename ",
            "reschedule ",
        )
    ):
        return FeatureName.BASIC_AI_ACTION

    return None


async def classify_prompt_feature_with_gemma(prompt: str, *, has_image_attachment: bool = False) -> str | None:
    deterministic = classify_prompt_feature(prompt, has_image_attachment=has_image_attachment)
    gemma_json = await GemmaClient().generate_json(
        schema_name="FeatureClassification",
        system_prompt=(
            "Classify which paid feature a calendar assistant prompt should use. Return JSON with "
            "feature and reason. feature must be one of BASIC_AI_ACTION, WEEKLY_PLANNING, "
            "MONTHLY_PLANNING, IMAGE_TO_CALENDAR, VOICE_TO_CALENDAR, ENERGY_SCHEDULING, "
            "SMART_RESCHEDULING, RECURRING_AI_PLANNING, or null. Use null for ordinary chat/search."
        ),
        payload={
            "message": prompt,
            "has_image_attachment": has_image_attachment,
            "deterministic_baseline": deterministic,
        },
        max_output_tokens=settings.nano_max_output_tokens,
    )
    if isinstance(gemma_json, dict):
        feature = gemma_json.get("feature")
        valid = {
            FeatureName.BASIC_AI_ACTION,
            FeatureName.WEEKLY_PLANNING,
            FeatureName.MONTHLY_PLANNING,
            FeatureName.IMAGE_TO_CALENDAR,
            FeatureName.VOICE_TO_CALENDAR,
            FeatureName.ENERGY_SCHEDULING,
            FeatureName.SMART_RESCHEDULING,
            FeatureName.RECURRING_AI_PLANNING,
            None,
        }
        if feature in valid:
            return feature
    return deterministic


def set_active_billing_feature(feature: str | None) -> Token:
    return ACTIVE_BILLING_FEATURE.set(_feature_value(feature))


def reset_active_billing_feature(token: Token) -> None:
    ACTIVE_BILLING_FEATURE.reset(token)


def should_skip_basic_ai_tool_usage() -> bool:
    return ACTIVE_BILLING_FEATURE.get() in {
        FeatureName.WEEKLY_PLANNING,
        FeatureName.MONTHLY_PLANNING,
        FeatureName.IMAGE_TO_CALENDAR,
        FeatureName.VOICE_TO_CALENDAR,
        FeatureName.ENERGY_SCHEDULING,
        FeatureName.SMART_RESCHEDULING,
        FeatureName.RECURRING_AI_PLANNING,
    }


class PaywallError(Exception):
    def __init__(self, payload: dict[str, Any], *, status_code: int = 402) -> None:
        self.payload = payload
        self.status_code = status_code
        super().__init__(payload.get("message") or "Paywall required")


@dataclass
class UsageReservation:
    user_id: uuid.UUID
    feature: str
    amount: int
    reason: str
    related_planning_request_id: uuid.UUID | None = None
    spent: bool = False


def get_user_plan(user: User | object) -> PlanName:
    loaded_plan = getattr(user, "__dict__", {}).get("plan")
    if loaded_plan is not None:
        return normalize_plan(loaded_plan)
    try:
        return normalize_plan(getattr(user, "plan", None))
    except Exception:
        return PlanName.FREE


def get_user_id(user: User | object) -> uuid.UUID:
    loaded_id = getattr(user, "__dict__", {}).get("id")
    if loaded_id is not None:
        return loaded_id
    return getattr(user, "id")


async def check_feature_access(db: AsyncSession, user: User, feature: str | FeatureName) -> dict[str, Any]:
    feature_value = _feature_value(feature)
    amount = feature_cost(feature_value)
    check = await check_credit_access(
        db,
        user_id=get_user_id(user),
        feature=feature_value,
        required_credits=amount,
    )
    if not check.allowed:
        payload = build_paywall_response(
            reason=check.reason.value if check.reason else "NOT_ENOUGH_CREDITS",
            feature=feature_value,
            required_credits=amount,
            available_credits=check.available_credits,
        )
        await analytics.track_paywall_shown(db, get_user_id(user), feature_value, payload["reason"], payload)
        await db.commit()
        raise PaywallError(payload)
    return {
        "allowed": True,
        "currentPlan": get_user_plan(user).value,
        "requiredCredits": amount,
        "availableCredits": check.available_credits,
    }


async def assert_feature_access(db: AsyncSession, user: User, feature: str | FeatureName) -> None:
    await check_feature_access(db, user, feature)


async def reserve_usage(
    db: AsyncSession,
    user: User,
    feature: str | FeatureName,
    *,
    reason: str | None = None,
    related_planning_request_id: uuid.UUID | None = None,
    amount: int | None = None,
) -> UsageReservation:
    feature_value = _feature_value(feature) or FeatureName.BASIC_AI_ACTION
    required = feature_cost(feature_value) if amount is None else amount
    await maybe_refill_credits(db, get_user_id(user))
    check = await check_credit_access(
        db,
        user_id=get_user_id(user),
        feature=feature_value,
        required_credits=required,
    )
    if not check.allowed:
        payload = build_paywall_response(
            reason=check.reason.value if check.reason else "NOT_ENOUGH_CREDITS",
            feature=feature_value,
            required_credits=required,
            available_credits=check.available_credits,
        )
        await analytics.track_paywall_shown(db, get_user_id(user), feature_value, payload["reason"], payload)
        await db.commit()
        raise PaywallError(payload)
    return UsageReservation(
        user_id=get_user_id(user),
        feature=feature_value,
        amount=required,
        reason=reason or f"AI planning action: {feature_value}",
        related_planning_request_id=related_planning_request_id,
    )


async def commit_usage(db: AsyncSession, reservation: UsageReservation | CreditReservation | None) -> int | None:
    if reservation is None or reservation.spent or reservation.amount <= 0:
        return None
    remaining = await spend_credits(
        db,
        user_id=reservation.user_id,
        amount=reservation.amount,
        reason=reservation.reason,
        feature=reservation.feature,
        related_planning_request_id=reservation.related_planning_request_id,
    )
    await analytics.track_event(
        db,
        reservation.user_id,
        "credits_used",
        {
            "amount": reservation.amount,
            "remaining": remaining,
            "planningRequestId": str(reservation.related_planning_request_id) if reservation.related_planning_request_id else None,
        },
        feature=reservation.feature,
    )
    if isinstance(reservation, UsageReservation):
        reservation.spent = True
    await db.commit()
    return remaining


async def refund_usage(db: AsyncSession, reservation: UsageReservation | CreditReservation | None) -> None:
    # Reservations only check access. Credits are spent by commit_usage after success,
    # so failed AI work does not create a deduct/refund transaction pair.
    return None


async def increment_usage(db: AsyncSession, user: User, feature: str | FeatureName) -> None:
    reservation = await reserve_usage(db, user, feature)
    await commit_usage(db, reservation)


async def build_usage_summary(db: AsyncSession, user: User) -> dict[str, Any]:
    await maybe_refill_credits(db, get_user_id(user))
    await db.refresh(user)
    balance = int(user.planning_credits or 0)
    return {
        "plan": get_user_plan(user).value,
        "subscriptionStatus": normalize_subscription_status(getattr(user, "subscription_status", None)),
        "planningCredits": balance,
        "creditsLastRefilledAt": user.credits_last_refilled_at.isoformat() if user.credits_last_refilled_at else None,
        "lowCredits": balance <= 3,
        "usage": {
            "planningCredits": {"used": 0, "limit": balance, "allowed": True},
            "aiActions": {"used": 0, "limit": None, "allowed": True},
            "weeklyPlans": {"used": 0, "limit": None, "allowed": True},
            "imageImports": {"used": 0, "limit": None, "allowed": True},
            "voiceInputs": {"used": 0, "limit": None, "allowed": True},
            "monthlyPlans": {"used": 0, "limit": None, "allowed": True},
            "smartReschedules": {"used": 0, "limit": None, "allowed": True},
            "energySchedules": {"used": 0, "limit": None, "allowed": True},
            "recurringPlans": {"used": 0, "limit": None, "allowed": True},
        },
    }


__all__ = [
    "FeatureName",
    "PaywallError",
    "PlanName",
    "SubscriptionStatus",
    "UsageReservation",
    "assert_feature_access",
    "build_usage_summary",
    "check_feature_access",
    "classify_prompt_feature",
    "classify_prompt_feature_with_gemma",
    "commit_usage",
    "estimate_credits_for_action",
    "get_user_id",
    "get_user_plan",
    "increment_usage",
    "refund_usage",
    "reserve_usage",
    "reset_active_billing_feature",
    "set_active_billing_feature",
    "should_skip_basic_ai_tool_usage",
]
