"""Vision / schedule import route — authenticated."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.models.user import User
from app.schemas.vision import ScheduleImportRequest, ScheduleImportResponse
from app.services.vision import preview_schedule_import

router = APIRouter()


@router.post("/import-preview", response_model=ScheduleImportResponse)
async def import_preview(
    payload: ScheduleImportRequest,
    user: User = Depends(get_current_user),
) -> ScheduleImportResponse:
    return preview_schedule_import(payload)
