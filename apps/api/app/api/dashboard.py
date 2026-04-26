"""Batch dashboard API: one request per role, Redis-cached.

GET /api/dashboard/manager — stats + progress + assignments + recommendations + gamification
GET /api/dashboard/rop — team stats + all members + leaderboard + tournament
GET /api/dashboard/knowledge-stats — Arena knowledge stats (Block 5 cross-module)
GET /api/dashboard/team-knowledge-stats — Team Arena stats for ROP (Block 5)
"""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from app.core.rate_limit import limiter
from sqlalchemy import Integer, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core import errors as err
from app.core.deps import get_current_user, require_role
from app.core.redis_pool import get_redis
from app.database import get_db
from app.models.training import SessionStatus, TrainingSession
from app.models.user import Team, User

logger = logging.getLogger(__name__)

router = APIRouter()

CACHE_TTL = 30  # seconds


async def _cache_get(key: str) -> dict | None:
    """Get cached dashboard data from Redis (shared pool)."""
    try:
        r = get_redis()
        raw = await r.get(key)
        if raw:
            return json.loads(raw)
    except Exception:
        logger.debug("Cache miss/error for key %s", key)
    return None


async def _cache_set(key: str, data: dict) -> None:
    """Cache dashboard data in Redis (shared pool)."""
    try:
        r = get_redis()
        await r.set(key, json.dumps(data, default=str), ex=CACHE_TTL)
    except Exception:
        logger.debug("Dashboard cache set failed for key %s", key, exc_info=True)


def _is_admin_dashboard_view(user: User) -> bool:
    return user.role.value == "admin"


