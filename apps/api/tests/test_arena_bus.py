"""Tests for app.services.arena_bus — Redis Streams pub/sub primitives.

Uses unittest.mock for the redis client so the test suite stays self-
contained (no real Redis, no fakeredis dependency). The contract we
verify here:

* publish() pipelines XADD on global + per-correlation streams
* publish() omits the per-correlation XADD when correlation_id is empty
* publish() sets MAXLEN approximate=True on the global stream
* publish() sets MAXLEN + EXPIRE on the per-correlation stream
* read_global() and read_correlation() decode envelopes correctly
* read_*() skip malformed entries instead of crashing the batch
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import arena_bus
from app.services.arena_envelope import ArenaEvent


def _patched_redis(pipeline_mock: MagicMock, xread_return: list | None = None) -> MagicMock:
    """Return a MagicMock standing in for ``get_redis()`` output."""
    r = MagicMock()
    r.pipeline = MagicMock(return_value=pipeline_mock)
    r.xread = AsyncMock(return_value=xread_return or [])
    return r


def _pipeline_mock(execute_returns: list | None = None) -> MagicMock:
    p = MagicMock()
    p.xadd = MagicMock(return_value=p)  # chainable, like real redis-py pipeline
    p.expire = MagicMock(return_value=p)
    p.execute = AsyncMock(return_value=execute_returns or ["0-0"])
    return p


@pytest.mark.asyncio
async def test_publish_writes_global_and_correlation_streams():
    pipe = _pipeline_mock(execute_returns=["1234567-0", "1234567-0", True])
    redis_mock = _patched_redis(pipe)
    event = ArenaEvent.create(
        type="duel.message",
        payload={"text": "hi"},
        correlation_id="duel-abc",
        producer="ws.pvp.handler",
    )
    with patch("app.services.arena_bus.get_redis", return_value=redis_mock):
        await arena_bus.publish(event)

    # Two xadd calls: global + correlation. Plus one expire on correlation.
    assert pipe.xadd.call_count == 2
    assert pipe.expire.call_count == 1
    # Global stream first, correlation second (order matters for return id).
    first_call_stream = pipe.xadd.call_args_list[0].args[0]
    second_call_stream = pipe.xadd.call_args_list[1].args[0]
    assert first_call_stream == "arena:bus:global"
    assert second_call_stream == "arena:bus:correlation:duel-abc"


@pytest.mark.asyncio
async def test_publish_skips_correlation_stream_when_correlation_empty():
    pipe = _pipeline_mock(execute_returns=["1234567-0"])
    redis_mock = _patched_redis(pipe)
    event = ArenaEvent.create(type="heartbeat", payload={})  # correlation_id=""

    with patch("app.services.arena_bus.get_redis", return_value=redis_mock):
        await arena_bus.publish(event)

    # Only the global xadd; no correlation, no expire.
    assert pipe.xadd.call_count == 1
    assert pipe.expire.call_count == 0


@pytest.mark.asyncio
async def test_publish_sets_maxlen_and_approximate_on_global():
    pipe = _pipeline_mock(execute_returns=["1234567-0"])
    redis_mock = _patched_redis(pipe)
    event = ArenaEvent.create(type="heartbeat", payload={})

    with patch("app.services.arena_bus.get_redis", return_value=redis_mock):
        await arena_bus.publish(event)

    kwargs = pipe.xadd.call_args_list[0].kwargs
    assert kwargs["maxlen"] == 10_000
    assert kwargs["approximate"] is True


@pytest.mark.asyncio
async def test_publish_returns_global_xadd_id():
    pipe = _pipeline_mock(execute_returns=["1700000000000-0", "1700000000000-1", True])
    redis_mock = _patched_redis(pipe)
    event = ArenaEvent.create(
        type="duel.message",
        payload={"text": "hi"},
        correlation_id="duel-x",
    )
    with patch("app.services.arena_bus.get_redis", return_value=redis_mock):
        returned_id = await arena_bus.publish(event)

    assert returned_id == "1700000000000-0"


@pytest.mark.asyncio
async def test_read_global_decodes_envelope():
    event = ArenaEvent.create(
        type="match.found",
        payload={"opponent_id": "u-42"},
        correlation_id="duel-z",
    )
    fields = event.to_redis()
    raw_xread = [
        ("arena:bus:global", [("1700000000-0", fields)]),
    ]
    pipe = _pipeline_mock()
    redis_mock = _patched_redis(pipe, xread_return=raw_xread)

    with patch("app.services.arena_bus.get_redis", return_value=redis_mock):
        out = await arena_bus.read_global(last_id="$", count=10, block_ms=0)

    assert len(out) == 1
    entry_id, decoded = out[0]
    assert entry_id == "1700000000-0"
    assert decoded.msg_id == event.msg_id
    assert decoded.payload == event.payload


@pytest.mark.asyncio
async def test_read_correlation_returns_empty_for_empty_id():
    """No-op fast path — don't issue an XREAD against an empty key name."""
    pipe = _pipeline_mock()
    redis_mock = _patched_redis(pipe)
    with patch("app.services.arena_bus.get_redis", return_value=redis_mock):
        out = await arena_bus.read_correlation("", last_id="0-0")
    assert out == []
    redis_mock.xread.assert_not_called()


@pytest.mark.asyncio
async def test_read_skips_malformed_entry_without_crashing_batch():
    """A poison entry must not block legitimate ones in the same batch."""
    good = ArenaEvent.create(type="x", payload={"k": "v"})
    bad_fields = {
        "msg_id": "broken",
        # missing required ``correlation_id``, ``type``, etc.
    }
    raw_xread = [(
        "arena:bus:global",
        [
            ("1-0", bad_fields),
            ("2-0", good.to_redis()),
        ],
    )]
    pipe = _pipeline_mock()
    redis_mock = _patched_redis(pipe, xread_return=raw_xread)

    with patch("app.services.arena_bus.get_redis", return_value=redis_mock):
        out = await arena_bus.read_global()

    # Only the good entry survives.
    assert len(out) == 1
    assert out[0][0] == "2-0"
    assert out[0][1].msg_id == good.msg_id


@pytest.mark.asyncio
async def test_read_global_returns_empty_when_xread_empty():
    pipe = _pipeline_mock()
    redis_mock = _patched_redis(pipe, xread_return=None)
    with patch("app.services.arena_bus.get_redis", return_value=redis_mock):
        out = await arena_bus.read_global()
    assert out == []


@pytest.mark.asyncio
async def test_read_correlation_uses_correlation_stream_name():
    pipe = _pipeline_mock()
    redis_mock = _patched_redis(pipe, xread_return=[])
    with patch("app.services.arena_bus.get_redis", return_value=redis_mock):
        await arena_bus.read_correlation("duel-42", last_id="0-0", count=50)

    redis_mock.xread.assert_awaited_once()
    call_kwargs = redis_mock.xread.call_args.kwargs
    assert call_kwargs["streams"] == {"arena:bus:correlation:duel-42": "0-0"}
    assert call_kwargs["count"] == 50
