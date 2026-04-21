"""
SM-2 + Leitner Hybrid Spaced Repetition for Hunter888 Knowledge Quiz.

Algorithm overview:
  1. SM-2 core: ease_factor, interval, repetition_count per classic SuperMemo 2
  2. Leitner boxes (0-4): quick visual progression indicator
     - Box 0: New / lapsed → review every session
     - Box 1: 1 day
     - Box 2: 3 days
     - Box 3: 7 days
     - Box 4: 21 days (mastered)
  3. Fuzzy intervals: ±10% jitter to prevent "review avalanche" on fixed days
  4. Per-category difficulty adjustment: categories with low avg EF get shorter intervals
  5. Streak bonuses: consecutive correct answers accelerate box promotion
  6. Quality mapping: quiz metadata (time, hints, correctness) → SM-2 quality 0-5

Priority queue for question selection:
  P1: Overdue items (next_review_at < now)  — sorted by most overdue first
  P2: Weak items (ease_factor < 2.0)        — sorted by lowest EF
  P3: Leitner box 0 items (new/lapsed)      — learning phase
  P4: Random new/unseen questions            — discovery

Reference: https://en.wikipedia.org/wiki/SuperMemo#SM-2
"""

from __future__ import annotations

import hashlib
import logging
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, func, and_, case, literal_column
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import UserAnswerHistory

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_EASE_FACTOR = 1.3
DEFAULT_EASE_FACTOR = 2.5
LEITNER_INTERVALS = {0: 0, 1: 1, 2: 3, 3: 7, 4: 21}  # box → days
MAX_LEITNER_BOX = 4
FUZZY_JITTER = 0.10  # ±10% interval randomization
MAX_QUALITY_HISTORY = 20  # keep last N quality scores
MASTERY_EF_THRESHOLD = 2.5
MASTERY_REP_THRESHOLD = 3


# ---------------------------------------------------------------------------
# SM-2 Core Algorithm (enhanced)
# ---------------------------------------------------------------------------

def sm2_update(
    ease_factor: float,
    interval_days: int,
    repetition_count: int,
    quality: int,
    *,
    category_difficulty: float = 1.0,
) -> tuple[float, int, int]:
    """
    Apply SM-2 algorithm update with per-category difficulty scaling.

    Args:
        ease_factor: Current EF (>= 1.3)
        interval_days: Current interval in days
        repetition_count: Consecutive correct count
        quality: Answer quality 0-5
        category_difficulty: Multiplier for interval (0.5-1.5).
            Categories with low avg EF → shorter intervals (< 1.0).
            Default 1.0 = standard SM-2.

    Returns:
        (new_ease_factor, new_interval_days, new_repetition_count)
    """
    quality = max(0, min(5, quality))

    # EF update: standard SM-2 formula
    new_ef = ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    new_ef = max(MIN_EASE_FACTOR, new_ef)

    if quality >= 3:
        # Correct answer
        if repetition_count == 0:
            new_interval = 1
        elif repetition_count == 1:
            new_interval = 6
        else:
            new_interval = round(interval_days * new_ef * category_difficulty)
        new_interval = max(1, new_interval)  # floor at 1 day
        new_rep = repetition_count + 1
    else:
        # Incorrect — reset
        new_interval = 1
        new_rep = 0

    return new_ef, new_interval, new_rep


def _apply_fuzzy_jitter(interval_days: int) -> int:
    """Add ±10% jitter to prevent review clustering on the same day."""
    if interval_days <= 1:
        return interval_days
    jitter = max(1, round(interval_days * FUZZY_JITTER))
    return interval_days + random.randint(-jitter, jitter)


def _update_leitner_box(current_box: int, is_correct: bool, streak: int = 0) -> int:
    """Update Leitner box: correct → promote, incorrect → demote to box 0.

    Streak bonus: 3+ correct in a row → skip a box.
    """
    if is_correct:
        promotion = 2 if streak >= 3 else 1
        return min(MAX_LEITNER_BOX, current_box + promotion)
    else:
        # Lapse → back to box 0 (not box 1 — forces immediate re-learning)
        return 0


# ---------------------------------------------------------------------------
# Quality Mapping
# ---------------------------------------------------------------------------

