"""Consumer skeleton for the arena bus (Эпик 2 PR-3).

Builds on PR-1 (envelope + publish) and PR-2 (WS dual-write). PR-3 adds
the read side: an ``ArenaBusConsumer`` base class plus a first concrete
``AuditLogConsumer`` that simply logs every event at INFO. The audit
consumer proves the loop works end-to-end without changing user-facing
behaviour — once it's running cleanly in prod for a sprint, the Match
Orchestrator and Notification Hub epics drop in as additional consumers
on the same primitive.

Why consumer groups (``XREADGROUP``) and not bare ``XREAD``:
* At-least-once semantics: each entry is delivered to one consumer in
  the group, tracked in the Pending Entries List (PEL) until ``XACK``.
* Crash safety: if a consumer dies mid-handle, its PEL entries can be
  re-claimed by another consumer (``XAUTOCLAIM``) so no event is lost.
* Horizontal scaling: multiple consumers in the same group share the
  load; multiple groups (one per concern) read the same stream
  independently. This is exactly what the architectural rework needs
  for Notification Hub vs Match Orchestrator vs audit.

The base class doesn't try to be a full distributed-task runtime — it
is a small, opinionated wrapper that handles:
* Idempotent group creation (BUSYGROUP error swallowed).
* Single ``run_forever`` loop with cancellation hygiene.
* Decoding envelopes via ``ArenaEvent.from_redis``.
* ``XACK`` per successfully-handled entry; failed handles are left in
  PEL so a redelivery occurs (the handler is responsible for keeping
  side-effects idempotent — see ``handle()`` docstring).

What this PR does NOT do:
* No automatic redelivery / dead-letter on repeated handle failures.
  Phase 2 of consumer work — adds backoff + DLQ once a real consumer
  needs it.
* No multi-stream consumer; each ``ArenaBusConsumer`` reads a single
  stream. Wrap in a higher-level orchestrator if you need fan-in.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.services.arena_envelope import ArenaEvent

logger = logging.getLogger(__name__)


# Stream name shared with arena_bus.publish (kept in one place would be
# nice but circular-import-free is more important — we re-declare here
# intentionally, with a one-line cross-reference for grep).
_GLOBAL_STREAM = "arena:bus:global"  # mirror of arena_bus._GLOBAL_STREAM


class ArenaBusConsumer:
    """Base class for an arena-bus subscriber.

    Subclass and implement :meth:`handle`. Start with :meth:`run_forever`.

    Idempotency contract: the bus delivers each entry at-least-once, so
    ``handle()`` must produce the same observable side-effects regardless
    of how many times it's invoked for the same ``event.msg_id``. The
    simplest pattern is a Redis ``SETNX`` keyed on ``msg_id`` with a TTL
    matching the stream retention.
    """

    def __init__(
        self,
        *,
        group: str,
        consumer: str,
        stream: str = _GLOBAL_STREAM,
        batch: int = 10,
        block_ms: int = 5000,
    ) -> None:
        self.group = group
        self.consumer = consumer
        self.stream = stream
        self.batch = batch
        self.block_ms = block_ms
        self._stopped = asyncio.Event()

    async def ensure_group(self) -> None:
        """Create the consumer group if it does not exist.

        ``XGROUP CREATE ... MKSTREAM`` so we don't fail when the stream
        is empty (no events published yet). The ``BUSYGROUP`` error from
        a duplicate create is intentionally swallowed — the group either
        already exists from a previous run or another worker just
        created it.
        """
        from app.core.redis_pool import get_redis

        r = get_redis()
        try:
            await r.xgroup_create(
                name=self.stream, groupname=self.group, id="$", mkstream=True,
            )
            logger.info(
                "arena_bus.consumer: created group %r on %r",
                self.group, self.stream,
            )
        except Exception as exc:
            # redis-py wraps the BUSYGROUP error in ResponseError; we don't
            # depend on the exact class to keep the import surface tiny.
            if "BUSYGROUP" not in str(exc):
                raise
            logger.debug("arena_bus.consumer: group %r already exists", self.group)

    async def consume(self) -> list[tuple[str, ArenaEvent]]:
        """Read up to ``self.batch`` new entries claimed for ``self.consumer``.

        Returns a list of ``(entry_id, event)`` pairs. Empty list when
        the block timeout elapses with no traffic — caller decides
        whether to continue the loop or back off.

        Malformed envelopes are logged and skipped; the entry id is NOT
        ack'd here (caller's :meth:`run_forever` ack loop also skips it
        because it's not in the returned list — but that means the entry
        stays in the PEL forever unless a manual ``XACK`` is issued).
        For PR-3 we accept that malformed entries pile up in PEL; phase 2
        adds explicit ack-and-skip on parse failure.
        """
        from app.core.redis_pool import get_redis

        r = get_redis()
        raw = await r.xreadgroup(
            groupname=self.group,
            consumername=self.consumer,
            streams={self.stream: ">"},  # ">" = new entries since last delivery
            count=self.batch,
            block=self.block_ms,
        )
        if not raw:
            return []

        out: list[tuple[str, ArenaEvent]] = []
        for _stream_name, entries in raw:
            for entry_id, fields in entries:
                try:
                    event = ArenaEvent.from_redis(fields)
                except (KeyError, ValueError) as exc:
                    logger.warning(
                        "arena_bus.consumer[%s/%s]: skipping malformed entry %s: %s",
                        self.group, self.consumer, entry_id, exc,
                    )
                    continue
                out.append((entry_id, event))
        return out

    async def ack(self, entry_ids: list[str]) -> None:
        """``XACK`` one or more entries on this group's PEL."""
        if not entry_ids:
            return
        from app.core.redis_pool import get_redis

        r = get_redis()
        await r.xack(self.stream, self.group, *entry_ids)

    async def handle(self, event: ArenaEvent) -> None:
        """Process one event. Override in subclasses.

        Must be idempotent — the bus delivers at-least-once, so a crash
        between handle() and ack() (or a network blip mid-batch) results
        in redelivery. Use ``event.msg_id`` as the dedup key.
        """
        raise NotImplementedError

    def stop(self) -> None:
        """Signal :meth:`run_forever` to exit after the current batch."""
        self._stopped.set()

    async def run_forever(self) -> None:
        """Loop: read batch → handle each → ack handled.

        Cancellation: a clean ``CancelledError`` propagates after the
        current batch finishes its acks (so we don't leave handled
        entries un-ack'd on shutdown). For an immediate stop without
        waiting for the current batch, send the cancellation and accept
        that some events may be redelivered on the next start.
        """
        await self.ensure_group()
        logger.info(
            "arena_bus.consumer[%s/%s]: started on stream %r",
            self.group, self.consumer, self.stream,
        )
        try:
            while not self._stopped.is_set():
                try:
                    batch = await self.consume()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    # Transient Redis error — log and back off briefly
                    # rather than crash the consumer task.
                    logger.warning(
                        "arena_bus.consumer[%s/%s]: consume failed",
                        self.group, self.consumer, exc_info=True,
                    )
                    await asyncio.sleep(1.0)
                    continue

                handled_ids: list[str] = []
                for entry_id, event in batch:
                    try:
                        await self.handle(event)
                        handled_ids.append(entry_id)
                    except asyncio.CancelledError:
                        # Re-raise after acking already-handled entries;
                        # the failed entry stays in PEL for redelivery.
                        if handled_ids:
                            await self.ack(handled_ids)
                        raise
                    except Exception:
                        logger.exception(
                            "arena_bus.consumer[%s/%s]: handle failed for %s",
                            self.group, self.consumer, entry_id,
                        )
                if handled_ids:
                    await self.ack(handled_ids)
        finally:
            logger.info(
                "arena_bus.consumer[%s/%s]: stopped",
                self.group, self.consumer,
            )


