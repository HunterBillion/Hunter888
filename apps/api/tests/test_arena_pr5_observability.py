"""PR-5 observability invariants — queue-status endpoint + zero-hits log.

The deep audit's complaint was that operators had no way to know
whether the live worker was keeping up with edits, how many chunks
were RAG-invisible right now, or which user questions hit zero
chunks (so the methodologist could go author one). Pre-fix all three
signals were buried in INFO/DEBUG logs that nobody scrapes.
"""
from __future__ import annotations

import os


SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_queue_status_endpoint_present_and_gated():
    """Pin the route definition and the role gate."""
    src = open(os.path.join(SRC_DIR, "app", "api", "rop.py")).read()
    assert '@router.get("/arena/queue-status")' in src
    assert "_require_methodologist" in src
    # Rate-limited like the rest of the surface
    assert '@limiter.limit("60/minute")' in src


def test_queue_status_response_shape():
    """Pin the response keys so the FE can build a status panel
    without guessing which key holds what."""
    src = open(os.path.join(SRC_DIR, "app", "api", "rop.py")).read()
    block_start = src.find("async def arena_queue_status")
    next_def = src.find("async def", block_start + 1)
    block = src[block_start:next_def]
    for key in (
        '"queue"',
        '"legal_chunks"',
        '"wiki_pages"',
        '"methodology_chunks"',
        '"chunks"',
        '"total_active"',
        '"embedding_null"',
        '"embedding_v2_null"',
        '"updated_in_last_hour"',
    ):
        assert key in block, f"queue-status response is missing {key}"


def test_queue_status_uses_soft_delete_filter():
    """The 'total_active' count must filter out tombstones — otherwise
    the panel claims an inflated chunk count and misleads operators."""
    src = open(os.path.join(SRC_DIR, "app", "api", "rop.py")).read()
    block_start = src.find("async def arena_queue_status")
    next_def = src.find("async def", block_start + 1)
    block = src[block_start:next_def]
    assert "deleted_at.is_(None)" in block


def test_rag_unified_logs_zero_hits_signal():
    """The 'no chunk matched' event is now a WARN with the structured
    `rag_zero_hits` prefix so an operator can grep + tally what to
    author. Pre-fix the only signal was a DEBUG log that didn't even
    include the query."""
    src = open(os.path.join(SRC_DIR, "app", "services", "rag_unified.py")).read()
    assert "rag_zero_hits" in src
    assert "logger.warning" in src
    # The signal includes the query so the operator can build a
    # frequency table; we don't want to log just the count.
    assert "query=%r" in src
