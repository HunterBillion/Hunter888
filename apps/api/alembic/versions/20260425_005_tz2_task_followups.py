"""TZ-2 §12 — TaskFollowUp canonical table.

Revision ID: 20260425_005
Revises: 20260425_004
Create Date: 2026-04-25

Creates ``task_followups`` table linked to ``lead_clients``,
``training_sessions``, and ``domain_events``. Coexists with the legacy
``manager_reminders`` table — neither is touched here. Migration writers
will dual-write during the transition window.

CHECK constraints enforce the §12 catalogs (reason, channel, status).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260425_005"
down_revision: Union[str, Sequence[str], None] = "20260425_004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "task_followups",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "lead_client_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lead_clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("training_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "domain_event_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("domain_events.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reason", sa.String(length=40), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("auto_generated", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "reason IN ("
            "'callback_requested','client_requests_later','need_documents_or_time',"
            "'continue_next_call','needs_followup','documents_required',"
            "'consent_pending','manual')",
            name="ck_task_followups_reason",
        ),
        sa.CheckConstraint(
            "channel IS NULL OR channel IN ('phone','chat','email','meeting','sms')",
            name="ck_task_followups_channel",
        ),
        sa.CheckConstraint(
            "status IN ('pending','in_progress','done','cancelled')",
            name="ck_task_followups_status",
        ),
    )
    op.create_index(
        "ix_task_followups_lead_client_id",
        "task_followups",
        ["lead_client_id"],
    )
    op.create_index(
        "ix_task_followups_session_id",
        "task_followups",
        ["session_id"],
    )
    op.create_index(
        "ix_task_followups_domain_event_id",
        "task_followups",
        ["domain_event_id"],
    )
    op.create_index(
        "ix_task_followups_reason",
        "task_followups",
        ["reason"],
    )
    op.create_index(
        "ix_task_followups_status",
        "task_followups",
        ["status"],
    )
    op.create_index(
        "ix_task_followups_lead_due",
        "task_followups",
        ["lead_client_id", "due_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_task_followups_lead_due", table_name="task_followups")
    op.drop_index("ix_task_followups_status", table_name="task_followups")
    op.drop_index("ix_task_followups_reason", table_name="task_followups")
    op.drop_index("ix_task_followups_domain_event_id", table_name="task_followups")
    op.drop_index("ix_task_followups_session_id", table_name="task_followups")
    op.drop_index("ix_task_followups_lead_client_id", table_name="task_followups")
    op.drop_table("task_followups")
