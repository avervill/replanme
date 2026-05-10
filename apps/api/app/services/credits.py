from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credit_transaction import CreditTransaction
from app.models.user import User
from app.services.billing_config import (
    FREE_MAX_CREDITS,
    FREE_SIGNUP_CREDITS,
    FREE_WEEKLY_REFILL_CREDITS,
    PRO_MAX_CREDITS,
    PRO_MONTHLY_REFILL_CREDITS,
    PlanName,
)


@dataclass(frozen=True)
class CreditReservation:
    user_id: uuid.UUID
    amount: int
    feature: str | None
    reason: str
    related_planning_request_id: uuid.UUID | None = None
    spent: bool = False


def _now() -> datetime:
    return datetime.now(UTC)


def _normalize_plan(value: str | None) -> PlanName:
    try:
        return PlanName(value or PlanName.FREE)
    except ValueError:
        return PlanName.FREE


def _require_integer_amount(amount: int) -> None:
    if not isinstance(amount, int):
        raise ValueError("Credit amount must be an integer.")


async def get_credit_balance(db: AsyncSession, user_id: uuid.UUID) -> int:
    result = await db.execute(select(User.planning_credits).where(User.id == user_id))
    balance = result.scalar_one_or_none()
    if balance is None:
        raise ValueError("User not found.")
    return int(balance)


async def can_spend_credits(db: AsyncSession, user_id: uuid.UUID, amount: int) -> bool:
    _require_integer_amount(amount)
    if amount < 0:
        raise ValueError("Credit amount must be non-negative.")
    return await get_credit_balance(db, user_id) >= amount


async def _transaction_row(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    amount: int,
    balance_before: int,
    balance_after: int,
    type: str,
    reason: str,
    feature: str | None = None,
    related_planning_request_id: uuid.UUID | None = None,
    created_by_admin_id: uuid.UUID | None = None,
) -> CreditTransaction:
    tx = CreditTransaction(
        user_id=user_id,
        amount=amount,
        balance_before=balance_before,
        balance_after=balance_after,
        type=type,
        reason=reason,
        feature=feature,
        related_planning_request_id=related_planning_request_id,
        created_by_admin_id=created_by_admin_id,
    )
    db.add(tx)
    await db.flush()
    return tx


async def spend_credits(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    amount: int,
    reason: str,
    feature: str | None = None,
    related_planning_request_id: uuid.UUID | None = None,
) -> int:
    _require_integer_amount(amount)
    if amount < 0:
        raise ValueError("Credit spend amount must be non-negative.")
    if amount == 0:
        return await get_credit_balance(db, user_id)

    result = await db.execute(
        update(User)
        .where(User.id == user_id, User.planning_credits >= amount)
        .values(planning_credits=User.planning_credits - amount)
    )
    if result.rowcount == 0:
        raise ValueError("Insufficient planning credits.")

    balance_after = await get_credit_balance(db, user_id)
    balance_before = balance_after + amount
    await _transaction_row(
        db,
        user_id=user_id,
        amount=-amount,
        balance_before=balance_before,
        balance_after=balance_after,
        type="deduct",
        reason=reason,
        feature=feature,
        related_planning_request_id=related_planning_request_id,
    )
    await db.flush()
    return balance_after


async def grant_credits(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    amount: int,
    reason: str,
    admin_id: uuid.UUID | None = None,
    transaction_type: str = "admin_grant",
    feature: str | None = None,
    related_planning_request_id: uuid.UUID | None = None,
    cap: int | None = None,
) -> int:
    _require_integer_amount(amount)
    if amount <= 0:
        raise ValueError("Grant amount must be positive.")
    if not reason.strip():
        raise ValueError("Reason is required.")

    user = await db.get(User, user_id)
    if user is None:
        raise ValueError("User not found.")
    balance_before = int(user.planning_credits or 0)
    balance_after = min(balance_before + amount, cap) if cap is not None else balance_before + amount
    actual_amount = balance_after - balance_before
    if actual_amount <= 0:
        return balance_before
    user.planning_credits = balance_after
    db.add(user)
    await db.flush()
    await _transaction_row(
        db,
        user_id=user_id,
        amount=actual_amount,
        balance_before=balance_before,
        balance_after=balance_after,
        type=transaction_type,
        reason=reason,
        feature=feature,
        related_planning_request_id=related_planning_request_id,
        created_by_admin_id=admin_id,
    )
    return balance_after


