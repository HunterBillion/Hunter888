"""Add missing columns from ORM models.

chunk_usage_logs: is_deleted, archived_at
outbox_events: aggregate_id, idempotency_key

Revision ID: 20260414_006
Revises: 20260414_005
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "20260414_006"
down_revision = "20260414_005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- chunk_usage_logs --
    op.add_column(
        "chunk_usage_logs",
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "chunk_usage_logs",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_chunk_usage_logs_is_deleted", "chunk_usage_logs", ["is_deleted"])

    # -- outbox_events --
    op.add_column(
        "outbox_events",
        sa.Column("aggregate_id", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "outbox_events",
        sa.Column("idempotency_key", sa.String(128), nullable=True),
    )
    op.create_index("ix_outbox_events_aggregate_id", "outbox_events", ["aggregate_id"])
    op.create_unique_constraint("uq_outbox_events_idempotency_key", "outbox_events", ["idempotency_key"])


def downgrade() -> None:
    # -- outbox_events --
    op.drop_constraint("uq_outbox_events_idempotency_key", "outbox_events", type_="unique")
    op.drop_index("ix_outbox_events_aggregate_id", table_name="outbox_events")
    op.drop_column("outbox_events", "idempotency_key")
    op.drop_column("outbox_events", "aggregate_id")

    # -- chunk_usage_logs --
    op.drop_index("ix_chunk_usage_logs_is_deleted", table_name="chunk_usage_logs")
    op.drop_column("chunk_usage_logs", "archived_at")
    op.drop_column("chunk_usage_logs", "is_deleted")
