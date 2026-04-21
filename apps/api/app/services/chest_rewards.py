"""Chest Rewards — variable reward system (intermittent reinforcement).

Three chest types with randomized rewards:
  - Bronze: daily drill completion
  - Silver: 3/3 daily quests completed
  - Gold: weekly league top 3, season milestone

Variable rewards are psychologically more engaging than fixed rewards
(Skinner's intermittent reinforcement schedule).
"""

from __future__ import annotations

import logging
import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.progress import ManagerProgress

logger = logging.getLogger(__name__)


@dataclass
class ChestReward:
    """Result of opening a chest."""
    chest_type: str       # bronze, silver, gold
    xp_reward: int
    ap_reward: int
    item_reward: str | None  # cosmetic item slug or None
    item_name: str | None
    is_rare_drop: bool    # for special UI celebration


# ── Chest configurations ─────────────────────────────────────────────────────

CHEST_CONFIG = {
    "bronze": {
        "xp_range": (10, 30),
        "ap_chance": 0.10,
        "ap_range": (5, 10),
        "item_chance": 0.0,
        "items": [],
    },
    "silver": {
        "xp_range": (30, 60),
        "ap_chance": 0.30,
        "ap_range": (10, 20),
        "item_chance": 0.05,
        "items": [
            ("border_basic", "Рамка: Серебряная волна"),
            ("title_diligent", "Титул: Усердный"),
        ],
    },
    "gold": {
        "xp_range": (60, 120),
        "ap_chance": 0.80,
        "ap_range": (20, 50),
        "item_chance": 0.15,
        "items": [
            ("border_animated", "Рамка: Золотое сияние"),
            ("title_champion", "Титул: Чемпион недели"),
            ("emblem_fire", "Эмблема: Огненный феникс"),
            ("nickname_gold", "Золотой никнейм"),
        ],
    },
}


async def open_chest(
    user_id: uuid.UUID,
    chest_type: str,
    db: AsyncSession,
) -> ChestReward:
    """Open a chest and award randomized rewards.

    Applies rewards directly to ManagerProgress.
    """
    config = CHEST_CONFIG.get(chest_type)
    if not config:
        raise ValueError(f"Unknown chest type: {chest_type}")

    # Roll rewards
    xp = random.randint(*config["xp_range"])

    ap = 0
    if random.random() < config["ap_chance"]:
        ap = random.randint(*config["ap_range"])

    item_slug = None
    item_name = None
    is_rare = False
    if config["items"] and random.random() < config["item_chance"]:
        item_slug, item_name = random.choice(config["items"])
        is_rare = True

    # Apply rewards
    from sqlalchemy import update
    await db.execute(
        update(ManagerProgress)
        .where(ManagerProgress.user_id == user_id)
        .values(
            total_xp=ManagerProgress.total_xp + xp,
            current_xp=ManagerProgress.current_xp + xp,
            arena_points=ManagerProgress.arena_points + ap,
            arena_points_total_earned=ManagerProgress.arena_points_total_earned + ap,
        )
    )

    # Write XPLog
    try:
        from app.models.xp_log import XPLog
        xp_log = XPLog(
            user_id=user_id,
            source=f"chest_{chest_type}",
            amount=xp,
            multiplier=1.0,
            season_points=0,
        )
        db.add(xp_log)
    except Exception:
        pass

    logger.info(
        "Chest opened: user=%s type=%s xp=%d ap=%d item=%s",
        user_id, chest_type, xp, ap, item_slug,
    )

    return ChestReward(
        chest_type=chest_type,
        xp_reward=xp,
        ap_reward=ap,
        item_reward=item_slug,
        item_name=item_name,
        is_rare_drop=is_rare,
    )