def quality_from_answer(
    is_correct: bool,
    response_time_ms: int | None,
    hint_used: bool,
    *,
    is_srs_review: bool = False,
) -> int:
    """
    Map quiz answer result to SM-2 quality score (0-5).

    Quality scale:
      5: correct, fast (<10s), no hint — perfect recall
      4: correct, moderate (<30s), no hint — good recall
      3: correct with hint OR slow (>30s) — recall with difficulty
      2: incorrect but attempted (not skipped)
      1: incorrect + used hint
      0: skipped / no answer

    SRS review mode gives slightly harsher scoring (promotes retention):
      - Hint use caps quality at 2 (not 3) during SRS review
    """
    if not is_correct:
        if hint_used:
            return 1
        return 2

    # Correct answer
    if hint_used:
        return 2 if is_srs_review else 3

    if response_time_ms is not None:
        if response_time_ms < 10_000:
            return 5
        if response_time_ms < 30_000:
            return 4
        return 3  # Slow but correct

    return 4  # Default for correct, no time data


def question_hash(text: str) -> str:
    """Generate stable hash for question text (for dedup)."""
    normalized = text.strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Per-category Difficulty
# ---------------------------------------------------------------------------

async def get_category_difficulty(
    db: AsyncSession,
    user_id: uuid.UUID,
    category: str,
) -> float:
    """Calculate per-category difficulty multiplier based on user's avg EF.

    If avg EF for this category is low → user struggles → shorter intervals (< 1.0).
    If avg EF is high → user is strong → standard/longer intervals (>= 1.0).

    Returns: float in range [0.6, 1.4]
    """
    result = await db.execute(
        select(func.avg(UserAnswerHistory.ease_factor))
        .where(
            UserAnswerHistory.user_id == user_id,
            UserAnswerHistory.question_category == category,
            UserAnswerHistory.total_reviews >= 2,
        )
    )
    avg_ef = result.scalar()
    if avg_ef is None or avg_ef == 0:
        return 1.0  # No data or corrupted zeros — standard difficulty (S4-03)

    # S4-03: Clamp avg_ef to valid SM-2 range — values below MIN_EASE_FACTOR
    # indicate data corruption and would produce a negative multiplier.
    avg_ef = max(float(avg_ef), MIN_EASE_FACTOR)

    # Map avg_ef (typically 1.3-3.0) to multiplier (0.6-1.4)
    # avg_ef 1.3 → 0.6 (hardest), avg_ef 2.5 → 1.0 (standard), avg_ef 3.0+ → 1.4
    multiplier = 0.6 + (avg_ef - MIN_EASE_FACTOR) * (0.8 / (DEFAULT_EASE_FACTOR - MIN_EASE_FACTOR))
    return max(0.6, min(1.4, multiplier))


# ---------------------------------------------------------------------------
# DB Operations
# ---------------------------------------------------------------------------

