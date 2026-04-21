"""UserSubscription model — S3-03 Entitlement System.

Tracks which plan a user is on, when it started/expires,
and links to payment references for future billing integration.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PlanType(str, PyEnum):
    scout = "scout"          # Free / trial
    ranger = "ranger"        # Basic paid
    hunter = "hunter"        # Pro
    master = "master"        # Enterprise


class UserSubscription(Base):
    """Persistent subscription record for a user."""

    __tablename__ = "user_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    plan_type: Mapped[str] = mapped_column(
        String(20), default=PlanType.scout.value, nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    payment_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
    )
    payment_provider: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
    )
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(),
    )

    # Relationships
    user = relationship("User", foreign_keys=[user_id], lazy="selectin")

    __table_args__ = (
        Index("ix_user_subscriptions_plan_expires", "plan_type", "expires_at"),
    )
