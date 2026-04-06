"""Add rating_type to pvp_ratings and arena streak fields to manager_progress.

Revision ID: 20260324_002
Revises: 20260324_001
Create Date: 2026-03-24
"""
from alembic import op
import sqlalchemy as sa


revision = "20260324_002"
down_revision = "20260324_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- pvp_ratings: add rating_type column ---
    op.add_column(
        "pvp_ratings",
        sa.Column("rating_type", sa.String(50), nullable=False, server_default="training_duel"),
    )

    # Drop old unique constraint on user_id (name may vary)
    op.drop_constraint("pvp_ratings_user_id_key", "pvp_ratings", type_="unique")

    # Add composite unique constraint (user_id, rating_type)
    op.create_unique_constraint(
        "uq_pvp_rating_user_type", "pvp_ratings", ["user_id", "rating_type"]
    )

    # --- manager_progress: add arena streak fields ---
    op.add_column(
        "manager_progress",
        sa.Column("arena_answer_streak", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "manager_progress",
        sa.Column("arena_best_answer_streak", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "manager_progress",
        sa.Column("arena_daily_streak", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "manager_progress",
        sa.Column("arena_last_quiz_date", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    # --- manager_progress: remove arena streak fields ---
    op.drop_column("manager_progress", "arena_last_quiz_date")
    op.drop_column("manager_progress", "arena_daily_streak")
    op.drop_column("manager_progress", "arena_best_answer_streak")
    op.drop_column("manager_progress", "arena_answer_streak")

    # --- pvp_ratings: revert rating_type ---
    op.drop_constraint("uq_pvp_rating_user_type", "pvp_ratings", type_="unique")
    op.create_unique_constraint("pvp_ratings_user_id_key", "pvp_ratings", ["user_id"])
    op.drop_column("pvp_ratings", "rating_type")
