"""
Season Pass progression — 30-tier reward track powered by Arena Points (DOC_15).

AP is the SINGLE currency: every AP earned also progresses the season pass.
Season resets quarterly (reset logic not implemented here — just earning + progression).
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.progress import ManagerProgress

logger = logging.getLogger(__name__)

# ─── Tier Thresholds: cumulative AP needed to reach each tier ────────────────

SEASON_TIER_THRESHOLDS: list[int] = [
    0,                                                                # T0 (start)
    50, 120, 200, 300, 420, 560, 720, 900, 1100,                     # T1-T9  (easy)
    1320,                                                             # T10
    1560, 1820, 2100, 2400, 2720, 3060, 3420, 3800, 4200,            # T11-T19 (medium)
    4620,                                                             # T20
    5060, 5520, 6000, 6500, 7020, 7560, 8120, 8700, 9300,            # T21-T29 (hard)
    9900,                                                             # T30
]

MAX_TIER = 30

# ─── Rewards per tier ────────────────────────────────────────────────────────

SEASON_REWARDS: dict[int, dict] = {
    1:  {"type": "xp_boost", "value": 50, "name": "XP бонус +50"},
    3:  {"type": "border", "value": "season_bronze", "name": "Бордюр: Бронза сезона"},
    5:  {"type": "title", "value": "season_fighter", "name": "Титул: Боец сезона"},
    7:  {"type": "xp_boost", "value": 100, "name": "XP бонус +100"},
    10: {"type": "border", "value": "season_silver", "name": "Бордюр: Серебро сезона"},
    12: {"type": "xp_boost", "value": 150, "name": "XP бонус +150"},
    15: {"type": "title", "value": "season_veteran", "name": "Титул: Ветеран сезона"},
    18: {"type": "xp_boost", "value": 200, "name": "XP бонус +200"},
    20: {"type": "border", "value": "season_gold", "name": "Бордюр: Золото сезона"},
    23: {"type": "xp_boost", "value": 250, "name": "XP бонус +250"},
    25: {"type": "title", "value": "season_elite", "name": "Титул: Элита сезона"},
    28: {"type": "xp_boost", "value": 300, "name": "XP бонус +300"},
    30: {"type": "legendary_border", "value": "season_legend", "name": "Бордюр: Легенда сезона"},
}


def _tier_for_points(season_points: int) -> int:
    """Return the highest tier reached for given cumulative season points."""
    tier = 0
    for i in range(1, len(SEASON_TIER_THRESHOLDS)):
        if season_points >= SEASON_TIER_THRESHOLDS[i]:
            tier = i
        else:
            break
    return min(tier, MAX_TIER)


async def get_season_progress(user_id: UUID, db: AsyncSession) -> dict:
    """Get current tier, points, next tier threshold, and earned rewards."""
    result = await db.execute(
        select(ManagerProgress).where(ManagerProgress.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        return {
            "tier": 0,
            "season_points": 0,
            "next_tier_threshold": SEASON_TIER_THRESHOLDS[1] if len(SEASON_TIER_THRESHOLDS) > 1 else 0,
            "points_to_next_tier": SEASON_TIER_THRESHOLDS[1] if len(SEASON_TIER_THRESHOLDS) > 1 else 0,
            "max_tier": MAX_TIER,
            "rewards_earned": [],
            "rewards_available": get_rewards_up_to_tier(0),
        }

    tier = profile.season_pass_tier
    pts = profile.season_points

    next_threshold = (
        SEASON_TIER_THRESHOLDS[tier + 1]
        if tier < MAX_TIER and tier + 1 < len(SEASON_TIER_THRESHOLDS)
        else None
    )
    points_to_next = (next_threshold - pts) if next_threshold is not None else 0

    return {
        "tier": tier,
        "season_points": pts,
        "next_tier_threshold": next_threshold,
        "points_to_next_tier": max(0, points_to_next),
        "max_tier": MAX_TIER,
        "rewards_earned": get_rewards_up_to_tier(tier),
        "rewards_available": get_rewards_up_to_tier(MAX_TIER),
    }


async def advance_season(user_id: UUID, ap_earned: int, db: AsyncSession) -> dict:
    """Called after every AP award. Adds AP to season_points and checks tier advancement.

    Returns dict with tier info and any new rewards unlocked.
    """
    if ap_earned <= 0:
        return {"tier_changed": False, "tier": 0, "new_rewards": []}

    result = await db.execute(
        select(ManagerProgress).where(ManagerProgress.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        return {"tier_changed": False, "tier": 0, "new_rewards": []}

    old_tier = profile.season_pass_tier
    profile.season_points += ap_earned

    new_tier = _tier_for_points(profile.season_points)
    profile.season_pass_tier = new_tier

    # Collect newly unlocked rewards
    new_rewards = []
    if new_tier > old_tier:
        for t in range(old_tier + 1, new_tier + 1):
            if t in SEASON_REWARDS:
                new_rewards.append({"tier": t, **SEASON_REWARDS[t]})

    next_threshold = (
        SEASON_TIER_THRESHOLDS[new_tier + 1]
        if new_tier < MAX_TIER and new_tier + 1 < len(SEASON_TIER_THRESHOLDS)
        else None
    )

    logger.info(
        "Season advance: user=%s ap_earned=%d points=%d tier=%d->%d rewards=%d",
        user_id, ap_earned, profile.season_points, old_tier, new_tier, len(new_rewards),
    )

    return {
        "tier_changed": new_tier > old_tier,
        "old_tier": old_tier,
        "tier": new_tier,
        "season_points": profile.season_points,
        "next_tier_threshold": next_threshold,
        "new_rewards": new_rewards,
    }


def get_rewards_up_to_tier(tier: int) -> list[dict]:
    """Get all rewards from tier 1 up to the given tier."""
    return [
        {"tier": t, **reward}
        for t, reward in sorted(SEASON_REWARDS.items())
        if t <= tier
    ]
