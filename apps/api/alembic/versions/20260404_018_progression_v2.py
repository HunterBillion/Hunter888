"""Progression v2: prestige, season pass, XP log (DOC_15).

Revision ID: 20260404_018
Revises: 20260404_017
Create Date: 2026-04-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "20260404_018"
down_revision = "20260404_017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Prestige + Season Pass fields on manager_progress
    op.add_column("manager_progress", sa.Column("prestige_level", sa.Integer(), server_default="0", nullable=False))
    op.add_column("manager_progress", sa.Column("prestige_xp_multiplier", sa.Float(), server_default="1.0", nullable=False))
    op.add_column("manager_progress", sa.Column("season_pass_tier", sa.Integer(), server_default="0", nullable=False))
    op.add_column("manager_progress", sa.Column("season_points", sa.Integer(), server_default="0", nullable=False))

    # XP Log table
    op.create_table(
        "xp_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("multiplier", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("season_points", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_xp_log_user", "xp_log", ["user_id"])
    op.create_index("ix_xp_log_created", "xp_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_xp_log_created", table_name="xp_log")
    op.drop_index("ix_xp_log_user", table_name="xp_log")
    op.drop_table("xp_log")
    op.drop_column("manager_progress", "season_points")
    op.drop_column("manager_progress", "season_pass_tier")
    op.drop_column("manager_progress", "prestige_xp_multiplier")
    op.drop_column("manager_progress", "prestige_level")
