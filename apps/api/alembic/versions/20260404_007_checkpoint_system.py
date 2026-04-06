"""Add checkpoint system tables (DOC_04).

Revision ID: 20260404_007
Revises: 20260404_006
Create Date: 2026-04-04

Creates checkpoint_definitions and user_checkpoints tables.
Adds checkpoints_completed and level_checkpoints_met to manager_progress.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "20260404_007"
down_revision = "20260404_006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── checkpoint_definitions ──
    op.create_table(
        "checkpoint_definitions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(80), unique=True, nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("order_num", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("condition", JSONB(), nullable=False),
        sa.Column("xp_reward", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("unlock_reward", JSONB(), nullable=True),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("category", sa.String(20), nullable=False, server_default="'training'"),
    )
    op.create_index("ix_checkpoint_definitions_code", "checkpoint_definitions", ["code"])
    op.create_index("ix_checkpoint_definitions_level", "checkpoint_definitions", ["level"])

    # ── user_checkpoints ──
    op.create_table(
        "user_checkpoints",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("checkpoint_id", UUID(as_uuid=True), sa.ForeignKey("checkpoint_definitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("progress", JSONB(), nullable=True),
        sa.Column("is_completed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("xp_awarded", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_softened", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("user_id", "checkpoint_id", name="uq_user_checkpoint"),
    )
    op.create_index("ix_user_checkpoints_user_id", "user_checkpoints", ["user_id"])

    # ── manager_progress additions ──
    op.add_column("manager_progress", sa.Column("checkpoints_completed", sa.Integer(), server_default="0", nullable=False))
    op.add_column("manager_progress", sa.Column("level_checkpoints_met", sa.Boolean(), server_default="true", nullable=False))


def downgrade() -> None:
    op.drop_column("manager_progress", "level_checkpoints_met")
    op.drop_column("manager_progress", "checkpoints_completed")
    op.drop_index("ix_user_checkpoints_user_id", table_name="user_checkpoints")
    op.drop_table("user_checkpoints")
    op.drop_index("ix_checkpoint_definitions_level", table_name="checkpoint_definitions")
    op.drop_index("ix_checkpoint_definitions_code", table_name="checkpoint_definitions")
    op.drop_table("checkpoint_definitions")
