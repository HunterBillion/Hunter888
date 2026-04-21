"""Arena Knowledge XP calculation and streak tracking.

XP from Arena sessions is separate from training XP but contributes
to the unified ManagerProgress.total_xp pool.

Base XP:
- AI Quiz: 30 base + score * 1.5
- PvP Win: 50 base + score * 2.0
- PvP Loss: 20 base + score * 0.5

Bonuses:
- Streak: +5 per day (max 30)
- Perfect (100%): +75
- Upset win (beat higher rated): +25-50

Cap: 200 XP per session.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.progress import ManagerProgress

logger = logging.getLogger(__name__)

MAX_ARENA_XP_PER_SESSION = 200


def calculate_arena_xp(
    mode: str,
    score: float,  # 0-100
    correct: int,
    total: int,
    streak_days: int,
    is_pvp_win: bool = False,
    pvp_opponent_rating: float | None = None,
    player_rating: float | None = None,
) -> dict:
    """Calculate XP earned from an Arena session.

    Returns dict with breakdown: {base, score_bonus, streak_bonus, perfect_bonus, upset_bonus, total}.
    """
    xp: dict[str, int] = {}

    # Base XP
    if mode == "pvp":
        if is_pvp_win:
            xp["base"] = 50
            xp["score_bonus"] = int(score * 2.0)
        else:
            xp["base"] = 20
            xp["score_bonus"] = int(score * 0.5)
    else:
        xp["base"] = 30
        xp["score_bonus"] = int(score * 1.5)

    # Streak bonus
    xp["streak_bonus"] = min(streak_days * 5, 30)

    # Perfect bonus
    if correct == total and total >= 10:
        xp["perfect_bonus"] = 75
    else:
        xp["perfect_bonus"] = 0

    # Upset win bonus (PvP only)
    xp["upset_bonus"] = 0
    if is_pvp_win and pvp_opponent_rating and player_rating:
        diff = pvp_opponent_rating - player_rating
        if diff > 200:
            xp["upset_bonus"] = 50
        elif diff > 100:
            xp["upset_bonus"] = 25

    xp["total"] = min(sum(xp.values()), MAX_ARENA_XP_PER_SESSION)

    return xp


async def update_arena_streak(
    user_id: uuid.UUID,
    correct_in_session: int,
    total_in_session: int,
    answer_streak_at_end: int,
    db: AsyncSession,
) -> ManagerProgress:
    """Update cross-session arena streak tracking in ManagerProgress.

    Args:
        correct_in_session: Number of correct answers in this session.
        total_in_session: Total questions in this session.
        answer_streak_at_end: Current answer streak at the end of the session
            (tracked in real-time during quiz via ws/knowledge.py).

    Returns the updated ManagerProgress.
    """
    # S2-07d: FOR UPDATE prevents concurrent double-counting of streak updates
    result = await db.execute(
        select(ManagerProgress)
        .where(ManagerProgress.user_id == user_id)
        .with_for_update()
    )
    progress = result.scalar_one_or_none()

    if progress is None:
        # Auto-create ManagerProgress if missing
        progress = ManagerProgress(user_id=user_id)
        db.add(progress)
        await db.flush()

    # Daily streak
    today = datetime.now(timezone.utc).date()
    if progress.arena_last_quiz_date:
        last_date = progress.arena_last_quiz_date
        if hasattr(last_date, 'date'):
            last_date = last_date.date()
        days_diff = (today - last_date).days
        if days_diff == 1:
            progress.arena_daily_streak += 1
        elif days_diff > 1:
            progress.arena_daily_streak = 1
        # Same day = no change
    else:
        progress.arena_daily_streak = 1

    progress.arena_last_quiz_date = datetime.now(timezone.utc)

    # Answer streak — persist best
    progress.arena_answer_streak = answer_streak_at_end
    if answer_streak_at_end > progress.arena_best_answer_streak:
        progress.arena_best_answer_streak = answer_streak_at_end

    await db.flush()
    return progress


async def apply_arena_xp_to_progress(
    user_id: uuid.UUID,
    xp_earned: int,
    db: AsyncSession,
) -> ManagerProgress:
    """Add Arena XP to the user's total XP in ManagerProgress."""
    from app.services.gamification import xp_for_level

    # S2-07d: FOR UPDATE prevents concurrent XP double-counting
    result = await db.execute(
        select(ManagerProgress)
        .where(ManagerProgress.user_id == user_id)
        .with_for_update()
    )
    progress = result.scalar_one_or_none()

    if progress is None:
        progress = ManagerProgress(user_id=user_id)
        db.add(progress)
        await db.flush()

    # S3-02: Apply daily soft cap
    try:
        from app.services.xp_daily_cap import apply_daily_cap
        xp_earned = await apply_daily_cap(user_id, xp_earned, source="arena_session")
    except Exception:
        logger.warning("Daily XP cap unavailable for arena, using full XP", exc_info=True)

    progress.total_xp += xp_earned
    progress.current_xp += xp_earned

    # Level up check
    next_level_xp = xp_for_level(progress.current_level + 1)
    while progress.total_xp >= next_level_xp and next_level_xp > 0:
        progress.current_level += 1
        next_level_xp = xp_for_level(progress.current_level + 1)

    await db.flush()
    return progress
