"""Rating system v2: 24 ranks, promotion/demotion, AP, season rewards (DOC_13).

Revision ID: 20260404_016
Revises: 20260404_015
Create Date: 2026-04-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "20260404_016"
down_revision = "20260404_015"
branch_labels = None
depends_on = None

NEW_RANK_TIERS = [
    "iron_3", "iron_2", "iron_1",
    "bronze_3", "bronze_2", "bronze_1",
    "silver_3", "silver_2", "silver_1",
    "gold_3", "gold_2", "gold_1",
    "platinum_3", "platinum_2", "platinum_1",
    "diamond_3", "diamond_2", "diamond_1",
    "master_3", "master_2", "master_1",
    "grandmaster",
]


def upgrade() -> None:
    # Extend PvPRankTier enum with 24 new values
    for tier in NEW_RANK_TIERS:
        op.execute(f"ALTER TYPE pvpranktier ADD VALUE IF NOT EXISTS '{tier}'")

    # Demotion fields on pvp_ratings
    op.add_column("pvp_ratings", sa.Column("demotion_shield_losses", sa.Integer(), server_default="0", nullable=False))
    op.add_column("pvp_ratings", sa.Column("demotion_warning_issued", sa.Boolean(), server_default="false", nullable=False))

    # Arena Points on manager_progress
    op.add_column("manager_progress", sa.Column("arena_points", sa.Integer(), server_default="0", nullable=False))
    op.add_column("manager_progress", sa.Column("arena_points_last_month", sa.Integer(), server_default="0", nullable=False))
    op.add_column("manager_progress", sa.Column("arena_points_total_earned", sa.Integer(), server_default="0", nullable=False))

    # Promotion series table
    op.create_table(
        "promotion_series",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rating_type", sa.String(50), nullable=False),
        sa.Column("from_tier", sa.String(30), nullable=False),
        sa.Column("to_tier", sa.String(30), nullable=False),
        sa.Column("matches_played", sa.Integer(), server_default="0"),
        sa.Column("wins", sa.Integer(), server_default="0"),
        sa.Column("losses", sa.Integer(), server_default="0"),
        sa.Column("duel_ids", JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("result", sa.String(20), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_promotion_series_user", "promotion_series", ["user_id"])

    # Season rewards table
    op.create_table(
        "season_rewards",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("season_id", UUID(as_uuid=True), sa.ForeignKey("pvp_seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("final_rating", sa.Float(), nullable=False),
        sa.Column("final_tier", sa.String(30), nullable=False),
        sa.Column("xp_reward", sa.Integer(), nullable=False),
        sa.Column("ap_reward", sa.Integer(), nullable=False),
        sa.Column("title_reward", sa.String(200), nullable=True),
        sa.Column("border_reward", sa.String(100), nullable=True),
        sa.Column("achievement_id", sa.String(100), nullable=True),
        sa.Column("awarded_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("season_id", "user_id", name="uq_season_reward_user"),
    )
    op.create_index("ix_season_rewards_season", "season_rewards", ["season_id"])
    op.create_index("ix_season_rewards_user", "season_rewards", ["user_id"])

    # AP purchases table
    op.create_table(
        "ap_purchases",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_type", sa.String(50), nullable=False),
        sa.Column("item_id", sa.String(100), nullable=False),
        sa.Column("cost_ap", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purchased_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_ap_purchases_user", "ap_purchases", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_ap_purchases_user", table_name="ap_purchases")
    op.drop_table("ap_purchases")
    op.drop_index("ix_season_rewards_user", table_name="season_rewards")
    op.drop_index("ix_season_rewards_season", table_name="season_rewards")
    op.drop_table("season_rewards")
    op.drop_index("ix_promotion_series_user", table_name="promotion_series")
    op.drop_table("promotion_series")
    op.drop_column("manager_progress", "arena_points_total_earned")
    op.drop_column("manager_progress", "arena_points_last_month")
    op.drop_column("manager_progress", "arena_points")
    op.drop_column("pvp_ratings", "demotion_warning_issued")
    op.drop_column("pvp_ratings", "demotion_shield_losses")
