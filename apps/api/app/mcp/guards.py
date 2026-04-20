"""Runtime guards: auth, per-user rate-limit, result-size cap.

Used by ``executor.dispatch`` before and after the handler runs. Each guard
can either return normally (pass) or raise ``GuardViolation``, which the
executor converts to an ``assistant.tool_error`` WS event with ``fatal=False``
so the LLM can decide whether to try a different approach.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.mcp.tool import Tool, ToolContext

logger = logging.getLogger(__name__)


class GuardViolation(Exception):
    """Raised when a guard refuses execution.

    ``code`` is surfaced in the WS error event; callers should pass a short
    machine-readable string like ``"rate_limited"`` or ``"result_too_large"``.
    """

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# ────────────────────────────────────────────────────────────────────
# Auth gate
# ────────────────────────────────────────────────────────────────────


def check_auth(tool: Tool, ctx: ToolContext) -> None:
    """Reject a call if ``tool.auth_required`` is True and ctx has no user."""

    if tool.auth_required and not ctx.user_id:
        raise GuardViolation(
            code="auth_required",
            message=f"tool {tool.name!r} requires an authenticated context",
        )


# ────────────────────────────────────────────────────────────────────
# Rate limit — Redis sliding window (per user × tool)
# ────────────────────────────────────────────────────────────────────


async def check_rate_limit(tool: Tool, ctx: ToolContext) -> None:
    """Enforce ``tool.rate_limit_per_min`` calls per (user, tool) minute.

    Uses Redis ``INCR`` with a 60-second TTL. If Redis is unavailable we fail
    open (log + allow) — we'd rather let a call through than block every tool
    on infrastructure hiccups.
    """

    if tool.rate_limit_per_min <= 0:
        return

    # Pick a rate-limit key that makes sense even for anonymous tool
    # contexts: fall back to session_id, then to global bucket.
    subject = ctx.user_id or ctx.session_id or "anonymous"
    bucket = int(time.time() // 60)  # changes each minute
    key = f"mcp:rl:{tool.name}:{subject}:{bucket}"

    try:
        from app.core.redis_pool import get_redis

        r = get_redis()
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, 65)  # slightly longer than the bucket window
    except Exception as exc:  # pragma: no cover — redis blip
        logger.warning("rate_limit guard: redis error (fail-open): %s", exc)
        return

    if count > tool.rate_limit_per_min:
        raise GuardViolation(
            code="rate_limited",
            message=(
                f"tool {tool.name!r} limit reached for {subject}: "
                f"{count}/{tool.rate_limit_per_min} per minute"
            ),
        )


# ────────────────────────────────────────────────────────────────────
# Result size cap
# ────────────────────────────────────────────────────────────────────


def check_result_size(tool: Tool, result: Any) -> None:
    """Reject results larger than ``tool.max_result_size_kb``.

    The JSON-encoded size is what the LLM ends up paying for in tokens, so
    we measure it the same way. Non-JSON-serializable results raise here too —
    tool handlers must return something JSON-able.
    """

    try:
        payload = json.dumps(result, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise GuardViolation(
            code="invalid_result",
            message=f"tool {tool.name!r} returned non-serializable: {exc}",
        )

    kb = len(payload.encode("utf-8")) / 1024
    if kb > tool.max_result_size_kb:
        raise GuardViolation(
            code="result_too_large",
            message=(
                f"tool {tool.name!r} produced {kb:.1f}KB "
                f"(limit {tool.max_result_size_kb}KB)"
            ),
        )
