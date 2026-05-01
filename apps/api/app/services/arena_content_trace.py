"""Content-trace events for the arena bus (Content→Arena PR-7, final).

PR-2 of this epic linked PvPDuel rows to ScenarioTemplate / ScenarioVersion
and PR-5 wired chunk-usage logs. Both surface in Postgres queries — but
operators reading from the bus (AuditLogConsumer from Эпик 2 PR-3, future
Match Orchestrator, Notification Hub) had to JOIN against the SQL DB to
understand which content played in a given duel.

This module publishes lightweight envelope events on the bus directly:

* ``arena.content.duel.started``  — emitted once when ``_load_duel_context``
  resolves a duel's content. Carries the template/version FKs and the
  archetype the bot will play. Lets a consumer see "duel X is about to
  run with template Y v3 and archetype Z" without touching Postgres.

* ``arena.content.round.scored``  — emitted once per round after
  ``judge_round`` returns. Carries the list of ``legal_chunk_ids`` the
  RAG surfaced and which subset the judge marked correct. Mirrors what
  ChunkUsageLog stores in SQL but available on the streaming side for
  near-real-time analytics.

These events flow exclusively through the bus (no WS payload mutation),
so the frontend protocol is unchanged. Consumers correlate them by
``correlation_id = duel_id`` (set by the LogContextFilter in PR A,
already populated for every WS task body).

Failure-mode contract
---------------------

* Bus disabled (``arena_bus_dual_write_enabled=False``) → silent skip.
  No-op when methodology decides to keep the bus shut.
* Redis unreachable → ``arena_bus.publish`` raises ConnectionError;
  helper logs at WARNING and swallows. Telemetry is best-effort, never
  blocks the duel runtime.
* AuditLogConsumer not running → events accumulate in the global stream
  bounded by ``MAXLEN ~ 10_000`` (Эпик 2 PR-1) — old entries auto-trim,
  Redis memory stays bounded.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Iterable

logger = logging.getLogger(__name__)


# Event-type discriminators — kept as constants so subscribers can match
# by string equality without re-deriving the prefix.
EVENT_DUEL_STARTED = "arena.content.duel.started"
EVENT_ROUND_SCORED = "arena.content.round.scored"


async def publish_duel_started(
    *,
    duel_id: uuid.UUID,
    scenario_template_id: uuid.UUID | None,
    scenario_version_id: uuid.UUID | None,
    archetype: str | None,
    is_pve: bool,
    difficulty: str | None = None,
) -> None:
    """Emit content trace at the start of a duel.

    Idempotent at the bus layer (each call gets a fresh ``msg_id``);
    callers should call once per duel ``_load_duel_context`` resolution.
    """
    await _safe_publish(
        type=EVENT_DUEL_STARTED,
        duel_id=duel_id,
        payload={
            "scenario_template_id": str(scenario_template_id) if scenario_template_id else None,
            "scenario_version_id": str(scenario_version_id) if scenario_version_id else None,
            "archetype_code": archetype,
            "is_pve": bool(is_pve),
            "difficulty": difficulty,
        },
    )


async def publish_round_scored(
    *,
    duel_id: uuid.UUID,
    round_number: int,
    legal_chunk_ids: Iterable[uuid.UUID],
    legal_chunk_ids_correct: Iterable[uuid.UUID],
    legal_chunk_ids_incorrect: Iterable[uuid.UUID],
    selling_score: float,
    legal_accuracy: float,
    degraded: bool,
) -> None:
    """Emit content trace after a round's judge verdict.

    Mirrors ``ChunkUsageLog`` rows but on the streaming side — analytics
    consumers can build "chunk effectiveness in last hour" without
    polling Postgres.
    """
    await _safe_publish(
        type=EVENT_ROUND_SCORED,
        duel_id=duel_id,
        payload={
            "round_number": int(round_number),
            "legal_chunk_ids": [str(c) for c in legal_chunk_ids],
            "legal_chunk_ids_correct": [str(c) for c in legal_chunk_ids_correct],
            "legal_chunk_ids_incorrect": [str(c) for c in legal_chunk_ids_incorrect],
            "selling_score": float(selling_score),
            "legal_accuracy": float(legal_accuracy),
            "degraded": bool(degraded),
        },
    )


# ── Internal ────────────────────────────────────────────────────────────────


async def _safe_publish(
    *,
    type: str,
    duel_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    """Publish to the bus when enabled; never raises."""
    try:
        from app.config import settings

        if not settings.arena_bus_dual_write_enabled:
            return
        from app.services.arena_bus import publish as _bus_publish
        from app.services.arena_envelope import ArenaEvent

        event = ArenaEvent.create(
            type=type,
            payload=payload,
            correlation_id=str(duel_id),
            producer="arena_content_trace",
        )
        await _bus_publish(event)
    except Exception:
        # Best-effort. The PvPDuel rows + ChunkUsageLog rows are still
        # written by the surrounding code paths (PR-2 + PR-5) so the
        # SQL-side trace is intact even if bus publish fails.
        logger.debug(
            "arena_content_trace: publish %s failed (non-critical)",
            type, exc_info=True,
        )


__all__ = [
    "EVENT_DUEL_STARTED",
    "EVENT_ROUND_SCORED",
    "publish_duel_started",
    "publish_round_scored",
]
