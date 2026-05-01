"""Tests for app.services.arena_envelope.

Locks in the on-the-wire envelope shape so consumers and producers can
trust the contract without re-deriving it from Redis dumps.
"""

from __future__ import annotations

import json

import pytest

from app.services.arena_envelope import ArenaEvent


def test_create_stamps_uuid_and_timestamp():
    e = ArenaEvent.create(type="duel.message", payload={"text": "hi"})
    assert len(e.msg_id) == 32  # uuid hex without dashes
    assert e.ts > 0
    assert e.version == 1
    assert e.correlation_id == ""  # default
    assert e.producer == "unknown"  # default


def test_create_propagates_optional_fields():
    e = ArenaEvent.create(
        type="match.found",
        payload={"opponent_id": "x"},
        correlation_id="duel-123",
        producer="matchmaker.task",
    )
    assert e.correlation_id == "duel-123"
    assert e.producer == "matchmaker.task"
    assert e.type == "match.found"
    assert e.payload == {"opponent_id": "x"}


def test_to_redis_returns_only_strings():
    """Redis Streams require all field values be str/bytes — verify."""
    e = ArenaEvent.create(
        type="duel.message",
        payload={"text": "hi", "round": 1, "metadata": {"nested": True}},
        correlation_id="duel-abc",
        producer="ws.pvp.handler",
    )
    fields = e.to_redis()
    assert all(isinstance(v, str) for v in fields.values())
    # Required keys present.
    assert {"msg_id", "correlation_id", "type", "payload", "producer", "ts", "version"} <= set(fields)


def test_round_trip_preserves_all_fields():
    """to_redis → from_redis is lossless for the full payload."""
    payload = {
        "text": "Здравствуйте — клиент, читал ваш сайт",
        "round": 2,
        "lifelines_remaining": {"hint": 1, "skip": 0, "fifty_fifty": 1},
        "metadata": {"nested": {"deeper": [1, 2, 3]}},
    }
    e = ArenaEvent.create(
        type="duel.message",
        payload=payload,
        correlation_id="duel-deadbeef",
        producer="ws.pvp.handler",
    )
    decoded = ArenaEvent.from_redis(e.to_redis())
    assert decoded.msg_id == e.msg_id
    assert decoded.correlation_id == e.correlation_id
    assert decoded.type == e.type
    assert decoded.payload == e.payload
    assert decoded.producer == e.producer
    assert decoded.ts == pytest.approx(e.ts)
    assert decoded.version == e.version


def test_unicode_payload_preserved_through_redis_serialisation():
    """Russian text and emojis must survive json.dumps + parse without escapes."""
    e = ArenaEvent.create(
        type="judge.score",
        payload={"summary": "Победа продавца — 67 очков ✅"},
    )
    decoded = ArenaEvent.from_redis(e.to_redis())
    assert decoded.payload["summary"] == "Победа продавца — 67 очков ✅"


def test_from_redis_raises_on_missing_required_field():
    """Malformed envelope → KeyError so the consumer can ack-and-skip
    deliberately rather than silently drop a partial entry."""
    bad = {
        "msg_id": "abc",
        # missing "correlation_id"
        "type": "duel.message",
        "payload": "{}",
        "producer": "x",
        "ts": "0",
    }
    with pytest.raises(KeyError):
        ArenaEvent.from_redis(bad)


def test_from_redis_handles_empty_payload():
    """Some events may legitimately carry no payload (e.g. heartbeat)."""
    fields = {
        "msg_id": "abc",
        "correlation_id": "",
        "type": "heartbeat",
        "payload": "",
        "producer": "scheduler",
        "ts": "1234567890.0",
    }
    e = ArenaEvent.from_redis(fields)
    assert e.payload == {}


def test_event_is_frozen():
    """Immutability prevents a consumer from mutating an event other
    consumers also see (matters when we add in-process fan-out)."""
    e = ArenaEvent.create(type="x", payload={})
    with pytest.raises((AttributeError, TypeError)):
        e.type = "y"  # type: ignore[misc]


def test_payload_with_uuid_serializes_via_default_str():
    """to_redis uses ``json.dumps(default=str)`` so callers can pass
    UUID objects directly without manual stringification."""
    import uuid

    duel_uuid = uuid.uuid4()
    e = ArenaEvent.create(
        type="duel.created",
        payload={"duel_id": duel_uuid},
    )
    fields = e.to_redis()
    parsed = json.loads(fields["payload"])
    assert parsed["duel_id"] == str(duel_uuid)
