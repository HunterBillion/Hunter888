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
