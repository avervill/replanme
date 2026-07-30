"""In-memory image-to-calendar proposal extraction."""

from __future__ import annotations

import base64
import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from openai import AsyncOpenAI

from app.core.config import settings
from app.core.rate_limit import enforce_rate_limit
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.plans import CalendarChangePlan, CalendarChangePlanDraft
from app.services.plans import save_plan

router = APIRouter()
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}


@router.post("/image", response_model=CalendarChangePlan)
async def import_image(
    request: Request,
    file: UploadFile = File(...),
    timezone: str = "UTC",
    user: User = Depends(get_current_user),
) -> CalendarChangePlan:
    await enforce_rate_limit(request, bucket="image", identity=str(user.id))
    content_type = (file.content_type or "").casefold()
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Upload a PNG, JPEG, or WebP image"
        )
    data = await file.read(settings.max_upload_bytes + 1)
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Image is empty")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Image is too large")

    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
    )
    encoded = base64.b64encode(data).decode()
    response = await client.responses.parse(
        model=settings.ai_complex_model,
        instructions=(
            "Extract calendar events visible in this image. Return a proposal only. Preserve uncertainty in warnings, "
            "never invent unreadable dates, and use the supplied timezone."
        ),
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": f"Build an editable calendar import proposal. Timezone: {timezone}.",
                    },
                    {"type": "input_image", "image_url": f"data:{content_type};base64,{encoded}"},
                ],
            }
        ],
        text_format=CalendarChangePlanDraft,
        reasoning={"effort": "medium"},
        max_output_tokens=1800,
        store=False,
        safety_identifier=hashlib.sha256(f"replanme:{user.id}".encode()).hexdigest()[:64],
    )
    draft = response.output_parsed
    if draft is None:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="No events could be extracted")
    plan = CalendarChangePlan(
        id=uuid.uuid4(),
        summary=draft.summary,
        changes=draft.changes,
        conflicts=draft.conflicts,
        warnings=draft.warnings,
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.plan_ttl_seconds),
    )
    await save_plan(plan, user_id=user.id)
    return plan
