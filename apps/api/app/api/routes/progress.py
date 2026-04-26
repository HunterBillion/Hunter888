"""
ТЗ-06: API endpoints для прогрессии менеджера.

Endpoints:
  GET  /api/progress/{user_id}                 — текущий прогресс
  GET  /api/progress/{user_id}/skills          — навыки (радар)
  GET  /api/progress/{user_id}/history         — история сессий
  GET  /api/progress/{user_id}/achievements    — достижения
  GET  /api/progress/{user_id}/recommendations — рекомендации
  GET  /api/progress/{user_id}/weak-points     — слабые места
  GET  /api/progress/{user_id}/weekly-report   — еженедельный отчёт
  GET  /api/leaderboard                        — лидерборд
  POST /api/progress/{user_id}/session-complete — обработка завершённой сессии
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.rate_limit import limiter
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_, cast, Numeric
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.progress import (
    ManagerProgress,
    SessionHistory,
    EarnedAchievement as Achievement,
    WeeklyReport,
    SKILL_NAMES,
)
from app.services.manager_progress import (
    ManagerProgressService,
    SessionParams,
    XPBreakdown,
)
from scripts.seed_levels import get_level_name, LEVEL_XP_THRESHOLDS

from app.database import get_db
from app.models.user import User
from app.core.deps import get_current_user


router = APIRouter(tags=["progress"])


def _check_ownership(user_id: uuid.UUID, user: User) -> None:
    """Raise 403 if the authenticated user does not own the resource and is not privileged."""
    if str(user_id) != str(user.id) and user.role.value not in ("admin", "rop"):
        raise HTTPException(status_code=403, detail="Access denied: you can only access your own data")


# ──────────────────────────────────────────────────────────────────────
#  Pydantic schemas
# ──────────────────────────────────────────────────────────────────────

class SkillsResponse(BaseModel):
    empathy: int
    knowledge: int
    objection_handling: int
    stress_resistance: int
    closing: int
    qualification: int


class ProgressResponse(BaseModel):
    user_id: str
    current_level: int
    level_name: str
    current_xp: int
    total_xp: int
    xp_to_next_level: int
    level_progress_pct: float
    total_sessions: int
    total_hours: float
    skills: SkillsResponse
    unlocked_archetypes: list[str]
    unlocked_scenarios: list[str]
    weak_points: list[str]
    focus_recommendation: str | None
    current_deal_streak: int
    best_deal_streak: int
    calibration_complete: bool
    skill_confidence: str


class SessionHistoryItem(BaseModel):
    id: str
    session_id: str
    scenario_code: str
    archetype_code: str
    difficulty: int
    duration_seconds: int
    score_total: int
    outcome: str
    emotion_peak: str
    traps_fell: int
    traps_dodged: int
    chain_completed: bool
    xp_earned: int
    created_at: str


class AchievementItem(BaseModel):
    code: str
    name: str
    description: str
    rarity: str
    xp_bonus: int
    category: str
    unlocked_at: str


class RecommendationResponse(BaseModel):
    difficulty: int
    scenario: str
    archetype: str
    focus_skill: str
    confidence: str
    weak_points: list[str] | None
    tips: list[str] | None


class WeakPointItem(BaseModel):
    skill: str
    value: int
    gap: float
    priority: str


class LeaderboardEntry(BaseModel):
    rank: int
    user_id: str
    display_name: str
    avatar_url: str | None = None
    level: int
    level_name: str
    score: float
    sessions_count: int
    win_rate: float
    best_score: int


class SessionCompleteRequest(BaseModel):
    session_id: str
    scenario_code: str
    archetype_code: str
    difficulty: int = Field(ge=1, le=10)
    duration_seconds: int = Field(gt=0)
    score_total: int = Field(ge=0, le=100)
    outcome: str
    score_breakdown: dict = Field(default_factory=dict)
    emotion_peak: str
    traps_fell: int = Field(ge=0, default=0)
    traps_dodged: int = Field(ge=0, default=0)
    chain_completed: bool = False
    # Adaptive data (от IntraSessionAdapter.finalize_session)
    adaptive_data: dict | None = None


class SessionCompleteResponse(BaseModel):
    xp_breakdown: dict
    level_up: bool
    new_level: int | None
    new_level_name: str | None
    new_achievements: list[dict]
    skills_update: dict | None


# ──────────────────────────────────────────────────────────────────────
#  GET /api/progress/{user_id}
# ──────────────────────────────────────────────────────────────────────

@router.get("/progress/{user_id}", response_model=ProgressResponse)
async def get_progress(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProgressResponse:
    """Текущий прогресс менеджера: уровень, XP, навыки, разблокировки."""
    _check_ownership(user_id, user)
    svc = ManagerProgressService(db)
    profile = await svc.get_or_create_profile(user_id)

    # Вычислить XP до следующего уровня
    current_threshold = LEVEL_XP_THRESHOLDS.get(profile.current_level, 0)
    next_level = min(20, profile.current_level + 1)
    next_threshold = LEVEL_XP_THRESHOLDS.get(next_level, current_threshold)
    xp_range = next_threshold - current_threshold
    xp_in_level = profile.total_xp - current_threshold
    pct = (xp_in_level / xp_range * 100) if xp_range > 0 else 100.0

    skills = profile.skills_dict()

    return ProgressResponse(
        user_id=str(profile.user_id),
        current_level=profile.current_level,
        level_name=get_level_name(profile.current_level),
        current_xp=profile.current_xp,
        total_xp=profile.total_xp,
        xp_to_next_level=max(0, next_threshold - profile.total_xp),
        level_progress_pct=round(min(100.0, pct), 1),
        total_sessions=profile.total_sessions,
        total_hours=float(profile.total_hours),
        skills=SkillsResponse(**skills),
        unlocked_archetypes=profile.unlocked_archetypes or [],
        unlocked_scenarios=profile.unlocked_scenarios or [],
        weak_points=profile.weak_points or [],
        focus_recommendation=profile.focus_recommendation,
        current_deal_streak=profile.current_deal_streak,
        best_deal_streak=profile.best_deal_streak,
        calibration_complete=profile.calibration_complete,
        skill_confidence=profile.skill_confidence,
    )


# ──────────────────────────────────────────────────────────────────────
#  GET /api/progress/{user_id}/skills
# ──────────────────────────────────────────────────────────────────────

@router.get("/progress/{user_id}/skills", response_model=SkillsResponse)
async def get_skills(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SkillsResponse:
    """6 навыков менеджера для визуализации радара."""
    _check_ownership(user_id, user)
    svc = ManagerProgressService(db)
    skills = await svc.calculate_skills(user_id)
    return SkillsResponse(**skills)


# ──────────────────────────────────────────────────────────────────────
#  GET /api/progress/{user_id}/history
# ──────────────────────────────────────────────────────────────────────

@router.get("/progress/{user_id}/history", response_model=list[SessionHistoryItem])
async def get_history(
    user_id: uuid.UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SessionHistoryItem]:
    """История тренировочных сессий."""
    _check_ownership(user_id, user)
    svc = ManagerProgressService(db)
    sessions = await svc.get_session_history(user_id, offset=offset, limit=limit)
    return [
        SessionHistoryItem(
            id=str(s.id),
            session_id=str(s.session_id),
            scenario_code=s.scenario_code,
            archetype_code=s.archetype_code,
            difficulty=s.difficulty,
            duration_seconds=s.duration_seconds,
            score_total=s.score_total,
            outcome=s.outcome,
            emotion_peak=s.emotion_peak,
            traps_fell=s.traps_fell,
            traps_dodged=s.traps_dodged,
            chain_completed=s.chain_completed,
            xp_earned=s.xp_earned,
            created_at=s.created_at.isoformat(),
        )
        for s in sessions
    ]


# ──────────────────────────────────────────────────────────────────────
#  GET /api/progress/{user_id}/achievements
# ──────────────────────────────────────────────────────────────────────

@router.get("/progress/{user_id}/achievements", response_model=list[AchievementItem])
async def get_achievements(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AchievementItem]:
    """Все достижения менеджера."""
    _check_ownership(user_id, user)
    result = await db.execute(
        select(Achievement)
        .where(Achievement.user_id == user_id)
        .order_by(Achievement.unlocked_at.desc()),
    )
    achievements = result.scalars().all()
    return [
        AchievementItem(
            code=a.achievement_code,
            name=a.achievement_name,
            description=a.achievement_description,
            rarity=a.rarity,
            xp_bonus=a.xp_bonus,
            category=a.category,
            unlocked_at=a.unlocked_at.isoformat(),
        )
        for a in achievements
    ]


# ──────────────────────────────────────────────────────────────────────
#  GET /api/progress/{user_id}/recommendations
# ──────────────────────────────────────────────────────────────────────

@router.get("/progress/{user_id}/recommendations", response_model=RecommendationResponse)
async def get_recommendations(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RecommendationResponse:
    """Рекомендации для следующей тренировочной сессии."""
    _check_ownership(user_id, user)
    svc = ManagerProgressService(db)
    params = await svc.recommend_next_session(user_id)
    return RecommendationResponse(
        difficulty=params.difficulty,
        scenario=params.scenario,
        archetype=params.archetype,
        focus_skill=params.focus_skill,
        confidence=params.confidence,
        weak_points=params.weak_points,
        tips=params.tips,
    )


# ──────────────────────────────────────────────────────────────────────
#  GET /api/progress/{user_id}/weak-points
# ──────────────────────────────────────────────────────────────────────

@router.get("/progress/{user_id}/weak-points", response_model=list[WeakPointItem])
async def get_weak_points(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[WeakPointItem]:
    """Слабые места менеджера с приоритетами."""
    _check_ownership(user_id, user)
    svc = ManagerProgressService(db)
    points = await svc.get_weak_points(user_id)
    return [WeakPointItem(**p) for p in points]


# ──────────────────────────────────────────────────────────────────────
#  GET /api/leaderboard
# ──────────────────────────────────────────────────────────────────────

@router.get("/leaderboard", response_model=list[LeaderboardEntry])
async def get_leaderboard(
    period: str = Query("weekly", pattern="^(daily|weekly|monthly|all_time)$"),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[LeaderboardEntry]:
    """Лидерборд за указанный период."""
    now = datetime.now(timezone.utc)

    if period == "daily":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "weekly":
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "monthly":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:  # all_time
        start = datetime(2020, 1, 1, tzinfo=timezone.utc)

    # Агрегация по session_history
    query = (
        select(
            SessionHistory.user_id,
            func.count().label("sessions_count"),
            func.round(cast(func.avg(SessionHistory.score_total), Numeric), 1).label("avg_score"),
            func.max(SessionHistory.score_total).label("best_score"),
            func.sum(SessionHistory.xp_earned).label("total_xp"),
            func.round(
                cast(
                    100.0
                    * func.count().filter(SessionHistory.outcome == "deal")
                    / func.nullif(func.count(), 0),
                    Numeric,
                ),
                1,
            ).label("win_rate"),
        )
        .where(SessionHistory.created_at >= start)
        .group_by(SessionHistory.user_id)
    )

    result = await db.execute(query)
    rows = result.all()

    # Для каждого пользователя — получить level
    entries: list[LeaderboardEntry] = []
    for i, row in enumerate(
        sorted(rows, key=lambda r: float(r.total_xp or 0), reverse=True)[:limit]
    ):
        # Получить профиль
        profile_result = await db.execute(
            select(ManagerProgress).where(ManagerProgress.user_id == row.user_id),
        )
        profile = profile_result.scalar_one_or_none()

        # Получить пользователя (имя + аватар)
        user_result = await db.execute(
            select(User).where(User.id == row.user_id),
        )
        user_obj = user_result.scalar_one_or_none()

        level = profile.current_level if profile else 1
        # Composite score (как в ТЗ)
        avg_sc = float(row.avg_score or 0)
        wr = float(row.win_rate or 0)
        sc_count = min(20, int(row.sessions_count or 0))
        composite = avg_sc * 0.35 + wr * 0.25 + (sc_count / 20) * 100 * 0.20

        display = (
            user_obj.full_name
            if user_obj and user_obj.full_name
            else f"Менеджер #{str(row.user_id)[:4]}"
        )

        entries.append(LeaderboardEntry(
            rank=i + 1,
            user_id=str(row.user_id),
            display_name=display,
            avatar_url=user_obj.avatar_url if user_obj else None,
            level=level,
            level_name=get_level_name(level),
            score=round(composite, 1),
            sessions_count=int(row.sessions_count or 0),
            win_rate=float(row.win_rate or 0),
            best_score=int(row.best_score or 0),
        ))

    # Пересортировать по composite score
    entries.sort(key=lambda e: e.score, reverse=True)
    for i, e in enumerate(entries):
        e.rank = i + 1

    return entries


# ──────────────────────────────────────────────────────────────────────
#  GET /api/progress/{user_id}/weekly-report
# ──────────────────────────────────────────────────────────────────────

@router.get("/progress/{user_id}/weekly-report")
async def get_weekly_report(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Еженедельный отчёт (текущая неделя)."""
    _check_ownership(user_id, user)
    now = datetime.now(timezone.utc)
    week_start = now - timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

    # Получить сессии за неделю
    result = await db.execute(
        select(SessionHistory)
        .where(
            and_(
                SessionHistory.user_id == user_id,
                SessionHistory.created_at >= week_start,
            ),
        )
        .order_by(SessionHistory.created_at),
    )
    sessions = list(result.scalars().all())

    if not sessions:
        return {"message": "Нет сессий за текущую неделю", "sessions_completed": 0}

    # Агрегация
    scores = [s.score_total for s in sessions]
    outcomes = {}
    for s in sessions:
        outcomes[s.outcome] = outcomes.get(s.outcome, 0) + 1

    deals = outcomes.get("deal", 0)
    total = len(sessions)

    # Профиль
    svc = ManagerProgressService(db)
    profile = await svc.get_or_create_profile(user_id)

    # Достижения за неделю
    ach_result = await db.execute(
        select(Achievement)
        .where(
            and_(
                Achievement.user_id == user_id,
                Achievement.unlocked_at >= week_start,
            ),
        ),
    )
    week_achievements = ach_result.scalars().all()

    return {
        "week_start": week_start.isoformat(),
        "week_end": (week_start + timedelta(days=6)).isoformat(),
        "sessions_completed": total,
        "total_time_minutes": sum(s.duration_seconds for s in sessions) // 60,
        "average_score": round(sum(scores) / len(scores), 1),
        "best_score": max(scores),
        "worst_score": min(scores),
        "outcomes": outcomes,
        "win_rate": round(100 * deals / total, 1) if total > 0 else 0,
        "xp_earned": sum(s.xp_earned for s in sessions),
        "current_level": profile.current_level,
        "level_name": get_level_name(profile.current_level),
        "skills": profile.skills_dict(),
        "weak_points": profile.weak_points or [],
        "new_achievements": [
            {"code": a.achievement_code, "name": a.achievement_name, "xp": a.xp_bonus}
            for a in week_achievements
        ],
    }


