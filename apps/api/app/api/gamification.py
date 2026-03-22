"""Gamification endpoints: XP, level, streak, achievements, leaderboard."""

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.gamification import (
    calculate_streak,
    check_and_award_achievements,
    get_leaderboard,
    get_user_total_xp,
    level_from_xp,
    xp_for_level,
)

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────


class ProgressResponse(BaseModel):
    total_xp: int
    level: int
    xp_current_level: int
    xp_next_level: int
    streak_days: int
    achievements: list[dict]


class LeaderboardEntry(BaseModel):
    rank: int
    user_id: str
    full_name: str
    avatar_url: str | None = None
    sessions_count: int
    total_score: float
    avg_score: float


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/me/progress", response_model=ProgressResponse)
async def get_my_progress(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's gamification progress: XP, level, streak, achievements."""
    total_xp = await get_user_total_xp(user.id, db)
    level = level_from_xp(total_xp)
    streak = await calculate_streak(user.id, db)

    # Check for new achievements
    new_achievements = await check_and_award_achievements(user.id, db)

    return ProgressResponse(
        total_xp=total_xp,
        level=level,
        xp_current_level=total_xp - xp_for_level(level),
        xp_next_level=xp_for_level(level + 1) - xp_for_level(level),
        streak_days=streak,
        achievements=new_achievements,
    )


@router.get("/leaderboard", response_model=list[LeaderboardEntry])
async def leaderboard(
    period: str = Query("week", pattern="^(week|month|all)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get leaderboard. ROP users see only their team."""
    team_id = None
    if user.role.value == "rop" and user.team_id:
        team_id = user.team_id

    rows = await get_leaderboard(db, period=period, team_id=team_id)
    return rows


@router.get("/daily-challenge")
async def daily_challenge(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get personalized daily challenge based on user history.

    Uses adaptive difficulty to pick the right scenario.
    If no history — returns a beginner-friendly challenge.
    """
    from datetime import date

    from app.services.difficulty import get_difficulty_profile, get_recommended_scenarios

    profile = await get_difficulty_profile(user.id, db)
    recs = await get_recommended_scenarios(user.id, db, count=1)

    # Challenge types rotate by day of year
    challenge_types = [
        {"type": "score", "title": "Побей свой рекорд", "description": "Набери больше {target} баллов в одной сессии", "xp_bonus": 50},
        {"type": "archetype", "title": "Новый архетип", "description": "Пройди тренировку с архетипом, которого давно не тренировал", "xp_bonus": 40},
        {"type": "streak", "title": "Не прерывай серию", "description": "Завершите хотя бы одну тренировку сегодня", "xp_bonus": 30},
        {"type": "quality", "title": "Без ошибок", "description": "Завершите тренировку без антипаттернов (penalty = 0)", "xp_bonus": 60},
        {"type": "speed", "title": "Быстрая сделка", "description": "Закройте клиента на консультацию за 5 минут", "xp_bonus": 70},
    ]

    day_index = date.today().timetuple().tm_yday % len(challenge_types)
    challenge = challenge_types[day_index]

    # Personalize target score
    if challenge["type"] == "score":
        target = max(60, int(profile.avg_score) + 5) if profile.avg_score > 0 else 60
        challenge["description"] = challenge["description"].format(target=target)

    # Add recommended scenario
    scenario = None
    if recs:
        r = recs[0]
        scenario = {
            "scenario_id": str(r.scenario_id),
            "title": r.title,
            "archetype": r.archetype_name,
            "difficulty": r.difficulty,
        }

    return {
        "challenge": challenge,
        "scenario": scenario,
        "date": str(date.today()),
    }
