"""Add knowledge quiz tables.

Creates tables for Knowledge Quiz system (AI Examiner + PvP Arena):
- knowledge_quiz_sessions
- quiz_participants
- knowledge_answers
- quiz_challenges

Revision ID: 20260323_002
Revises: 20260323_001
Create Date: 2026-03-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "20260323_002"
down_revision: Union[str, None] = "20260323_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- knowledge_quiz_sessions ---
    op.create_table(
        "knowledge_quiz_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "mode",
            sa.Enum("free_dialog", "blitz", "themed", "pvp", name="quizmode"),
            nullable=False,
        ),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("difficulty", sa.Integer(), server_default="3"),
        sa.Column("total_questions", sa.Integer(), server_default="0"),
        sa.Column("correct_answers", sa.Integer(), server_default="0"),
        sa.Column("incorrect_answers", sa.Integer(), server_default="0"),
        sa.Column("skipped", sa.Integer(), server_default="0"),
        sa.Column("score", sa.Float(), server_default="0.0"),
        sa.Column("max_players", sa.Integer(), server_default="1"),
        sa.Column(
            "status",
            sa.Enum("waiting", "active", "completed", "abandoned", "expired", name="quizsessionstatus"),
            server_default="active",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("ai_personality", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_knowledge_quiz_sessions_user_id", "knowledge_quiz_sessions", ["user_id"])

    # --- quiz_participants ---
    op.create_table(
        "quiz_participants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("knowledge_quiz_sessions.id"),
            nullable=False,
        ),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("score", sa.Float(), server_default="0.0"),
        sa.Column("correct_answers", sa.Integer(), server_default="0"),
        sa.Column("incorrect_answers", sa.Integer(), server_default="0"),
        sa.Column("final_rank", sa.Integer(), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_quiz_participants_session_id", "quiz_participants", ["session_id"])

    # --- knowledge_answers ---
    op.create_table(
        "knowledge_answers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("knowledge_quiz_sessions.id"),
            nullable=False,
        ),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("question_number", sa.Integer(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("question_category", sa.String(50), nullable=False),
        sa.Column("user_answer", sa.Text(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("article_reference", sa.String(200), nullable=True),
        sa.Column("score_delta", sa.Float(), server_default="0.0"),
        sa.Column("rag_chunks_used", JSONB(), nullable=True),
        sa.Column("hint_used", sa.Boolean(), server_default="false"),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_knowledge_answers_session_id", "knowledge_answers", ["session_id"])

    # --- quiz_challenges ---
    op.create_table(
        "quiz_challenges",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("challenger_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("max_players", sa.Integer(), server_default="2"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("knowledge_quiz_sessions.id"),
            nullable=True,
        ),
        sa.Column("accepted_by", JSONB(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_quiz_challenges_challenger_id", "quiz_challenges", ["challenger_id"])


def downgrade() -> None:
    op.drop_table("quiz_challenges")
    op.drop_table("knowledge_answers")
    op.drop_table("quiz_participants")
    op.drop_table("knowledge_quiz_sessions")
    op.execute("DROP TYPE IF EXISTS quizsessionstatus")
    op.execute("DROP TYPE IF EXISTS quizmode")
