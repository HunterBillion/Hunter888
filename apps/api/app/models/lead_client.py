"""Canonical LeadClient aggregate for unified client domain (TZ-1).

Also hosts the canonical TaskFollowUp aggregate (TZ-2 §12) — it shares
the lead_clients FK contract and naturally lives next to LeadClient.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, func
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

    # TZ-1 §8 status lattice — enforced at DB level so the canonical model
    # cannot accept free-text values from any code path. Sync these lists
    # with `LIFECYCLE_STAGES` / `WORK_STATES` in app.services.client_domain.
    __table_args__ = (
        Index("ix_lead_clients_owner_stage", "owner_user_id", "lifecycle_stage"),
        Index("ix_lead_clients_team_state", "team_id", "work_state"),
        CheckConstraint(
            "lifecycle_stage IN ("
            "'new','contacted','interested','consultation','thinking',"
            "'consent_received','contract_signed','documents_in_progress',"
            "'case_in_progress','completed','lost')",
            name="ck_lead_clients_lifecycle_stage",
        ),
        CheckConstraint(
            "work_state IN ("
            "'active','callback_scheduled','waiting_client','waiting_documents',"
            "'consent_pending','paused','consent_revoked','duplicate_review',"
            "'archived')",
            name="ck_lead_clients_work_state",
        ),
    )


class TaskFollowUp(Base):
    """Canonical follow-up task linked to a LeadClient (TZ-2 §12).

    Distinct from the legacy ``manager_reminders`` table:
      * FK to ``lead_clients`` (the canonical aggregate), not ``real_clients``
      * Typed ``reason`` enum instead of free-text ``message``
      * Linked to the originating ``training_sessions`` and ``domain_events``
      * Status as enum (pending/done/cancelled) instead of boolean ``is_completed``

    Coexists with ``ManagerReminder`` during the migration window —
    ``crm_followup.ensure_followup_for_session`` writes to BOTH so legacy
    UI continues to work and new analytics can read the canonical table.
    """

    __tablename__ = "task_followups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lead_clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    domain_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("domain_events.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    reason: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    channel: Mapped[str | None] = mapped_column(String(16), nullable=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    auto_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # TZ-2 §12 catalogs — enforced at DB level.
    __table_args__ = (
        Index("ix_task_followups_lead_due", "lead_client_id", "due_at"),
        CheckConstraint(
            "reason IN ("
            "'callback_requested','client_requests_later','need_documents_or_time',"
            "'continue_next_call','needs_followup','documents_required',"
            "'consent_pending','manual')",
            name="ck_task_followups_reason",
        ),
        CheckConstraint(
            "channel IS NULL OR channel IN ('phone','chat','email','meeting','sms')",
            name="ck_task_followups_channel",
        ),
        CheckConstraint(
            "status IN ('pending','in_progress','done','cancelled')",
            name="ck_task_followups_status",
        ),
    )
