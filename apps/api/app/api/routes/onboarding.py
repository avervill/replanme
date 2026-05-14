from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.onboarding import OnboardingSaveRequest, OnboardingStatusResponse

router = APIRouter()


def _status(user: User) -> OnboardingStatusResponse:
    return OnboardingStatusResponse(
        onboardingCompleted=bool(user.onboarding_completed),
        onboardingSkipped=bool(user.onboarding_skipped),
        onboardingData=user.onboarding_data,
    )


@router.get("/status", response_model=OnboardingStatusResponse)
async def onboarding_status(
    user: User = Depends(get_current_user),
) -> OnboardingStatusResponse:
    return _status(user)


@router.post("/save", response_model=OnboardingStatusResponse)
async def save_onboarding(
    payload: OnboardingSaveRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OnboardingStatusResponse:
    user.onboarding_data = payload.model_dump(mode="json")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _status(user)


@router.post("/complete", response_model=OnboardingStatusResponse)
async def complete_onboarding(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OnboardingStatusResponse:
    user.onboarding_completed = True
    user.onboarding_completed_at = datetime.now(UTC)
    user.onboarding_skipped = False
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _status(user)


@router.post("/skip", response_model=OnboardingStatusResponse)
async def skip_onboarding(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OnboardingStatusResponse:
    user.onboarding_skipped = True
    user.onboarding_completed = True
    user.onboarding_completed_at = datetime.now(UTC)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _status(user)

