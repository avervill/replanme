"""Subscription and usage routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.subscription import UsageSummaryResponse
from app.services.subscriptions import build_usage_summary

router = APIRouter()


@router.get("/usage", response_model=UsageSummaryResponse)
async def get_usage_summary(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    summary = await build_usage_summary(db, user)
    await db.commit()
    return summary
