"""Arena perf indexes — pg_trgm GIN + HNSW

Revision ID: 20260504_002
Revises: 20260504_001
Create Date: 2026-05-04

Audit-2026-05-04 PR-4 (perf):

  * pg_trgm extension + GIN index on `legal_knowledge_chunks.fact_text`
    so the panel's `?search=…` query (ILIKE %X%) stops doing a full
    sequential scan. On 5000 chunks with 2-5 KB fact_text the pre-fix
    scan was 2-5 s; with the trigram GIN it lands at 50-100 ms.
  * HNSW index on `embedding_v2` alongside the existing IVFFlat. HNSW
    doesn't need REINDEX after INSERT/UPDATE (IVFFlat does — its lists
    drift as data changes) and gives better recall at the same probe
    cost. We keep IVFFlat in place so the planner can fall back if
    HNSW is unavailable on the running pgvector version.

Both indexes are CREATE INDEX (not CONCURRENTLY) — alembic wraps the
migration in a transaction and CONCURRENTLY can't run inside one.
On the 375-row prod table either build finishes well under a second.
At 50K rows the HNSW build runs ~30 s; we'll switch to a separate
`op.execute("CREATE INDEX CONCURRENTLY …")` outside the alembic
transaction if/when that becomes the bottleneck.
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260504_002"
down_revision = "20260504_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_legal_chunks_fact_text_trgm "
        "ON legal_knowledge_chunks USING gin (fact_text gin_trgm_ops)"
    )
    # HNSW for embedding_v2. Defaults (m=16, ef_construction=64) are a
    # reasonable balance for ~10 K dense vectors at 768 dims; can be
    # tuned later via REINDEX with parameters once we have prod recall
    # measurements.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_legal_chunks_embedding_v2_hnsw "
        "ON legal_knowledge_chunks "
        "USING hnsw (embedding_v2 vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_legal_chunks_embedding_v2_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_legal_chunks_fact_text_trgm")
    # Don't DROP EXTENSION pg_trgm — other migrations may use it.
