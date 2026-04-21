"""Update CustomCharacter statistics when a linked TrainingSession ends.

2026-04-21 (constructor v2 wrap-up): CustomCharacter has had
``play_count / best_score / avg_score / last_played_at`` columns since
migration 20260402_004a, but no code ever wrote to them. Grep across the
services directory returned zero hits until this file landed — so every
saved character showed ``0`` plays forever regardless of real activity.

This service is the single, idempotent place that reconciles the stats.
REST end_session and the two WS end paths (normal end + story call end)
call it once per session finish. Failures log and swallow — we never
want a statistics-update glitch to bubble up and fail a legitimate
session-end operation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.custom_character import CustomCharacter
from app.models.training import TrainingSession

logger = logging.getLogger(__name__)


async def update_custom_character_stats(
    session: TrainingSession,
    db: AsyncSession,
) -> None:
    """Increment play_count and refresh best/avg scores on the linked
    CustomCharacter.

    Safe to call unconditionally at end-of-session — no-ops when the
    session has no ``custom_character_id`` or the row is missing.

    The update is ``db.flush()``-only; the outer end-session transaction
    is responsible for the commit. This keeps the stats write inside the
    same unit of work as the session's ``ended_at`` write, so either both
    land or neither does.

    Args:
        session: The TrainingSession that just completed. Its
            ``custom_character_id``, ``score_total`` and id are read.
        db: Active async session participating in the caller's transaction.
    """
    char_id = getattr(session, "custom_character_id", None)
    if char_id is None:
        return

    try:
        result = await db.execute(
            select(CustomCharacter).where(CustomCharacter.id == char_id)
        )
        char = result.scalar_one_or_none()
        if char is None:
            # FK row was deleted between start and end — not actionable.
            logger.debug(
                "CustomCharacter %s gone at end of session %s, skipping stats",
                char_id, session.id,
            )
            return

        score = session.score_total or 0
        now = datetime.now(timezone.utc)

        # Read old values BEFORE incrementing for the rolling average.
        old_count = char.play_count or 0
        old_avg = char.avg_score or 0

        # Inc play_count + stamp last_played_at.
        char.play_count = old_count + 1
        char.last_played_at = now

        # Best = max of existing and current.
        if char.best_score is None or score > char.best_score:
            char.best_score = int(score)

        # Rolling average: ((old_avg * old_count) + current) / new_count
        # Matches what a user would expect — each completed session
        # weighs exactly 1/N. Incomplete/abandoned sessions should NOT
        # reach here (callers gate on session.status or equivalent).
        new_count = char.play_count
        if new_count > 0:
            char.avg_score = int(round((old_avg * old_count + score) / new_count))

        await db.flush()
        logger.info(
            "CustomCharacter stats updated | char=%s | play=%d best=%s avg=%s score=%s",
            char_id, char.play_count, char.best_score, char.avg_score, score,
        )
    except Exception:
        # Stats are observability, not correctness — never block session end.
        logger.warning(
            "update_custom_character_stats failed for session=%s char=%s",
            getattr(session, "id", "?"), char_id,
            exc_info=True,
        )