async def record_review(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    question_text: str,
    question_category: str,
    is_correct: bool,
    response_time_ms: int | None = None,
    hint_used: bool = False,
    source_type: str = "quiz",
    is_srs_review: bool = False,
) -> UserAnswerHistory:
    """Record a quiz answer and update SM-2 + Leitner parameters.

    Args:
        user_id: Who answered
        question_text: Full question text
        question_category: Legal category (eligibility, procedure, etc.)
        is_correct: Whether the answer was correct
        response_time_ms: Time to answer in milliseconds
        hint_used: Whether user used a hint
        source_type: Where the answer came from (quiz, pvp, training, blitz)
        is_srs_review: Whether this was a dedicated SRS review session

    Returns:
        Updated UserAnswerHistory record
    """
    qhash = question_hash(question_text)
    quality = quality_from_answer(is_correct, response_time_ms, hint_used, is_srs_review=is_srs_review)
    now = datetime.now(timezone.utc)

    # Find or create history entry
    result = await db.execute(
        select(UserAnswerHistory).where(
            UserAnswerHistory.user_id == user_id,
            UserAnswerHistory.question_hash == qhash,
        )
    )
    history = result.scalar_one_or_none()

    # Get per-category difficulty
    cat_diff = await get_category_difficulty(db, user_id, question_category)

    if history is None:
        # New question — initialize
        new_ef, new_interval, new_rep = sm2_update(
            DEFAULT_EASE_FACTOR, 1, 0, quality, category_difficulty=cat_diff,
        )
        new_interval = _apply_fuzzy_jitter(new_interval)
        new_box = _update_leitner_box(0, is_correct)

        history = UserAnswerHistory(
            user_id=user_id,
            question_category=question_category,
            question_hash=qhash,
            question_text=question_text,
            ease_factor=new_ef,
            interval_days=new_interval,
            repetition_count=new_rep,
            quality_history=[quality],
            next_review_at=now + timedelta(days=new_interval),
            last_reviewed_at=now,
            total_reviews=1,
            total_correct=1 if is_correct else 0,
            leitner_box=new_box,
            source_type=source_type,
            current_streak=1 if is_correct else 0,
            best_streak=1 if is_correct else 0,
        )
        db.add(history)
    else:
        # Update existing
        old_streak = history.current_streak or 0

        new_ef, new_interval, new_rep = sm2_update(
            history.ease_factor,
            history.interval_days,
            history.repetition_count,
            quality,
            category_difficulty=cat_diff,
        )
        new_interval = _apply_fuzzy_jitter(new_interval)

        # Update SM-2 params
        history.ease_factor = new_ef
        history.interval_days = new_interval
        history.repetition_count = new_rep
        history.next_review_at = now + timedelta(days=new_interval)
        history.last_reviewed_at = now
        history.total_reviews = (history.total_reviews or 0) + 1
        if is_correct:
            history.total_correct = (history.total_correct or 0) + 1

        # Update Leitner box
        history.leitner_box = _update_leitner_box(
            history.leitner_box or 0, is_correct, streak=old_streak,
        )

        # Update streak
        if is_correct:
            history.current_streak = old_streak + 1
            history.best_streak = max(history.best_streak or 0, history.current_streak)
        else:
            history.current_streak = 0

        # Update source if different (track last source)
        if source_type != "quiz":
            history.source_type = source_type

        # Keep last N quality scores
        qh = list(history.quality_history or [])
        qh.append(quality)
        history.quality_history = qh[-MAX_QUALITY_HISTORY:]

    return history


# ---------------------------------------------------------------------------
# Query Operations
# ---------------------------------------------------------------------------

