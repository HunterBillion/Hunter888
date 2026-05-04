"""Weak-category bias for adaptive quiz selection.

Reuses existing `KnowledgeAnswer` rows — no new schema. Computes a
per-user accuracy per category, surfaces the worst one when there's
enough signal (≥3 answers) and the accuracy gap is meaningful.

Used by `_next_question` in WebSocket handler:
  • free_dialog mode picks weakest category 40% of the time
  • blitz / themed override stay user-controlled
  • SRS already has its own targeting → not affected

Design notes:
  - Threshold of ≥3 answers per category before considering — avoids
    one-off noise (a single mistake shouldn't dominate selection).
  - Returns None if the user has very even performance (worst < 60%
    floor and nothing dramatically lower than rest) — bias only fires
    when there's a real weak spot.
  - Look-back window: last 50 answers per category, so old mistakes
    don't haunt forever after the user has clearly improved.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeAnswer

logger = logging.getLogger(__name__)

MIN_ANSWERS_PER_CATEGORY = 3
LOOKBACK_PER_CATEGORY = 50
WEAK_FLOOR = 0.65  # only flag a category as weak if accuracy ≤ this


async def get_weakest_category(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> Optional[str]:
    """Return the user's weakest category code, or None if no clear weak spot.

    Strategy: rank categories by accuracy (correct / total) on the most
    recent LOOKBACK_PER_CATEGORY answers each. Return the lowest one
    only if it dips under WEAK_FLOOR — otherwise the user is uniformly
    competent and forced bias would feel arbitrary.
    """
    try:
        # One scan over recent answers; group on category in Python so
        # we don't need a window-function query (cleaner and portable).
        result = await db.execute(
            select(
                KnowledgeAnswer.question_category,
                KnowledgeAnswer.is_correct,
            )
            .where(KnowledgeAnswer.user_id == user_id)
            .order_by(KnowledgeAnswer.created_at.desc())
            .limit(500)  # hard cap — categories cap themselves at LOOKBACK below
        )
        rows = result.all()
    except Exception as exc:
        logger.warning("get_weakest_category query failed: %s", exc)
        return None

    if not rows:
        return None

    buckets: dict[str, list[bool]] = {}
    for cat, ok in rows:
        if cat is None:
            continue
        bucket = buckets.setdefault(cat, [])
        if len(bucket) < LOOKBACK_PER_CATEGORY:
            bucket.append(bool(ok))

    # Only categories with enough signal qualify for ranking.
    ranked: list[tuple[str, float]] = []
    for cat, results in buckets.items():
        if len(results) < MIN_ANSWERS_PER_CATEGORY:
            continue
        accuracy = sum(1 for x in results if x) / len(results)
        ranked.append((cat, accuracy))

    if not ranked:
        return None

    ranked.sort(key=lambda x: x[1])
    weakest_cat, weakest_acc = ranked[0]
    if weakest_acc > WEAK_FLOOR:
        # The user is uniformly competent — don't force bias.
        return None
    logger.info(
        "weak category for user=%s: %s (%.0f%% accuracy across %d recent)",
        user_id, weakest_cat, weakest_acc * 100, len(buckets[weakest_cat]),
    )
    return weakest_cat
