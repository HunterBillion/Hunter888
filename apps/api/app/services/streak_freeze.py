"""Streak Freeze — purchasable streak protection (loss aversion mechanic).

Purchase: 25 AP per freeze, max 2 per month.
Usage: Automatically applied when drill streak would break (gap > 1 day).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.progress import ManagerProgress, StreakFreeze

logger = logging.getLogger(__name__)

FREEZE_COST_AP = 25
MAX_FREEZES_PER_MONTH = 2


async def purchase_streak_freeze(
    user_id: uuid.UUID, db: AsyncSession
) -> dict:
    """Purchase a streak freeze for AP.

    Returns:
        dict with success, remaining_ap, freezes_remaining, or error message
    """
    now = datetime.now(timezone.utc)
    month_year = now.strftime("%Y-%m")

    # Check monthly limit
    count_result = await db.execute(
        select(func.count(StreakFreeze.id)).where(
            StreakFreeze.user_id == user_id,
            StreakFreeze.month_year == month_year,
        )
    )
    current_count = count_result.scalar() or 0
    if current_count >= MAX_FREEZES_PER_MONTH:
        return {
            "success": False,
            "error": f"Лимит заморозок в этом месяце: {MAX_FREEZES_PER_MONTH}",
            "freezes_this_month": current_count,
        }

    # Check AP balance
    result = await db.execute(
        select(ManagerProgress).where(ManagerProgress.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if not profile or profile.arena_points < FREEZE_COST_AP:
        return {
            "success": False,
            "error": f"Недостаточно AP. Нужно {FREEZE_COST_AP}, у вас {profile.arena_points if profile else 0}",
        }

    # Deduct AP and create freeze
    profile.arena_points -= FREEZE_COST_AP
    freeze = StreakFreeze(
        user_id=user_id,
        month_year=month_year,
    )
    db.add(freeze)
    await db.flush()

    # Count unused freezes
    unused_result = await db.execute(
        select(func.count(StreakFreeze.id)).where(
            StreakFreeze.user_id == user_id,
            StreakFreeze.used_at.is_(None),
        )
    )
    unused_count = unused_result.scalar() or 0

    logger.info(
        "Streak freeze purchased: user=%s ap_cost=%d remaining_ap=%d unused_freezes=%d",
        user_id, FREEZE_COST_AP, profile.arena_points, unused_count,
    )

    return {
        "success": True,
        "ap_spent": FREEZE_COST_AP,
        "remaining_ap": profile.arena_points,
        "unused_freezes": unused_count,
        "freezes_this_month": current_count + 1,
        "max_per_month": MAX_FREEZES_PER_MONTH,
    }


async def get_freeze_status(
    user_id: uuid.UUID, db: AsyncSession
) -> dict:
    """Get current streak freeze inventory."""
    now = datetime.now(timezone.utc)
    month_year = now.strftime("%Y-%m")

    unused_result = await db.execute(
        select(func.count(StreakFreeze.id)).where(
            StreakFreeze.user_id == user_id,
            StreakFreeze.used_at.is_(None),
        )
    )
    unused = unused_result.scalar() or 0

    month_result = await db.execute(
        select(func.count(StreakFreeze.id)).where(
            StreakFreeze.user_id == user_id,
            StreakFreeze.month_year == month_year,
        )
    )
    this_month = month_result.scalar() or 0

    return {
        "unused_freezes": unused,
        "purchased_this_month": this_month,
        "max_per_month": MAX_FREEZES_PER_MONTH,
        "can_purchase": this_month < MAX_FREEZES_PER_MONTH,
        "cost_ap": FREEZE_COST_AP,
    }
