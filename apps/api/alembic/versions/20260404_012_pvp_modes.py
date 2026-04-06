"""PvP expansion: 4 modes, new models (DOC_09).

Revision ID: 20260404_012
Revises: 20260404_011
Create Date: 2026-04-04

Adds: mode field to pvp_duels, new tables for Team Battle, Gauntlet, Rapid Fire.
Extends RatingType enum with team_battle, rapid_fire.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "20260404_012"
down_revision = "20260404_011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add mode field to pvp_duels
    op.add_column("pvp_duels", sa.Column("mode", sa.String(20), nullable=False, server_default="classic"))
    op.create_index("ix_pvp_duels_mode", "pvp_duels", ["mode"])

    # Extend RatingType enum
    op.execute("ALTER TYPE ratingtype ADD VALUE IF NOT EXISTS 'team_battle'")
    op.execute("ALTER TYPE ratingtype ADD VALUE IF NOT EXISTS 'rapid_fire'")

    # Create pvp_teams table
    op.create_table(
        "pvp_teams",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("player1_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("player2_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("avg_rating", sa.Float(), nullable=False, server_default="1500.0"),
        sa.Column("duel_id", UUID(as_uuid=True), sa.ForeignKey("pvp_duels.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # Create pvp_gauntlet_runs table
    op.create_table(
        "pvp_gauntlet_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("total_duels", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("completed_duels", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("losses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duel_ids", JSONB(), nullable=False, server_default="'[]'::jsonb"),
        sa.Column("scores", JSONB(), nullable=False, server_default="'[]'::jsonb"),
        sa.Column("difficulties", JSONB(), nullable=False, server_default="'[]'::jsonb"),
        sa.Column("final_score", sa.Float(), nullable=True),
        sa.Column("rating_bonus", sa.Float(), nullable=True),
        sa.Column("rd_bonus", sa.Float(), nullable=True),
        sa.Column("is_completed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_eliminated", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_pvp_gauntlet_runs_user_id", "pvp_gauntlet_runs", ["user_id"])

    # Create pvp_rapid_fire_matches table
    op.create_table(
        "pvp_rapid_fire_matches",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("player1_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("player2_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_pve", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("archetypes", JSONB(), nullable=False, server_default="'[]'::jsonb"),
        sa.Column("mini_scores", JSONB(), nullable=False, server_default="'[]'::jsonb"),
        sa.Column("difficulty_progression", JSONB(), nullable=False, server_default="'[]'::jsonb"),
        sa.Column("total_score", sa.Float(), nullable=True),
        sa.Column("normalized_score", sa.Float(), nullable=True),
        sa.Column("bonuses", JSONB(), nullable=True),
        sa.Column("rating_delta", sa.Float(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_pvp_rapid_fire_player1", "pvp_rapid_fire_matches", ["player1_id"])


def downgrade() -> None:
    op.drop_index("ix_pvp_rapid_fire_player1", table_name="pvp_rapid_fire_matches")
    op.drop_table("pvp_rapid_fire_matches")
    op.drop_index("ix_pvp_gauntlet_runs_user_id", table_name="pvp_gauntlet_runs")
    op.drop_table("pvp_gauntlet_runs")
    op.drop_table("pvp_teams")
    op.drop_index("ix_pvp_duels_mode", table_name="pvp_duels")
    op.drop_column("pvp_duels", "mode")
    # Note: PostgreSQL doesn't support removing enum values
