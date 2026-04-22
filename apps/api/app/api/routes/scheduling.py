"""Energy-based scheduling route — authenticated."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.models.user import User
from app.schemas.scheduling import EnergySchedulingRequest, EnergySchedulingResponse
from app.services.scheduler import preview_energy_schedule

router = APIRouter()


@router.post("/energy/preview", response_model=EnergySchedulingResponse)
async def energy_preview(
    payload: EnergySchedulingRequest,
    user: User = Depends(get_current_user),
) -> EnergySchedulingResponse:
    return preview_energy_schedule(payload)
