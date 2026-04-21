"""WebSocket message rate limiters — per-connection (local) + per-user (Redis).

Two layers:

1. `WsRateLimiter` (per-connection, in-memory): prevents one WebSocket from
   flooding messages. Fast, no Redis hop. Each connection gets its own deque.

2. `check_user_rate_limit` (per-user, Redis): caps total message volume
   across ALL active WebSocket connections for a given user_id. Prevents the
   "N tabs × M msgs/10s" multiplication attack. Uses a Redis sorted-set
   sliding window (ZADD + ZREMRANGEBYSCORE + ZCARD, atomic via pipeline).

Both layers should be checked on every incoming message — the per-connection
limiter is O(1) memory and O(1) ops; the per-user limiter adds one Redis
roundtrip (~1ms local, acceptable).

Usage:
    limiter = training_limiter()  # per-connection
    # In message loop:
    if not limiter.is_allowed():
        await _send(ws, "error", {"code": "rate_limited_conn", ...})
        continue
    if not await check_user_rate_limit(user_id, scope="training"):
        await _send(ws, "error", {"code": "rate_limited_user", ...})
        continue
"""

import logging
import time
from collections import deque

from app.core.redis_pool import get_redis

_logger = logging.getLogger(__name__)


class WsRateLimiter:
    """Sliding-window rate limiter for a single WebSocket connection.

    Thread-safe for asyncio (single-threaded event loop).  Does NOT use Redis —
    state lives in the connection object, so no cross-process coordination needed.

    Args:
        max_messages: maximum messages allowed in the window
        window_seconds: length of the sliding window in seconds
    """

    __slots__ = ("max_messages", "window_seconds", "_timestamps")

    def __init__(self, max_messages: int = 30, window_seconds: float = 10.0) -> None:
        self.max_messages = max_messages
        self.window_seconds = window_seconds
        self._timestamps: deque[float] = deque()

    def is_allowed(self) -> bool:
        """Check if the next message is within rate limits.

        Records the message timestamp if allowed.  Call once per incoming message
        BEFORE processing it.

        Returns:
            True  — message is within limits, proceed normally.
            False — rate limit exceeded; reject the message.
        """
        now = time.monotonic()
        cutoff = now - self.window_seconds
        # Drop timestamps outside the window (oldest first)
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()
        if len(self._timestamps) >= self.max_messages:
            return False
        self._timestamps.append(now)
        return True

    def reset(self) -> None:
        """Clear recorded timestamps (e.g. after an auth change)."""
        self._timestamps.clear()


# ── Preset limiters for each WS handler ─────────────────────────────────────
#
# training:  audio.chunk messages arrive ~5-10/s during voice input → allow 60/10s (6/s)
# pvp:       answer + ping messages, moderate rate              → allow 30/10s (3/s)
# knowledge: quiz answers + ping, low frequency                 → allow 20/10s (2/s)
# game_crm:  story.message + ping, low frequency                → allow 20/10s (2/s)
# notify:    ping + notification.read, very low frequency       → allow 15/10s (1.5/s)

def training_limiter() -> WsRateLimiter:
    return WsRateLimiter(max_messages=60, window_seconds=10.0)

def pvp_limiter() -> WsRateLimiter:
    return WsRateLimiter(max_messages=30, window_seconds=10.0)

def knowledge_limiter() -> WsRateLimiter:
    return WsRateLimiter(max_messages=20, window_seconds=10.0)

def game_crm_limiter() -> WsRateLimiter:
    return WsRateLimiter(max_messages=20, window_seconds=10.0)

def notification_limiter() -> WsRateLimiter:
    return WsRateLimiter(max_messages=15, window_seconds=10.0)


# ── Per-user rate limiter (Redis, cross-connection) ─────────────────────────
#
# Purpose: cap the TOTAL message rate for a user_id regardless of how many
# parallel WS connections they opened. Without this, a user with N tabs can
# amplify the per-connection limit by N (20 tabs × 60 msg/10s = 1200 msg/10s
# → LLM bill or OOM).
#
# User-reviewed 2026-04-17: 300 msg/10s total (≈ 5 windows simultaneously).
# Fail-open on Redis error: WS messages keep flowing if Redis hiccups; the
# per-connection limiter is still in effect as a safety net.

# Defaults per scope — tune if needed.
USER_LIMITS: dict[str, tuple[int, float]] = {
    "training":     (300, 10.0),
    "pvp":          (150, 10.0),
    "knowledge":    (120, 10.0),
    "game_crm":     (120, 10.0),
    "notification": (60,  10.0),
    # Catch-all default when scope is unknown
    "default":      (300, 10.0),
}


async def check_user_rate_limit(
    user_id: str,
    scope: str = "default",
    *,
    max_messages: int | None = None,
    window_seconds: float | None = None,
) -> bool:
    """Check and record a message against the per-user Redis sliding window.

    Returns True if under limit (message allowed), False if over.

    Implementation: Redis sorted set keyed by `ws_rl:{scope}:{user_id}`.
    Score = timestamp (ms). Atomic pipeline:
      1. ZREMRANGEBYSCORE to drop old entries
      2. ZCARD to count current window size
      3. If under limit: ZADD with unique member (ts + random) and EXPIRE
      4. Return bool

    Fail-open: any Redis error returns True so the per-connection limiter
    still caps the flow.
    """
    if max_messages is None or window_seconds is None:
        default_max, default_win = USER_LIMITS.get(scope, USER_LIMITS["default"])
        max_messages = max_messages or default_max
        window_seconds = window_seconds or default_win

    key = f"ws_rl:{scope}:{user_id}"
    now_ms = int(time.time() * 1000)
    cutoff_ms = now_ms - int(window_seconds * 1000)

    try:
        r = get_redis()
        # Use a pipeline for atomicity
        async with r.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, 0, cutoff_ms)
            pipe.zcard(key)
            _, current_size = await pipe.execute()

        if current_size >= max_messages:
            return False

        # Record. Member must be unique — use timestamp + counter.
        # Since Python's asyncio is single-threaded, a monotonic counter is OK.
        global _ws_rl_counter
        _ws_rl_counter = (globals().get("_ws_rl_counter", 0) + 1) % 1_000_000
        member = f"{now_ms}:{_ws_rl_counter}"

        async with r.pipeline(transaction=True) as pipe:
            pipe.zadd(key, {member: now_ms})
            pipe.expire(key, int(window_seconds) + 2)  # auto-cleanup
            await pipe.execute()

        return True
    except Exception as exc:
        # Fail-open: per-connection limiter still protects us.
        _logger.warning(
            "Per-user WS rate-limit check failed for user=%s scope=%s (%s) — "
            "allowing message; per-connection limiter remains in effect",
            user_id, scope, exc,
        )
        return True
