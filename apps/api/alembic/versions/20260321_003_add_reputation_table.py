"""Add manager_reputations table (Agent 5 — Reputation System).

Revision ID: 20260321_003
Revises: 20260321_gcm, 20260321_002
Create Date: 2026-03-21

Merges game_client_events + pvp heads AND adds reputation table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260321_003"
down_revision: Union[str, None] = ("20260321_gcm", "20260321_002")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Reputation tier enum — create_type=False prevents auto-CREATE in create_table
reputation_tier_enum = postgresql.ENUM(
    "trainee", "manager", "senior", "expert", "hunter",
    name="reputation_tier",
    create_type=False,
)


def upgrade() -> None:
    # Create reputation tier enum idempotently
    op.execute(sa.text(
        "DO $$ BEGIN "
        "CREATE TYPE reputation_tier AS ENUM "
        "('trainee', 'manager', 'senior', 'expert', 'hunter'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    ))

    op.create_table(
        "manager_reputations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("score", sa.Float(), nullable=False, server_default=sa.text("50.0")),
        sa.Column(
            "tier",
            reputation_tier_enum,
            nullable=False,
            server_default=sa.text("'senior'"),
        ),
        sa.Column("ema_state", sa.Float(), nullable=False, server_default=sa.text("50.0")),
        sa.Column("sessions_rated", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_session_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_decay_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("peak_score", sa.Float(), nullable=False, server_default=sa.text("50.0")),
        sa.Column(
            "peak_tier",
            reputation_tier_enum,
            nullable=False,
            server_default=sa.text("'senior'"),
        ),
        sa.Column("history", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_manager_reputations_user_id", "manager_reputations", ["user_id"])
    op.create_index("ix_manager_reputations_tier", "manager_reputations", ["tier"])
    op.create_index("ix_manager_reputations_score", "manager_reputations", ["score"])


def downgrade() -> None:
    op.drop_table("manager_reputations")
    op.execute(sa.text("DROP TYPE IF EXISTS reputation_tier"))
