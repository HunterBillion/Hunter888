"""Create user_answer_history table for SM-2 spaced repetition.

Revision ID: 20260402_001
Revises: 20260401_001
Create Date: 2026-04-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

# revision identifiers
revision: str = "20260402_001"
down_revision: Union[str, None] = "20260401_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_answer_history",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_category", sa.String(50), nullable=False),
        sa.Column("question_hash", sa.String(64), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),

        # SM-2 parameters
        sa.Column("ease_factor", sa.Float(), server_default="2.5", nullable=False),
        sa.Column("interval_days", sa.Integer(), server_default="1", nullable=False),
        sa.Column("repetition_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("quality_history", postgresql.JSONB(), nullable=True),

        # Scheduling
        sa.Column("next_review_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),

        # Stats
        sa.Column("total_reviews", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_correct", sa.Integer(), server_default="0", nullable=False),

        # Leitner box (hybrid extension)
        sa.Column("leitner_box", sa.Integer(), server_default="0", nullable=False),

        # Source tracking (quiz, pvp, training, blitz)
        sa.Column("source_type", sa.String(20), server_default="'quiz'", nullable=False),

        # Streak tracking
        sa.Column("current_streak", sa.Integer(), server_default="0", nullable=False),
        sa.Column("best_streak", sa.Integer(), server_default="0", nullable=False),

        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Indexes
    op.create_index("ix_uah_user_id", "user_answer_history", ["user_id"])
    op.create_index("ix_uah_next_review", "user_answer_history", ["next_review_at"])
    op.create_index(
        "ix_uah_user_category",
        "user_answer_history",
        ["user_id", "question_category"],
    )
    op.create_index(
        "ix_uah_user_hash",
        "user_answer_history",
        ["user_id", "question_hash"],
        unique=True,
    )
    # For overdue queries: user_id + next_review_at combo
    # Note: partial index with NOW() is invalid (non-IMMUTABLE function).
    # A plain composite index efficiently covers WHERE next_review_at <= $ts queries.
    op.create_index(
        "ix_uah_user_overdue",
        "user_answer_history",
        ["user_id", "next_review_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_uah_user_overdue", table_name="user_answer_history")
    op.drop_index("ix_uah_user_hash", table_name="user_answer_history")
    op.drop_index("ix_uah_user_category", table_name="user_answer_history")
    op.drop_index("ix_uah_next_review", table_name="user_answer_history")
    op.drop_index("ix_uah_user_id", table_name="user_answer_history")
    op.drop_table("user_answer_history")
