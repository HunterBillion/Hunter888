"""Gamification endpoints: XP, level, streak, achievements, leaderboard, goals, challenges."""

import uuid

from app.core.rate_limit import limiter
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User

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
    all_achievements: list[dict] = []


class LeaderboardEntry(BaseModel):
    rank: int
    user_id: str
    full_name: str
    avatar_url: str | None = None
    sessions_count: int
    total_score: float
    avg_score: float


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/me/progress")
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

    # Query ALL earned achievements for the user (join to get achievement details)
    from app.models.analytics import UserAchievement, Achievement
    all_earned_result = await db.execute(
        select(UserAchievement, Achievement)
        .join(Achievement, Achievement.id == UserAchievement.achievement_id)
        .where(UserAchievement.user_id == user.id)
        .order_by(UserAchievement.earned_at.desc())
    )
    all_earned = all_earned_result.all()
    all_achievements_list = [
        {
            "id": str(ua.achievement_id),
            "slug": ach.slug,
            "title": ach.title,
            "description": ach.description,
            "icon_url": ach.icon_url,
            "earned_at": ua.earned_at.isoformat() if ua.earned_at else None,
        }
        for ua, ach in all_earned
    ]

    # Story arc progress (Путь Охотника)
    story_data = None
    try:
        from app.services.story_progression import get_story_progress
        story_progress = await get_story_progress(user.id, db)
        story_data = story_progress.to_dict()
    except Exception:
        pass  # graceful degradation — story is non-blocking

    resp = ProgressResponse(
        total_xp=total_xp,
        level=level,
        xp_current_level=total_xp - xp_for_level(level),
        xp_next_level=xp_for_level(level + 1) - xp_for_level(level),
        streak_days=streak,
        achievements=new_achievements,
        all_achievements=all_achievements_list,
    )
    # Attach story data as extra field (not in Pydantic model, use .model_dump)
    result = resp.model_dump()
    if story_data:
        result["story"] = story_data
    return result


