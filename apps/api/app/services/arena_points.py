"""
Arena Points (AP) service (DOC_13).

AP is an activity-based currency earned from PvP/PvE/Knowledge/Tournaments.
Monthly reset. Spent in AP Shop for cosmetics.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.progress import ManagerProgress
from app.models.pvp import APPurchase


# ─── AP Earning Rates ────────────────────────────────────────────────────────

AP_RATES: dict[str, int] = {
    "pvp_win": 10,
    "pvp_loss": 3,
    "pvp_draw": 5,
    "pve_match": 5,
    "knowledge_session_low": 3,
    "knowledge_session_mid": 5,
    "knowledge_session_high": 8,
    "daily_challenge": 5,
    "promotion_success": 50,
    "first_match_of_day": 5,
    # Tournament placements
    "tournament_1st": 100,
    "tournament_2nd": 60,
    "tournament_3rd": 30,
}

# AP Shop prices
AP_SHOP_ITEMS: dict[str, dict] = {
    "border_basic": {"cost": 50, "type": "profile_border", "permanent": True},
    "border_animated": {"cost": 150, "type": "profile_border", "permanent": True},
    "custom_title": {"cost": 100, "type": "profile", "permanent": True},
    "emblem": {"cost": 75, "type": "profile", "permanent": True},
    "nickname_color": {"cost": 50, "type": "profile", "permanent": True},
    "exclusive_archetype": {"cost": 200, "type": "gameplay", "permanent": True},
    "replay_save": {"cost": 10, "type": "storage", "permanent": True},
    "queue_priority_24h": {"cost": 25, "type": "qol", "permanent": False, "duration_hours": 24},
}

# Season reward AP by tier
SEASON_AP_REWARDS: dict[str, int] = {
    "grandmaster": 500, "master": 350, "diamond": 250, "platinum": 175,
    "gold": 100, "silver": 50, "bronze": 25, "iron": 10,
}

# Season reward XP by tier
SEASON_XP_REWARDS: dict[str, int] = {
    "grandmaster": 1000, "master": 700, "diamond": 500, "platinum": 350,
    "gold": 200, "silver": 100, "bronze": 50, "iron": 25,
}


async def award_arena_points(
    db: AsyncSession,
    user_id: UUID,
    source: str,
    amount: int | None = None,
) -> int:
    """Award AP to a user. Returns new balance."""
    result = await db.execute(
        select(ManagerProgress).where(ManagerProgress.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        return 0

    pts = amount if amount is not None else AP_RATES.get(source, 0)
    if pts <= 0:
        return profile.arena_points

    profile.arena_points += pts
    profile.arena_points_total_earned += pts
    return profile.arena_points


async def purchase_item(
    db: AsyncSession,
    user_id: UUID,
    item_id: str,
) -> dict:
    """Purchase an AP shop item. Returns result dict."""
    item = AP_SHOP_ITEMS.get(item_id)
    if not item:
        return {"success": False, "error": "Item not found"}

    result = await db.execute(
        select(ManagerProgress).where(ManagerProgress.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        return {"success": False, "error": "Profile not found"}

    cost = item["cost"]
    if profile.arena_points < cost:
        return {"success": False, "error": f"Insufficient AP: {profile.arena_points}/{cost}"}

    profile.arena_points -= cost

    expires_at = None
    if not item.get("permanent", True):
        from datetime import timedelta
        hours = item.get("duration_hours", 24)
        expires_at = datetime.utcnow() + timedelta(hours=hours)

    purchase = APPurchase(
        user_id=user_id,
        item_type=item["type"],
        item_id=item_id,
        cost_ap=cost,
        expires_at=expires_at,
    )
    db.add(purchase)

    return {
        "success": True,
        "item_id": item_id,
        "cost": cost,
        "ap_remaining": profile.arena_points,
        "expires_at": expires_at.isoformat() if expires_at else None,
    }


async def reset_monthly_ap(db: AsyncSession) -> int:
    """Reset all users' AP to 0. Called on 1st of each month. Returns count."""
    from sqlalchemy import update

    result = await db.execute(
        update(ManagerProgress)
        .where(ManagerProgress.arena_points > 0)
        .values(
            arena_points_last_month=ManagerProgress.arena_points,
            arena_points=0,
        )
    )
    return result.rowcount or 0


def get_tier_name(rank_tier: str) -> str:
    """Extract tier name from rank (e.g., 'gold_2' → 'gold', 'grandmaster' → 'grandmaster')."""
    parts = rank_tier.rsplit("_", 1)
    if len(parts) == 2 and parts[1] in ("1", "2", "3"):
        return parts[0]
    return rank_tier


def combined_rating(training_rating: float, knowledge_rating: float,
                    training_placed: bool, knowledge_placed: bool) -> float:
    """Compute combined rating for unified leaderboard (DOC_13)."""
    if training_placed and knowledge_placed:
        return training_rating * 0.6 + knowledge_rating * 0.4
    elif training_placed:
        return training_rating
    elif knowledge_placed:
        return knowledge_rating
    return 1500.0
