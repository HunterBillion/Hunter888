"""Add roleplay v5 tables: personality_profiles, trap_cascades, client_stories,
episodic_memories, story_stage_directions.

These tables are defined in app/models/roleplay.py but had no migration.
client_stories is required as FK target by 20260321_gcm (game_client_events).

All CREATE TABLE statements use IF NOT EXISTS because the tables may already
have been auto-created by SQLAlchemy Base.metadata.create_all() at app startup.

Revision ID: 20260321_004
Revises: fead4bf27c54
Create Date: 2026-03-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260321_004"
down_revision: Union[str, None] = "fead4bf27c54"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enum: stagedirectiontype ──
    op.execute(sa.text(
        "DO $$ BEGIN "
        "CREATE TYPE stagedirectiontype AS ENUM ("
        "'emotion_trigger','trap','action','memory','storylet','consequence','factor'"
        "); EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    ))

    # ── personality_profiles ──
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS personality_profiles (
            id UUID PRIMARY KEY,
            archetype_code VARCHAR(50) NOT NULL,
            openness DOUBLE PRECISION NOT NULL,
            conscientiousness DOUBLE PRECISION NOT NULL,
            extraversion DOUBLE PRECISION NOT NULL,
            agreeableness DOUBLE PRECISION NOT NULL,
            neuroticism DOUBLE PRECISION NOT NULL,
            pleasure_baseline DOUBLE PRECISION DEFAULT 0.0,
            arousal_baseline DOUBLE PRECISION DEFAULT 0.0,
            dominance_baseline DOUBLE PRECISION DEFAULT 0.0,
            occ_tendencies JSONB,
            behavioral_modifiers JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_personality_profiles_archetype_code "
        "ON personality_profiles (archetype_code)"
    ))

    # ── trap_cascades ──
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS trap_cascades (
            id UUID PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            theme VARCHAR(100) NOT NULL,
            difficulty_range VARCHAR(20) DEFAULT '3-8',
            levels JSONB NOT NULL,
            emotion_escalation JSONB,
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))

    # ── client_stories ──
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS client_stories (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            client_profile_id UUID REFERENCES client_profiles(id) ON DELETE SET NULL,
            story_name VARCHAR(300) DEFAULT 'Untitled Story',
            total_calls_planned INTEGER DEFAULT 3,
            current_call_number INTEGER DEFAULT 0,
            is_completed BOOLEAN DEFAULT false,
            personality_profile JSONB NOT NULL DEFAULT '{}'::jsonb,
            active_factors JSONB NOT NULL DEFAULT '[]'::jsonb,
            between_call_events JSONB NOT NULL DEFAULT '[]'::jsonb,
            consequences JSONB NOT NULL DEFAULT '[]'::jsonb,
            compressed_history TEXT,
            director_state JSONB,
            voice_id VARCHAR(100),
            voice_params_snapshot JSONB,
            couple_voice_config JSONB,
            started_at TIMESTAMPTZ DEFAULT now(),
            ended_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_client_stories_user_id "
        "ON client_stories (user_id)"
    ))

    # ── episodic_memories ──
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS episodic_memories (
            id UUID PRIMARY KEY,
            story_id UUID NOT NULL REFERENCES client_stories(id) ON DELETE CASCADE,
            session_id UUID NOT NULL REFERENCES training_sessions(id) ON DELETE CASCADE,
            call_number INTEGER NOT NULL,
            memory_type VARCHAR(50) NOT NULL,
            content TEXT NOT NULL,
            salience INTEGER DEFAULT 5,
            valence DOUBLE PRECISION DEFAULT 0.0,
            is_compressed BOOLEAN DEFAULT false,
            token_count INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_episodic_memories_story_id "
        "ON episodic_memories (story_id)"
    ))

    # ── story_stage_directions ──
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS story_stage_directions (
            id UUID PRIMARY KEY,
            story_id UUID NOT NULL REFERENCES client_stories(id) ON DELETE CASCADE,
            session_id UUID NOT NULL REFERENCES training_sessions(id) ON DELETE CASCADE,
            call_number INTEGER NOT NULL,
            message_sequence INTEGER NOT NULL,
            direction_type stagedirectiontype NOT NULL,
            raw_tag TEXT NOT NULL,
            parsed_payload JSONB,
            was_applied BOOLEAN DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_story_stage_directions_story_id "
        "ON story_stage_directions (story_id)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS story_stage_directions"))
    op.execute(sa.text("DROP TABLE IF EXISTS episodic_memories"))
    op.execute(sa.text("DROP TABLE IF EXISTS client_stories"))
    op.execute(sa.text("DROP TABLE IF EXISTS trap_cascades"))
    op.execute(sa.text("DROP TABLE IF EXISTS personality_profiles"))
    op.execute(sa.text("DROP TYPE IF EXISTS stagedirectiontype"))
