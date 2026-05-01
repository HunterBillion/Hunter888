"""TZ-8 PR-D — methodology chunk telemetry.

Mirrors the legal-side helpers in ``rag_feedback`` for the
methodology source. Two collection points and one aggregator:

  * :func:`log_methodology_retrieval` — fires when the retriever
    returns a chunk to a coach / training / arena prompt.
    Writes one ``ChunkUsageLog`` row per returned chunk with
    ``chunk_kind='methodology'``.

  * :func:`record_methodology_outcome` — fires after a judge /
    scorer concludes whether the user's answer used the chunk's
    guidance. Patches the existing usage log row with
    ``answer_correct`` / ``score_delta`` so the aggregator can
    compute "this playbook actually helps" rates.

  * :func:`get_methodology_chunk_stats` — read side, powers the
    methodology effectiveness UI panel (PR-D2). Returns per-chunk
    counts of retrievals, correct-answer rate, last fired
    timestamp, source-type breakdown.

Why a new module instead of extending ``rag_feedback``?
-------------------------------------------------------

``rag_feedback`` is hard-coded for ``LegalKnowledgeChunk``
joins (``effectiveness_score`` aggregations, category breakdowns,
``error_frequency`` denormalisations). Bolting methodology onto
those queries would force every legacy aggregator to special-case
``chunk_kind='legal'``. Keeping the methodology side in its own
module — same shape but separate query surface — gives a clean
deprecation path when ``rag_feedback`` eventually unifies.

Failure-mode contract
---------------------

* Telemetry is **best-effort**. Any exception in the logger MUST
  be swallowed (logged at ``WARNING``) and never bubble up to
  fail the user-facing retrieval. A coach session that didn't
  log a chunk usage is annoying for analytics but the user still
  got their answer.
* Aggregations are bounded by ``days`` window so the dashboard
  can't accidentally scan years of data.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag import ChunkUsageLog

logger = logging.getLogger(__name__)


# ── Collection ─────────────────────────────────────────────────────────


async def log_methodology_retrieval(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    chunk_id: uuid.UUID,
    source_type: str,
    source_id: uuid.UUID | None = None,
    query_text: str | None = None,
    relevance_score: float | None = None,
    retrieval_rank: int | None = None,
) -> uuid.UUID | None:
    """Log a single methodology-chunk retrieval.

    Returns the new ``ChunkUsageLog.id`` so the caller can later
    patch the outcome via :func:`record_methodology_outcome`. ``None``
    on failure (the caller treats this as "telemetry skipped" and
    proceeds — nothing user-facing depends on it).

    ``source_type`` is a free-form string (e.g. ``"training"`` /
    ``"pvp_duel"`` / ``"coach"`` / ``"methodology_retrieval"`` for
    direct retrievals). The aggregation read-side groups by it.
    """
    try:
        log = ChunkUsageLog(
            chunk_id=chunk_id,
            chunk_kind="methodology",
            user_id=user_id,
            source_type=source_type,
            source_id=source_id,
            query_text=(query_text or None),
            retrieval_method="embedding",
            relevance_score=relevance_score,
            retrieval_rank=retrieval_rank,
            was_answered=False,
        )
        db.add(log)
        # Caller is expected to be in a session with auto-commit on
        # close (typical FastAPI dep). No commit here so we don't
        # interfere with the surrounding transaction.
        await db.flush()
        return log.id
    except Exception:
        logger.warning(
            "methodology_telemetry: log_methodology_retrieval failed for "
            "chunk %s, user %s (best-effort, swallowed)",
            chunk_id, user_id, exc_info=True,
        )
        return None


async def record_methodology_outcome(
    db: AsyncSession,
    log_id: uuid.UUID,
    *,
    answer_correct: bool | None,
    score_delta: float | None = None,
    user_answer_excerpt: str | None = None,
    discovered_error: str | None = None,
) -> bool:
    """Patch a previously-logged retrieval row with the outcome.

    Returns True if the row was updated. ``False`` is the
    "tolerated" path: log row not found, transient DB error, etc.
    The methodology coach loop should never block on this.
    """
    try:
        from sqlalchemy import update

        await db.execute(
            update(ChunkUsageLog)
            .where(ChunkUsageLog.id == log_id)
            .values(
                was_answered=True,
                answer_correct=answer_correct,
                score_delta=score_delta,
                user_answer_excerpt=(
                    (user_answer_excerpt or "")[:500] or None
                ),
                discovered_error=(
                    (discovered_error or "")[:500] or None
                ),
            )
        )
        return True
    except Exception:
        logger.warning(
            "methodology_telemetry: record_methodology_outcome failed for "
            "log %s (best-effort, swallowed)",
            log_id, exc_info=True,
        )
        return False


# ── Aggregation (read side) ────────────────────────────────────────────


async def get_methodology_chunk_stats(
    db: AsyncSession,
    *,
    chunk_id: uuid.UUID,
    days: int = 30,
) -> dict:
    """Effectiveness summary for one chunk over the last ``days`` days.

    Output shape (matches the methodology UI's effectiveness panel
    expectations — see TZ-8 §8.2):

      ``{
          "chunk_id": str,
          "retrieval_count": int,
          "answered_count": int,
          "correct_count": int,
          "correct_rate": float | None,    # None when answered_count == 0
          "last_used_at": datetime | None,
          "by_source_type": {source_type: count, …},
      }``

    Bounded by ``days`` so a dashboard refresh can't accidentally
    scan years of data on a hot chunk.
    """
    if days <= 0:
        days = 1
    window_start = datetime.now(timezone.utc) - timedelta(days=days)

    base = (
        select(ChunkUsageLog)
        .where(ChunkUsageLog.chunk_kind == "methodology")
        .where(ChunkUsageLog.chunk_id == chunk_id)
        .where(ChunkUsageLog.created_at >= window_start)
        .where(ChunkUsageLog.is_deleted.is_(False))
    )

    total = (
        await db.execute(
            select(func.count()).select_from(base.subquery())
        )
    ).scalar() or 0

    answered = (
        await db.execute(
            select(func.count()).select_from(
                base.where(ChunkUsageLog.was_answered.is_(True)).subquery()
            )
        )
    ).scalar() or 0

    correct = (
        await db.execute(
            select(func.count()).select_from(
                base.where(ChunkUsageLog.answer_correct.is_(True)).subquery()
            )
        )
    ).scalar() or 0

    last_used_at = (
        await db.execute(
            select(func.max(ChunkUsageLog.created_at)).select_from(
                base.subquery()
            )
        )
    ).scalar()

    by_source_rows = (
        await db.execute(
            select(
                ChunkUsageLog.source_type,
                func.count().label("c"),
            )
            .where(ChunkUsageLog.chunk_kind == "methodology")
            .where(ChunkUsageLog.chunk_id == chunk_id)
            .where(ChunkUsageLog.created_at >= window_start)
            .where(ChunkUsageLog.is_deleted.is_(False))
            .group_by(ChunkUsageLog.source_type)
        )
    ).all()

    return {
        "chunk_id": str(chunk_id),
        "retrieval_count": int(total),
        "answered_count": int(answered),
        "correct_count": int(correct),
        "correct_rate": (correct / answered) if answered > 0 else None,
        "last_used_at": last_used_at,
        "by_source_type": {row.source_type: int(row.c) for row in by_source_rows},
    }


async def get_team_methodology_stats(
    db: AsyncSession,
    *,
    team_id: uuid.UUID,
    days: int = 30,
    limit: int = 50,
) -> list[dict]:
    """Top methodology chunks for a team by retrieval count.

    Powers the "what's working" panel in PR-D2. Joins
    ``ChunkUsageLog`` to ``MethodologyChunk`` on
    ``chunk_id`` *and* ``chunk_kind='methodology'`` (the polymorphic
    join — the discriminator is the index entry that makes this
    cheap).

    Returns a list of ``{chunk_id, title, kind, retrieval_count,
    correct_rate}`` ordered by ``retrieval_count`` DESC.
    """
    from app.models.methodology import MethodologyChunk

    if days <= 0:
        days = 1
    window_start = datetime.now(timezone.utc) - timedelta(days=days)

    rows = (
        await db.execute(
            select(
                MethodologyChunk.id,
                MethodologyChunk.title,
                MethodologyChunk.kind,
                func.count(ChunkUsageLog.id).label("retrieval_count"),
                func.count(
                    func.nullif(ChunkUsageLog.answer_correct, False)
                ).label("correct_count"),
                func.count(
                    func.nullif(ChunkUsageLog.was_answered, False)
                ).label("answered_count"),
            )
            .join(
                ChunkUsageLog,
                (ChunkUsageLog.chunk_id == MethodologyChunk.id)
                & (ChunkUsageLog.chunk_kind == "methodology"),
                isouter=False,
            )
            .where(MethodologyChunk.team_id == team_id)
            .where(ChunkUsageLog.created_at >= window_start)
            .where(ChunkUsageLog.is_deleted.is_(False))
            .group_by(
                MethodologyChunk.id,
                MethodologyChunk.title,
                MethodologyChunk.kind,
            )
            .order_by(func.count(ChunkUsageLog.id).desc())
            .limit(limit)
        )
    ).all()

    out = []
    for row in rows:
        answered = int(row.answered_count or 0)
        correct = int(row.correct_count or 0)
        out.append(
            {
                "chunk_id": str(row.id),
                "title": row.title,
                "kind": row.kind,
                "retrieval_count": int(row.retrieval_count or 0),
                "answered_count": answered,
                "correct_count": correct,
                "correct_rate": (correct / answered) if answered > 0 else None,
            }
        )
    return out


__all__ = [
    "log_methodology_retrieval",
    "record_methodology_outcome",
    "get_methodology_chunk_stats",
    "get_team_methodology_stats",
]