@router.get("/manager")
@limiter.limit("30/minute")
async def manager_dashboard(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Complete manager dashboard in one request.

    Returns: stats, recent sessions, gamification, recommendations, assignments, tournament.
    Cached for 30 seconds per user.
    """
    cache_key = f"dashboard:manager:{user.id}"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    # ── Stats ──
    stats_result = await db.execute(
        select(
            func.count(TrainingSession.id),
            func.avg(TrainingSession.score_total),
            func.max(TrainingSession.score_total),
            func.sum(TrainingSession.duration_seconds),
        ).where(
            TrainingSession.user_id == user.id,
            TrainingSession.status == SessionStatus.completed,
        )
    )
    row = stats_result.one()
    total_sessions = row[0] or 0
    avg_score = round(float(row[1]), 1) if row[1] else None
    best_score = round(float(row[2]), 1) if row[2] else None
    total_duration = row[3] or 0

    completed_result = await db.execute(
        select(func.count(TrainingSession.id)).where(
            TrainingSession.user_id == user.id,
            TrainingSession.status == SessionStatus.completed,
        )
    )
    completed = completed_result.scalar() or 0

    week_result = await db.execute(
        select(func.count(TrainingSession.id)).where(
            TrainingSession.user_id == user.id,
            TrainingSession.started_at >= week_ago,
        )
    )
    sessions_this_week = week_result.scalar() or 0

    # ── Recent sessions (last 5) ──
    recent_result = await db.execute(
        select(TrainingSession)
        .where(TrainingSession.user_id == user.id)
        .order_by(TrainingSession.started_at.desc())
        .limit(5)
    )
    recent_sessions = [
        {
            "id": str(s.id),
            "status": s.status.value,
            "score_total": s.score_total,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "duration_seconds": s.duration_seconds,
        }
        for s in recent_result.scalars().all()
    ]

    # ── Gamification ──
    gamification = {}
    try:
        from app.services.gamification import calculate_streak, get_user_total_xp, level_from_xp, xp_for_level
        total_xp = await get_user_total_xp(user.id, db)
        level = level_from_xp(total_xp)
        streak = await calculate_streak(user.id, db)
        gamification = {
            "total_xp": total_xp,
            "level": level,
            "xp_current_level": total_xp - xp_for_level(level),
            "xp_next_level": xp_for_level(level + 1) - xp_for_level(level),
            "streak_days": streak,
        }
    except Exception:
        logger.warning("Dashboard sub-query failed", exc_info=True)

    # ── Recommendations (top 3) ──
    recommendations = []
    try:
        from app.services.difficulty import get_difficulty_profile, get_recommended_scenarios
        profile = await get_difficulty_profile(user.id, db)
        recs = await get_recommended_scenarios(user.id, db, count=3)
        recommendations = [
            {
                "scenario_id": str(r.scenario_id),
                "title": r.title,
                "archetype": r.archetype_name,
                "difficulty": r.difficulty,
                "reason": r.reason,
                "tags": r.tags,
            }
            for r in recs
        ]
    except Exception:
        logger.warning("Dashboard sub-query failed", exc_info=True)

    # ── Assignments ──
    assignments = []
    try:
        from app.models.training import AssignedTraining
        from app.models.scenario import Scenario
        assign_result = await db.execute(
            select(AssignedTraining, Scenario.title)
            .join(Scenario, Scenario.id == AssignedTraining.scenario_id)
            .where(
                AssignedTraining.user_id == user.id,
                AssignedTraining.completed_at.is_(None),
            )
            .order_by(AssignedTraining.created_at.desc())
            .limit(5)
        )
        assignments = [
            {
                "id": str(row[0].id),
                "scenario_title": row[1],
                "deadline": row[0].deadline.isoformat() if row[0].deadline else None,
            }
            for row in assign_result.all()
        ]
    except Exception:
        logger.warning("Dashboard sub-query failed", exc_info=True)

    # ── Active tournament ──
    tournament = None
    try:
        from app.services.tournament import get_active_tournament, get_tournament_leaderboard
        t = await get_active_tournament(db)
        if t:
            lb = await get_tournament_leaderboard(t.id, db, limit=5)
            tournament = {
                "id": str(t.id),
                "title": t.title,
                "scenario_id": str(t.scenario_id),
                "week_end": t.week_end.isoformat(),
                "leaderboard": lb,
            }
    except Exception:
        logger.warning("Dashboard sub-query failed", exc_info=True)

    # ── Daily Hook data (weak skills, failed traps) for personalized greeting ──
    daily_hook: dict = {}
    try:
        from app.models.progress import ManagerProgress, SessionHistory
        mp_result = await db.execute(
            select(ManagerProgress).where(ManagerProgress.user_id == user.id)
        )
        mp = mp_result.scalar_one_or_none()
        if mp:
            daily_hook["weak_points"] = mp.weak_points or []
            daily_hook["focus_recommendation"] = mp.focus_recommendation

        # Most failed trap (from recent sessions)
        sh_result = await db.execute(
            select(SessionHistory).where(
                SessionHistory.user_id == user.id,
            ).order_by(SessionHistory.created_at.desc()).limit(10)
        )
        recent_history = sh_result.scalars().all()
        trap_fails: dict[str, int] = {}
        for sh in recent_history:
            bd = sh.score_breakdown or {}
            trap_name = bd.get("worst_trap_name") or bd.get("_trap_name")
            if trap_name and sh.traps_fell and sh.traps_fell > 0:
                trap_fails[trap_name] = trap_fails.get(trap_name, 0) + sh.traps_fell
        if trap_fails:
            worst_trap = max(trap_fails, key=trap_fails.get)  # type: ignore[arg-type]
            daily_hook["worst_trap"] = worst_trap
            daily_hook["worst_trap_count"] = trap_fails[worst_trap]
    except Exception:
        logger.warning("Daily hook data failed", exc_info=True)

    data = {
        "stats": {
            "total_sessions": total_sessions,
            "completed_sessions": completed,
            "avg_score": avg_score,
            "best_score": best_score,
            "sessions_this_week": sessions_this_week,
            "total_duration_minutes": total_duration // 60,
        },
        "recent_sessions": recent_sessions,
        "gamification": gamification,
        "recommendations": recommendations,
        "assignments": assignments,
        "tournament": tournament,
        "daily_hook": daily_hook,
    }

    await _cache_set(cache_key, data)
    return data


@router.get("/rop")
@limiter.limit("30/minute")
async def rop_dashboard(
    request: Request,
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Complete ROP dashboard in one request.

    - admin: sees ALL users from ALL teams
    - rop: sees only their own team

    Returns: team stats, all members with scores, leaderboard, tournament.
    Cached for 30 seconds per scope.
    """
    is_admin = _is_admin_dashboard_view(user)

    if is_admin:
        cache_key = "dashboard:rop:admin:all"
    elif not user.team_id:
        return {"error": err.NO_TEAM_ASSIGNED}
    else:
        cache_key = f"dashboard:rop:{user.team_id}"

    cached = await _cache_get(cache_key)
    if cached:
        return cached

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    # ── Team + Members in ONE query (join avoids N+1) ──
    if is_admin:
        members_result = await db.execute(
            select(User, Team.name.label("team_name"))
            .outerjoin(Team, User.team_id == Team.id)
            .order_by(Team.name, User.full_name)
        )
    else:
        members_result = await db.execute(
            select(User, Team.name.label("team_name"))
            .outerjoin(Team, User.team_id == Team.id)
            .where(User.team_id == user.team_id)
            .order_by(User.full_name)
        )
    rows = members_result.all()
    members = [row[0] for row in rows]
    team_names_by_user = {row[0].id: row[1] for row in rows}
    team_name = "Все команды" if is_admin else (rows[0][1] if rows else "Команда")

    team_user_ids = [m.id for m in members]

    # ── Per-member stats + week activity in ONE combined query ──
    # Uses conditional aggregation to get both lifetime and week stats in a single pass.
    member_stats_result = await db.execute(
        select(
            TrainingSession.user_id,
            # Lifetime stats (completed only)
            func.count(TrainingSession.id).filter(
                TrainingSession.status == SessionStatus.completed
            ).label("total"),
            func.avg(TrainingSession.score_total).filter(
                TrainingSession.status == SessionStatus.completed
            ).label("avg"),
            func.max(TrainingSession.score_total).filter(
                TrainingSession.status == SessionStatus.completed
            ).label("best"),
            # Week activity (all statuses)
            func.count(TrainingSession.id).filter(
                TrainingSession.started_at >= week_ago
            ).label("week_count"),
        )
        .where(TrainingSession.user_id.in_(team_user_ids))
        .group_by(TrainingSession.user_id)
    )
    stats_by_user = {}
    week_by_user = {}
    for row in member_stats_result.all():
        uid = row[0]
        stats_by_user[uid] = {
            "total": row[1], "avg": round(float(row[2] or 0), 1), "best": round(float(row[3] or 0), 1)
        }
        week_by_user[uid] = row[4]

    members_data = []
    for m in members:
        s = stats_by_user.get(m.id, {"total": 0, "avg": None, "best": None})
        members_data.append({
            "id": str(m.id),
            "full_name": m.full_name,
            "email": m.email,
            "role": m.role.value,
            "team_name": team_names_by_user.get(m.id),
            "is_active": m.is_active,
            "total_sessions": s["total"],
            "avg_score": s["avg"] if s["total"] > 0 else None,
            "best_score": s["best"] if s["total"] > 0 else None,
            "sessions_this_week": week_by_user.get(m.id, 0),
        })

    # Sort: most active first
    members_data.sort(key=lambda x: (x["total_sessions"] or 0), reverse=True)

    # ── Team aggregates ──
    total_sessions = sum(m["total_sessions"] for m in members_data)
    scored = [m for m in members_data if m["avg_score"] is not None]
    avg_score = round(sum(m["avg_score"] for m in scored) / len(scored), 1) if scored else None
    active_this_week = sum(1 for m in members_data if m["sessions_this_week"] > 0)
    best_performer = max(scored, key=lambda m: m["avg_score"])["full_name"] if scored else None

    # ── Tournament ──
    tournament = None
    try:
        from app.services.tournament import get_active_tournament, get_tournament_leaderboard
        t = await get_active_tournament(db)
        if t:
            lb = await get_tournament_leaderboard(t.id, db, limit=10)
            tournament = {
                "id": str(t.id),
                "title": t.title,
                "week_end": t.week_end.isoformat(),
                "leaderboard": lb,
            }
    except Exception:
        logger.warning("Dashboard sub-query failed", exc_info=True)

    data = {
        "team": {
            "name": team_name,
            "total_members": len(members),
            "active_members": sum(1 for m in members if m.is_active),
            "is_admin_view": is_admin,  # Frontend uses this to show "Все команды"
        },
        "stats": {
            "total_sessions": total_sessions,
            "avg_score": avg_score,
            "active_this_week": active_this_week,
            "best_performer": best_performer,
        },
        "members": members_data,
        "tournament": tournament,
    }

    await _cache_set(cache_key, data)
    return data


# ══════════════════════════════════════════════════════════════════════════════
# Block 5: Arena Knowledge Dashboard Stats
# ══════════════════════════════════════════════════════════════════════════════

CATEGORY_DISPLAY_NAMES: dict[str, str] = {
    "eligibility": "Условия подачи",
    "procedure": "Порядок процедуры",
    "property": "Имущество",
    "consequences": "Последствия",
    "costs": "Стоимость",
    "creditors": "Кредиторы",
    "documents": "Документы",
    "timeline": "Сроки",
    "court": "Судебные процессы",
    "rights": "Права должника",
}


@router.get("/knowledge-stats")
@limiter.limit("30/minute")
async def knowledge_dashboard_stats(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID | None = Query(None, description="View another user (ROP/admin)"),
):
    """Dashboard stats for Arena Knowledge section.

    Returns: overall_accuracy, category_progress, pvp_stats,
    recent_sessions, weak_areas, recommendations.
    Cached for 30 seconds.
    """
    # ROP/admin can view another user; others see only themselves
    target_id = user.id
    if user_id and user.role.value in ("rop", "admin"):
        # Admin can view anyone; ROP must be on same team
        if user.role.value == "admin":
            target_id = user_id
        else:
            target_user = (await db.execute(
                select(User).where(User.id == user_id)
            )).scalar_one_or_none()
            if target_user and target_user.team_id == user.team_id:
                target_id = user_id
            # else: silently fall back to own stats (no IDOR)

    cache_key = f"dashboard:knowledge:{target_id}"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    # ── Overall accuracy ──
    from app.models.knowledge import (
        KnowledgeAnswer,
        KnowledgeQuizSession,
        QuizSessionStatus,
    )
    from app.services.knowledge_quiz import get_category_progress, get_user_weak_areas

    category_progress = await get_category_progress(target_id, db)
    total_correct = sum(cp.get("correct_answers", 0) for cp in category_progress)
    total_answered = sum(cp.get("total_answers", 0) for cp in category_progress)
    overall_accuracy = (
        round(total_correct / total_answered * 100, 1) if total_answered > 0 else 0
    )

    # ── PvP rating ──
    pvp_stats = {}
    try:
        from app.services.arena_difficulty import get_arena_rating_for_user

        pvp_stats = await get_arena_rating_for_user(target_id, db)
    except Exception:
        logger.warning("PvP rating unavailable", exc_info=True)
        pvp_stats = {
            "rating": 1500, "rank_tier": "unranked",
            "wins": 0, "losses": 0, "current_streak": 0,
        }

    # ── Recent sessions (last 5) ──
    recent_result = await db.execute(
        select(KnowledgeQuizSession)
        .where(
            KnowledgeQuizSession.user_id == target_id,
            KnowledgeQuizSession.status == QuizSessionStatus.completed,
        )
        .order_by(KnowledgeQuizSession.ended_at.desc())
        .limit(5)
    )
    recent_sessions = [
        {
            "id": str(s.id),
            "mode": s.mode.value,
            "score": s.score,
            "correct": s.correct_answers,
            "total": s.total_questions,
            "category": s.category,
            "date": s.ended_at.isoformat() if s.ended_at else None,
        }
        for s in recent_result.scalars().all()
    ]

    # ── Weak areas ──
    weak_areas = await get_user_weak_areas(target_id, db, limit=3)

    # ── Cross-module recommendations ──
    recommendations = []
    try:
        from app.services.cross_recommendations import CrossModuleRecommendationEngine

        engine = CrossModuleRecommendationEngine()
        recs = await engine.get_training_recommendations_from_arena(target_id, db)
        recommendations = [
            {
                "category": r["category"],
                "accuracy": r["accuracy"],
                "recommendation": r["recommendation"],
                "priority": r["priority"],
                "suggested_action": r["suggested_action"],
            }
            for r in recs[:3]
        ]
    except Exception:
        logger.warning("Cross-module recommendations unavailable", exc_info=True)

    data = {
        "overall_accuracy": overall_accuracy,
        "total_quizzes": total_answered,
        "category_progress": [
            {
                "category": cp["category"],
                "display_name": CATEGORY_DISPLAY_NAMES.get(cp["category"], cp["category"]),
                "accuracy": cp.get("mastery_pct", 0),
                "total_answered": cp.get("total_answers", 0),
                "correct_answers": cp.get("correct_answers", 0),
            }
            for cp in category_progress
        ],
        "pvp_stats": pvp_stats,
        "recent_sessions": recent_sessions,
        "weak_areas": weak_areas,
        "recommendations": recommendations,
    }

    await _cache_set(cache_key, data)
    return data


@router.get("/team-knowledge-stats")
@limiter.limit("30/minute")
async def team_knowledge_stats(
    request: Request,
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Team knowledge stats for ROP dashboard.

    Returns per-member: accuracy, quiz sessions this week, needs_attention flag.
    """
    if not user.team_id and user.role.value != "admin":
        return {"error": err.NO_TEAM_ASSIGNED}

    cache_key = f"dashboard:team_knowledge:{user.team_id or 'all'}"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    from app.models.knowledge import KnowledgeAnswer, KnowledgeQuizSession, QuizSessionStatus

    # Get team members
    if user.role.value == "admin":
        team_filter = User.is_active == True  # noqa: E712
    else:
        team_filter = (User.team_id == user.team_id) & (User.is_active == True)  # noqa: E712

    members_result = await db.execute(select(User).where(team_filter))
    members = members_result.scalars().all()

    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    member_ids = [m.id for m in members]

    # Batch: answer accuracy per user
    ans_batch = await db.execute(
        select(
            KnowledgeAnswer.user_id,
            func.count(KnowledgeAnswer.id).label("total"),
            func.sum(
                case((KnowledgeAnswer.is_correct == True, 1), else_=0)  # noqa: E712
            ).label("correct"),
        )
        .where(KnowledgeAnswer.user_id.in_(member_ids))
        .group_by(KnowledgeAnswer.user_id)
    )
    ans_map = {r.user_id: {"total": r.total, "correct": r.correct or 0} for r in ans_batch}

    # Batch: weekly session count per user
    week_batch = await db.execute(
        select(
            KnowledgeQuizSession.user_id,
            func.count().label("cnt"),
        )
        .where(
            KnowledgeQuizSession.user_id.in_(member_ids),
            KnowledgeQuizSession.started_at >= week_ago,
            KnowledgeQuizSession.status == QuizSessionStatus.completed,
        )
        .group_by(KnowledgeQuizSession.user_id)
    )
    week_map = {r.user_id: r.cnt for r in week_batch}

    team_stats = []
    for member in members:
        ans_data = ans_map.get(member.id, {"total": 0, "correct": 0})
        total_a = ans_data["total"]
        correct_a = ans_data["correct"]
        accuracy = round((correct_a / total_a * 100), 1) if total_a > 0 else 0

        week_count = week_map.get(member.id, 0)

        team_stats.append({
            "user_id": str(member.id),
            "name": member.full_name,
            "accuracy": accuracy,
            "total_answers": total_a,
            "sessions_this_week": week_count,
            "needs_attention": accuracy < 60 and total_a >= 5,
        })

    team_stats.sort(key=lambda m: m["accuracy"])

    data = {
        "team_members": team_stats,
        "members_needing_attention": [m for m in team_stats if m["needs_attention"]],
        "total_members": len(team_stats),
    }

    await _cache_set(cache_key, data)
    return data


# ═══════════════════════════════════════════════════════════════════════════
# ROP DASHBOARD V2 — Team Heatmap, Weak Links, Benchmark, ROI
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/rop/heatmap")
@limiter.limit("30/minute")
async def rop_heatmap(
    request: Request,
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Team skill heatmap: managers x 6 skills matrix with trends."""
    is_admin = _is_admin_dashboard_view(user)
    if not user.team_id and not is_admin:
        return {"team_name": "—", "skill_names": [], "rows": [], "team_avg": {}}

    from app.services.team_analytics import get_team_heatmap
    scope_key = "all" if is_admin else str(user.team_id)
    cache_key = f"dashboard:rop_heatmap:{scope_key}"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    data = await get_team_heatmap(None if is_admin else user.team_id, db)
    await _cache_set(cache_key, data)
    return data


@router.get("/rop/weak-links")
@limiter.limit("30/minute")
async def rop_weak_links(
    request: Request,
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Managers needing attention: declining scores, inactivity, low performance."""
    is_admin = _is_admin_dashboard_view(user)
    if not user.team_id and not is_admin:
        return {"needs_attention": [], "total_team": 0, "attention_count": 0}

    from app.services.team_analytics import get_weak_links
    scope_key = "all" if is_admin else str(user.team_id)
    cache_key = f"dashboard:rop_weak_links:{scope_key}"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    data = await get_weak_links(None if is_admin else user.team_id, db)
    await _cache_set(cache_key, data)
    return data


@router.get("/rop/benchmark")
@limiter.limit("30/minute")
async def rop_benchmark(
    request: Request,
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Compare managers within team: each vs team average with percentiles."""
    is_admin = _is_admin_dashboard_view(user)
    if not user.team_id and not is_admin:
        return {"team_name": "—", "entries": [], "team_avg_score": 0}

    from app.services.team_analytics import compare_managers
    scope_key = "all" if is_admin else str(user.team_id)
    cache_key = f"dashboard:rop_benchmark:{scope_key}"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    data = await compare_managers(None if is_admin else user.team_id, db)
    await _cache_set(cache_key, data)
    return data


@router.get("/rop/roi")
@limiter.limit("30/minute")
async def rop_roi(
    request: Request,
    weeks: int = Query(8, ge=4, le=26),
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """ROI: correlation between training hours and score improvement."""
    if not user.team_id:
        return {"data_points": [], "correlation": 0.0, "summary": "Нет команды"}

    from app.services.team_analytics import get_team_roi
    data = await get_team_roi(user.team_id, db, weeks)
    return data


@router.get("/benchmark")
@limiter.limit("30/minute")
async def platform_benchmark(
    request: Request,
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Team vs platform benchmark with percentiles."""
    is_admin = _is_admin_dashboard_view(user)
    if not user.team_id and not is_admin:
        return {"team_name": "—", "skills": [], "team_avg_score": 0, "platform_avg_score": 0}

    from app.services.team_analytics import get_team_vs_platform
    scope_key = "all" if is_admin else str(user.team_id)
    cache_key = f"dashboard:benchmark:{scope_key}"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    data = await get_team_vs_platform(None if is_admin else user.team_id, db)
    await _cache_set(cache_key, data)
    return data


# ═══════════════════════════════════════════════════════════════════════════
# WEEKLY REPORTS
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/weekly-report")
@limiter.limit("30/minute")
async def get_weekly_report(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get latest weekly report for current user."""
    from app.models.progress import WeeklyReport

    result = await db.execute(
        select(WeeklyReport).where(
            WeeklyReport.user_id == user.id,
        ).order_by(WeeklyReport.week_start.desc()).limit(1)
    )
    report = result.scalar_one_or_none()

    if not report:
        # GAP-3 fix: on-demand generation if no report exists yet
        try:
            from app.services.weekly_report import generate_weekly_report as gen_report
            await gen_report(db, user.id)
            await db.commit()
            # Re-fetch
            result = await db.execute(
                select(WeeklyReport).where(
                    WeeklyReport.user_id == user.id,
                ).order_by(WeeklyReport.week_start.desc()).limit(1)
            )
            report = result.scalar_one_or_none()
        except Exception:
            pass
    if not report:
        return {"message": "Нет данных для отчёта. Проведите хотя бы одну тренировку."}

    return {
        "id": str(report.id),
        "user_id": str(report.user_id),
        "week_start": report.week_start.isoformat(),
        "week_end": report.week_end.isoformat(),
        "sessions_completed": report.sessions_completed,
        "total_time_minutes": report.total_time_minutes,
        "average_score": float(report.average_score) if report.average_score else None,
        "best_score": report.best_score,
        "worst_score": report.worst_score,
        "score_trend": report.score_trend,
        "skills_snapshot": report.skills_snapshot,
        "skills_change": report.skills_change,
        "weak_points": report.weak_points,
        "recommendations": report.recommendations,
        "report_text": report.report_text,
        "weekly_rank": report.weekly_rank,
        "rank_change": report.rank_change,
        "new_achievements": report.new_achievements,
        "xp_earned": report.xp_earned,
    }


@router.get("/weekly-report/history")
@limiter.limit("30/minute")
async def get_weekly_report_history(
    request: Request,
    weeks: int = Query(12, ge=1, le=52),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get weekly report history."""
    from app.models.progress import WeeklyReport

    result = await db.execute(
        select(WeeklyReport).where(
            WeeklyReport.user_id == user.id,
        ).order_by(WeeklyReport.week_start.desc()).limit(weeks)
    )
    reports = result.scalars().all()

    return {
        "reports": [
            {
                "id": str(r.id),
                "week_start": r.week_start.isoformat(),
                "week_end": r.week_end.isoformat(),
                "sessions_completed": r.sessions_completed,
                "average_score": float(r.average_score) if r.average_score else None,
                "score_trend": r.score_trend,
                "weekly_rank": r.weekly_rank,
                "xp_earned": r.xp_earned,
            }
            for r in reports
        ],
        "total": len(reports),
    }


@router.get("/weekly-report/export")
@limiter.limit("5/minute")
async def export_weekly_report(
    request: Request,
    report_id: uuid.UUID = Query(...),
    format: str = Query("csv", regex="^(csv|json)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export individual weekly report as CSV or JSON."""
    from app.models.progress import WeeklyReport

    report = await db.get(WeeklyReport, report_id)
    if not report or report.user_id != user.id:
        raise HTTPException(status_code=404, detail="Report not found")

    data = {
        "week": f"{report.week_start.strftime('%Y-%m-%d')} — {report.week_end.strftime('%Y-%m-%d')}",
        "sessions": report.sessions_completed,
        "average_score": float(report.average_score) if report.average_score else 0,
        "best_score": float(report.best_score) if report.best_score else 0,
        "score_trend": report.score_trend or "stable",
        "xp_earned": report.xp_earned or 0,
        "weekly_rank": report.weekly_rank,
        "skills": report.skills_snapshot or {},
    }

    if format == "csv":
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Metric", "Value"])
        for k, v in data.items():
            if isinstance(v, dict):
                for sk, sv in v.items():
                    writer.writerow([f"{k}.{sk}", sv])
            else:
                writer.writerow([k, v])
        content = output.getvalue()
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=report_{report.week_start.strftime('%Y%m%d')}.csv"},
        )

    return data


@router.get("/rop/weekly-digest")
@limiter.limit("30/minute")
async def rop_weekly_digest(
    request: Request,
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Team weekly digest for ROP: top improvements, degrading members."""
    if not user.team_id:
        return {"team_name": "—", "members": []}

    from app.services.weekly_report_generator import get_team_weekly_digest
    data = await get_team_weekly_digest(user.team_id, db)
    return data


# ══════════════════════════════════════════════════════════════════════════════
# Block M3: Team Trends, Activity, Alerts, Sessions, PDF Export
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/rop/trends")
@limiter.limit("30/minute")
async def rop_trends(
    request: Request,
    period: str = Query("month", pattern="^(week|month|all)$"),
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Weekly trend data: avg score, sessions, active managers over time."""
    is_admin = _is_admin_dashboard_view(user)
    if not user.team_id and not is_admin:
        return {"weeks": [], "period": period}

    from app.services.team_analytics import get_team_trends
    scope_key = "all" if is_admin else str(user.team_id)
    cache_key = f"dashboard:rop_trends:{scope_key}:{period}"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    data = await get_team_trends(None if is_admin else user.team_id, db, period)
    await _cache_set(cache_key, data)
    return data


@router.get("/rop/activity")
@limiter.limit("30/minute")
async def rop_activity(
    request: Request,
    days: int = Query(14, ge=7, le=30),
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Daily session counts for the team over the last N days."""
    is_admin = _is_admin_dashboard_view(user)
    if not user.team_id and not is_admin:
        return {"days": [], "total_sessions": 0}

    from app.services.team_analytics import get_daily_activity
    scope_key = "all" if is_admin else str(user.team_id)
    cache_key = f"dashboard:rop_activity:{scope_key}:{days}"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    data = await get_daily_activity(None if is_admin else user.team_id, db, days)
    await _cache_set(cache_key, data)
    return data


@router.get("/rop/alerts")
@limiter.limit("30/minute")
async def rop_alerts(
    request: Request,
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Auto-generated alerts: inactive managers, records, skill drops."""
    if not user.team_id:
        return {"alerts": [], "total": 0}

    from app.services.rop_alerts import get_active_alerts
    cache_key = f"dashboard:rop_alerts:{user.team_id}"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    data = await get_active_alerts(user.team_id, db)
    await _cache_set(cache_key, data)
    return data


@router.get("/rop/sessions")
@limiter.limit("30/minute")
async def rop_member_sessions(
    request: Request,
    manager_id: str = Query(..., description="Manager UUID"),
    limit: int = Query(20, ge=1, le=50),
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """List training sessions for a specific team member (ROP access)."""
    if not user.team_id:
        return {"sessions": [], "total": 0}

    # Verify the manager belongs to the same team
    manager_uuid = uuid.UUID(manager_id)
    member_r = await db.execute(
        select(User).where(User.id == manager_uuid, User.team_id == user.team_id)
    )
    member = member_r.scalar_one_or_none()
    if not member:
        return {"sessions": [], "total": 0, "error": "Manager not in your team"}

    sessions_r = await db.execute(
        select(TrainingSession).where(
            TrainingSession.user_id == manager_uuid,
            TrainingSession.status == SessionStatus.completed,
        ).order_by(TrainingSession.started_at.desc()).limit(limit)
    )
    sessions = sessions_r.scalars().all()

    return {
        "manager_name": member.full_name,
        "sessions": [
            {
                "id": str(s.id),
                "scenario_id": str(s.scenario_id) if s.scenario_id else None,
                "score_total": round(float(s.score_total or 0), 1),
                "duration_seconds": s.duration_seconds,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "status": s.status.value if s.status else "unknown",
            }
            for s in sessions
        ],
        "total": len(sessions),
    }


@router.get("/rop/export")
@limiter.limit("5/minute")
async def rop_export_pdf(
    request: Request,
    period: str = Query("week", pattern="^(week|month)$"),
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Export team report as PDF."""
    if not user.team_id:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "No team assigned"}, status_code=400)

    from app.services.rop_export import generate_team_report_pdf
    pdf_bytes = await generate_team_report_pdf(user.team_id, user.full_name, period, db)

    from fastapi.responses import Response
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="team_report_{period}.pdf"',
        },
    )


# ═══════════════════════════════════════════════════════════════════════════════
# RAG Feedback Analytics — knowledge base health and effectiveness
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/rag/feedback-summary")
@limiter.limit("30/minute")
async def rag_feedback_summary(
    request: Request,
    days: int = Query(30, ge=1, le=365),
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """RAG feedback summary: retrieval stats, accuracy rates, weak chunks."""
    from app.services.rag_feedback import get_feedback_summary
    return await get_feedback_summary(db, days=days)


@router.get("/rag/category-errors")
@limiter.limit("30/minute")
async def rag_category_errors(
    request: Request,
    days: int = Query(30, ge=1, le=365),
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Per-category error rates: which legal topics are hardest for managers."""
    from app.services.rag_feedback import get_category_error_rates
    return await get_category_error_rates(db, days=days)


@router.get("/rag/weak-chunks")
@limiter.limit("30/minute")
async def rag_weak_chunks(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Chunks with lowest effectiveness (most user errors). For ROP review."""
    from app.services.rag_legal import get_weak_chunks
    return await get_weak_chunks(db, limit=limit)


@router.get("/rag/unused-chunks")
@limiter.limit("30/minute")
async def rag_unused_chunks(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Active chunks that have never been retrieved. Content gap analysis."""
    from app.services.rag_legal import get_unused_chunks
    return await get_unused_chunks(db, limit=limit)


@router.get("/rag/user-weak-areas/{user_id}")
@limiter.limit("30/minute")
async def rag_user_weak_areas(
    request: Request,
    user_id: uuid.UUID,
    days: int = Query(30, ge=1, le=365),
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Individual manager's weak legal categories based on answer history."""
    # Team-scope: ROP can only inspect own team. Admin can inspect anyone.
    if user.role.value != "admin":
        target = (await db.execute(
            select(User).where(User.id == user_id)
        )).scalar_one_or_none()
        if not target or target.team_id != user.team_id:
            raise HTTPException(status_code=403, detail="Member not in your team")
    from app.services.rag_feedback import get_user_weak_areas
    return await get_user_weak_areas(db, user_id=user_id, days=days)


# ═══════════════════════════════════════════════════════════════════════════════
# Team member deep-dive — single bundle endpoint for /dashboard/team/[id]
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/team/member/{member_id}")
@limiter.limit("30/minute")
async def team_member_bundle(
    request: Request,
    member_id: uuid.UUID,
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Methodologist-style deep dive on a single team member.

    Bundles member info, behavior + OCEAN profile, weak spots, recent
    sessions, and recommendations into one round-trip so the FE doesn't
    fan out 5 calls. ROP can only inspect own-team members; admin can
    inspect anyone.
    """
    # ── Lookup + permission gate ──────────────────────────────────────────
    member = (await db.execute(
        select(User).options(selectinload(User.team)).where(User.id == member_id)
    )).scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    if user.role.value != "admin" and member.team_id != user.team_id:
        raise HTTPException(status_code=403, detail="Member not in your team")

    # ── Stats (sessions count, avg, best, week) ───────────────────────────
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    stats_row = (await db.execute(
        select(
            func.count(TrainingSession.id),
            func.avg(TrainingSession.score_total),
            func.max(TrainingSession.score_total),
            func.sum(case((TrainingSession.started_at >= week_ago, 1), else_=0)),
        ).where(
            TrainingSession.user_id == member_id,
            TrainingSession.status == SessionStatus.completed,
        )
    )).one()
    total_sessions, avg_score, best_score, week_sessions = stats_row

    # ── Behavior profile + OCEAN ──────────────────────────────────────────
    from app.services.manager_emotion_profiler import (
        get_or_create_profile,
        get_ocean_profile,
    )
    profile = await get_or_create_profile(member_id, db)
    ocean = await get_ocean_profile(member_id, db)

    # ── Weak spots (top 5) ────────────────────────────────────────────────
    from app.services.analytics import analyze_weak_spots
    weak_spots_raw = await analyze_weak_spots(member_id, db, last_n=15)
    weak_spots = [
        {
            "skill": w.skill,
            "sub_skill": w.sub_skill,
            "pct": round(w.pct, 1),
            "trend": w.trend,
            "trend_delta": round(w.trend_delta, 1),
            "archetype": w.archetype,
            "recommendation": w.recommendation,
        }
        for w in weak_spots_raw[:5]
    ]

    # ── Recent sessions (last 10 completed) ───────────────────────────────
    sessions_r = await db.execute(
        select(TrainingSession).where(
            TrainingSession.user_id == member_id,
            TrainingSession.status == SessionStatus.completed,
        ).order_by(TrainingSession.started_at.desc()).limit(10)
    )
    recent_sessions = [
        {
            "id": str(s.id),
            "scenario_id": str(s.scenario_id) if s.scenario_id else None,
            "score_total": round(float(s.score_total or 0), 1),
            "duration_seconds": s.duration_seconds,
            "started_at": s.started_at.isoformat() if s.started_at else None,
        }
        for s in sessions_r.scalars().all()
    ]

    return {
        "member": {
            "id": str(member.id),
            "full_name": member.full_name,
            "email": member.email,
            "role": member.role.value if hasattr(member.role, "value") else str(member.role),
            "team_id": str(member.team_id) if member.team_id else None,
            "team_name": member.team.name if member.team else None,
            "is_active": member.is_active,
        },
        "stats": {
            "total_sessions": int(total_sessions or 0),
            "avg_score": round(float(avg_score or 0), 1),
            "best_score": round(float(best_score or 0), 1),
            "sessions_this_week": int(week_sessions or 0),
        },
        "behavior": {
            "composite": {
                "confidence": round(profile.overall_confidence, 1),
                "stress_resistance": round(profile.overall_stress_resistance, 1),
                "adaptability": round(profile.overall_adaptability, 1),
                "empathy": round(profile.overall_empathy, 1),
            },
            "performance": {
                "under_hostility": profile.performance_under_hostility,
                "under_stress": profile.performance_under_stress,
                "with_empathy": profile.performance_with_empathy,
            },
            "archetype_scores": profile.archetype_scores or {},
            "sessions_analyzed": profile.sessions_analyzed,
        },
        "ocean": ocean,
        "weak_spots": weak_spots,
        "recent_sessions": recent_sessions,
    }