async def adjust_credits(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    amount: int,
    reason: str,
    admin_id: uuid.UUID,
) -> int:
    _require_integer_amount(amount)
    if amount == 0:
        raise ValueError("Adjustment amount cannot be zero.")
    if not reason.strip():
        raise ValueError("Reason is required.")
    user = await db.get(User, user_id)
    if user is None:
        raise ValueError("User not found.")
    balance_before = int(user.planning_credits or 0)
    balance_after = balance_before + amount
    user.planning_credits = balance_after
    db.add(user)
    await db.flush()
    await _transaction_row(
        db,
        user_id=user_id,
        amount=amount,
        balance_before=balance_before,
        balance_after=balance_after,
        type="admin_adjustment",
        reason=reason,
        created_by_admin_id=admin_id,
    )
    return balance_after


async def refund_credits(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    amount: int,
    reason: str,
    related_planning_request_id: uuid.UUID | None = None,
    feature: str | None = None,
) -> int:
    _require_integer_amount(amount)
    if amount <= 0:
        raise ValueError("Refund amount must be positive.")
    return await grant_credits(
        db,
        user_id=user_id,
        amount=amount,
        reason=reason,
        transaction_type="refund",
        feature=feature,
        related_planning_request_id=related_planning_request_id,
    )


async def grant_signup_credits_if_needed(db: AsyncSession, user: User) -> None:
    if int(user.planning_credits or 0) > 0:
        return
    result = await db.execute(
        select(CreditTransaction.id).where(
            CreditTransaction.user_id == user.id,
            CreditTransaction.type == "signup_bonus",
        )
    )
    if result.scalar_one_or_none() is not None:
        return
    await grant_credits(
        db,
        user_id=user.id,
        amount=FREE_SIGNUP_CREDITS,
        reason="Signup planning credits",
        transaction_type="signup_bonus",
        cap=FREE_MAX_CREDITS,
    )


async def refill_weekly_free_credits(db: AsyncSession, user_id: uuid.UUID) -> int:
    user = await db.get(User, user_id)
    if user is None:
        raise ValueError("User not found.")
    balance = int(user.planning_credits or 0)
    amount = min(FREE_WEEKLY_REFILL_CREDITS, max(0, FREE_MAX_CREDITS - balance))
    user.credits_last_refilled_at = _now()
    db.add(user)
    await db.flush()
    if amount <= 0:
        return balance
    return await grant_credits(
        db,
        user_id=user_id,
        amount=amount,
        reason="Weekly free planning credits",
        transaction_type="weekly_refill",
        cap=FREE_MAX_CREDITS,
    )


async def refill_monthly_pro_credits(db: AsyncSession, user_id: uuid.UUID) -> int:
    user = await db.get(User, user_id)
    if user is None:
        raise ValueError("User not found.")
    balance = int(user.planning_credits or 0)
    amount = min(PRO_MONTHLY_REFILL_CREDITS, max(0, PRO_MAX_CREDITS - balance))
    user.credits_last_refilled_at = _now()
    db.add(user)
    await db.flush()
    if amount <= 0:
        return balance
    return await grant_credits(
        db,
        user_id=user_id,
        amount=amount,
        reason="Monthly Pro planning credits",
        transaction_type="monthly_pro_refill",
        cap=PRO_MAX_CREDITS,
    )


async def maybe_refill_credits(db: AsyncSession, user_id: uuid.UUID) -> int:
    user = await db.get(User, user_id)
    if user is None:
        raise ValueError("User not found.")
    plan = _normalize_plan(user.plan)
    last = user.credits_last_refilled_at
    now = _now()
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=UTC)

    if plan == PlanName.PRO:
        if last is None or now - last >= timedelta(days=30):
            return await refill_monthly_pro_credits(db, user_id)
    elif plan == PlanName.ADMIN:
        return int(user.planning_credits or 0)
    else:
        if last is None or now - last >= timedelta(days=7):
            return await refill_weekly_free_credits(db, user_id)
    return int(user.planning_credits or 0)
