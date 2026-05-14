import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    plan: Mapped[str] = mapped_column(String(16), default="free", server_default="free", nullable=False)
    planning_credits: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    credits_last_refilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    subscription_status: Mapped[str] = mapped_column(
        String(32),
        default="none",
        server_default="none",
        nullable=False,
    )
    subscription_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    subscription_provider_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subscription_current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    onboarding_skipped: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    onboarding_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
