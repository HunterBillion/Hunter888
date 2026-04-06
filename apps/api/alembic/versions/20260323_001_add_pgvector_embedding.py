"""Add pgvector embedding column to legal_knowledge_chunks.

Enables semantic search via cosine similarity on embedding vectors
produced by Gemini embedding API (768 dimensions).

Revision ID: 20260323_001
Revises: 20260322_002
Create Date: 2026-03-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260323_001"
down_revision: Union[str, None] = "20260322_002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension (idempotent)
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))

    # Create LegalCategory enum type if not exists
    op.execute(sa.text("""
        DO $$ BEGIN
            CREATE TYPE legalcategory AS ENUM (
                'eligibility', 'procedure', 'property', 'consequences', 'costs',
                'creditors', 'documents', 'timeline', 'court', 'rights'
            );
        EXCEPTION WHEN duplicate_object THEN null;
        END $$
    """))

    # Create LegalAccuracy enum type if not exists
    op.execute(sa.text("""
        DO $$ BEGIN
            CREATE TYPE legalaccuracy AS ENUM (
                'correct', 'correct_cited', 'partial', 'incorrect', 'n/a'
            );
        EXCEPTION WHEN duplicate_object THEN null;
        END $$
    """))

    # Create legal_knowledge_chunks table if it doesn't exist yet
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS legal_knowledge_chunks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            category legalcategory NOT NULL,
            fact_text TEXT NOT NULL,
            law_article VARCHAR(100) NOT NULL,
            common_errors JSONB DEFAULT '[]'::jsonb,
            match_keywords JSONB DEFAULT '[]'::jsonb,
            correct_response_hint TEXT,
            error_frequency INTEGER DEFAULT 5,
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_legal_chunks_category "
        "ON legal_knowledge_chunks (category)"
    ))

    # Create legal_validation_results table if it doesn't exist yet
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS legal_validation_results (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id UUID NOT NULL REFERENCES training_sessions(id),
            message_sequence INTEGER NOT NULL,
            manager_statement TEXT NOT NULL,
            knowledge_chunk_id UUID REFERENCES legal_knowledge_chunks(id),
            accuracy legalaccuracy NOT NULL,
            score_delta FLOAT DEFAULT 0.0,
            explanation TEXT,
            law_reference VARCHAR(200),
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_legal_validation_session "
        "ON legal_validation_results (session_id)"
    ))

    # Add embedding column (768-dim vector for gemini-embedding-001)
    op.execute(sa.text(
        "ALTER TABLE legal_knowledge_chunks "
        "ADD COLUMN IF NOT EXISTS embedding vector(768)"
    ))

    # Create IVFFlat index for fast cosine similarity search.
    # lists=10 is suitable for < 1000 rows; increase for larger datasets.
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_legal_chunks_embedding "
        "ON legal_knowledge_chunks USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists = 10)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_legal_chunks_embedding"))
    op.execute(sa.text(
        "ALTER TABLE legal_knowledge_chunks DROP COLUMN IF EXISTS embedding"
    ))
