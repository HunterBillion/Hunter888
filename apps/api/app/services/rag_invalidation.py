"""RAG cache invalidation + admin-CRUD broadcast (PR-8, 2026-05-07).

Before this module existed, when a methodologist edited a chunk via
``/dashboard?tab=content&sub=arena`` the change was invisible to running
quiz / PvP sessions until the Redis ``rag:ctx:*`` TTL (300s) elapsed —
or worse, until the API restarted (the in-memory `BlitzQuestionPool`
loads at startup only). Pilot users would see "I just fixed that
mistake!" complaints because the AI was reading a stale chunk.

This module exposes a single fire-and-forget helper:

    await invalidate_chunk(chunk_id, action="updated")

It does three things, each best-effort (failure logs but doesn't
interrupt the CRUD response):

  1. Drops every ``rag:ctx:*`` Redis cache key (we don't know which
     queries cited this chunk; a flush of the cache prefix is cheap).
  2. Broadcasts ``knowledge.chunk.updated`` over /ws/notifications so
     active FE sessions can show a toast («База знаний обновлена —
     последующие ответы могут учитывать новые данные»).
  3. Schedules a ``BlitzQuestionPool.load(db)`` reload on action in
     ("updated","deleted") because blitz pre-builds its question
     bank in memory at startup; without the reload, an edited chunk
     keeps serving its old text in blitz mode for the rest of the
     process lifetime.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

from app.core.redis_pool import get_redis as _redis
from app.database import async_session
from app.ws.notifications import notification_manager

logger = logging.getLogger(__name__)

ChunkAction = Literal["created", "updated", "deleted"]
RAG_CACHE_PREFIX = "rag:ctx:"
EVENT_TYPE = "knowledge.chunk.updated"


async def _drop_rag_ctx_cache() -> int:
    """Best-effort delete of all ``rag:ctx:*`` keys.

    Uses SCAN+DELETE in batches rather than KEYS (which blocks the Redis
    event loop on large keyspaces). Returns the number of keys removed.
    """
    try:
        r = _redis()
        deleted = 0
        async for key in r.scan_iter(match=f"{RAG_CACHE_PREFIX}*", count=200):
            await r.delete(key)
            deleted += 1
        if deleted:
            logger.info("RAG ctx cache invalidated: %d keys dropped", deleted)
        return deleted
    except Exception as exc:
        logger.warning("RAG ctx cache invalidation failed: %s", exc)
        return 0


async def _reload_blitz_pool() -> None:
    """Re-load the in-memory blitz question pool from DB.

    Lazy import — `BlitzQuestionPool` lives in `rag_legal` which has a
    heavy dependency graph; importing at module top inflates startup.
    """
    try:
        from app.services.rag_legal import blitz_pool
        async with async_session() as db:
            await blitz_pool.load(db)
        logger.info("BlitzQuestionPool reloaded after chunk change")
    except Exception as exc:
        logger.warning("BlitzQuestionPool reload failed: %s", exc)


async def invalidate_chunk(chunk_id: uuid.UUID, *, action: ChunkAction) -> None:
    """Invalidate caches + broadcast event after an admin chunk CRUD.

    Best-effort: every step is wrapped in try/except so a failed
    broadcast doesn't propagate back into the CRUD response.

    Args:
        chunk_id: id of the chunk that changed
        action: one of "created" / "updated" / "deleted"
    """
    # 1. Redis cache flush (covers /knowledge + /pvp quiz RAG retrievals).
    deleted = await _drop_rag_ctx_cache()

    # 2. Broadcast — runs in the same task so the FE event arrives
    #    AFTER the cache flush. This guarantees the next request
    #    triggered by the toast will hit a fresh DB read.
    payload = {
        "type": EVENT_TYPE,
        "data": {
            "chunk_id": str(chunk_id),
            "action": action,
            "ts": datetime.now(timezone.utc).isoformat(),
            "cache_keys_dropped": deleted,
        },
    }
    try:
        await notification_manager.broadcast(payload)
    except Exception as exc:
        logger.warning("WS broadcast of chunk.updated failed: %s", exc)

    # 3. Blitz pool reload — only on update/delete, fire-and-forget.
    #    Created chunks are picked up on next blitz session start anyway.
    if action in ("updated", "deleted"):
        # Don't await — pool reload reads the whole table; we don't want
        # to block the CRUD response. Let it run in the background.
        asyncio.create_task(_reload_blitz_pool())
