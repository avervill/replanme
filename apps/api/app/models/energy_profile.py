import uuid
from datetime import time

from sqlalchemy import ForeignKey, String, Time, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class EnergyProfile(TimestampMixin, Base):
    __tablename__ = "energy_profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    peak_start: Mapped[time] = mapped_column(Time)
    peak_end: Mapped[time] = mapped_column(Time)
    slump_start: Mapped[time] = mapped_column(Time)
    slump_end: Mapped[time] = mapped_column(Time)
    chronotype: Mapped[str | None] = mapped_column(String(50), nullable=True)

