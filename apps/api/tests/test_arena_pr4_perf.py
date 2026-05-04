"""Pin invariants for the PR-4 perf migration + dual-write.

The migration runs DDL only; we don't have a pg_trgm-capable test DB
in CI, so the SQL itself is exercised at deploy time via
`alembic upgrade head` against prod (and the verify-script measures
search latency before/after). These tests pin the **structural**
properties:

  * The migration chains off the PR-2 head (`20260504_001`).
  * Live + cold backfill paths now write `embedding_v2` alongside
    `embedding` (otherwise toggling `RAG_LEGAL_USE_V2=1` at any time
    would silently break retrieval for every recently-indexed chunk).
  * Live worker UPDATE includes `updated_at = updated_at` so the
    embedding-only write doesn't fire `onupdate` and bump the
    optimistic-lock token, which would 412 the methodologist's next
    Save with no visible diff.
"""
from __future__ import annotations

import os
import runpy

VERSIONS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "alembic", "versions",
)


def test_perf_migration_chains_to_pr2_head():
    ns = runpy.run_path(os.path.join(VERSIONS, "20260504_002_arena_perf_indexes.py"))
    assert ns["revision"] == "20260504_002"
    assert ns["down_revision"] == "20260504_001"
    assert callable(ns["upgrade"])
    assert callable(ns["downgrade"])


def test_perf_migration_creates_pg_trgm_extension():
    """A search-by-text panel without a trigram index is a sequential
    scan trap at scale. Pin the ext-creation in the upgrade SQL."""
    src = open(
        os.path.join(VERSIONS, "20260504_002_arena_perf_indexes.py")
    ).read()
    assert "CREATE EXTENSION IF NOT EXISTS pg_trgm" in src
    assert "gin_trgm_ops" in src
    assert "ix_legal_chunks_fact_text_trgm" in src


def test_perf_migration_creates_hnsw_for_embedding_v2():
    """HNSW alongside (not replacing) IVFFlat — pgvector's planner can
    pick whichever is available; we keep IVFFlat as a fallback for
    older runtimes that don't have HNSW."""
    src = open(
        os.path.join(VERSIONS, "20260504_002_arena_perf_indexes.py")
    ).read()
    assert "USING hnsw" in src
    assert "vector_cosine_ops" in src
    assert "ix_legal_chunks_embedding_v2_hnsw" in src


def test_live_backfill_writes_both_embedding_columns():
    """`embedding_v2` was added in 20260417_005 as a shadow column for
    the gemini → next-gen transition, but only offline scripts wrote
    it. If RAG_LEGAL_USE_V2=1 is ever flipped, retrieval filters
    `embedding_v2 IS NOT NULL` — every recently-edited chunk would
    silently drop. Pin: the live worker writes BOTH columns from the
    same vector, with the same model name."""
    src = open(
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "app", "services", "embedding_live_backfill.py",
        )
    ).read()
    # The dual-write update is in populate_single_legal_chunk_embedding.
    block_start = src.find("async def populate_single_legal_chunk_embedding")
    next_def = src.find("async def populate_single_wiki_page_embedding", block_start)
    block = src[block_start:next_def]
    assert "embedding=embeddings[0]" in block
    assert "embedding_v2=embeddings[0]" in block
    assert 'embedding_v2_model="gemini-embedding-001"' in block


def test_live_backfill_does_not_bump_updated_at():
    """The live worker tick writes only the embedding columns; bumping
    `updated_at` (via `onupdate=func.now()`) would invalidate the
    optimistic-lock token the methodologist captured at GET time. Pin:
    the SET clause includes `updated_at=...c.updated_at` so SQLAlchemy
    suppresses `onupdate`."""
    src = open(
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "app", "services", "embedding_live_backfill.py",
        )
    ).read()
    block_start = src.find("async def populate_single_legal_chunk_embedding")
    next_def = src.find("async def populate_single_wiki_page_embedding", block_start)
    block = src[block_start:next_def]
    # Either explicit self-reference or raw SQL that omits updated_at.
    assert (
        "updated_at=LegalKnowledgeChunk.__table__.c.updated_at" in block
        or "SET embedding" in block
    )


def test_cold_backfill_writes_both_embedding_columns():
    """Same pin for the cold sweep at API boot — pre-fix it only wrote
    `embedding`, so a freshly-restarted prod with `RAG_LEGAL_USE_V2=1`
    would have v2 NULL on every chunk that wasn't seeded by an offline
    script."""
    src = open(
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "app", "services", "embedding_backfill.py",
        )
    ).read()
    block_start = src.find("async def populate_legal_chunk_embeddings")
    next_def = src.find("async def invalidate_stale_legal_embeddings", block_start)
    block = src[block_start:next_def]
    assert "embedding=emb" in block
    assert "embedding_v2=emb" in block
    assert "embedding_v2_model=current_model" in block
