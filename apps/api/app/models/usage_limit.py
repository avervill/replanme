import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class UsageLimit(TimestampMixin, Base):
    __tablename__ = "usage_limits"
    __table_args__ = (
        UniqueConstraint("user_id", "period_start", "period_end", name="uq_usage_limits_user_period"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ai_actions_used: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    weekly_plans_used: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    image_imports_used: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    voice_inputs_used: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    monthly_plans_used: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    smart_reschedules_used: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    energy_schedules_used: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    recurring_plans_used: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
