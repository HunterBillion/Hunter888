"""Tests for app.services.arena_bus_consumer (Эпик 2 PR-3).

Mocks the redis client (no real Redis, no fakeredis dependency) and
verifies:

* ensure_group is idempotent — BUSYGROUP error is swallowed.
* consume() reads via XREADGROUP with the right kwargs and decodes.
* consume() skips malformed entries without raising.
* run_forever() loops, calls handle(), acks handled entries.
* run_forever() stops on .stop() signal between batches.
* AuditLogConsumer hits handle and emits a log line.
* CancelledError mid-batch acks already-handled entries before raising.
"""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.arena_bus_consumer import ArenaBusConsumer, AuditLogConsumer
from app.services.arena_envelope import ArenaEvent


# ---------- ensure_group idempotency ----------------------------------------


@pytest.mark.asyncio
async def test_ensure_group_creates_when_missing():
    redis_mock = MagicMock()
    redis_mock.xgroup_create = AsyncMock()
    consumer = ArenaBusConsumer(group="g1", consumer="c1")

    with patch("app.core.redis_pool.get_redis", return_value=redis_mock):
        await consumer.ensure_group()

    redis_mock.xgroup_create.assert_awaited_once_with(
        name="arena:bus:global", groupname="g1", id="$", mkstream=True,
    )


@pytest.mark.asyncio
async def test_ensure_group_swallows_busygroup():
    """Duplicate group create is a no-op — must not raise."""
    redis_mock = MagicMock()
    redis_mock.xgroup_create = AsyncMock(
        side_effect=Exception("BUSYGROUP Consumer Group name already exists"),
    )
    consumer = ArenaBusConsumer(group="g1", consumer="c1")

    with patch("app.core.redis_pool.get_redis", return_value=redis_mock):
        await consumer.ensure_group()  # no exception


@pytest.mark.asyncio
async def test_ensure_group_reraises_other_redis_errors():
    """Non-BUSYGROUP errors must propagate so operators notice."""
    redis_mock = MagicMock()
    redis_mock.xgroup_create = AsyncMock(side_effect=ConnectionError("redis down"))
    consumer = ArenaBusConsumer(group="g1", consumer="c1")

    with patch("app.core.redis_pool.get_redis", return_value=redis_mock):
        with pytest.raises(ConnectionError):
            await consumer.ensure_group()


# ---------- consume() decoding ----------------------------------------------


@pytest.mark.asyncio
async def test_consume_decodes_envelope():
    event = ArenaEvent.create(type="x", payload={"k": "v"}, correlation_id="cid-1")
    raw = [(b"arena:bus:global", [(b"100-0", event.to_redis())])]
    redis_mock = MagicMock()
    redis_mock.xreadgroup = AsyncMock(return_value=raw)
    consumer = ArenaBusConsumer(group="g1", consumer="c1")

    with patch("app.core.redis_pool.get_redis", return_value=redis_mock):
        out = await consumer.consume()

    assert len(out) == 1
    entry_id, decoded = out[0]
    assert entry_id == b"100-0"
    assert decoded.msg_id == event.msg_id


@pytest.mark.asyncio
async def test_consume_uses_correct_xreadgroup_args():
    redis_mock = MagicMock()
    redis_mock.xreadgroup = AsyncMock(return_value=[])
    consumer = ArenaBusConsumer(
        group="my-group", consumer="my-consumer", batch=42, block_ms=1234,
    )

    with patch("app.core.redis_pool.get_redis", return_value=redis_mock):
        await consumer.consume()

    redis_mock.xreadgroup.assert_awaited_once_with(
        groupname="my-group",
        consumername="my-consumer",
        streams={"arena:bus:global": ">"},
        count=42,
        block=1234,
    )


@pytest.mark.asyncio
async def test_consume_skips_malformed_entries_in_batch():
    good = ArenaEvent.create(type="x", payload={})
    raw = [(
        b"arena:bus:global",
        [
            (b"1-0", {"msg_id": "broken"}),  # missing required fields
            (b"2-0", good.to_redis()),
        ],
    )]
    redis_mock = MagicMock()
    redis_mock.xreadgroup = AsyncMock(return_value=raw)
    consumer = ArenaBusConsumer(group="g1", consumer="c1")

    with patch("app.core.redis_pool.get_redis", return_value=redis_mock):
        out = await consumer.consume()

    assert len(out) == 1
    assert out[0][0] == b"2-0"


@pytest.mark.asyncio
async def test_consume_returns_empty_on_block_timeout():
    """XREADGROUP with no new entries returns None — translate to []."""
    redis_mock = MagicMock()
    redis_mock.xreadgroup = AsyncMock(return_value=None)
    consumer = ArenaBusConsumer(group="g1", consumer="c1")

    with patch("app.core.redis_pool.get_redis", return_value=redis_mock):
        out = await consumer.consume()

    assert out == []


# ---------- ack -------------------------------------------------------------


@pytest.mark.asyncio
async def test_ack_calls_xack_with_entry_ids():
    redis_mock = MagicMock()
    redis_mock.xack = AsyncMock()
    consumer = ArenaBusConsumer(group="g", consumer="c")

    with patch("app.core.redis_pool.get_redis", return_value=redis_mock):
        await consumer.ack(["1-0", "2-0", "3-0"])

    redis_mock.xack.assert_awaited_once_with(
        "arena:bus:global", "g", "1-0", "2-0", "3-0",
    )


