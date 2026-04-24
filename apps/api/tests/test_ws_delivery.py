"""Phase 5 WS Outbox tests (Roadmap §10.7 acceptance)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.ws_outbox import WsOutboxEvent, WsOutboxStatus
from app.services import ws_delivery


def _fake_db(row=None, rows=None):
    db = SimpleNamespace()
    db.added: list = []

    async def _flush():
        for obj in db.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    db.flush = AsyncMock(side_effect=_flush)

    def _add(obj):
        db.added.append(obj)

    db.add = MagicMock(side_effect=_add)

    class _Result:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

        def scalars(self):
            return SimpleNamespace(all=lambda: self._value or [])

    if rows is not None:
        db.execute = AsyncMock(return_value=_Result(rows))
    elif row is not None:
        db.execute = AsyncMock(return_value=_Result(row))
    else:
        db.execute = AsyncMock(return_value=_Result([]))
    return db


@pytest.mark.asyncio
async def test_enqueue_persists_event_with_ttl():
    db = _fake_db()
    user_id = uuid.uuid4()
    event = await ws_delivery.enqueue(
        db,
        user_id=user_id,
        event_type="match.found",
        payload={"duel_id": "x"},
    )
    assert event.user_id == user_id
    assert event.event_type == "match.found"
    assert event.status == WsOutboxStatus.pending.value
    assert event.expires_at > event.created_at
    # match.found TTL override (§10.1 baseline)
    assert (event.expires_at - event.created_at).total_seconds() == 120
    assert db.added == [event]


@pytest.mark.asyncio
async def test_enqueue_defaults_ttl_when_event_unknown():
    db = _fake_db()
    event = await ws_delivery.enqueue(
        db, user_id=uuid.uuid4(), event_type="something.custom",
    )
    assert (event.expires_at - event.created_at).total_seconds() == ws_delivery.DEFAULT_TTL_SECONDS


@pytest.mark.asyncio
async def test_try_deliver_marks_delivered_on_success():
    now = datetime.now(UTC)
    event = WsOutboxEvent(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        event_type="match.found",
        payload={"x": 1},
        status=WsOutboxStatus.pending.value,
        attempts=0,
        created_at=now,
        expires_at=now + timedelta(seconds=120),
    )
    db = _fake_db()
    send = AsyncMock(return_value=True)

    ok = await ws_delivery.try_deliver(db, event, send_fn=send)

    assert ok is True
    assert event.status == WsOutboxStatus.delivered.value
    assert event.delivered_at is not None
    assert event.attempts == 1
    send.assert_awaited_once_with(event.user_id, "match.found", {"x": 1})


@pytest.mark.asyncio
async def test_try_deliver_leaves_pending_when_user_offline():
    now = datetime.now(UTC)
    event = WsOutboxEvent(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        event_type="match.found",
        payload={},
        status=WsOutboxStatus.pending.value,
        attempts=0,
        created_at=now,
        expires_at=now + timedelta(seconds=120),
    )
    db = _fake_db()
    send = AsyncMock(return_value=False)

    ok = await ws_delivery.try_deliver(db, event, send_fn=send)

    assert ok is False
    assert event.status == WsOutboxStatus.pending.value  # stays for replay
    assert event.delivered_at is None
    assert event.attempts == 1
    assert event.next_retry_at is not None


@pytest.mark.asyncio
async def test_try_deliver_expires_past_deadline():
    expired_at = datetime.now(UTC) - timedelta(seconds=60)
    event = WsOutboxEvent(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        event_type="match.found",
        payload={},
        status=WsOutboxStatus.pending.value,
        attempts=0,
        created_at=expired_at - timedelta(seconds=120),
        expires_at=expired_at,
    )
    db = _fake_db()
    send = AsyncMock(return_value=True)

    ok = await ws_delivery.try_deliver(db, event, send_fn=send)

    assert ok is False
    assert event.status == WsOutboxStatus.expired.value
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_pending_drains_queue_in_order():
    user_id = uuid.uuid4()
    now = datetime.now(UTC)
    older = WsOutboxEvent(
        id=uuid.uuid4(),
        user_id=user_id,
        event_type="notification.new",
        payload={"n": 1},
        status=WsOutboxStatus.pending.value,
        attempts=0,
        created_at=now - timedelta(seconds=10),
        expires_at=now + timedelta(seconds=100),
    )
    newer = WsOutboxEvent(
        id=uuid.uuid4(),
        user_id=user_id,
        event_type="session.ended",
        payload={"n": 2},
        status=WsOutboxStatus.pending.value,
        attempts=0,
        created_at=now,
        expires_at=now + timedelta(seconds=100),
    )
    db = _fake_db(rows=[older, newer])
    delivered_calls: list[tuple[str, dict]] = []

    async def send(user, etype, payload):
        delivered_calls.append((etype, payload))
        return True

    count = await ws_delivery.process_pending_for_user(db, user_id, send_fn=send)

    assert count == 2
    # FIFO — older event first
    assert delivered_calls[0][0] == "notification.new"
    assert delivered_calls[1][0] == "session.ended"


@pytest.mark.asyncio
async def test_list_pending_returns_non_expired_only(monkeypatch):
    user_id = uuid.uuid4()
    now = datetime.now(UTC)
    expected = WsOutboxEvent(
        id=uuid.uuid4(),
        user_id=user_id,
        event_type="match.found",
        payload={},
        status=WsOutboxStatus.pending.value,
        attempts=0,
        created_at=now,
        expires_at=now + timedelta(seconds=100),
    )
    db = _fake_db(rows=[expected])

    result = await ws_delivery.list_pending_for_user(db, user_id)
    assert result == [expected]
