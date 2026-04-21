"""user_story_states — 12-chapter narrative progression

Revision ID: 20260415_003
Revises: 20260415_002
Create Date: 2026-04-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260415_003"
down_revision: Union[str, None] = "20260415_002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_story_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Position
        sa.Column("current_chapter", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("current_epoch", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "chapter_started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        # Chapter progress
        sa.Column("chapter_sessions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chapter_avg_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("chapter_best_score", sa.Float(), nullable=False, server_default="0"),
        # Specialization
        sa.Column("specialization", sa.String(50), nullable=True),
        # Epoch timestamps
        sa.Column("epoch_1_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("epoch_2_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("epoch_3_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("epoch_4_completed_at", sa.DateTime(timezone=True), nullable=True),
        # Narrative
        sa.Column("last_narrative_trigger", sa.String(500), nullable=True),
        sa.Column("flashback_shown", sa.Boolean(), nullable=False, server_default="false"),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_user_story_states_user_id", "user_story_states", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_user_story_states_user_id", table_name="user_story_states")
    op.drop_table("user_story_states")
