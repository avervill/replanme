from __future__ import annotations

import uuid

from sqlalchemy import JSON, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class CalendarActionAudit(TimestampMixin, Base):
    __tablename__ = "calendar_action_audit"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), index=True)
    change_type: Mapped[str] = mapped_column(String(16))
    provider_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32))
    before_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
