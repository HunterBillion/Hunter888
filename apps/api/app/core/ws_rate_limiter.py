"""Per-connection WebSocket message rate limiter (sliding window).

Usage:
    limiter = WsRateLimiter(max_messages=30, window_seconds=10.0)
    # In message loop:
    if not limiter.is_allowed():
        await _send(ws, "error", {"code": "rate_limited", "message": "Too many messages"})
        continue
"""

import time
from collections import deque


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
