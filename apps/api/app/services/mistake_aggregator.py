"""Aggregate mistake_detector firings per session for downstream scoring.

Why this exists
───────────────
The real-time ``mistake_detector`` (``app.services.mistake_detector``) emits
``coaching.mistake`` WebSocket events when it spots monologue / talk-ratio /
repeat / open-question / early-pricing patterns in a manager turn. Those
events are surfaced as toasts in the FE, but until BUG B3 v3 (this module)
nothing persisted them anywhere ``calculate_scores`` could see — the
detector's per-session state in Redis is small rolling counters meant for
"should I emit this hint NOW", not historical totals. Result: the L4
anti-patterns scoring layer was blind to repeated bad habits.

Contract
────────
- Storage: Redis hash keyed by ``scoring:mistakes:{session_id}``. Field
  per Mistake.type, value is monotonically incrementing count.
- TTL: ``STATE_TTL_SECONDS`` (4h, matches ``mistake_detector``). Refreshed
  on every write so the counts survive long sessions.
- Read API: ``fetch_counts`` returns ``{}`` if the key is missing — caller
  should treat that as "no firings recorded" not "Redis is broken".

Failure mode
────────────
Pure storage; no scoring logic in here. If Redis hiccups during
``record_fired`` the caller (``ws/training.py``) swallows the exception
inside the same try/except that already protects the WS emit, so the
existing flow is never broken by aggregation overhead.
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.mistake_detector import Mistake

logger = logging.getLogger(__name__)


REDIS_KEY_FMT = "scoring:mistakes:{session_id}"
STATE_TTL_SECONDS = 4 * 60 * 60  # match mistake_detector.STATE_TTL_SECONDS


def _key(session_id: str) -> str:
    return REDIS_KEY_FMT.format(session_id=session_id)


async def record_fired(
    redis: Any,
    session_id: str,
    mistakes: "list[Mistake]",
) -> None:
    """Increment per-type counters for the given fired mistakes.

    No-op if ``mistakes`` is empty. All increments go through ``HINCRBY``
    so concurrent calls are atomic on the Redis side. TTL is refreshed
    (not extended past) on every write so a long session keeps the key
    alive without unbounded growth.
    """
    if not mistakes:
        return
    key = _key(session_id)
    try:
        for m in mistakes:
            mtype = getattr(m, "type", None)
            if not mtype:
                continue
            await redis.hincrby(key, str(mtype), 1)
        await redis.expire(key, STATE_TTL_SECONDS)
    except Exception:
        # Storage is best-effort; never break the realtime WS flow.
        logger.debug(
            "mistake_aggregator.record_fired failed for %s", session_id, exc_info=True,
        )


async def fetch_counts(redis: Any, session_id: str) -> dict[str, int]:
    """Return ``{type: count}`` for the session, or ``{}`` if absent.

    Values are coerced to ``int`` (Redis returns bytes/strings depending
    on the client decoder). Keys with non-int payloads are skipped — they
    indicate a poisoned write outside our control and should not crash
    the scoring path.
    """
    key = _key(session_id)
    try:
        raw = await redis.hgetall(key)
    except Exception:
        logger.debug(
            "mistake_aggregator.fetch_counts failed for %s", session_id, exc_info=True,
        )
        return {}
    if not raw:
        return {}

    out: dict[str, int] = {}
    for k, v in raw.items():
        if isinstance(k, (bytes, bytearray)):
            k = k.decode("utf-8", errors="replace")
        if isinstance(v, (bytes, bytearray)):
            v = v.decode("utf-8", errors="replace")
        try:
            out[str(k)] = int(v)
        except (TypeError, ValueError):
            continue
    return out
