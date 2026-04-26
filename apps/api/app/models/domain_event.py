"""Canonical client domain event log (TZ-1 foundation)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DomainEvent(Base):
    """Immutable domain fact for the unified client domain."""

    __tablename__ = "domain_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lead_clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    aggregate_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    aggregate_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    call_attempt_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    actor_type: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    causation_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # TZ-1 §15.1 invariant 4 — every event must carry a correlation_id so the
    # timeline / replay tooling can join sessions, aggregate ranges, and chain
    # reissues. Helper ``client_domain.emit_domain_event`` defaults this from
    # session_id → aggregate_id → lead_client_id when the caller omits it, so
    # the column is safely NOT NULL at the DB layer (migration 20260426_001).
    correlation_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_domain_events_lead_occurred", "lead_client_id", "occurred_at"),
        Index("ix_domain_events_type_occurred", "event_type", "occurred_at"),
    )
