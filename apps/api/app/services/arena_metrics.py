"""Prometheus metrics for the PvP arena.

Defines histograms and counters that arena code paths emit into. They
register with the default ``prometheus_client.REGISTRY`` at import time
and are exposed via the ``/metrics`` endpoint that
``prometheus-fastapi-instrumentator`` mounts on app startup (gated by
``settings.metrics_enabled``).

Conventions:
* Histogram names end in ``_seconds`` per Prometheus best practice.
* Counter names end in ``_total``.
* Buckets for latency histograms are tuned to operator-meaningful
  thresholds (8s = "feels stuck", 12s = "judge SLO breach").

Wiring into hot code paths is the responsibility of PR B; this module
only defines the metric handles. Importing it has no side-effect beyond
registry registration, so it can sit unused for one deploy without
affecting metrics output (each metric simply has no observations yet).

Failure mode: if ``prometheus_client`` is unavailable (e.g. dev install
without the dep), every public symbol still exists but is a no-op stub.
This keeps imports safe in environments where metrics are intentionally
disabled — no production environment should hit the stub branch.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


try:
    from prometheus_client import Counter, Histogram

    _PROM_AVAILABLE = True
except ImportError:  # pragma: no cover — dev-only branch
    _PROM_AVAILABLE = False
    logger.warning(
        "prometheus_client not installed; arena_metrics is a no-op. "
        "Install via pyproject extras to enable observability."
    )


# Bucket presets ---------------------------------------------------------------

# AI calls: bot/judge.  Anything above 8s feels broken to the player; 12s is
# our judge SLO; 30s is the hard timeout in pvp_judge.py.
_AI_LATENCY_BUCKETS = (0.25, 0.5, 1.0, 2.0, 4.0, 6.0, 8.0, 12.0, 20.0, 30.0)

# Queue wait: ranges from instant (PvE fallback) to "we gave up" (~90s).
_QUEUE_WAIT_BUCKETS = (1, 5, 10, 15, 30, 45, 60, 90, 120, 180)

# Round duration: typical ROUND_TIME_LIMIT is 90s; long-tail is timeouts.
_ROUND_DURATION_BUCKETS = (15, 30, 45, 60, 75, 90, 105, 120, 180, 240)


# ---- Stub fallback -----------------------------------------------------------


class _NoopMetric:
    """Drop-in for prometheus_client metrics when the dep is missing.

    Mirrors the surface we use (``labels``, ``inc``, ``observe``,
    ``time``) so callers don't need to special-case the missing dep.
    """

    def labels(self, *args, **kwargs) -> "_NoopMetric":
        return self

    def inc(self, amount: float = 1.0) -> None:
        return None

    def observe(self, amount: float) -> None:
        return None

    def time(self):
        import contextlib

        @contextlib.contextmanager
        def _noop_timer():
            yield

        return _noop_timer()


def _hist(name: str, doc: str, labels: tuple[str, ...], buckets: tuple) -> "Histogram | _NoopMetric":
    if not _PROM_AVAILABLE:
        return _NoopMetric()
    return Histogram(name, doc, list(labels), buckets=buckets)


def _ctr(name: str, doc: str, labels: tuple[str, ...]) -> "Counter | _NoopMetric":
    if not _PROM_AVAILABLE:
        return _NoopMetric()
    return Counter(name, doc, list(labels))


# Metric definitions -----------------------------------------------------------

ARENA_AI_BOT_LATENCY = _hist(
    "arena_ai_bot_latency_seconds",
    "Latency of AI bot reply generation in PvE/PvP duels.",
    ("provider", "status"),  # provider: gemini|claude|openai|fallback ; status: ok|timeout|error
    _AI_LATENCY_BUCKETS,
)

ARENA_AI_JUDGE_LATENCY = _hist(
    "arena_ai_judge_latency_seconds",
    "Latency of AI judge scoring (per round and per duel).",
    ("judge_type", "status"),  # judge_type: round|duel ; status: ok|timeout|degraded|error
    _AI_LATENCY_BUCKETS,
)

ARENA_QUEUE_WAIT = _hist(
    "arena_queue_wait_seconds",
    "Time a player spent in the matchmaking queue before pairing or fallback.",
    ("mode", "outcome"),  # mode: classic|rapid|gauntlet|team ; outcome: matched|pve_fallback|cancelled|timeout
    _QUEUE_WAIT_BUCKETS,
)

ARENA_ROUND_DURATION = _hist(
    "arena_round_duration_seconds",
    "Round duration from round.start to round.end (or timeout).",
    ("mode", "round_no", "end_reason"),  # end_reason: message_limit|timeout|disconnect
    _ROUND_DURATION_BUCKETS,
)

# NOTE on Counter naming: ``prometheus_client.Counter`` auto-appends the
# ``_total`` suffix in the wire format. We therefore declare the base name
# without ``_total`` here — the actual /metrics output will be
# ``arena_finalize_attempts_total`` etc.
ARENA_FINALIZE_ATTEMPTS = _ctr(
    "arena_finalize_attempts",
    "Calls to finalize_pvp_duel — labelled by outcome and idempotency status. "
    "Mirrors runtime_metrics.record_finalize for arena-specific dashboards.",
    ("outcome", "already_completed"),  # outcome: win|loss|draw|abandoned ; already_completed: true|false
)

ARENA_JUDGE_DEGRADED = _ctr(
    "arena_judge_degraded",
    "Judge fell back to neutral default scores. High value = AI provider unhealthy.",
    ("reason",),  # reason: timeout|safety_block|parse_error|all_providers_down
)

ARENA_DUEL_STATE_TRANSITIONS = _ctr(
    "arena_duel_state_transitions",
    "State machine transitions per duel — tracks the FSM health.",
    ("from_state", "to_state"),
)

ARENA_WS_DISCONNECT = _ctr(
    "arena_ws_disconnect",
    "WebSocket disconnects on /ws/pvp — labelled by phase and reason.",
    ("phase", "reason"),  # phase: lobby|in_duel|spectating ; reason: client_close|timeout|kicked|error
)


__all__ = [
    "ARENA_AI_BOT_LATENCY",
    "ARENA_AI_JUDGE_LATENCY",
    "ARENA_DUEL_STATE_TRANSITIONS",
    "ARENA_FINALIZE_ATTEMPTS",
    "ARENA_JUDGE_DEGRADED",
    "ARENA_QUEUE_WAIT",
    "ARENA_ROUND_DURATION",
    "ARENA_WS_DISCONNECT",
]
