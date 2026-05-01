"""ArenaBus — Redis-Streams pub/sub for the arena (Эпик 2 fundament).

Two streams per event publish:

* ``arena:bus:global``                 — single stream every consumer
  joins. Notification Hub, audit, observability, dashboards. Used for
  cross-cutting subscribers that don't care which duel an event came
  from.

* ``arena:bus:correlation:{cid}``      — per-correlation stream (one
  per ``duel_id`` / ``session_id`` / ``queue_id``). Match Orchestrator
  consumes its own duel's stream; spectator consumers join here too.

Why dual-write rather than one stream + filter: per-correlation
subscribers can ``XREAD BLOCK`` against a single dense stream with
known cardinality (50–500 events / duel) instead of polling a global
stream that's hot with thousands of unrelated events. Cost of two
``XADD`` is ~80 µs in a Redis pipeline, well within budget.

Bounded growth: every ``XADD`` carries ``MAXLEN ~ N`` so the global
stream auto-trims. Per-correlation streams expire via a TTL set on
first publish; orchestrator cleanup at finalize is best-effort but the
TTL guarantees Redis memory bounds even if cleanup misses.

This module is intentionally thin: publish + read primitives only.
Consumers (Match Orchestrator, Notification Hub, …) live elsewhere
and own their consumer-group state. ``arena_bus`` does not know what
state-machine is reading from it — it's the postal service, not the
recipient.

Compat with current code:
* Existing WS-event broadcasts (`_send_to_user`, etc.) are NOT replaced
  by this module in this PR. PR-2 of Эпик 2 will dual-write a copy of
  every WS-event to the bus under a feature flag.
* `runtime_metrics` and `arena_metrics` (PR A/B) are unaffected: the
  bus is a transport, the metrics layer keeps measuring whatever code
  calls it.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.redis_pool import get_redis
from app.services.arena_envelope import ArenaEvent

logger = logging.getLogger(__name__)


# Stream-name templates ------------------------------------------------------

_GLOBAL_STREAM = "arena:bus:global"
_CORRELATION_STREAM = "arena:bus:correlation:{cid}"


# Bounded growth -------------------------------------------------------------

# Trim the global stream to the last N events. 10 000 events at average
# ~512 bytes/envelope = ~5 MB Redis memory; aggressively pruned because
# global subscribers are expected to keep up in near-real-time.
_GLOBAL_MAXLEN = 10_000

# Per-correlation stream lifetime. A duel completes in 5–10 minutes;
# 1 hour gives consumers ample replay window plus buffer for
# disconnect-grace + reconnect (60s) + finalize race recovery. After
# 1 hour the stream auto-evicts, releasing memory even if the
# orchestrator never explicitly cleans up.
_CORRELATION_TTL_SECONDS = 3600

# Per-correlation MAXLEN guards against pathological events-per-duel
# producers (a misconfigured loop that floods one duel with millions
# of events would otherwise OOM Redis even within 1 hour).
_CORRELATION_MAXLEN = 5_000


# Public API -----------------------------------------------------------------


async def publish(event: ArenaEvent) -> str:
    """Publish ``event`` to both the global stream and the per-correlation
    stream (if ``event.correlation_id`` is non-empty).

    Returns the global-stream entry id (``"<ms>-<seq>"``) — useful for
    callers that want to log a bus-level reference for the publication.

    Failure modes:
    * Redis unreachable → ``ConnectionError`` is logged at WARNING and
      re-raised. Callers (typically background tasks) should treat the
      bus as best-effort: a missed publish degrades observability but
      MUST NOT block the user-facing path. The recommended pattern is
      ``await asyncio.shield(publish(...))`` inside a try/except.
    * Empty ``correlation_id`` → only the global stream gets written.
      Skipping the per-correlation write is the right behaviour: there
      is no correlation to subscribe to.
    """
    r = get_redis()
    fields = event.to_redis()

    pipe = r.pipeline()
    pipe.xadd(_GLOBAL_STREAM, fields, maxlen=_GLOBAL_MAXLEN, approximate=True)
    if event.correlation_id:
        cid_key = _CORRELATION_STREAM.format(cid=event.correlation_id)
        pipe.xadd(cid_key, fields, maxlen=_CORRELATION_MAXLEN, approximate=True)
        pipe.expire(cid_key, _CORRELATION_TTL_SECONDS)

    results = await pipe.execute()
    # First entry is the XADD id from the global stream.
    return results[0] if isinstance(results[0], str) else results[0].decode()


async def read_global(
    *,
    last_id: str = "$",
    count: int = 100,
    block_ms: int = 0,
) -> list[tuple[str, ArenaEvent]]:
    """Read up to ``count`` events from the global stream after ``last_id``.

    ``last_id="$"`` means "events arriving from now" (typical first call
    for a fresh subscriber). Subsequent calls pass back the last id seen
    to walk the stream forward.

    ``block_ms=0`` means non-blocking (return immediately if no new
    events). Pass a positive value for blocking ``XREAD`` semantics.

    Returns a list of ``(stream_entry_id, ArenaEvent)`` tuples in the
    order Redis returned them. Malformed entries (missing required
    envelope fields) are SKIPPED with a WARNING log so a single bad
    entry can't poison the whole batch.
    """
    r = get_redis()
    raw = await r.xread(
        streams={_GLOBAL_STREAM: last_id},
        count=count,
        block=block_ms,
    )
    return _decode_xread(raw)


async def read_correlation(
    correlation_id: str,
    *,
    last_id: str = "0-0",
    count: int = 500,
    block_ms: int = 0,
) -> list[tuple[str, ArenaEvent]]:
    """Read events for a single correlation_id.

    ``last_id="0-0"`` returns the full retained history (up to
    ``_CORRELATION_MAXLEN``). Use this for replay on consumer restart;
    pass the last seen entry id for incremental catch-up.
    """
    if not correlation_id:
        return []
    r = get_redis()
    cid_key = _CORRELATION_STREAM.format(cid=correlation_id)
    raw = await r.xread(
        streams={cid_key: last_id},
        count=count,
        block=block_ms,
    )
    return _decode_xread(raw)


# Internal -------------------------------------------------------------------


def _decode_xread(raw: Any) -> list[tuple[str, ArenaEvent]]:
    """Flatten the ``XREAD`` response shape and decode envelopes.

    Redis returns ``[(stream_name, [(entry_id, fields), ...]), ...]``;
    we discard ``stream_name`` because each call targets a single stream
    and return a flat list of ``(entry_id, ArenaEvent)``.
    """
    if not raw:
        return []

    out: list[tuple[str, ArenaEvent]] = []
    for _stream_name, entries in raw:
        for entry_id, fields in entries:
            try:
                event = ArenaEvent.from_redis(fields)
            except (KeyError, ValueError) as exc:
                logger.warning(
                    "arena_bus: skipping malformed entry %s: %s",
                    entry_id, exc,
                )
                continue
            out.append((entry_id, event))
    return out


__all__ = [
    "publish",
    "read_correlation",
    "read_global",
]
