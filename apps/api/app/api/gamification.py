"""Gamification endpoints: XP, level, streak, achievements, leaderboard, goals, challenges."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User

limiter = Limiter(key_func=get_remote_address)
from app.services.gamification import (
    calculate_streak,
    check_and_award_achievements,
    get_leaderboard,
    get_leaderboard_extended,
    get_team_leaderboard,
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


# ── Daily/Weekly Goals ───────────────────────────────────────────────────────


@router.get("/goals")
async def get_goals(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get daily and weekly goal progress for current user."""
    from app.services.daily_goals import get_goals_snapshot

    snapshot = await get_goals_snapshot(user.id, db)

    return {
        "daily": [
            {
                "id": g.goal_id,
                "label": g.label,
                "description": g.description,
                "target": g.target,
                "current": g.current,
                "progress_pct": g.progress_pct,
                "xp": g.xp,
                "completed": g.completed,
                "icon": g.icon,
            }
            for g in snapshot.daily
        ],
        "weekly": [
            {
                "id": g.goal_id,
                "label": g.label,
                "description": g.description,
                "target": g.target,
                "current": g.current,
                "progress_pct": g.progress_pct,
                "xp": g.xp,
                "completed": g.completed,
                "icon": g.icon,
            }
            for g in snapshot.weekly
        ],
        "total_xp_available": snapshot.total_xp_available,
        "total_xp_earned": snapshot.total_xp_earned,
    }


# ── Extended Leaderboard ─────────────────────────────────────────────────────


class ExtendedLeaderboardEntry(BaseModel):
    rank: int
    user_id: str
    full_name: str
    avatar_url: str | None = None
    sessions_count: int
    total_score: float
    avg_score: float
    total_xp: int = 0
    level: int = 1
    streak: int = 0
    combined_score: float | None = None


