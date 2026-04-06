"""Add PvP Arena fields to knowledge_quiz_sessions.

Revision ID: 20260324_arena
Revises: 20260324_002
Create Date: 2026-03-24

Changes:
- knowledge_quiz_sessions: +contains_bot, +anti_cheat_flags, +rating_changes_applied
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260324_arena"
down_revision: Union[str, None] = "20260324_002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "knowledge_quiz_sessions",
        sa.Column("contains_bot", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "knowledge_quiz_sessions",
        sa.Column("anti_cheat_flags", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "knowledge_quiz_sessions",
        sa.Column("rating_changes_applied", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("knowledge_quiz_sessions", "rating_changes_applied")
    op.drop_column("knowledge_quiz_sessions", "anti_cheat_flags")
    op.drop_column("knowledge_quiz_sessions", "contains_bot")
