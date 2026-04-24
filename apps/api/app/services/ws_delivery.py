"""WS delivery service — persisted queue with replay on reconnect.

Producer flow:
    event = await enqueue(db, user_id=..., event_type="match.found", payload=..., ttl_seconds=300)
    # Same transaction as business write — commit owns both.
    await db.commit()
    # Best-effort immediate delivery. Outcome does not roll back the
    # business commit.
    await try_deliver(event, send_fn=local_send_fn)

Consumer flow on reconnect:
    pending = await process_pending_for_user(db, user_id, send_fn=local_send_fn)
    # pending is count of delivered events.

``send_fn`` is injected so the service never imports the per-route
``_active_connections`` maps (they live in ``ws/pvp.py``,
``ws/notifications.py``, ``ws/training.py``). The caller passes its
local lookup function.

Expiration: events past ``expires_at`` are marked ``expired`` on the
next poll and skipped — this avoids replaying a stale ``match.found``
to a player who joined a different queue two days later.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Awaitable, Callable

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ws_outbox import WsOutboxEvent, WsOutboxStatus

logger = logging.getLogger(__name__)


SendFn = Callable[[uuid.UUID, str, dict[str, Any]], Awaitable[bool]]
"""Returns True if delivery succeeded (recipient was connected), False otherwise."""


# Default TTLs (seconds) per event type. Anything not listed falls back
# to 5 minutes — that was the §10.1 baseline.
DEFAULT_TTL_SECONDS = 300
TTL_BY_EVENT_TYPE: dict[str, int] = {
    "match.found": 120,       # 2 min — if you didn't see it, the queue moved on
    "session.ended": 600,     # 10 min — user must get their results even after reload
    "session.results_ready": 600,
    "notification.new": 3600, # 1 hour — non-urgent
    "client.hangup": 300,
    "pvp.duel_cancelled": 300,
}


async def enqueue(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    event_type: str,
    payload: dict[str, Any] | None = None,
    correlation_id: str | None = None,
    ttl_seconds: int | None = None,
) -> WsOutboxEvent:
    """Persist a WS event to the outbox. Call inside the producer txn."""
    ttl = ttl_seconds if ttl_seconds is not None else TTL_BY_EVENT_TYPE.get(event_type, DEFAULT_TTL_SECONDS)
    now = datetime.now(UTC)
    event = WsOutboxEvent(
        id=uuid.uuid4(),
        user_id=user_id,
        event_type=event_type,
        payload=payload or {},
        status=WsOutboxStatus.pending.value,
        attempts=0,
        correlation_id=correlation_id,
        created_at=now,
        expires_at=now + timedelta(seconds=max(10, ttl)),
    )
    db.add(event)
    await db.flush()
    return event


async def try_deliver(
    db: AsyncSession,
    event: WsOutboxEvent,
    *,
    send_fn: SendFn,
) -> bool:
    """Attempt one send. Marks delivered on success, increments attempts
    on failure. Returns whether the send actually reached the user.
    """
    if event.status != WsOutboxStatus.pending.value:
        return event.status == WsOutboxStatus.delivered.value

    if event.expires_at and event.expires_at < datetime.now(UTC):
        event.status = WsOutboxStatus.expired.value
        await db.flush()
        return False

    try:
        delivered = await send_fn(event.user_id, event.event_type, event.payload or {})
    except Exception as exc:
        event.attempts += 1
        event.last_error = str(exc)[:500]
        event.next_retry_at = datetime.now(UTC) + timedelta(seconds=min(120, 5 * (2**min(event.attempts, 6))))
        await db.flush()
        logger.warning(
            "ws_delivery.send_failed user=%s type=%s attempt=%d",
            event.user_id, event.event_type, event.attempts, exc_info=True,
        )
        return False

    event.attempts += 1
    if delivered:
        event.status = WsOutboxStatus.delivered.value
        event.delivered_at = datetime.now(UTC)
    else:
        # User not connected — leave pending for later replay on reconnect.
        event.next_retry_at = datetime.now(UTC) + timedelta(seconds=min(60, 2 * event.attempts))
    await db.flush()
    return delivered


async def process_pending_for_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    send_fn: SendFn,
    limit: int = 50,
) -> int:
    """Drain the queue for ``user_id``. Called on reconnect.

    Returns the count of successfully delivered events. Events that
    expired in the meantime are marked ``expired`` and not sent.
    """
    now = datetime.now(UTC)
    pending = (
        await db.execute(
            select(WsOutboxEvent)
            .where(
                WsOutboxEvent.user_id == user_id,
                WsOutboxEvent.status == WsOutboxStatus.pending.value,
            )
            .order_by(WsOutboxEvent.created_at.asc())
            .limit(limit)
        )
    ).scalars().all()

    delivered_count = 0
    for event in pending:
        if event.expires_at and event.expires_at < now:
            event.status = WsOutboxStatus.expired.value
            continue
        if await try_deliver(db, event, send_fn=send_fn):
            delivered_count += 1
    await db.flush()
    return delivered_count


async def list_pending_for_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    limit: int = 50,
) -> list[WsOutboxEvent]:
    """Read-only fetch — used by ``GET /me/pending-events`` polling fallback."""
    now = datetime.now(UTC)
    stmt = (
        select(WsOutboxEvent)
        .where(
            WsOutboxEvent.user_id == user_id,
            WsOutboxEvent.status == WsOutboxStatus.pending.value,
            WsOutboxEvent.expires_at > now,
        )
        .order_by(WsOutboxEvent.created_at.asc())
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().all())


async def mark_delivered_by_ids(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    ids: list[uuid.UUID],
) -> int:
    """Mark a batch of events as delivered — used by the HTTP polling
    fallback when the client confirms it rendered them.
    """
    if not ids:
        return 0
    stmt = (
        update(WsOutboxEvent)
        .where(WsOutboxEvent.user_id == user_id, WsOutboxEvent.id.in_(ids))
        .values(status=WsOutboxStatus.delivered.value, delivered_at=datetime.now(UTC))
    )
    result = await db.execute(stmt)
    await db.flush()
    return result.rowcount or 0


async def expire_stale(db: AsyncSession, *, batch: int = 500) -> int:
    """Periodic cleanup — marks pending events whose ``expires_at`` is in
    the past as ``expired``. Safe to call from a scheduler every minute.
    """
    now = datetime.now(UTC)
    stmt = (
        update(WsOutboxEvent)
        .where(
            WsOutboxEvent.status == WsOutboxStatus.pending.value,
            WsOutboxEvent.expires_at < now,
        )
        .values(status=WsOutboxStatus.expired.value)
        .execution_options(synchronize_session=False)
    )
    result = await db.execute(stmt)
    await db.flush()
    return result.rowcount or 0


__all__ = [
    "DEFAULT_TTL_SECONDS",
    "SendFn",
    "TTL_BY_EVENT_TYPE",
    "enqueue",
    "expire_stale",
    "list_pending_for_user",
    "mark_delivered_by_ids",
    "process_pending_for_user",
    "try_deliver",
]
