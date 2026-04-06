"""Knowledge quiz expansion: 7 new modes, debate/team/daily tables (DOC_11).

Revision ID: 20260404_014
Revises: 20260404_013
Create Date: 2026-04-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "20260404_014"
down_revision = "20260404_013"
branch_labels = None
depends_on = None

NEW_MODES = [
    "rapid_blitz", "case_study", "debate", "mock_court",
    "article_deep_dive", "team_quiz", "daily_challenge",
]


def upgrade() -> None:
    # Extend QuizMode enum
    for mode in NEW_MODES:
        op.execute(f"ALTER TYPE quizmode ADD VALUE IF NOT EXISTS '{mode}'")

    # Debate sessions (for debate + mock_court modes)
    op.create_table(
        "debate_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("quiz_session_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_quiz_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("topic", sa.String(500), nullable=False),
        sa.Column("player_position", sa.Text(), nullable=False),
        sa.Column("ai_position", sa.Text(), nullable=False),
        sa.Column("total_rounds", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("rounds_data", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_debate_sessions_quiz", "debate_sessions", ["quiz_session_id"])

    # Team quiz teams (for team_quiz mode)
    op.create_table(
        "team_quiz_teams",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_quiz_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_name", sa.String(1), nullable=False),
        sa.Column("player1_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("player2_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("passes_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_team_quiz_session", "team_quiz_teams", ["session_id"])

    # Daily challenges
    op.create_table(
        "daily_challenges",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("challenge_date", sa.Date(), nullable=False, unique=True),
        sa.Column("questions", JSONB(), nullable=False),
        sa.Column("personality", sa.String(50), nullable=False),
        sa.Column("total_participants", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_daily_challenges_date", "daily_challenges", ["challenge_date"])

    # Daily challenge entries
    op.create_table(
        "daily_challenge_entries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("challenge_id", UUID(as_uuid=True), sa.ForeignKey("daily_challenges.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_quiz_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("total_time_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("challenge_id", "user_id", name="uq_daily_entry_user"),
    )
    op.create_index("ix_daily_entries_challenge", "daily_challenge_entries", ["challenge_id"])
    op.create_index("ix_daily_entries_user", "daily_challenge_entries", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_daily_entries_user", table_name="daily_challenge_entries")
    op.drop_index("ix_daily_entries_challenge", table_name="daily_challenge_entries")
    op.drop_table("daily_challenge_entries")
    op.drop_index("ix_daily_challenges_date", table_name="daily_challenges")
    op.drop_table("daily_challenges")
    op.drop_index("ix_team_quiz_session", table_name="team_quiz_teams")
    op.drop_table("team_quiz_teams")
    op.drop_index("ix_debate_sessions_quiz", table_name="debate_sessions")
    op.drop_table("debate_sessions")
    # Note: PostgreSQL doesn't support removing enum values
