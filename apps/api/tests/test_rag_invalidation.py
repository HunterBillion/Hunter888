"""PR-8 tests: RAG cache invalidation + WS broadcast on admin chunk CRUD.

Before this change, methodologist edits via /dashboard?tab=content&sub=arena
took up to 300s (Redis TTL) to be visible to running quiz sessions, and
blitz mode kept stale text until API restart. The new
``invalidate_chunk`` helper:

  1. drops every ``rag:ctx:*`` key in Redis (best-effort, async SCAN)
  2. broadcasts ``knowledge.chunk.updated`` to all WS clients
  3. on update/delete, schedules a BlitzQuestionPool reload (background)
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest


class _FakeRedis:
    """Minimal async-redis double — supports scan_iter + delete."""

    def __init__(self):
        self.store: dict[str, str] = {}

    async def scan_iter(self, match: str = "*", count: int = 200):
        prefix = match.replace("*", "")
        for k in list(self.store):
            if k.startswith(prefix):
                yield k

    async def delete(self, *keys):
        n = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                n += 1
        return n


@pytest.mark.asyncio
async def test_invalidate_chunk_drops_rag_ctx_keys():
    from app.services import rag_invalidation

    fr = _FakeRedis()
    fr.store = {
        "rag:ctx:abc": "old1",
        "rag:ctx:def": "old2",
        "unrelated:key": "keep",
    }
    with patch("app.services.rag_invalidation._redis", return_value=fr), \
         patch("app.services.rag_invalidation.notification_manager.broadcast", new_callable=AsyncMock):
        await rag_invalidation.invalidate_chunk(uuid.uuid4(), action="updated")
    # rag:ctx:* dropped, unrelated kept
    assert "rag:ctx:abc" not in fr.store
    assert "rag:ctx:def" not in fr.store
    assert "unrelated:key" in fr.store


@pytest.mark.asyncio
async def test_invalidate_chunk_broadcasts_event():
    from app.services import rag_invalidation

    chunk_id = uuid.uuid4()
    broadcast_mock = AsyncMock()
    with patch("app.services.rag_invalidation._redis", return_value=_FakeRedis()), \
         patch("app.services.rag_invalidation.notification_manager.broadcast", broadcast_mock):
        await rag_invalidation.invalidate_chunk(chunk_id, action="created")

    broadcast_mock.assert_called_once()
    payload = broadcast_mock.call_args.args[0]
    assert payload["type"] == "knowledge.chunk.updated"
    assert payload["data"]["chunk_id"] == str(chunk_id)
    assert payload["data"]["action"] == "created"
    assert "ts" in payload["data"]


@pytest.mark.asyncio
async def test_invalidate_chunk_schedules_blitz_reload_on_update():
    """update/delete schedule the pool reload; create does NOT."""
    from app.services import rag_invalidation

    reload_mock = AsyncMock()
    with patch("app.services.rag_invalidation._redis", return_value=_FakeRedis()), \
         patch("app.services.rag_invalidation.notification_manager.broadcast", new_callable=AsyncMock), \
         patch("app.services.rag_invalidation._reload_blitz_pool", reload_mock):

        # created → no reload (new chunks picked up on next session start)
        await rag_invalidation.invalidate_chunk(uuid.uuid4(), action="created")
        await asyncio.sleep(0.05)
        assert reload_mock.call_count == 0

        # updated → reload scheduled
        await rag_invalidation.invalidate_chunk(uuid.uuid4(), action="updated")
        await asyncio.sleep(0.05)
        assert reload_mock.call_count == 1

        # deleted → reload scheduled
        await rag_invalidation.invalidate_chunk(uuid.uuid4(), action="deleted")
        await asyncio.sleep(0.05)
        assert reload_mock.call_count == 2


@pytest.mark.asyncio
async def test_invalidate_chunk_swallows_redis_failure():
    """Redis going down must not interrupt the CRUD response."""
    from app.services import rag_invalidation

    bad = AsyncMock()
    bad.scan_iter.side_effect = ConnectionError("redis down")
    bcast = AsyncMock()
    with patch("app.services.rag_invalidation._redis", return_value=bad), \
         patch("app.services.rag_invalidation.notification_manager.broadcast", bcast):
        # Must not raise.
        await rag_invalidation.invalidate_chunk(uuid.uuid4(), action="updated")
    # Broadcast still attempted.
    bcast.assert_called_once()


@pytest.mark.asyncio
async def test_invalidate_chunk_swallows_broadcast_failure():
    """A WS broadcast failure must not propagate."""
    from app.services import rag_invalidation

    bcast = AsyncMock(side_effect=RuntimeError("ws dead"))
    with patch("app.services.rag_invalidation._redis", return_value=_FakeRedis()), \
         patch("app.services.rag_invalidation.notification_manager.broadcast", bcast):
        await rag_invalidation.invalidate_chunk(uuid.uuid4(), action="updated")
