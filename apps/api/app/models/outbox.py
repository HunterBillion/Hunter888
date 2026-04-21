"""Outbox Event model — transactional outbox for guaranteed event delivery.

S2-01: Events are persisted in the same DB transaction as the business logic.
A background worker polls and processes them with retry + dead-letter.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OutboxStatus(str, PyEnum):
    pending = "pending"
    processing = "processing"
    processed = "processed"
    failed = "failed"  # dead-letter after max retries


class OutboxEvent(Base):
    """Persistent event for transactional outbox pattern."""

    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    # 6.1: Link to source entity (duel_id, session_id, etc.)
    aggregate_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True, index=True,
    )
    # 6.1: Deduplication key — prevents processing the same event twice
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=True,
    )
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=OutboxStatus.pending, nullable=False, index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("idx_outbox_pending_retry", "status", "next_retry_at"),
    )

    def __repr__(self) -> str:
        return f"<OutboxEvent {self.id} type={self.event_type} status={self.status} attempts={self.attempts}>"
