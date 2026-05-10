from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.billing_config import CREDIT_COSTS, LOW_CREDIT_THRESHOLD, PaywallReason, PlanName
from app.services.credits import can_spend_credits, get_credit_balance, maybe_refill_credits


@dataclass
class PaywallCheck:
    allowed: bool
    reason: PaywallReason | None
    feature: str | None
    required_credits: int
    available_credits: int


def normalize_plan(value: str | None) -> PlanName:
    try:
        return PlanName(value or PlanName.FREE)
    except ValueError:
        return PlanName.FREE


def normalize_subscription_status(value: str | None) -> str:
    if value in {"active", "past_due", "cancelled", "none"}:
        return value
    if value in {"inactive", "canceled"}:
        return "none" if value == "inactive" else "cancelled"
    return "none"


def feature_cost(feature: str | None) -> int:
    if not feature:
        return 0
    mapping = {
        "BASIC_AI_ACTION": "QUICK_ADD",
        "WEEKLY_PLANNING": "PLAN_WEEK",
        "MONTHLY_PLANNING": "PLAN_MONTH",
        "IMAGE_TO_CALENDAR": "IMAGE_TO_CALENDAR",
        "VOICE_TO_CALENDAR": "VOICE_TO_CALENDAR",
        "ENERGY_SCHEDULING": "COMPLEX_MULTI_STEP_ACTION",
        "SMART_RESCHEDULING": "OPTIMIZE_WEEK",
        "RECURRING_AI_PLANNING": "PLAN_WEEK",
    }
    return CREDIT_COSTS.get(mapping.get(feature, feature), CREDIT_COSTS["COMPLEX_MULTI_STEP_ACTION"])


def estimate_credits_for_action(intent: str | None, feature: str | None, complexity: int | None = None) -> int:
    if feature:
        return feature_cost(feature)
    if intent in {"simple_chat", "answer_question", "CHAT", "SEARCH_EVENTS", "CONFIRMATION_YES", "CONFIRMATION_NO"}:
        return 0
    if intent in {"create_single_event", "delete_event", "update_event", "move_event"}:
        return CREDIT_COSTS["QUICK_ADD"]
    if intent == "duplicate_period":
        return CREDIT_COSTS["DUPLICATE_WEEK"]
    if intent == "optimize_schedule":
        return CREDIT_COSTS["OPTIMIZE_WEEK"] if (complexity or 0) > 5 else CREDIT_COSTS["OPTIMIZE_DAY"]
    if intent in {"generate_plan", "modify_existing_plan"}:
        if (complexity or 0) > 10:
            return CREDIT_COSTS["PLAN_MONTH"]
        if (complexity or 0) > 5:
            return CREDIT_COSTS["PLAN_WEEK"]
        return CREDIT_COSTS["PLAN_DAY"]
    return 0


async def get_user_entitlements(db: AsyncSession, user_id: uuid.UUID) -> dict[str, Any]:
    user = await db.get(User, user_id)
    if user is None:
        raise ValueError("User not found.")
    await maybe_refill_credits(db, user_id)
    await db.refresh(user)
    plan = normalize_plan(user.plan)
    return {
        "plan": plan.value,
        "subscriptionStatus": normalize_subscription_status(user.subscription_status),
        "planningCredits": int(user.planning_credits or 0),
        "lowCredits": int(user.planning_credits or 0) <= LOW_CREDIT_THRESHOLD,
        "isAdmin": bool(user.is_admin),
    }


async def check_feature_access(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    feature: str | None,
    required_credits: int,
) -> PaywallCheck:
    await maybe_refill_credits(db, user_id)
    available = await get_credit_balance(db, user_id)
    if required_credits <= 0:
        return PaywallCheck(True, None, feature, required_credits, available)
    if available <= 0:
        return PaywallCheck(False, PaywallReason.NO_CREDITS, feature, required_credits, available)
    if not await can_spend_credits(db, user_id, required_credits):
        return PaywallCheck(False, PaywallReason.NOT_ENOUGH_CREDITS, feature, required_credits, available)
    return PaywallCheck(True, None, feature, required_credits, available)


def build_paywall_response(
    *,
    reason: str,
    feature: str | None,
    required_credits: int,
    available_credits: int,
) -> dict[str, Any]:
    if reason in {PaywallReason.NO_CREDITS.value, PaywallReason.NOT_ENOUGH_CREDITS.value}:
        title = "Not enough planning credits"
        description = (
            f"This action needs {required_credits} credits, but you only have {available_credits}. "
            "Upgrade to Pro to get 300 planning credits every month."
        )
        primary_action = "upgrade"
        secondary_action = "simpler_plan"
    else:
        title = "Unlock advanced AI planning"
        description = (
            "This feature is available on Pro. Upgrade to unlock weekly planning, image-to-calendar, "
            "voice-to-calendar, and advanced optimization."
        )
        primary_action = "upgrade"
        secondary_action = "maybe_later"
    return {
        "ok": False,
        "type": "paywall",
        "error": "PAYWALL_REQUIRED",
        "reason": reason,
        "feature": feature,
        "requiredCredits": required_credits,
        "availableCredits": available_credits,
        "message": title,
        "upgradeMessage": description,
        "currentPlan": "free",
        "paywall": {
            "title": title,
            "description": description,
            "primaryAction": primary_action,
            "secondaryAction": secondary_action,
        },
    }
