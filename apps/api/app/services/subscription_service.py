from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.billing_config import PlanName
from app.services.credits import refill_monthly_pro_credits
from app.services.paywall import normalize_plan


async def get_user_plan(db: AsyncSession, user_id: uuid.UUID) -> PlanName:
    user = await db.get(User, user_id)
    if user is None:
        raise ValueError("User not found.")
    return normalize_plan(user.plan)


async def set_user_plan(db: AsyncSession, user_id: uuid.UUID, plan: str, admin_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise ValueError("User not found.")
    normalized = normalize_plan(plan)
    user.plan = normalized.value
    user.subscription_status = "active" if normalized in {PlanName.PRO, PlanName.ADMIN} else "none"
    user.subscription_provider = "manual"
    db.add(user)
    await db.flush()
    if normalized == PlanName.PRO:
        await refill_monthly_pro_credits(db, user_id)
    return user


async def is_pro(db: AsyncSession, user_id: uuid.UUID) -> bool:
    return await get_user_plan(db, user_id) == PlanName.PRO


async def apply_monthly_pro_credits(db: AsyncSession, user_id: uuid.UUID) -> int:
    return await refill_monthly_pro_credits(db, user_id)
