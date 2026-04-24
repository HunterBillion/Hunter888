"""Projection state tables for client-domain projectors."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CrmTimelineProjectionState(Base):
    """Idempotency + audit state for CRM timeline projector."""

    __tablename__ = "crm_timeline_projection_state"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("domain_events.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    lead_client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lead_clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    interaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("client_interactions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    projection_name: Mapped[str] = mapped_column(String(60), nullable=False, default="crm_timeline")
    projection_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="projected", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    projected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_crm_proj_lead_projected", "lead_client_id", "projected_at"),
    )