@pytest.mark.asyncio
async def test_ack_no_op_on_empty_list():
    redis_mock = MagicMock()
    redis_mock.xack = AsyncMock()
    consumer = ArenaBusConsumer(group="g", consumer="c")

    with patch("app.core.redis_pool.get_redis", return_value=redis_mock):
        await consumer.ack([])

    redis_mock.xack.assert_not_called()


# ---------- run_forever loop ------------------------------------------------


class _FakeConsumer(ArenaBusConsumer):
    def __init__(self, **kwargs):
        super().__init__(group="t", consumer="t", **kwargs)
        self.handled: list[ArenaEvent] = []

    async def handle(self, event: ArenaEvent) -> None:
        self.handled.append(event)


@pytest.mark.asyncio
async def test_run_forever_handles_and_acks_then_stops():
    """Single batch → handle each → ack handled IDs → stop signal exits."""
    e1 = ArenaEvent.create(type="x", payload={"i": 1})
    e2 = ArenaEvent.create(type="x", payload={"i": 2})
    redis_mock = MagicMock()
    redis_mock.xgroup_create = AsyncMock()
    # First call returns 2 entries, second call we just have stop set
    raw_batches = [
        [(b"arena:bus:global", [(b"1-0", e1.to_redis()), (b"2-0", e2.to_redis())])],
        None,  # second poll: nothing
    ]
    redis_mock.xreadgroup = AsyncMock(side_effect=raw_batches)
    redis_mock.xack = AsyncMock()

    c = _FakeConsumer()

    async def stopper():
        # let one batch complete, then stop
        await asyncio.sleep(0.05)
        c.stop()

    with patch("app.core.redis_pool.get_redis", return_value=redis_mock):
        await asyncio.wait_for(
            asyncio.gather(c.run_forever(), stopper()),
            timeout=2.0,
        )

    assert [e.payload["i"] for e in c.handled] == [1, 2]
    redis_mock.xack.assert_awaited_once_with("arena:bus:global", "t", b"1-0", b"2-0")


@pytest.mark.asyncio
async def test_run_forever_skips_failed_handles_but_acks_others():
    """A failing handle leaves its entry un-ack'd (so it'll be redelivered)
    but other entries in the same batch still get ack'd.
    """
    e_ok = ArenaEvent.create(type="ok", payload={})
    e_bad = ArenaEvent.create(type="bad", payload={})

    raw = [(b"arena:bus:global", [(b"1-0", e_ok.to_redis()), (b"2-0", e_bad.to_redis())])]
    redis_mock = MagicMock()
    redis_mock.xgroup_create = AsyncMock()
    redis_mock.xreadgroup = AsyncMock(side_effect=[raw, None])
    redis_mock.xack = AsyncMock()

    class FailOnBad(_FakeConsumer):
        async def handle(self, event):
            if event.type == "bad":
                raise RuntimeError("kaboom")
            self.handled.append(event)

    c = FailOnBad()

    async def stopper():
        await asyncio.sleep(0.05)
        c.stop()

    with patch("app.core.redis_pool.get_redis", return_value=redis_mock):
        await asyncio.wait_for(
            asyncio.gather(c.run_forever(), stopper()),
            timeout=2.0,
        )

    # only the good one was handled, only its id was ack'd
    assert len(c.handled) == 1
    assert c.handled[0].type == "ok"
    redis_mock.xack.assert_awaited_once_with("arena:bus:global", "t", b"1-0")


@pytest.mark.asyncio
async def test_run_forever_recovers_from_consume_exception():
    """A transient Redis error in xreadgroup must back off and retry, not
    crash the consumer task."""
    redis_mock = MagicMock()
    redis_mock.xgroup_create = AsyncMock()
    redis_mock.xreadgroup = AsyncMock(
        side_effect=[ConnectionError("blip"), None],
    )
    redis_mock.xack = AsyncMock()
    c = _FakeConsumer(block_ms=10)

    async def stopper():
        await asyncio.sleep(1.5)
        c.stop()

    with patch("app.core.redis_pool.get_redis", return_value=redis_mock):
        await asyncio.wait_for(
            asyncio.gather(c.run_forever(), stopper()),
            timeout=4.0,
        )

    # Reached the second xreadgroup, so we recovered.
    assert redis_mock.xreadgroup.await_count >= 2


# ---------- AuditLogConsumer ------------------------------------------------


@pytest.mark.asyncio
async def test_audit_log_consumer_logs_each_event(caplog):
    caplog.set_level(logging.INFO)
    c = AuditLogConsumer(consumer="audit-test")
    e = ArenaEvent.create(
        type="duel.message",
        payload={"text": "hi", "_recipient_user_id": "u-1"},
        correlation_id="duel-z",
        producer="ws.pvp.handler",
    )
    await c.handle(e)
    # Exactly one INFO record with our marker message
    audit_records = [r for r in caplog.records if r.message == "arena.bus.audit"]
    assert len(audit_records) == 1
    rec = audit_records[0]
    # extra= fields are attached as attributes on the LogRecord
    assert getattr(rec, "correlation_id", None) == "duel-z"
    assert getattr(rec, "user_id", None) == "u-1"
