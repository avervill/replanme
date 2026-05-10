"""Energy-based scheduling route — authenticated."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.scheduling import EnergySchedulingRequest, EnergySchedulingResponse
from app.services.scheduler import preview_energy_schedule
from app.services.subscriptions import FeatureName, commit_usage, reserve_usage

router = APIRouter()


@router.post("/energy/preview", response_model=EnergySchedulingResponse)
async def energy_preview(
    payload: EnergySchedulingRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EnergySchedulingResponse:
    reservation = await reserve_usage(db, user, FeatureName.ENERGY_SCHEDULING)
    result = preview_energy_schedule(payload)
    await commit_usage(db, reservation)
    return result
