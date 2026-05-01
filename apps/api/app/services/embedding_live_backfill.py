"""Live embedding backfill for RAG-eligible rows (Content→Arena PR-6, PR-X).

Problem this solves
-------------------

Existing ``embedding_backfill.populate_legal_chunk_embeddings`` (services/
embedding_backfill.py:199) runs ONCE on API startup. After it finishes,
any newly-written row (auto-published ``LegalKnowledgeChunk`` from
arena PR-3, or a manually-edited ``WikiPage``) has ``embedding=NULL``
until the API is restarted — semantic search via pgvector treats NULL
as a non-match, so the judge's / coach's RAG falls back to keyword
retrieval and misses the new content. Until next deploy.

This module adds a live path that handles both row types behind one
worker:

* ``enqueue_chunk(chunk_id)`` — RPUSH a legal_knowledge_chunks id onto
  ``arena:embedding:backfill:legal_chunks``.
* ``enqueue_wiki_page(page_id)`` — RPUSH a wiki_pages id onto
  ``arena:embedding:backfill:wiki_pages`` (PR-X foundation fix #1).
  Called from ``manager_wiki.update_wiki_page`` after every manual
  edit so the embedding never goes stale relative to the prose.
* ``LiveEmbeddingBackfillWorker.run_forever()`` — single BLPOP loop
  watching BOTH queues, dispatching to the right populator per
  queue key. Started by the lifespan when
  ``settings.arena_embedding_live_backfill_enabled`` is true.

Why a Redis list, not a SQL ``after_insert`` listener
-----------------------------------------------------

SQLAlchemy event listeners are sync-by-design; making them push to an
async Redis queue inside the flush/commit boundary leads to subtle
ordering bugs (the embedding worker can pull a chunk that hasn't been
visibly committed yet). Calling ``enqueue_*`` explicitly *after*
the row's transaction commits is simpler, observable, and works the
same way the rest of this codebase ships durable side-effects (see
``services/event_bus``).

Why a separate module from ``embedding_backfill``
-------------------------------------------------

The existing module owns the cold-start sweep (large batches, sleep
between, table-by-table). This module owns hot single-row enqueues
that should land within seconds. Keeping them apart means a slow cold
sweep can't starve the live queue and vice versa.

Why one worker, two queues
--------------------------

Both queues drain at human-edit pace (a ROP approving a chunk or
saving a wiki page is rarely more than a few writes per minute).
Running two BLPOP loops would double the idle pressure on Redis and
the per-worker bookkeeping for no throughput gain. ``BLPOP key1
key2 timeout`` returns from whichever queue produces first and
exposes the source key, so a single dispatcher per worker is the
natural shape. If either queue ever needs back-pressure isolation
the split is one-line refactor (one worker per ``_QUEUE_KEYS``
entry).

Failure-mode contract
---------------------

* Redis unreachable on enqueue → log WARNING, do NOT raise. The row
  still exists in Postgres with ``embedding=NULL`` and the next cold
  sweep on restart will pick it up. Live backfill is best-effort.
* Embedding provider unreachable inside the worker → row stays
  ``embedding=NULL`` after a transient retry; we log and move on.
  Re-enqueue happens on the next write or via the cold sweep on
  restart.
* Worker is cancelled (graceful shutdown) → in-flight row goes back
  to NULL embedding state — no partial write, since each row's
  update is its own transaction.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

logger = logging.getLogger(__name__)


# ── Redis queue layout ──────────────────────────────────────────────────────

# Two FIFO lists, one per row type, drained by the same worker via
# ``BLPOP key1 key2``. Independent of the arena bus (Эпик 2) — the bus
# is for cross-component events, these queues are for an internal job
# (embedding compute).
_QUEUE_KEY = "arena:embedding:backfill:legal_chunks"
_QUEUE_KEY_WIKI = "arena:embedding:backfill:wiki_pages"

# Watch order matters when both queues have data: BLPOP returns from
# the first key with a value. Wiki pages are user-edited and tend to
# be the "fresh signal" the manager just saved — drain those first so
# the next coach query sees the change. Legal chunks are bulk-imports
# and can wait a few seconds longer without hurting UX.
_QUEUE_KEYS = (_QUEUE_KEY_WIKI, _QUEUE_KEY)

# Hard cap so a runaway producer (e.g. import flood) cannot OOM Redis.
# 5 000 ids × ~50 bytes ≈ 250 KB per queue. The cold sweep on next
# restart picks up anything that overflowed.
_QUEUE_MAXLEN = 5_000


async def _rpush_bounded(queue_key: str, payload: str) -> None:
    """RPUSH + LTRIM in a pipeline. Best-effort — Redis errors logged."""
    from app.core.redis_pool import get_redis

    r = get_redis()
    # LTRIM keeps the LAST _QUEUE_MAXLEN entries (drops oldest first
    # when the cap is hit). BLPOP from the left preserves FIFO.
    pipe = r.pipeline()
    pipe.rpush(queue_key, payload)
    pipe.ltrim(queue_key, -_QUEUE_MAXLEN, -1)
    await pipe.execute()


# ── Public API ──────────────────────────────────────────────────────────────


async def enqueue_chunk(chunk_id: uuid.UUID) -> None:
    """Push a legal_knowledge_chunks id onto the live-backfill queue.

    Best-effort. Failures (Redis unreachable, etc.) are logged and
    swallowed — the chunk still exists in Postgres and the cold sweep
    on next restart will pick it up.
    """
    try:
        await _rpush_bounded(_QUEUE_KEY, str(chunk_id))
    except Exception:
        logger.warning(
            "embedding_live_backfill: enqueue failed for chunk %s (non-critical)",
            chunk_id, exc_info=True,
        )


async def enqueue_wiki_page(page_id: uuid.UUID) -> None:
    """Push a wiki_pages id onto the live-backfill queue (PR-X #1).

    Called from ``manager_wiki.update_wiki_page`` after each manual
    edit. Same best-effort contract as :func:`enqueue_chunk`: a Redis
    failure here doesn't fail the user-facing PUT — the next cold
    sweep on restart eventually catches up.
    """
    try:
        await _rpush_bounded(_QUEUE_KEY_WIKI, str(page_id))
    except Exception:
        logger.warning(
            "embedding_live_backfill: enqueue failed for wiki page %s (non-critical)",
            page_id, exc_info=True,
        )


async def queue_length() -> int:
    """Return current legal-chunks backlog size (operators / health probes)."""
    try:
        from app.core.redis_pool import get_redis

        r = get_redis()
        return int(await r.llen(_QUEUE_KEY))
    except Exception:
        return -1


async def wiki_queue_length() -> int:
    """Return current wiki-pages backlog size (operators / health probes)."""
    try:
        from app.core.redis_pool import get_redis

        r = get_redis()
        return int(await r.llen(_QUEUE_KEY_WIKI))
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


async def populate_single_wiki_page_embedding(page_id: uuid.UUID) -> bool:
    """Compute and write the embedding for one wiki page (PR-X #1).

    Mirrors :func:`populate_single_legal_chunk_embedding` but for
    ``WikiPage`` rows. Re-uses the same 1500-char truncation as the
    cold path (``rag_wiki.generate_wiki_embedding``) so a row's
    embedding is identical regardless of which path computed it.

    Returns True on successful write, False otherwise. Each call uses
    its own DB session so a failure on one page doesn't poison the
    worker's surrounding transaction.
    """
    try:
        from app.database import async_session
        from app.models.manager_wiki import WikiPage
        from app.services.llm import get_embeddings_batch
        from sqlalchemy import select, update

        async with async_session() as db:
            row = (
                await db.execute(
                    select(WikiPage.content).where(WikiPage.id == page_id)
                )
            ).first()
            if row is None:
                logger.info(
                    "embedding_live_backfill: wiki page %s not found, skipping",
                    page_id,
                )
                return False
            text = (row.content or "")[:1500]  # match rag_wiki.generate_wiki_embedding
            if not text:
                return False
            embeddings = await get_embeddings_batch([text])
            if not embeddings or not embeddings[0]:
                logger.warning(
                    "embedding_live_backfill: provider returned empty for wiki page %s",
                    page_id,
                )
                return False
            await db.execute(
                update(WikiPage)
                .where(WikiPage.id == page_id)
                .values(embedding=embeddings[0])
            )
            await db.commit()
            return True
    except Exception:
        logger.warning(
            "embedding_live_backfill: failed to embed wiki page %s "
            "(transient, will be picked up by cold sweep on restart)",
            page_id, exc_info=True,
        )
        return False


# ── Worker ──────────────────────────────────────────────────────────────────


# Per-queue dispatch table. Adding a new RAG-eligible row type means:
#   1. Define a ``populate_single_<row>_embedding`` coroutine above.
#   2. Add ``("arena:embedding:backfill:<row>", populate_single_<row>_...)``
#      below.
# The worker will pick it up on the next start. No other code changes.
_DISPATCH = {
    _QUEUE_KEY: populate_single_legal_chunk_embedding,
    _QUEUE_KEY_WIKI: populate_single_wiki_page_embedding,
}


class LiveEmbeddingBackfillWorker:
    """BLPOP-based consumer of the live-backfill queues.

    Started by the lifespan (main.py) when the feature flag is on.
    Cancellation aware: ``stop()`` exits after the current row
    finishes, ``CancelledError`` propagates after the in-flight
    row's commit (or rollback) so we don't leave half-written
    embeddings.

    PR-X (foundation): drains both ``legal_chunks`` and ``wiki_pages``
    queues via a single ``BLPOP key1 key2`` call — see module
    docstring "Why one worker, two queues".
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

    async def _next(self) -> tuple[str, uuid.UUID] | None:
        """BLPOP one entry across all watched queues.

        Returns ``(queue_key, row_id)`` or ``None`` on timeout / malformed
        entry. The queue_key is what the dispatcher uses to pick the
        right populator.
        """
        try:
            from app.core.redis_pool import get_redis

            r = get_redis()
            # ``BLPOP key1 key2 timeout`` — first non-empty queue wins.
            res = await r.blpop(list(_QUEUE_KEYS), timeout=self.block_timeout)
        except Exception:
            logger.warning(
                "embedding_live_backfill.worker: BLPOP failed",
                exc_info=True,
            )
            return None
        if res is None:
            return None
        # res = (queue_name, value). Both bytes or str depending on client.
        queue_raw, raw = res
        if isinstance(queue_raw, (bytes, bytearray)):
            queue_raw = queue_raw.decode()
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode()
        if str(queue_raw) not in _DISPATCH:
            logger.warning(
                "embedding_live_backfill.worker: unknown queue %r, skipping entry %r",
                queue_raw, raw,
            )
            return None
        try:
            return str(queue_raw), uuid.UUID(str(raw))
        except (ValueError, TypeError):
            logger.warning(
                "embedding_live_backfill.worker: malformed queue entry %r on %s, skipping",
                raw, queue_raw,
            )
            return None

    async def run_forever(self) -> None:
        logger.info(
            "embedding_live_backfill.worker: started (watching %d queues: %s)",
            len(_QUEUE_KEYS), ", ".join(_QUEUE_KEYS),
        )
        try:
            while not self._stopped.is_set():
                entry = await self._next()
                if entry is None:
                    # Idle tick — yield briefly so a cooperative cancel
                    # has a chance to fire even when the queue is busy.
                    await asyncio.sleep(self.idle_sleep)
                    continue
                queue_key, row_id = entry
                populator = _DISPATCH[queue_key]
                ok = await populator(row_id)
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
    "enqueue_wiki_page",
    "populate_single_legal_chunk_embedding",
    "populate_single_wiki_page_embedding",
    "queue_length",
    "wiki_queue_length",
]