async def get_overdue_questions(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    category: str | None = None,
    limit: int = 5,
) -> list[UserAnswerHistory]:
    """Get questions that are overdue for review (next_review_at < now)."""
    now = datetime.now(timezone.utc)
    query = (
        select(UserAnswerHistory)
        .where(
            UserAnswerHistory.user_id == user_id,
            UserAnswerHistory.next_review_at <= now,
        )
        .order_by(UserAnswerHistory.next_review_at.asc())
        .limit(limit)
    )
    if category:
        query = query.where(UserAnswerHistory.question_category == category)

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_weak_questions(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    category: str | None = None,
    limit: int = 5,
) -> list[UserAnswerHistory]:
    """Get questions with low ease factor (struggling items, box 0-1)."""
    query = (
        select(UserAnswerHistory)
        .where(
            UserAnswerHistory.user_id == user_id,
            UserAnswerHistory.ease_factor < 2.0,
            UserAnswerHistory.total_reviews >= 2,
        )
        .order_by(UserAnswerHistory.ease_factor.asc())
        .limit(limit)
    )
    if category:
        query = query.where(UserAnswerHistory.question_category == category)

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_learning_items(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    category: str | None = None,
    limit: int = 5,
) -> list[UserAnswerHistory]:
    """Get items in learning phase (Leitner box 0-1)."""
    query = (
        select(UserAnswerHistory)
        .where(
            UserAnswerHistory.user_id == user_id,
            UserAnswerHistory.leitner_box <= 1,
        )
        .order_by(UserAnswerHistory.last_reviewed_at.asc())
        .limit(limit)
    )
    if category:
        query = query.where(UserAnswerHistory.question_category == category)

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_review_priority_queue(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    category: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """
    Build 4-tier prioritized question queue for SRS review:
      P1: Overdue items (need immediate review)
      P2: Weak items (low ease factor, struggling)
      P3: Learning items (Leitner box 0-1, recently lapsed)
      P4: Remaining slots filled by oldest reviewed items

    Returns list of dicts with question info + priority label.
    """
    queue: list[dict] = []
    seen_hashes: set[str] = set()

    def _add_items(items: list[UserAnswerHistory], priority: str) -> None:
        for item in items:
            if len(queue) >= limit:
                return
            if item.question_hash not in seen_hashes:
                queue.append({
                    "question_text": item.question_text,
                    "question_category": item.question_category,
                    "question_hash": item.question_hash,
                    "priority": priority,
                    "ease_factor": item.ease_factor,
                    "interval_days": item.interval_days,
                    "leitner_box": item.leitner_box or 0,
                    "current_streak": item.current_streak or 0,
                    "total_reviews": item.total_reviews or 0,
                })
                seen_hashes.add(item.question_hash)

    # P1: Overdue
    overdue = await get_overdue_questions(db, user_id, category=category, limit=limit)
    _add_items(overdue, "overdue")

    if len(queue) >= limit:
        return queue[:limit]

    # P2: Weak
    remaining = limit - len(queue)
    weak = await get_weak_questions(db, user_id, category=category, limit=remaining)
    _add_items(weak, "weak")

    if len(queue) >= limit:
        return queue[:limit]

    # P3: Learning (Leitner box 0-1)
    remaining = limit - len(queue)
    learning = await get_learning_items(db, user_id, category=category, limit=remaining)
    _add_items(learning, "learning")

    return queue[:limit]


# ---------------------------------------------------------------------------
# SRS Study Session
# ---------------------------------------------------------------------------

async def start_srs_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    category: str | None = None,
    session_size: int = 10,
) -> dict:
    """Start a dedicated SRS review session.

    Returns a structured session with:
    - review_queue: Prioritized list of questions to review
    - session_stats: Current SRS stats
    - estimated_time_minutes: Estimated session duration
    """
    queue = await get_review_priority_queue(
        db, user_id, category=category, limit=session_size,
    )
    stats = await get_user_srs_stats(db, user_id)
    category_breakdown = await get_category_mastery(db, user_id)

    return {
        "mode": "srs_review",
        "review_queue": queue,
        "session_size": len(queue),
        "stats": stats,
        "category_breakdown": category_breakdown,
        "estimated_time_minutes": max(1, len(queue) * 1.5),  # ~1.5 min per question
    }


# ---------------------------------------------------------------------------
# Statistics & Analytics
# ---------------------------------------------------------------------------

