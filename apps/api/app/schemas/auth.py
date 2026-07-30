from __future__ import annotations

import uuid

from pydantic import BaseModel


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None = None
    timezone: str = "UTC"
    has_google_calendar: bool = False


class SessionResponse(BaseModel):
    authenticated: bool
    user: UserResponse | None = None
