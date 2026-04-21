"""
Hunter Score — unified composite metric (DOC_14 §4.3).

Combines: Training level (35%) + PvP rating (25%) + Knowledge (20%) +
          Achievement completion (10%) + Reputation (10%) = 0-100.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.progress import ManagerProgress


def calculate_hunter_score(
    training_level: int,
    pvp_rating_percentile: float,   # 0.0–1.0
    knowledge_avg_score: float,      # 0–100
    achievement_completion_pct: float,  # 0.0–1.0
    reputation_score: float,          # 0–100
) -> float:
    """Unified composite metric. Range: 0-100."""
    score = (
        0.35 * (training_level / 20 * 100)
        + 0.25 * (pvp_rating_percentile * 100)
        + 0.20 * knowledge_avg_score
        + 0.10 * (achievement_completion_pct * 100)
        + 0.10 * reputation_score
    )
    return round(min(100.0, max(0.0, score)), 1)


async def update_hunter_score(db: AsyncSession, user_id: UUID) -> float:
    """Recalculate and persist Hunter Score for a user."""
    result = await db.execute(
        select(ManagerProgress).where(ManagerProgress.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        return 0.0

    # Training level component
    training_level = profile.current_level

    # PvP rating percentile (simplified: rating / 3000 capped at 1.0)
    try:
        from app.models.pvp import PvPRating
        pvp_result = await db.execute(
            select(PvPRating.rating).where(
                PvPRating.user_id == user_id,
                PvPRating.rating_type == "training_duel",
            )
        )
        pvp_rating = pvp_result.scalar_one_or_none() or 1500.0
        pvp_percentile = min(1.0, max(0.0, (pvp_rating - 1000) / 2000))
    except Exception:
        pvp_percentile = 0.0

    # Knowledge avg score (simplified: from skills)
    knowledge_avg = getattr(profile, "skill_legal_knowledge", 50)

    # Achievement completion (S3-06: dynamic total from AchievementDefinition)
    try:
        from app.models.analytics import UserAchievement
        from app.models.progress import AchievementDefinition

        ach_count_result = await db.execute(
            select(func.count()).select_from(UserAchievement).where(
                UserAchievement.user_id == user_id
            )
        )
        ach_count = ach_count_result.scalar() or 0

        total_result = await db.execute(
            select(func.count()).select_from(AchievementDefinition)
        )
        total_achievements = total_result.scalar() or 140  # fallback to 140 if table empty
        ach_pct = min(1.0, ach_count / total_achievements)
    except Exception:
        ach_pct = 0.0

    # Reputation score
    try:
        from app.models.reputation import ManagerReputation
        rep_result = await db.execute(
            select(ManagerReputation.score).where(ManagerReputation.user_id == user_id)
        )
        rep_score = rep_result.scalar_one_or_none() or 50.0
    except Exception:
        rep_score = 50.0

    score = calculate_hunter_score(
        training_level=training_level,
        pvp_rating_percentile=pvp_percentile,
        knowledge_avg_score=knowledge_avg,
        achievement_completion_pct=ach_pct,
        reputation_score=rep_score,
    )

    profile.hunter_score = score
    profile.hunter_score_updated_at = datetime.now(timezone.utc)

    return score


# ─── PVP Rank → Recommended Difficulty (DOC_14 §2.4) ────────────────────────

PVP_RANK_TO_DIFFICULTY: dict[str, tuple[int, int]] = {
    "iron": (1, 3),
    "bronze": (3, 5),
    "silver": (5, 6),
    "gold": (6, 7),
    "platinum": (7, 8),
    "diamond": (8, 9),
    "master": (9, 10),
    "grandmaster": (10, 10),
}

# ─── Knowledge Category → Training Archetypes (DOC_14 §2.5) ─────────────────

CATEGORY_TO_TRAINING_ARCHETYPES: dict[str, list[str]] = {
    "eligibility": ["skeptic", "know_it_all", "lawyer_client"],
    "procedure": ["anxious", "paranoid", "rushed"],
    "property": ["desperate", "couple", "widow"],
    "consequences": ["passive", "frozen", "avoidant"],
    "costs": ["pragmatic", "shopper", "negotiator"],
    "creditors": ["aggressive", "hostile", "pre_court"],
    "documents": ["overwhelmed", "memory_issues", "delegator"],
    "timeline": ["rushed", "sarcastic", "court_notice"],
    "court": ["litigious", "lawyer_client", "puppet_master"],
    "rights": ["righteous", "hostile", "journalist"],
}

# ─── PvP Win Streak → Training XP Multiplier (DOC_14 §2.3) ──────────────────

def get_streak_xp_multiplier(pvp_win_streak: int) -> float:
    """Get XP multiplier for training sessions based on PvP win streak."""
    if pvp_win_streak >= 15:
        return 1.5
    elif pvp_win_streak >= 10:
        return 1.3
    elif pvp_win_streak >= 5:
        return 1.2
    return 1.0
