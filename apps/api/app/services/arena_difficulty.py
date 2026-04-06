"""Arena difficulty engine: maps user's PvP rating to question difficulty.

Uses the existing PvPRating model (Glicko-2) to determine appropriate
question difficulty range for Arena quizzes.

Block 5 (ТЗ_БЛОК_5_CROSS_MODULE): Difficulty Engine integration.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pvp import PvPRating

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rating → Difficulty mapping
# ---------------------------------------------------------------------------

# Tier boundaries and corresponding difficulty profiles
DIFFICULTY_PROFILES = [
    # (max_rating, difficulty_range, prefer_court_practice, tier_name)
    (1400, (1, 3), False, "Бронзовый уровень"),
    (1600, (2, 4), False, "Серебряный уровень"),
    (1800, (3, 5), True, "Золотой уровень"),
    (9999, (4, 5), True, "Платиновый+ уровень"),
]

# Default profile for users with no PvP history
DEFAULT_PROFILE = {
    "difficulty_range": (1, 3),
    "prefer_court_practice": False,
    "description": "Начинающий — базовые вопросы",
    "rating": 1500,
    "has_pvp_data": False,
}


async def get_arena_difficulty_profile(
    user_id: uuid.UUID, db: AsyncSession,
) -> dict:
    """Determine appropriate question difficulty based on Arena PvP rating.

    Returns:
        dict with keys:
            difficulty_range: tuple[int, int]  — (min, max) difficulty
            prefer_court_practice: bool — whether to include court practice questions
            description: str — human-readable tier name
            rating: float — current rating
            has_pvp_data: bool — whether user has played PvP
    """
    result = await db.execute(
        select(PvPRating).where(
            PvPRating.user_id == user_id,
            PvPRating.rating_type == "knowledge_arena",
        )
    )
    rating_record = result.scalar_one_or_none()

    if not rating_record or rating_record.total_duels == 0:
        return DEFAULT_PROFILE

    r = rating_record.rating

    for max_r, diff_range, court, name in DIFFICULTY_PROFILES:
        if r < max_r:
            return {
                "difficulty_range": diff_range,
                "prefer_court_practice": court,
                "description": name,
                "rating": r,
                "has_pvp_data": True,
            }

    # Fallback (shouldn't reach here)
    return {
        "difficulty_range": (4, 5),
        "prefer_court_practice": True,
        "description": "Топ-уровень",
        "rating": r,
        "has_pvp_data": True,
    }


async def get_arena_rating_for_user(
    user_id: uuid.UUID, db: AsyncSession,
) -> dict:
    """Get PvP rating summary for a user (for dashboard display).

    Returns:
        dict with rating, rank_tier, wins, losses, streak, peak_rating
    """
    result = await db.execute(
        select(PvPRating).where(
            PvPRating.user_id == user_id,
            PvPRating.rating_type == "knowledge_arena",
        )
    )
    rating = result.scalar_one_or_none()

    if not rating:
        return {
            "rating": 1500,
            "rank_tier": "unranked",
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "total_duels": 0,
            "current_streak": 0,
            "best_streak": 0,
            "peak_rating": 1500,
            "placement_done": False,
        }

    return {
        "rating": rating.rating,
        "rank_tier": rating.rank_tier.value if rating.rank_tier else "unranked",
        "wins": rating.wins,
        "losses": rating.losses,
        "draws": rating.draws,
        "total_duels": rating.total_duels,
        "current_streak": rating.current_streak,
        "best_streak": rating.best_streak,
        "peak_rating": rating.peak_rating,
        "placement_done": rating.placement_done,
    }
