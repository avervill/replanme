"""Auth-related Pydantic schemas."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None = None
    timezone: str = "UTC"
    has_google_calendar: bool = False

    model_config = {"from_attributes": True}
