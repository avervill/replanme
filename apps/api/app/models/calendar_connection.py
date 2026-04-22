"""CalendarConnection model — stores encrypted Google OAuth tokens."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class CalendarConnection(TimestampMixin, Base):
    __tablename__ = "calendar_connections"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(64), default="google")
    external_email: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="active")
    scopes: Mapped[str] = mapped_column(String(500))

    # Encrypted Google OAuth tokens
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
