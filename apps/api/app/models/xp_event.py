"""XP Event model — time-limited XP multiplier events (2x Happy Hours, etc.)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class XPEvent(Base):
    """Time-limited XP multiplier event."""
    __tablename__ = "xp_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=2.0)
    start_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    end_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
