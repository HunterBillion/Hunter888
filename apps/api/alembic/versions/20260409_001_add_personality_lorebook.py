"""add personality_chunks and personality_examples tables for lorebook RAG

Revision ID: 20260409_001
Revises: fead4bf27c54
Create Date: 2026-04-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260409_001"
down_revision: Union[str, None] = "fead4bf27c54"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension (idempotent) — needed for embedding vector(768)
    # on fresh DB where the earlier 20260323_001 branch may not have run yet
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Create enum types
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE traitcategory AS ENUM (
                'core_identity', 'financial_situation', 'backstory', 'family_context',
                'legal_fears', 'objection_price', 'objection_trust', 'objection_necessity',
                'objection_time', 'objection_competitor', 'breakpoint_trust',
                'speech_examples', 'emotional_triggers', 'decision_drivers'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE personalitychunksource AS ENUM ('manual', 'extracted', 'generated', 'learned');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # PersonalityChunk — lorebook entries
    op.execute("""
        CREATE TABLE IF NOT EXISTS personality_chunks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            archetype_code VARCHAR(50) NOT NULL,
            trait_category traitcategory NOT NULL,
            content TEXT NOT NULL,
            keywords JSONB DEFAULT '[]'::jsonb,
            priority INTEGER DEFAULT 5,
            source personalitychunksource DEFAULT 'manual',
            embedding vector(768),
            retrieval_count INTEGER DEFAULT 0,
            hit_count INTEGER DEFAULT 0,
            effectiveness_score FLOAT,
            is_active BOOLEAN DEFAULT true,
            content_hash VARCHAR(32),
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_pc_archetype ON personality_chunks (archetype_code);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_pc_category ON personality_chunks (trait_category);")

    # PersonalityExample — few-shot RAG examples
    op.execute("""
        CREATE TABLE IF NOT EXISTS personality_examples (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            chunk_id UUID REFERENCES personality_chunks(id) ON DELETE SET NULL,
            archetype_code VARCHAR(50) NOT NULL,
            situation TEXT NOT NULL,
            dialogue TEXT NOT NULL,
            emotion VARCHAR(30),
            source personalitychunksource DEFAULT 'extracted',
            embedding vector(768),
            retrieval_count INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMPTZ DEFAULT now()
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_pe_archetype ON personality_examples (archetype_code);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_pe_chunk ON personality_examples (chunk_id);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS personality_examples;")
    op.execute("DROP TABLE IF EXISTS personality_chunks;")
    op.execute("DROP TYPE IF EXISTS traitcategory;")
    op.execute("DROP TYPE IF EXISTS personalitychunksource;")
