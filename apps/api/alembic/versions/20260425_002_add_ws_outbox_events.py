"""Phase 5 — WsOutboxEvent table (Roadmap §10.1).

Revision ID: 20260425_002
Revises: 20260425_001
Create Date: 2026-04-25

Durable queue for critical WebSocket events. Fire-and-forget delivery
used to drop messages if the target user was offline at the millisecond
the message was produced — match.found was the most visible casualty.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260425_002"
down_revision: Union[str, Sequence[str], None] = "20260425_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    return sa.inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return _inspector().has_table(name)


def _index_exists(table: str, name: str) -> bool:
    if not _table_exists(table):
        return False
    return any(idx["name"] == name for idx in _inspector().get_indexes(table))


def upgrade() -> None:
    if not _table_exists("ws_outbox_events"):
        op.create_table(
            "ws_outbox_events",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column(
                "user_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("event_type", sa.String(length=60), nullable=False),
            sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_error", sa.String(length=500), nullable=True),
            sa.Column("correlation_id", sa.String(length=120), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        )

    for name, cols in (
        ("ix_ws_outbox_user_status", ["user_id", "status"]),
        ("ix_ws_outbox_expires_at", ["expires_at"]),
        ("ix_ws_outbox_events_user_id", ["user_id"]),
        ("ix_ws_outbox_events_event_type", ["event_type"]),
        ("ix_ws_outbox_events_status", ["status"]),
        ("ix_ws_outbox_events_correlation_id", ["correlation_id"]),
    ):
        if not _index_exists("ws_outbox_events", name):
            op.create_index(name, "ws_outbox_events", cols, unique=False)


def downgrade() -> None:
    for name in (
        "ix_ws_outbox_events_correlation_id",
        "ix_ws_outbox_events_status",
        "ix_ws_outbox_events_event_type",
        "ix_ws_outbox_events_user_id",
        "ix_ws_outbox_expires_at",
        "ix_ws_outbox_user_status",
    ):
        if _index_exists("ws_outbox_events", name):
            op.drop_index(name, table_name="ws_outbox_events")
    if _table_exists("ws_outbox_events"):
        op.drop_table("ws_outbox_events")
