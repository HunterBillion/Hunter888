"""Live embedding backfill for ``LegalKnowledgeChunk`` (Content→Arena PR-6).

Problem this solves
-------------------

Existing ``embedding_backfill.populate_legal_chunk_embeddings`` (services/
embedding_backfill.py:199) runs ONCE on API startup. After it finishes,
any ``LegalKnowledgeChunk`` row that ROP/admin auto-publishes (PR-3) has
``embedding=NULL`` until the API is restarted — semantic search via
pgvector treats NULL as a non-match, so the judge's RAG falls back to
keyword retrieval and misses the new fact.

This module adds a live path:

* ``enqueue_chunk(chunk_id)`` — RPUSH the chunk id onto a Redis list.
* ``LiveEmbeddingBackfillWorker.run_forever()`` — BLPOP-based loop that
  drains the list and calls ``populate_single_legal_chunk_embedding``
  for each id. Started by the lifespan when
  ``settings.arena_embedding_live_backfill_enabled`` is true.
* ROP's ``approve_arena_knowledge_draft`` calls ``enqueue_chunk`` after
  the chunk is committed (whether auto-published or queued for review,
  so even reviewers' eventual approve has its embedding ready).

Why a Redis list, not a SQL ``after_insert`` listener
-----------------------------------------------------

SQLAlchemy event listeners are sync-by-design; making them push to an
async Redis queue inside the flush/commit boundary leads to subtle
ordering bugs (the embedding worker can pull a chunk that hasn't been
visibly committed yet). Calling ``enqueue_chunk`` explicitly *after*
the row's transaction commits is simpler, observable, and works the
same way the rest of this codebase ships durable side-effects (see
``services/event_bus``).

Why a separate module from ``embedding_backfill``
-------------------------------------------------

The existing module owns the cold-start sweep (large batches, sleep
between, table-by-table). This module owns hot single-row enqueues
that should land within seconds. Keeping them apart means a slow cold
sweep can't starve the live queue and vice versa.

Failure-mode contract
---------------------

* Redis unreachable on enqueue → log WARNING, do NOT raise. The chunk
  still exists in Postgres with ``embedding=NULL`` and the next cold
  sweep on restart will pick it up. Live backfill is best-effort.
* Embedding provider unreachable inside the worker → row stays
  ``embedding=NULL`` after a transient retry; we log and move on.
  Re-enqueue happens on the next ``approve_arena_knowledge_draft`` or
  via the cold sweep on restart.
* Worker is cancelled (graceful shutdown) → in-flight chunk goes back
  to NULL embedding state — no partial write, since each chunk's
  update is its own transaction.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

logger = logging.getLogger(__name__)


# ── Redis queue layout ──────────────────────────────────────────────────────

# Single FIFO list: RPUSH on enqueue, BLPOP on consume. Independent of the
# arena bus (Эпик 2) — the bus is for cross-component events, this queue
# is for an internal job (embedding compute).
_QUEUE_KEY = "arena:embedding:backfill:legal_chunks"

# Hard cap so a runaway producer (e.g. import flood) cannot OOM Redis.
# 5 000 ids × ~50 bytes ≈ 250 KB. The cold sweep on next restart picks
# up anything that overflowed.
_QUEUE_MAXLEN = 5_000


# ── Public API ──────────────────────────────────────────────────────────────


async def enqueue_chunk(chunk_id: uuid.UUID) -> None:
    """Push a chunk id onto the live-backfill queue.

    Best-effort. Failures (Redis unreachable, etc.) are logged and
    swallowed — the chunk still exists in Postgres and the cold sweep
    on next restart will pick it up.
    """
    try:
        from app.core.redis_pool import get_redis

        r = get_redis()
        # Use LPUSH+LTRIM for natural FIFO with bounded length: consumer
        # uses BRPOPLPUSH/BRPOP from the right end; we trim from the left
        # so old entries get dropped first when the cap is hit. (BLPOP +
        # LTRIM 0..MAXLEN-1 give the same shape on the produce side.)
        pipe = r.pipeline()
        pipe.rpush(_QUEUE_KEY, str(chunk_id))
        pipe.ltrim(_QUEUE_KEY, -_QUEUE_MAXLEN, -1)
        await pipe.execute()
    except Exception:
        logger.warning(
            "embedding_live_backfill: enqueue failed for chunk %s (non-critical)",
            chunk_id, exc_info=True,
        )


async def queue_length() -> int:
    """Return current backlog size (operators / health probes)."""
    try:
        from app.core.redis_pool import get_redis

        r = get_redis()
        return int(await r.llen(_QUEUE_KEY))
    except Exception:
        return -1


# ── Per-chunk embedding ────────────────────────────────────────────────────


async def populate_single_legal_chunk_embedding(chunk_id: uuid.UUID) -> bool:
    """Compute and write the embedding for one chunk.

    Returns True on successful write, False otherwise. Each call uses
    its own DB session so a failure on one chunk doesn't poison the
    worker's surrounding transaction.
    """
    try:
        from app.database import async_session
        from app.models.rag import LegalKnowledgeChunk
        from app.services.llm import get_embeddings_batch
        from sqlalchemy import select, update

        async with async_session() as db:
            row = (
                await db.execute(
                    select(LegalKnowledgeChunk.fact_text, LegalKnowledgeChunk.is_active)
                    .where(LegalKnowledgeChunk.id == chunk_id)
                )
            ).first()
            if row is None:
                logger.info(
                    "embedding_live_backfill: chunk %s not found, skipping",
                    chunk_id,
                )
                return False
            # Inactive chunks can be skipped — they aren't surfaced by
            # the judge anyway (rag_legal SELECT filters is_active).
            if not row.is_active:
                logger.debug(
                    "embedding_live_backfill: chunk %s inactive, skipping",
                    chunk_id,
                )
                return False

            text = (row.fact_text or "")[:1000]  # match cold-sweep truncation
            if not text:
                return False
            embeddings = await get_embeddings_batch([text])
            if not embeddings or not embeddings[0]:
                logger.warning(
                    "embedding_live_backfill: provider returned empty for chunk %s",
                    chunk_id,
                )
                return False
            await db.execute(
                update(LegalKnowledgeChunk)
                .where(LegalKnowledgeChunk.id == chunk_id)
                .values(embedding=embeddings[0])
            )
            await db.commit()
            return True
    except Exception:
        logger.warning(
            "embedding_live_backfill: failed to embed chunk %s (transient, will be picked up by cold sweep on restart)",
            chunk_id, exc_info=True,
        )
        return False


# ── Worker ──────────────────────────────────────────────────────────────────


class LiveEmbeddingBackfillWorker:
    """BLPOP-based consumer of the live-backfill queue.

    Started by the lifespan (main.py) when the feature flag is on.
    Cancellation aware: ``stop()`` exits after the current chunk
    finishes, ``CancelledError`` propagates after the in-flight
    chunk's commit (or rollback) so we don't leave half-written
    embeddings.
    """

    def __init__(
        self,
        *,
        block_timeout_seconds: int = 5,
        idle_sleep: float = 1.0,
    ) -> None:
        self.block_timeout = block_timeout_seconds
        self.idle_sleep = idle_sleep
        self._stopped = asyncio.Event()
        self.processed_count = 0  # Exposed for tests / metrics

    def stop(self) -> None:
        self._stopped.set()

    async def _next(self) -> uuid.UUID | None:
        """BLPOP one entry. Returns None on timeout (no traffic)."""
        try:
            from app.core.redis_pool import get_redis

            r = get_redis()
            res = await r.blpop(_QUEUE_KEY, timeout=self.block_timeout)
        except Exception:
            logger.warning(
                "embedding_live_backfill.worker: BLPOP failed",
                exc_info=True,
            )
            return None
        if res is None:
            return None
        # res = (queue_name, value). Both bytes or str depending on client.
        _, raw = res
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode()
        try:
            return uuid.UUID(str(raw))
        except (ValueError, TypeError):
            logger.warning(
                "embedding_live_backfill.worker: malformed queue entry %r, skipping",
                raw,
            )
            return None

    async def run_forever(self) -> None:
        logger.info("embedding_live_backfill.worker: started")
        try:
            while not self._stopped.is_set():
                chunk_id = await self._next()
                if chunk_id is None:
                    # Idle tick — yield briefly so a cooperative cancel
                    # has a chance to fire even when the queue is busy.
                    await asyncio.sleep(self.idle_sleep)
                    continue
                ok = await populate_single_legal_chunk_embedding(chunk_id)
                if ok:
                    self.processed_count += 1
        except asyncio.CancelledError:
            raise
        finally:
            logger.info(
                "embedding_live_backfill.worker: stopped (processed=%d)",
                self.processed_count,
            )


__all__ = [
    "LiveEmbeddingBackfillWorker",
    "enqueue_chunk",
    "populate_single_legal_chunk_embedding",
    "queue_length",
]
