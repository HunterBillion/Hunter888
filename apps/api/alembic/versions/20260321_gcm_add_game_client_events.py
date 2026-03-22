"""Add game_client_events table for Game CRM (Agent 7, spec 10.1).

Revision ID: 20260321_gcm
Revises: 20260321_004
Create Date: 2026-03-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260321_gcm"
down_revision = "20260321_004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum idempotently
    op.execute(sa.text(
        "DO $$ BEGIN "
        "CREATE TYPE game_event_type AS ENUM "
        "('call', 'message', 'consequence', 'storylet', 'status_change', 'callback'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    ))

    op.create_table(
        "game_client_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("story_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("client_stories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "event_type",
            postgresql.ENUM("call", "message", "consequence", "storylet", "status_change", "callback", name="game_event_type", create_type=False),
            nullable=False,
        ),
        sa.Column("source", sa.String(100), nullable=False, server_default="system"),
        sa.Column("narrative_date", sa.String(100), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("training_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reminder_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("severity", sa.Float(), nullable=True),
        sa.Column("is_read", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_game_client_events_story_id", "game_client_events", ["story_id"])
    op.create_index("ix_game_client_events_user_id", "game_client_events", ["user_id"])
    op.create_index("ix_game_events_story_created", "game_client_events", ["story_id", "created_at"])
    op.create_index("ix_game_events_user_type", "game_client_events", ["user_id", "event_type"])


def downgrade() -> None:
    op.drop_table("game_client_events")
    op.execute("DROP TYPE IF EXISTS game_event_type")
