"""Tests for the live embedding backfill (Content→Arena PR-6).

Locks in:

* enqueue_chunk pushes onto the right Redis list and trims to MAXLEN
* enqueue_chunk swallows Redis errors (best-effort contract)
* queue_length returns -1 when Redis is down
* The worker BLPOPs, decodes UUIDs, and dispatches to the embedder
* Worker skips non-existent chunks gracefully
* Worker skips inactive chunks (rag_legal already filters them)
* Worker writes the embedding row when the provider returns a vector
* Worker handles malformed queue entries without crashing the loop
* Worker.stop() exits the run_forever loop cooperatively
* Embedding-provider failure does not crash the worker
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import embedding_live_backfill as elb


def _redis_mock() -> MagicMock:
    r = MagicMock()
    r.rpush = AsyncMock()
    r.ltrim = AsyncMock()
    r.llen = AsyncMock(return_value=0)
    r.blpop = AsyncMock()
    pipe = MagicMock()
    pipe.rpush = MagicMock(return_value=pipe)
    pipe.ltrim = MagicMock(return_value=pipe)
    pipe.execute = AsyncMock()
    r.pipeline = MagicMock(return_value=pipe)
    return r


# ── enqueue / queue_length ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enqueue_pushes_to_correct_list_and_trims():
    r = _redis_mock()
    chunk_id = uuid.uuid4()

    with patch("app.core.redis_pool.get_redis", return_value=r):
        await elb.enqueue_chunk(chunk_id)

    pipe = r.pipeline.return_value
    pipe.rpush.assert_called_once_with("arena:embedding:backfill:legal_chunks", str(chunk_id))
    pipe.ltrim.assert_called_once_with("arena:embedding:backfill:legal_chunks", -5_000, -1)


@pytest.mark.asyncio
async def test_enqueue_swallows_redis_errors():
    """Best-effort: Redis down → no exception bubbles up."""
    r = MagicMock()
    r.pipeline = MagicMock(side_effect=ConnectionError("redis down"))

    with patch("app.core.redis_pool.get_redis", return_value=r):
        # Must not raise.
        await elb.enqueue_chunk(uuid.uuid4())


@pytest.mark.asyncio
async def test_queue_length_returns_minus_one_on_redis_failure():
    r = MagicMock()
    r.llen = AsyncMock(side_effect=ConnectionError("redis down"))

    with patch("app.core.redis_pool.get_redis", return_value=r):
        assert await elb.queue_length() == -1


@pytest.mark.asyncio
async def test_queue_length_happy_path():
    r = _redis_mock()
    r.llen = AsyncMock(return_value=42)

    with patch("app.core.redis_pool.get_redis", return_value=r):
        assert await elb.queue_length() == 42


# ── populate_single_legal_chunk_embedding ────────────────────────────────


@pytest.mark.asyncio
async def test_populate_single_writes_embedding_for_active_chunk():
    chunk_id = uuid.uuid4()

    # Stub DB session: select returns (fact_text, is_active=True);
    # update + commit are AsyncMocks.
    select_row = MagicMock(fact_text="ст. 213.3 — порог банкротства", is_active=True)
    select_result = MagicMock()
    select_result.first = MagicMock(return_value=select_row)
    db = MagicMock()
    db.execute = AsyncMock(return_value=select_result)
    db.commit = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=False)

    expected_vec = [0.1] * 768

    with patch("app.database.async_session", return_value=cm), \
         patch(
            "app.services.llm.get_embeddings_batch",
            new=AsyncMock(return_value=[expected_vec]),
         ):
        ok = await elb.populate_single_legal_chunk_embedding(chunk_id)

    assert ok is True
    db.commit.assert_awaited_once()
    # Two execute calls: SELECT then UPDATE.
    assert db.execute.await_count >= 2


@pytest.mark.asyncio
async def test_populate_single_skips_inactive_chunk():
    select_row = MagicMock(fact_text="x", is_active=False)
    select_result = MagicMock()
    select_result.first = MagicMock(return_value=select_row)
    db = MagicMock()
    db.execute = AsyncMock(return_value=select_result)
    db.commit = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.database.async_session", return_value=cm), \
         patch("app.services.llm.get_embeddings_batch", new=AsyncMock()) as mock_emb:
        ok = await elb.populate_single_legal_chunk_embedding(uuid.uuid4())

    assert ok is False
    mock_emb.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_populate_single_returns_false_when_chunk_missing():
    select_result = MagicMock()
    select_result.first = MagicMock(return_value=None)
    db = MagicMock()
    db.execute = AsyncMock(return_value=select_result)
    db.commit = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.database.async_session", return_value=cm):
        ok = await elb.populate_single_legal_chunk_embedding(uuid.uuid4())

    assert ok is False
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_populate_single_returns_false_on_provider_failure():
    select_row = MagicMock(fact_text="text", is_active=True)
    select_result = MagicMock()
    select_result.first = MagicMock(return_value=select_row)
    db = MagicMock()
    db.execute = AsyncMock(return_value=select_result)
    db.commit = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.database.async_session", return_value=cm), \
         patch(
            "app.services.llm.get_embeddings_batch",
            new=AsyncMock(side_effect=Exception("provider down")),
         ):
        ok = await elb.populate_single_legal_chunk_embedding(uuid.uuid4())

    assert ok is False


# ── Worker ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_worker_dispatches_dequeued_chunk_to_embedder():
    """End-to-end loop: BLPOP returns one id → embedder is called."""
    chunk_id = uuid.uuid4()
    r = _redis_mock()
    r.blpop = AsyncMock(side_effect=[
        ("arena:embedding:backfill:legal_chunks", str(chunk_id)),
        None,  # second poll: timeout, lets stop signal exit the loop
    ])

    embedder = AsyncMock(return_value=True)
    worker = elb.LiveEmbeddingBackfillWorker(block_timeout_seconds=0, idle_sleep=0.01)

    async def stopper():
        await asyncio.sleep(0.05)
        worker.stop()

    with patch("app.core.redis_pool.get_redis", return_value=r), \
         patch.object(elb, "populate_single_legal_chunk_embedding", embedder):
        await asyncio.wait_for(
            asyncio.gather(worker.run_forever(), stopper()),
            timeout=2.0,
        )

    embedder.assert_awaited_once_with(chunk_id)
    assert worker.processed_count == 1


@pytest.mark.asyncio
async def test_worker_handles_malformed_queue_entry():
    r = _redis_mock()
    r.blpop = AsyncMock(side_effect=[
        ("arena:embedding:backfill:legal_chunks", "not-a-uuid"),
        None,
    ])
    embedder = AsyncMock()
    worker = elb.LiveEmbeddingBackfillWorker(block_timeout_seconds=0, idle_sleep=0.01)

    async def stopper():
        await asyncio.sleep(0.05)
        worker.stop()

    with patch("app.core.redis_pool.get_redis", return_value=r), \
         patch.object(elb, "populate_single_legal_chunk_embedding", embedder):
        await asyncio.wait_for(
            asyncio.gather(worker.run_forever(), stopper()),
            timeout=2.0,
        )

    embedder.assert_not_called()
    assert worker.processed_count == 0


@pytest.mark.asyncio
async def test_worker_recovers_from_blpop_exception():
    """A transient Redis error must not kill the worker task."""
    r = MagicMock()
    r.blpop = AsyncMock(side_effect=[ConnectionError("blip"), None])

    embedder = AsyncMock(return_value=True)
    worker = elb.LiveEmbeddingBackfillWorker(block_timeout_seconds=0, idle_sleep=0.01)

    async def stopper():
        await asyncio.sleep(0.1)
        worker.stop()

    with patch("app.core.redis_pool.get_redis", return_value=r), \
         patch.object(elb, "populate_single_legal_chunk_embedding", embedder):
        await asyncio.wait_for(
            asyncio.gather(worker.run_forever(), stopper()),
            timeout=2.0,
        )

    embedder.assert_not_called()
    # Worker reached a second BLPOP after the first raised, proving recovery.
    assert r.blpop.await_count >= 2


@pytest.mark.asyncio
async def test_worker_does_not_increment_count_on_failed_embed():
    r = _redis_mock()
    r.blpop = AsyncMock(side_effect=[
        ("arena:embedding:backfill:legal_chunks", str(uuid.uuid4())),
        None,
    ])
    failing_embed = AsyncMock(return_value=False)
    worker = elb.LiveEmbeddingBackfillWorker(block_timeout_seconds=0, idle_sleep=0.01)

    async def stopper():
        await asyncio.sleep(0.05)
        worker.stop()

    with patch("app.core.redis_pool.get_redis", return_value=r), \
         patch.object(elb, "populate_single_legal_chunk_embedding", failing_embed):
        await asyncio.wait_for(
            asyncio.gather(worker.run_forever(), stopper()),
            timeout=2.0,
        )

    failing_embed.assert_awaited_once()
    assert worker.processed_count == 0  # only success increments


@pytest.mark.asyncio
async def test_worker_decodes_bytes_payload():
    """Some redis-py configurations return bytes — worker handles both."""
    chunk_id = uuid.uuid4()
    r = _redis_mock()
    r.blpop = AsyncMock(side_effect=[
        (b"arena:embedding:backfill:legal_chunks", str(chunk_id).encode()),
        None,
    ])
    embedder = AsyncMock(return_value=True)
    worker = elb.LiveEmbeddingBackfillWorker(block_timeout_seconds=0, idle_sleep=0.01)

    async def stopper():
        await asyncio.sleep(0.05)
        worker.stop()

    with patch("app.core.redis_pool.get_redis", return_value=r), \
         patch.object(elb, "populate_single_legal_chunk_embedding", embedder):
        await asyncio.wait_for(
            asyncio.gather(worker.run_forever(), stopper()),
            timeout=2.0,
        )

    embedder.assert_awaited_once_with(chunk_id)