class AuditLogConsumer(ArenaBusConsumer):
    """Reference consumer that logs every event at INFO.

    Production purpose: prove the bus loop works end-to-end before
    real consumers (Match Orchestrator, Notification Hub) ship. Also
    serves as a permanent audit trail — JSON logs from this consumer
    join logs ↔ bus events on ``correlation_id`` for forensics.

    The ``msg_id`` field is logged for at-least-once dedup analysis;
    if the same msg_id appears twice in a short window in production,
    it indicates either a redelivery (acceptable, expected on consumer
    crash) or a publish-side bug (escalate).
    """

    def __init__(self, consumer: str = "audit-1") -> None:
        super().__init__(
            group="arena.audit",
            consumer=consumer,
            stream=_GLOBAL_STREAM,
            batch=20,
            block_ms=5000,
        )

    async def handle(self, event: ArenaEvent) -> None:
        logger.info(
            "arena.bus.audit",
            extra={
                # Reuse the JSONFormatter whitelist (request_id /
                # correlation_id are auto-injected by LogContextFilter
                # but we set correlation_id explicitly for the consumer
                # task — the contextvar isn't bound here unless the
                # caller does it).
                "correlation_id": event.correlation_id,
                "user_id": (event.payload or {}).get("_recipient_user_id"),
            },
        )
        # The event metadata is also folded into the message body for
        # operators grepping a plain text view (when log_format=text).
        logger.debug(
            "arena.bus.audit detail msg_id=%s type=%s producer=%s ts=%.3f",
            event.msg_id, event.type, event.producer, event.ts,
        )


__all__ = [
    "ArenaBusConsumer",
    "AuditLogConsumer",
]
