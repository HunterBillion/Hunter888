"""add embedding_v2 shadow column to legal_knowledge_chunks + personality_chunks + personality_examples + wiki_pages

Revision ID: 20260417_005
Revises: 20260417_004
Create Date: 2026-04-17

Shadow-column migration to move RAG embeddings from text-embedding-3-small@768
to gemini-embedding-001@768 without downtime.

Strategy:
  1. Add `embedding_v2 VECTOR(768)` to 4 RAG tables (NULL default).
  2. Backfill script writes gemini embeddings to embedding_v2 while the app
     keeps reading the old `embedding` column.
  3. Once backfill is 100% complete, switch reader code to prefer embedding_v2
     (COALESCE or simple swap).
  4. Later migration can drop `embedding` once the migration is confirmed.

This matches the pattern used for legal_document (20260417_004) which already
has embedding_v2 as its primary vector column.
"""

from alembic import op
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = "20260417_005"
down_revision = "20260417_004"
branch_labels = None
depends_on = None


TABLES = [
    "legal_knowledge_chunks",
    "personality_chunks",
    "personality_examples",
    "wiki_pages",
]


def upgrade() -> None:
    import sqlalchemy as sa

    for tbl in TABLES:
        op.add_column(
            tbl,
            sa.Column("embedding_v2", Vector(768), nullable=True),
        )
        op.add_column(
            tbl,
            sa.Column("embedding_v2_model", sa.String(64), nullable=True),
        )
        # IVFFlat index for cosine similarity on the new column.
        # lists=50 is a reasonable default for tables under 10K rows; can be
        # retuned later once fully populated.
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{tbl}_embedding_v2 "
            f"ON {tbl} USING ivfflat (embedding_v2 vector_cosine_ops) WITH (lists = 50)"
        )


def downgrade() -> None:
    for tbl in TABLES:
        op.execute(f"DROP INDEX IF EXISTS ix_{tbl}_embedding_v2")
        op.drop_column(tbl, "embedding_v2_model")
        op.drop_column(tbl, "embedding_v2")
