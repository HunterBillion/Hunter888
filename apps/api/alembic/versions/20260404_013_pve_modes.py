"""PvE expansion: 5 modes, Bot Ladder + Boss Rush tables (DOC_10).

Revision ID: 20260404_013
Revises: 20260404_012
Create Date: 2026-04-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "20260404_013"
down_revision = "20260404_012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extend pvp_duels with PvE mode fields
    op.add_column("pvp_duels", sa.Column("pve_mode", sa.String(30), nullable=True))
    op.add_column("pvp_duels", sa.Column("pve_metadata", JSONB(), nullable=True))
    op.create_index("ix_pvp_duels_pve_mode", "pvp_duels", ["pve_mode"])

    # Bot Ladder runs
    op.create_table(
        "pve_ladder_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("current_bot_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bots_defeated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cumulative_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("bot_configs", JSONB(), nullable=False, server_default="'[]'::jsonb"),
        sa.Column("duel_ids", JSONB(), nullable=False, server_default="'[]'::jsonb"),
        sa.Column("is_complete", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("all_defeated", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("xp_earned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rating_delta", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_pve_ladder_user", "pve_ladder_runs", ["user_id"])

    # Boss Rush runs
    op.create_table(
        "pve_boss_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("boss_index", sa.Integer(), nullable=False),
        sa.Column("boss_type", sa.String(50), nullable=False),
        sa.Column("duel_id", UUID(as_uuid=True), sa.ForeignKey("pvp_duels.id", ondelete="SET NULL"), nullable=True),
        sa.Column("score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("is_defeated", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("special_mechanics_log", JSONB(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_pve_boss_user", "pve_boss_runs", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_pve_boss_user", table_name="pve_boss_runs")
    op.drop_table("pve_boss_runs")
    op.drop_index("ix_pve_ladder_user", table_name="pve_ladder_runs")
    op.drop_table("pve_ladder_runs")
    op.drop_index("ix_pvp_duels_pve_mode", table_name="pvp_duels")
    op.drop_column("pvp_duels", "pve_metadata")
    op.drop_column("pvp_duels", "pve_mode")