# ──────────────────────────────────────────────────────────────────────
#  POST /api/progress/{user_id}/session-complete
# ──────────────────────────────────────────────────────────────────────

@router.post("/progress/{user_id}/session-complete", response_model=SessionCompleteResponse)
@limiter.limit("10/minute")
async def session_complete(
    request: Request,
    user_id: uuid.UUID,
    body: SessionCompleteRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionCompleteResponse:
    """Обработка завершённой тренировочной сессии: XP, навыки, уровень, достижения."""
    _check_ownership(user_id, user)
    # Создать запись SessionHistory
    session_record = SessionHistory(
        user_id=user_id,
        session_id=uuid.UUID(body.session_id),
        scenario_code=body.scenario_code,
        archetype_code=body.archetype_code,
        difficulty=body.difficulty,
        duration_seconds=body.duration_seconds,
        score_total=body.score_total,
        outcome=body.outcome,
        score_breakdown=body.score_breakdown,
        emotion_peak=body.emotion_peak,
        traps_fell=body.traps_fell,
        traps_dodged=body.traps_dodged,
        chain_completed=body.chain_completed,
    )

    # Применить adaptive data
    if body.adaptive_data:
        session_record.max_good_streak = body.adaptive_data.get("max_good_streak", 0)
        session_record.max_bad_streak = body.adaptive_data.get("max_bad_streak", 0)
        session_record.final_difficulty_modifier = body.adaptive_data.get("final_difficulty_modifier", 0)
        session_record.had_comeback = body.adaptive_data.get("had_comeback", False)
        session_record.mercy_activated = body.adaptive_data.get("mercy_activated", False)

    db.add(session_record)
    await db.flush()

    # Обработать через ManagerProgressService
    svc = ManagerProgressService(db)
    result = await svc.update_after_session(user_id, session_record, body.adaptive_data)

    # Записать xp в session_record
    session_record.xp_earned = result["xp_breakdown"]["grand_total"]
    session_record.xp_breakdown = result["xp_breakdown"]

    await db.commit()

    return SessionCompleteResponse(**result)


# ──────────────────────────────────────────────────────────────────────
#  Weekly Reports — persist & list
# ──────────────────────────────────────────────────────────────────────


class WeeklyReportResponse(BaseModel):
    id: str
    user_id: str
    week_start: str
    week_end: str
    sessions_completed: int
    total_time_minutes: int
    average_score: float | None
    best_score: int | None
    worst_score: int | None
    score_trend: str | None
    outcomes: dict
    win_rate: float | None
    skills_snapshot: dict
    skills_change: dict
    xp_earned: int
    level_at_start: int
    level_at_end: int
    new_achievements: list
    weak_points: list
    recommendations: list
    weekly_rank: int | None
    rank_change: int | None
    report_text: str | None
    created_at: str


def _report_to_response(r: WeeklyReport) -> WeeklyReportResponse:
    return WeeklyReportResponse(
        id=str(r.id),
        user_id=str(r.user_id),
        week_start=r.week_start.isoformat(),
        week_end=r.week_end.isoformat(),
        sessions_completed=r.sessions_completed,
        total_time_minutes=r.total_time_minutes,
        average_score=float(r.average_score) if r.average_score else None,
        best_score=r.best_score,
        worst_score=r.worst_score,
        score_trend=r.score_trend,
        outcomes=r.outcomes or {},
        win_rate=float(r.win_rate) if r.win_rate else None,
        skills_snapshot=r.skills_snapshot or {},
        skills_change=r.skills_change or {},
        xp_earned=r.xp_earned,
        level_at_start=r.level_at_start,
        level_at_end=r.level_at_end,
        new_achievements=r.new_achievements or [],
        weak_points=r.weak_points or [],
        recommendations=r.recommendations or [],
        weekly_rank=r.weekly_rank,
        rank_change=r.rank_change,
        report_text=r.report_text,
        created_at=r.created_at.isoformat() if r.created_at else "",
    )


@router.get(
    "/reports/weekly/{user_id}",
    response_model=list[WeeklyReportResponse],
)
async def list_weekly_reports(
    user_id: uuid.UUID,
    limit: int = Query(12, ge=1, le=52),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[WeeklyReportResponse]:
    """Список сохранённых еженедельных отчётов (последние N недель)."""
    _check_ownership(user_id, user)
    result = await db.execute(
        select(WeeklyReport)
        .where(WeeklyReport.user_id == user_id)
        .order_by(WeeklyReport.week_start.desc())
        .limit(limit)
    )
    reports = list(result.scalars().all())
    return [_report_to_response(r) for r in reports]


@router.post(
    "/reports/weekly/{user_id}/generate",
    response_model=WeeklyReportResponse,
)
@limiter.limit("10/minute")
async def generate_report_endpoint(
    request: Request,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WeeklyReportResponse:
    """Генерирует (или обновляет) отчёт за текущую неделю."""
    _check_ownership(user_id, user)
    from app.services.weekly_report import generate_weekly_report

    report = await generate_weekly_report(db, user_id)
    await db.commit()
    return _report_to_response(report)