@router.get("/leaderboard/extended", response_model=list[ExtendedLeaderboardEntry])
async def leaderboard_extended(
    sort_by: str = Query("xp", pattern="^(xp|score|streak|combined)$"),
    period: str = Query("week", pattern="^(week|month|all)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Extended leaderboard with XP/Score/Streak/Combined sorting."""
    team_id = None
    if user.role.value == "rop" and user.team_id:
        team_id = user.team_id

    return await get_leaderboard_extended(db, sort_by=sort_by, period=period, team_id=team_id)


# ── Composite Leaderboard (3.3) ────────────────────────────────────────────


class CompositeLeaderboardEntry(BaseModel):
    rank: int
    user_id: str
    full_name: str
    avatar_url: str | None = None
    composite_score: float
    training_avg: float
    pvp_rating_norm: float
    knowledge_score: float
    streak_bonus: float


@router.get("/leaderboard/composite", response_model=list[CompositeLeaderboardEntry])
@limiter.limit("10/minute")
async def composite_leaderboard(
    request: Request,
    period: str = Query("all", pattern="^(week|month|all)$"),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Composite leaderboard: 40% training + 30% PvP + 20% knowledge + 10% streak."""
    from sqlalchemy import select as sa_select, func as sa_func, case, literal
    from app.models.training import TrainingSession
    from app.models.pvp import PvPRating as PvPProfile
    from app.models.user import User as UserModel

    # Sub-query: training avg score per user
    training_sq = (
        sa_select(
            TrainingSession.user_id,
            sa_func.avg(TrainingSession.score_total).label("avg_score"),
        )
        .where(TrainingSession.score_total.isnot(None))
        .group_by(TrainingSession.user_id)
        .subquery()
    )

    # Sub-query: PvP rating (training_duel only for composite)
    pvp_sq = (
        sa_select(
            PvPProfile.user_id,
            PvPProfile.rating,
        )
        .where(PvPProfile.rating_type == "training_duel")
        .subquery()
    )

    # Sub-query: knowledge quiz accuracy
    try:
        from app.models.knowledge import UserAnswerHistory
        knowledge_sq = (
            sa_select(
                UserAnswerHistory.user_id,
                (sa_func.sum(case((UserAnswerHistory.is_correct == True, 1), else_=0)) * 100.0 /  # noqa: E712
                 sa_func.count(UserAnswerHistory.id)).label("accuracy"),
            )
            .group_by(UserAnswerHistory.user_id)
            .subquery()
        )
        has_knowledge = True
    except Exception:
        has_knowledge = False

    # Build composite query
    query = (
        sa_select(
            UserModel.id,
            UserModel.full_name,
            UserModel.avatar_url,
            sa_func.coalesce(training_sq.c.avg_score, literal(0)).label("training_avg"),
            sa_func.coalesce(pvp_sq.c.rating, literal(1500)).label("pvp_rating"),
        )
        .outerjoin(training_sq, training_sq.c.user_id == UserModel.id)
        .outerjoin(pvp_sq, pvp_sq.c.user_id == UserModel.id)
    )

    if has_knowledge:
        query = query.add_columns(
            sa_func.coalesce(knowledge_sq.c.accuracy, literal(0)).label("knowledge_acc"),
        ).outerjoin(knowledge_sq, knowledge_sq.c.user_id == UserModel.id)

    # Only users with at least some activity
    query = query.where(
        (training_sq.c.avg_score.isnot(None)) | (pvp_sq.c.rating.isnot(None))
    )

    result = await db.execute(query)
    rows = result.all()

    # Normalize and calculate composite scores
    max_rating = max((r.pvp_rating for r in rows), default=2000) or 2000
    min_rating = min((r.pvp_rating for r in rows), default=1200) or 1200
    rating_range = max(max_rating - min_rating, 1)

    entries = []
    for r in rows:
        training_norm = min(100, float(r.training_avg or 0))
        pvp_norm = ((float(r.pvp_rating or 1500) - min_rating) / rating_range) * 100
        knowledge_norm = float(getattr(r, "knowledge_acc", 0) or 0) if has_knowledge else 0.0
        streak_norm = 0.0  # Will be filled from streak calculation

        try:
            streak = await calculate_streak(r.id, db)
            streak_norm = min(100, streak * 10)  # 10 days streak = 100%
        except Exception:
            pass

        composite = (
            0.40 * training_norm +
            0.30 * pvp_norm +
            0.20 * knowledge_norm +
            0.10 * streak_norm
        )

        entries.append(CompositeLeaderboardEntry(
            rank=0,
            user_id=str(r.id),
            full_name=r.full_name or "—",
            avatar_url=r.avatar_url,
            composite_score=round(composite, 1),
            training_avg=round(training_norm, 1),
            pvp_rating_norm=round(pvp_norm, 1),
            knowledge_score=round(knowledge_norm, 1),
            streak_bonus=round(streak_norm, 1),
        ))

    entries.sort(key=lambda e: e.composite_score, reverse=True)
    for i, e in enumerate(entries[:limit]):
        e.rank = i + 1

    return entries[:limit]


@router.get("/leaderboard/teams")
async def team_leaderboard(
    period: str = Query("week", pattern="^(week|month|all)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Team leaderboard: ranked by average score. Visible to ROP+."""
    return await get_team_leaderboard(db, period=period)


# ── Skill Mastery ────────────────────────────────────────────────────────────


# ── OCEAN Profile (3.5) ────────────────────────────────────────────────────


@router.get("/me/ocean-profile")
@limiter.limit("20/minute")
async def get_ocean_profile_endpoint(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get manager's OCEAN Big Five profile with archetype recommendations."""
    from app.services.manager_emotion_profiler import get_ocean_profile

    return await get_ocean_profile(user.id, db)


@router.get("/me/skill-mastery")
async def get_skill_mastery_endpoint(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get skill mastery levels for current user."""
    from app.models.progress import ManagerProgress
    from app.services.manager_progress import get_all_skill_masteries
    from sqlalchemy import select

    result = await db.execute(
        select(ManagerProgress).where(ManagerProgress.user_id == user.id)
    )
    progress = result.scalar_one_or_none()

    if not progress:
        return {"skills": {}, "message": "No training data yet"}

    skills = {
        "empathy": float(progress.empathy or 0),
        "knowledge": float(progress.knowledge or 0),
        "objection_handling": float(progress.objection_handling or 0),
        "stress_resistance": float(progress.stress_resistance or 0),
        "closing": float(progress.closing or 0),
        "qualification": float(progress.qualification or 0),
    }

    masteries = get_all_skill_masteries(skills)

    return {
        "skills": {
            name: {
                "score": round(skills[name], 1),
                **mastery,
            }
            for name, mastery in masteries.items()
        }
    }


# ── Team Challenges ──────────────────────────────────────────────────────────


class CreateChallengeRequest(BaseModel):
    team_b_id: str
    scenario_code: str | None = None
    deadline_days: int = 5
    bonus_xp: int = 100


@router.post("/challenges")
@limiter.limit("10/minute")
async def create_team_challenge(
    body: CreateChallengeRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a team challenge (ROP only)."""
    if user.role.value not in ("rop", "admin", "methodologist"):
        raise HTTPException(403, "Only ROP/Admin can create team challenges")

    if not user.team_id:
        raise HTTPException(400, "You must be part of a team")

    from app.services.team_challenge import create_challenge

    info = await create_challenge(
        creator_id=user.id,
        team_a_id=user.team_id,
        team_b_id=uuid.UUID(body.team_b_id),
        db=db,
        scenario_code=body.scenario_code,
        deadline_days=body.deadline_days,
        bonus_xp=body.bonus_xp,
    )

    return {
        "id": info.id,
        "team_a": info.team_a_name,
        "team_b": info.team_b_name,
        "deadline": info.deadline.isoformat(),
        "status": info.status,
        "bonus_xp": info.bonus_xp,
    }


@router.get("/challenges/{challenge_id}")
async def get_challenge(
    challenge_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get challenge progress."""
    from app.services.team_challenge import get_challenge_progress

    result = await get_challenge_progress(challenge_id, db)
    if not result:
        raise HTTPException(404, "Challenge not found")

    return {
        "id": result.challenge_id,
        "status": result.status.value,
        "team_a": {"id": result.team_a_id, "name": result.team_a_name, "avg_score": result.team_a_avg, "completed": result.team_a_completed},
        "team_b": {"id": result.team_b_id, "name": result.team_b_name, "avg_score": result.team_b_avg, "completed": result.team_b_completed},
        "winner": {"id": result.winner_team_id, "name": result.winner_team_name} if result.winner_team_id else None,
        "bonus_xp": result.bonus_xp,
    }


@router.get("/challenges")
async def list_challenges(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List active challenges for user's team."""
    if not user.team_id:
        return []

    from app.services.team_challenge import get_active_challenges
    return await get_active_challenges(user.team_id)


@router.delete("/challenges/{challenge_id}")
@limiter.limit("10/minute")
async def cancel_team_challenge(
    challenge_id: str,
    request: Request,
    user: User = Depends(get_current_user),
):
    """Cancel a challenge (creator only)."""
    from app.services.team_challenge import cancel_challenge

    success = await cancel_challenge(challenge_id, user.id)
    if not success:
        raise HTTPException(404, "Challenge not found or you are not the creator")
    return {"status": "cancelled"}


# ─── Checkpoint Endpoints (DOC_04 §28) ──────────────────────────────────────

@router.get("/checkpoints")
async def get_checkpoints(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all checkpoints for user's current level with progress."""
    from app.models.progress import ManagerProgress
    from app.services.checkpoint_validator import CheckpointValidator

    profile = await db.execute(
        select(ManagerProgress).where(ManagerProgress.user_id == user.id)
    )
    mp = profile.scalar_one_or_none()
    level = mp.current_level if mp else 1

    validator = CheckpointValidator(db)
    statuses = await validator.check_all_for_level(user.id, level)

    return [
        {
            "code": s.code,
            "name": s.name,
            "description": s.description,
            "is_required": s.is_required,
            "is_completed": s.is_completed,
            "progress": s.progress,
            "xp_reward": s.xp_reward,
            "category": s.category,
        }
        for s in statuses
    ]


@router.get("/checkpoints/progress")
async def get_checkpoints_progress(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get checkpoint progress summary."""
    from app.models.progress import ManagerProgress
    from app.services.checkpoint_validator import CheckpointValidator

    profile = await db.execute(
        select(ManagerProgress).where(ManagerProgress.user_id == user.id)
    )
    mp = profile.scalar_one_or_none()
    level = mp.current_level if mp else 1

    validator = CheckpointValidator(db)
    statuses = await validator.check_all_for_level(user.id, level)

    required = [s for s in statuses if s.is_required]
    bonus = [s for s in statuses if not s.is_required]

    return {
        "level": level,
        "required_total": len(required),
        "required_completed": sum(1 for s in required if s.is_completed),
        "bonus_total": len(bonus),
        "bonus_completed": sum(1 for s in bonus if s.is_completed),
        "total_xp_available": sum(s.xp_reward for s in statuses),
        "total_xp_earned": sum(s.xp_reward for s in statuses if s.is_completed),
    }


@router.get("/can-level-up")
async def can_level_up(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check if user can advance to next level (XP + checkpoints)."""
    from app.models.progress import ManagerProgress
    from app.services.checkpoint_validator import CheckpointValidator

    profile = await db.execute(
        select(ManagerProgress).where(ManagerProgress.user_id == user.id)
    )
    mp = profile.scalar_one_or_none()
    level = mp.current_level if mp else 1

    validator = CheckpointValidator(db)
    result = await validator.can_level_up(user.id, level)

    return {
        "xp_met": result.xp_sufficient,
        "checkpoints_met": result.checkpoints_met,
        "missing": result.missing_checkpoints,
        "message": result.message,
    }


@router.post("/checkpoints/{code}/hint")
async def get_checkpoint_hint(
    code: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a personalized hint for a stuck checkpoint."""
    from app.models.checkpoint import CheckpointDefinition
    from app.services.catch_up_manager import CatchUpManager

    cp_result = await db.execute(
        select(CheckpointDefinition).where(CheckpointDefinition.code == code)
    )
    cp_def = cp_result.scalar_one_or_none()
    if not cp_def:
        raise HTTPException(404, "Checkpoint not found")

    manager = CatchUpManager(db)
    hint = manager._generate_hint(cp_def)

    return {"code": code, "hint": hint}
