"""Canonical LeadClient aggregate for unified client domain (TZ-1)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LeadClient(Base):
    """Canonical business aggregate for a real client/case.

    During migration phase, ``id`` is intentionally aligned with ``real_clients.id``
    (physical anchor) to keep compatibility with legacy references.
    """

    __tablename__ = "lead_clients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True, index=True
    )
    profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    crm_card_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    lifecycle_stage: Mapped[str] = mapped_column(String(40), nullable=False, default="new", index=True)
    work_state: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)
    status_tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    source_system: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)

    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_lead_clients_owner_stage", "owner_user_id", "lifecycle_stage"),
        Index("ix_lead_clients_team_state", "team_id", "work_state"),
    )