@router.get("/challenges")
async def personal_challenges(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Петля 7: Personal micro-events (trap revenge, rival update, chapter teaser, etc.)."""
    from app.services.personal_challenge import get_personal_challenges
    return {"challenges": await get_personal_challenges(user.id, db)}


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
    from datetime import datetime, timezone

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

    day_index = datetime.now(timezone.utc).date().timetuple().tm_yday % len(challenge_types)
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
        "date": str(datetime.now(timezone.utc).date()),
    }


# ── S3-02: Daily XP Cap Status ──────────────────────────────────────────────


@router.get("/xp-daily")
async def get_xp_daily_status(
    user: User = Depends(get_current_user),
):
    """Get daily XP cap status for the current user."""
    from app.services.xp_daily_cap import get_daily_xp_status
    return await get_daily_xp_status(user.id)


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
        # Backward-compatible flat array for frontend consumers expecting "goals"
        "goals": [
            {
                "id": g.goal_id,
                "title": g.label,
                "label": g.label,
                "description": g.description,
                "target": g.target,
                "progress": g.current,
                "current": g.current,
                "progress_pct": g.progress_pct,
                "xp": g.xp,
                "completed": g.completed,
                "icon": g.icon,
                "period": g.period,
            }
            for g in snapshot.daily + snapshot.weekly
        ],
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
    from app.models.training import TrainingSession, SessionStatus
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

    # Batch: pre-compute streaks for all users to avoid N+1 queries
    from collections import defaultdict
    from app.services.gamification import _count_consecutive_days

    user_ids = [r.id for r in rows]

    # Try GoalCompletionLog first (primary streak source)
    goal_date_map: dict = {}
    try:
        from app.models.progress import GoalCompletionLog
        goal_dates_r = await db.execute(
            sa_select(
                GoalCompletionLog.user_id,
                sa_func.date(GoalCompletionLog.completed_at).label("d"),
            )
            .where(GoalCompletionLog.user_id.in_(user_ids))
            .distinct()
            .order_by(GoalCompletionLog.user_id, sa_func.date(GoalCompletionLog.completed_at).desc())
        )
        goal_date_map_raw: dict[uuid.UUID, list] = defaultdict(list)
        for row in goal_dates_r:
            goal_date_map_raw[row.user_id].append(row.d)
        goal_date_map = {uid: _count_consecutive_days(dates) for uid, dates in goal_date_map_raw.items()}
    except Exception:
        pass  # Table may not exist yet

    # Fallback: completed training sessions for users without goal data
    fallback_ids = [uid for uid in user_ids if uid not in goal_date_map or goal_date_map[uid] == 0]
    session_streak_map: dict = {}
    if fallback_ids:
        session_dates_r = await db.execute(
            sa_select(
                TrainingSession.user_id,
                sa_func.date(TrainingSession.started_at).label("d"),
            )
            .where(
                TrainingSession.user_id.in_(fallback_ids),
                TrainingSession.status == SessionStatus.completed,
            )
            .distinct()
            .order_by(TrainingSession.user_id, sa_func.date(TrainingSession.started_at).desc())
        )
        session_date_map_raw: dict[uuid.UUID, list] = defaultdict(list)
        for row in session_dates_r:
            session_date_map_raw[row.user_id].append(row.d)
        session_streak_map = {uid: _count_consecutive_days(dates) for uid, dates in session_date_map_raw.items()}

    # Merge: goal streaks take priority, fallback to session streaks
    user_streaks = {uid: goal_date_map.get(uid, 0) or session_streak_map.get(uid, 0) for uid in user_ids}

    entries = []
    for r in rows:
        training_norm = min(100, float(r.training_avg or 0))
        pvp_norm = ((float(r.pvp_rating or 1500) - min_rating) / rating_range) * 100
        knowledge_norm = float(getattr(r, "knowledge_acc", 0) or 0) if has_knowledge else 0.0

        streak = user_streaks.get(r.id, 0)
        streak_norm = min(100, streak * 10)  # 10 days streak = 100%

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
        "empathy": float(progress.skill_empathy or 0),
        "knowledge": float(progress.skill_knowledge or 0),
        "objection_handling": float(progress.skill_objection_handling or 0),
        "stress_resistance": float(progress.skill_stress_resistance or 0),
        "closing": float(progress.skill_closing or 0),
        "qualification": float(progress.skill_qualification or 0),
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
    return await get_active_challenges(user.team_id, db)


@router.delete("/challenges/{challenge_id}")
@limiter.limit("10/minute")
async def cancel_team_challenge(
    challenge_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a challenge (creator only)."""
    from app.services.team_challenge import cancel_challenge

    success = await cancel_challenge(challenge_id, user.id, db)
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


# ═══════════════════════════════════════════════════════════════════════════
# Daily Drill — 3-minute micro-simulation habit loop
# ═══════════════════════════════════════════════════════════════════════════
# Hunter leaderboard — unified rating across all activities
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/leaderboard/hunters")
async def get_hunter_leaderboard_endpoint(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    scope: str = "company",
    limit: int = 50,
):
    """Unified Hunter Score leaderboard. Composite of training + PvP + knowledge + achievements + reputation."""
    from app.services.hunter_leaderboard import get_hunter_leaderboard
    from dataclasses import asdict

    if scope not in ("team", "company"):
        raise HTTPException(400, "scope must be 'team' or 'company'")
    if scope == "company" and user.role.value not in ("admin", "rop", "methodologist"):
        scope = "team"  # Managers see only team scope

    entries = await get_hunter_leaderboard(
        db, viewer=user, scope=scope, limit=min(100, max(1, limit)),
    )
    return [asdict(e) for e in entries]


@router.get("/leaderboard/weekly-tp")
async def get_weekly_tp_leaderboard_endpoint(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    scope: str = "company",
    limit: int = 50,
):
    """Current ISO-week Tournament Points ranking."""
    from app.services.hunter_leaderboard import get_weekly_tp_ranking

    if scope not in ("team", "company"):
        raise HTTPException(400, "scope must be 'team' or 'company'")
    if scope == "company" and user.role.value not in ("admin", "rop", "methodologist"):
        scope = "team"

    return await get_weekly_tp_ranking(
        db, viewer=user, scope=scope, limit=min(100, max(1, limit)),
    )


@router.get("/leaderboard/my-breakdown")
async def get_my_tp_breakdown_endpoint(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """My TP earned this ISO week, split by source."""
    from app.services.hunter_leaderboard import get_my_tp_breakdown
    return await get_my_tp_breakdown(db, user.id)


# ═══════════════════════════════════════════════════════════════════════════


@router.get("/daily-drill")
async def get_daily_drill(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get today's daily drill configuration (skill focus, archetype, etc.)."""
    from app.services.daily_drill import get_drill_config

    config = await get_drill_config(user.id, db)
    return {
        "drill_id": config.drill_id,
        "skill_focus": config.skill_focus,
        "skill_name": config.skill_name_ru,
        "archetype": config.archetype,
        "title": config.title,
        "focus": config.focus_description,
        "max_exchanges": config.max_exchanges,
        "already_completed_today": config.already_completed_today,
    }


@router.post("/daily-drill/reply")
async def daily_drill_reply(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Generate an AI-client reply + quality score for a drill exchange.

    Replaces the old hardcoded client replies. Uses LLM to actually react
    to what the trainee said, and a simple heuristic+LLM score to judge quality.

    Body: {
      archetype: str,        // from GET /daily-drill
      skill_focus: str,      // what we're drilling
      history: list[{role, content}],  // full exchange so far
      user_message: str,     // latest manager line
    }
    Returns: {
      client_reply: str,
      quality: "good" | "neutral" | "bad",
      feedback: str  // one-sentence note for the trainee
    }
    """
    from app.services.llm import generate_response
    from app.services.content_filter import filter_ai_output

    body = await request.json()
    archetype = (body.get("archetype") or "skeptic").lower()
    skill_focus = body.get("skill_focus") or "sales_general"
    history = body.get("history") or []
    user_message = (body.get("user_message") or "").strip()

    if not user_message:
        raise HTTPException(400, "user_message is required")

    # H4 (Roadmap Phase 0 §5.1): был inline-дубликат с 9 архетипами из
    # 15, несовпадающими кодами ("lawyer"/"aggressor" vs "know_it_all"/
    # "aggressive" в between_call_narrator) и без gender-variants.
    # Переводим на общий каталог ``trait_for`` — один источник истины,
    # согласованная грамматика по гендеру клиента.
    from app.services.between_call_narrator import trait_for
    gender = (body.get("client_gender") or "unknown").lower()
    trait = trait_for(archetype, gender if gender in ("male", "female") else None)

    system_prompt = (
        f"Ты — КЛИЕНТ-ДОЛЖНИК в коротком тренировочном упражнении. Архетип: {archetype} ({trait}). "
        f"Менеджер звонит тебе чтобы предложить финансовую консультацию. "
        f"Это разминка на навык «{skill_focus}» — 3 коротких обмена репликами. "
        f"Правила: отвечай В РОЛИ клиента, максимум 1-2 предложения, разговорно. "
        f"НЕ представляйся именем менеджера, НЕ говори 'звоню по вашему запросу'. "
        f"Ты отвечаешь на звонок, скептичен, раздражён, задаёшь встречные вопросы."
    )

    messages = [
        {"role": m.get("role", "user"), "content": str(m.get("content", ""))[:500]}
        for m in history
        if m.get("content")
    ]
    messages.append({"role": "user", "content": user_message})

    try:
        llm_result = await generate_response(
            system_prompt=system_prompt,
            messages=messages,
            emotion_state="cold",
            task_type="roleplay",
            prefer_provider="auto",
        )
        reply_text, _ = filter_ai_output(llm_result.content)
    except Exception as e:
        logger.warning("Daily drill LLM failed: %s", e)
        reply_text = "А что конкретно вы хотите?"

    # Simple heuristic quality scoring
    quality, feedback = _judge_drill_reply(user_message, skill_focus)

    return {
        "client_reply": reply_text.strip() or "Хм, продолжайте.",
        "quality": quality,
        "feedback": feedback,
    }


def _judge_drill_reply(user_message: str, skill_focus: str) -> tuple[str, str]:
    """Heuristic + keyword judgment for drill reply quality.

    Not perfect — but far better than hardcoded score=75. Returns tuple
    (quality_tier, one_line_feedback).
    """
    msg = user_message.lower().strip()
    length = len(msg)

    if length < 5:
        return "bad", "Слишком коротко — клиент почувствует, что вы не настроены на диалог"
    if any(word in msg for word in ["хуй", "бля", "пизд", "сука", "ебан"]):
        return "bad", "Мат в разговоре с клиентом — мгновенный провал"
    if length > 400:
        return "neutral", "Слишком длинно — клиент не дослушает, режьте фразы короче"

    # Skill-specific heuristics
    good_signals = {
        "empathy": ["понимаю", "слышу", "сочувствую", "тяжело", "чувствую"],
        "objection_handling": ["правильно", "согласен", "давайте", "уточню", "проверим"],
        "legal_knowledge": ["127-фз", "446", "банкротст", "закон", "статья", "пристав"],
        "sales_general": ["предлож", "решен", "помочь", "рассчит", "вариант"],
    }
    signals = good_signals.get(skill_focus, good_signals["sales_general"])
    if any(sig in msg for sig in signals):
        return "good", "Сильная реплика — используется подходящая лексика навыка"

    if "?" in msg and length > 20:
        return "good", "Хороший открытый вопрос"
    if length < 20:
        return "neutral", "Можно развернуть — короткая реплика слабее"

    return "neutral", "Нормально, но без явных сигналов навыка"


@router.post("/daily-drill/complete")
async def complete_daily_drill(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Complete today's daily drill and receive XP + streak update.

    Score is now computed from aggregate quality of replies (sent by client),
    not blindly accepted. Frontend should pass `qualities` array with
    "good" | "neutral" | "bad" per exchange.
    """
    from app.services.daily_drill import complete_drill

    body = await request.json()
    qualities = body.get("qualities") or []
    if qualities and isinstance(qualities, list):
        # Compute score from qualities: good=90, neutral=55, bad=15
        weights = {"good": 90, "neutral": 55, "bad": 15}
        scores = [weights.get(q, 50) for q in qualities]
        score = sum(scores) / max(1, len(scores))
    else:
        # Backwards-compat: trust provided score but cap at 75 if we can't verify
        score = min(float(body.get("score", 50)), 75)

    result = await complete_drill(user.id, score, db)
    await db.commit()

    return {
        "xp_earned": result.xp_earned,
        "streak_bonus": result.streak_bonus,
        "drill_streak": result.new_drill_streak,
        "best_drill_streak": result.best_drill_streak,
        "total_drills": result.total_drills,
        "chest_type": result.chest_type,
        "final_score": round(score, 1),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Streak Freeze — streak protection purchase
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/streak-freeze")
async def get_streak_freeze_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current streak freeze inventory and purchase eligibility."""
    from app.services.streak_freeze import get_freeze_status
    return await get_freeze_status(user.id, db)


@router.post("/streak-freeze/purchase")
async def purchase_freeze(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Purchase a streak freeze for AP (25 AP, max 2/month)."""
    from app.services.streak_freeze import purchase_streak_freeze

    result = await purchase_streak_freeze(user.id, db)
    if result["success"]:
        await db.commit()
    return result


# ═══════════════════════════════════════════════════════════════════════════
# Weekly League — social pressure engine
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/league/me")
async def get_my_league(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's weekly league: position, tier, standings."""
    from app.services.weekly_league import get_my_league as _get_my_league

    snapshot = await _get_my_league(user.id, db)
    if not snapshot:
        return {"tier": 0, "tier_name": "Стажёр", "group_size": 0, "rank": 0, "standings": []}

    return {
        "tier": snapshot.tier,
        "tier_name": snapshot.tier_name,
        "group_size": snapshot.group_size,
        "rank": snapshot.rank,
        "weekly_xp": snapshot.weekly_xp,
        "standings": snapshot.standings,
        "week_start": snapshot.week_start,
        "promotion_zone": snapshot.promotion_zone,
        "demotion_zone": snapshot.demotion_zone,
        "days_remaining": snapshot.days_remaining,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Content Season — narrative structure
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/season/active")
async def get_active_season(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the currently active content season with chapters."""
    from app.services.content_season import get_active_season as _get

    season = await _get(db)
    if not season:
        return {"active": False}
    return {"active": True, **season}


# ═══════════════════════════════════════════════════════════════════════════
# Chest Rewards — variable reward system
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/chest/open")
async def open_chest(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Open a chest and receive random rewards."""
    from app.services.chest_rewards import open_chest as _open

    body = await request.json()
    chest_type = body.get("chest_type", "bronze")

    if chest_type not in ("bronze", "silver", "gold"):
        raise HTTPException(400, "Invalid chest type")

    reward = await _open(user.id, chest_type, db)
    await db.commit()

    return {
        "chest_type": reward.chest_type,
        "xp_reward": reward.xp_reward,
        "ap_reward": reward.ap_reward,
        "item_reward": reward.item_reward,
        "item_name": reward.item_name,
        "is_rare_drop": reward.is_rare_drop,
    }


# ═══════════════════════════════════════════════════════════════════════════
# XP Events — Happy Hours and multiplier events
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/xp-event/active")
async def get_active_xp_event(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check if there's an active XP multiplier event."""
    from app.services.xp_events import get_active_event

    event = await get_active_event(db)
    if not event:
        return {"active": False, "multiplier": 1.0}

    return {
        "active": True,
        "name": event.name,
        "multiplier": event.multiplier,
        "ends_at": event.ends_at,
        "minutes_remaining": event.minutes_remaining,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Deal Portfolio — completed deals archive
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/portfolio")
async def get_deal_portfolio(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=0, le=100),
    offset: int = Query(0, ge=0),
):
    """Get user's deal portfolio — all completed training sessions with deal outcome."""
    from app.models.progress import SessionHistory
    from sqlalchemy import select

    result = await db.execute(
        select(SessionHistory)
        .where(
            SessionHistory.user_id == user.id,
            SessionHistory.outcome == "deal",
        )
        .order_by(SessionHistory.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    deals = result.scalars().all()

    # Total count
    from sqlalchemy import func as sqf
    count_result = await db.execute(
        select(sqf.count(SessionHistory.id)).where(
            SessionHistory.user_id == user.id,
            SessionHistory.outcome == "deal",
        )
    )
    total = count_result.scalar() or 0

    return {
        "total_deals": total,
        "deals": [
            {
                "id": str(d.id),
                "archetype": d.archetype_code,
                "scenario": d.scenario_code,
                "score": d.score_total,
                "difficulty": d.difficulty,
                "duration_seconds": d.duration_seconds,
                "xp_earned": d.xp_earned or 0,
                "had_comeback": d.had_comeback or False,
                "chain_completed": d.chain_completed or False,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in deals
        ],
    }
