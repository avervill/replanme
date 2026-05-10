from __future__ import annotations

import uuid

from sqlalchemy import JSON, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class PlanningMemory(TimestampMixin, Base):
    __tablename__ = "planning_memories"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        unique=True,
    )
    memory: Mapped[dict] = mapped_column(JSON, default=dict)