async def get_user_srs_stats(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Get user's comprehensive SRS stats."""
    now = datetime.now(timezone.utc)

    # Use a single aggregation query for performance
    result = await db.execute(
        select(
            func.count().label("total"),
            func.count().filter(UserAnswerHistory.next_review_at <= now).label("overdue"),
            func.count().filter(
                and_(
                    UserAnswerHistory.ease_factor >= MASTERY_EF_THRESHOLD,
                    UserAnswerHistory.repetition_count >= MASTERY_REP_THRESHOLD,
                )
            ).label("mastered"),
            func.avg(UserAnswerHistory.ease_factor).label("avg_ef"),
            func.sum(UserAnswerHistory.total_reviews).label("total_reviews"),
            func.sum(UserAnswerHistory.total_correct).label("total_correct"),
            func.max(UserAnswerHistory.best_streak).label("best_streak"),
        )
        .where(UserAnswerHistory.user_id == user_id)
    )
    row = result.one()
    total = row.total or 0
    mastered = row.mastered or 0
    total_reviews = row.total_reviews or 0
    total_correct = row.total_correct or 0

    # Leitner box distribution
    box_result = await db.execute(
        select(
            UserAnswerHistory.leitner_box,
            func.count().label("count"),
        )
        .where(UserAnswerHistory.user_id == user_id)
        .group_by(UserAnswerHistory.leitner_box)
    )
    box_distribution = {r.leitner_box or 0: r.count for r in box_result.all()}

    return {
        "total_items": total,
        "overdue": row.overdue or 0,
        "mastered": mastered,
        "learning": total - mastered,
        "avg_ease_factor": round(row.avg_ef, 2) if row.avg_ef else None,
        "accuracy_pct": round(total_correct / total_reviews * 100, 1) if total_reviews > 0 else None,
        "total_reviews": total_reviews,
        "best_streak": row.best_streak or 0,
        "leitner_distribution": box_distribution,
    }


async def get_category_mastery(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> list[dict]:
    """Get mastery breakdown by legal category."""
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(
            UserAnswerHistory.question_category,
            func.count().label("total"),
            func.count().filter(
                and_(
                    UserAnswerHistory.ease_factor >= MASTERY_EF_THRESHOLD,
                    UserAnswerHistory.repetition_count >= MASTERY_REP_THRESHOLD,
                )
            ).label("mastered"),
            func.count().filter(UserAnswerHistory.next_review_at <= now).label("overdue"),
            func.avg(UserAnswerHistory.ease_factor).label("avg_ef"),
            func.sum(UserAnswerHistory.total_correct).label("correct"),
            func.sum(UserAnswerHistory.total_reviews).label("reviews"),
        )
        .where(UserAnswerHistory.user_id == user_id)
        .group_by(UserAnswerHistory.question_category)
        .order_by(func.avg(UserAnswerHistory.ease_factor).asc())  # Weakest first
    )

    categories = []
    for row in result.all():
        total = row.total or 0
        mastered = row.mastered or 0
        reviews = row.reviews or 0
        correct = row.correct or 0
        categories.append({
            "category": row.question_category,
            "total": total,
            "mastered": mastered,
            "overdue": row.overdue or 0,
            "mastery_pct": round(mastered / total * 100, 1) if total > 0 else 0,
            "accuracy_pct": round(correct / reviews * 100, 1) if reviews > 0 else 0,
            "avg_ease_factor": round(row.avg_ef, 2) if row.avg_ef else None,
        })

    return categories


# ---------------------------------------------------------------------------
# Historical Backfill
# ---------------------------------------------------------------------------

async def backfill_from_quiz_answers(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    batch_size: int = 100,
) -> int:
    """Backfill SRS records from existing KnowledgeAnswer history.

    Processes un-tracked quiz answers and creates UserAnswerHistory entries.
    Returns number of records created.
    """
    from app.models.knowledge import KnowledgeAnswer

    # Find answered questions not yet in SRS
    existing_hashes = (
        select(UserAnswerHistory.question_hash)
        .where(UserAnswerHistory.user_id == user_id)
    )

    answers = await db.execute(
        select(KnowledgeAnswer)
        .where(
            KnowledgeAnswer.user_id == user_id,
        )
        .order_by(KnowledgeAnswer.created_at.asc())
        .limit(batch_size)
    )

    created = 0
    for answer in answers.scalars().all():
        q_text = answer.question_text or ""
        if not q_text:
            continue

        qhash = question_hash(q_text)

        # Check if already tracked
        exists = await db.execute(
            select(func.count()).where(
                UserAnswerHistory.user_id == user_id,
                UserAnswerHistory.question_hash == qhash,
            )
        )
        if (exists.scalar() or 0) > 0:
            continue

        # Create initial SRS entry from historical data
        is_correct = getattr(answer, "is_correct", False)
        quality = 4 if is_correct else 2
        new_ef, new_interval, new_rep = sm2_update(DEFAULT_EASE_FACTOR, 1, 0, quality)
        now = datetime.now(timezone.utc)

        entry = UserAnswerHistory(
            user_id=user_id,
            question_category=getattr(answer, "category", "unknown"),
            question_hash=qhash,
            question_text=q_text,
            ease_factor=new_ef,
            interval_days=new_interval,
            repetition_count=new_rep,
            quality_history=[quality],
            next_review_at=now + timedelta(days=new_interval),
            last_reviewed_at=now,
            total_reviews=1,
            total_correct=1 if is_correct else 0,
            leitner_box=1 if is_correct else 0,
            source_type="backfill",
            current_streak=1 if is_correct else 0,
            best_streak=1 if is_correct else 0,
        )
        db.add(entry)
        created += 1

    if created > 0:
        await db.flush()
        logger.info("Backfilled %d SRS records for user %s", created, user_id)

    return created
