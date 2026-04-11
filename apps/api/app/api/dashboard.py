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

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
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


@router.get("/manager")
async def manager_dashboard(
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
        logger.debug("Dashboard sub-query failed", exc_info=True)

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
        logger.debug("Dashboard sub-query failed", exc_info=True)

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
        logger.debug("Dashboard sub-query failed", exc_info=True)

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
        logger.debug("Dashboard sub-query failed", exc_info=True)

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
    }

    await _cache_set(cache_key, data)
    return data


@router.get("/rop")
async def rop_dashboard(
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Complete ROP dashboard in one request.

    Returns: team stats, all members with scores, leaderboard, tournament.
    Cached for 30 seconds per team.
    """
    if not user.team_id:
        return {"error": err.NO_TEAM_ASSIGNED}

    cache_key = f"dashboard:rop:{user.team_id}"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    # ── Team + Members in ONE query (join avoids N+1) ──
    members_result = await db.execute(
        select(User, Team.name)
        .outerjoin(Team, User.team_id == Team.id)
        .where(User.team_id == user.team_id)
        .order_by(User.full_name)
    )
    rows = members_result.all()
    members = [row[0] for row in rows]
    team_name = rows[0][1] if rows else "Команда"

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
        logger.debug("Dashboard sub-query failed", exc_info=True)

    data = {
        "team": {
            "name": team_name,
            "total_members": len(members),
            "active_members": sum(1 for m in members if m.is_active),
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
async def knowledge_dashboard_stats(
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
    if user_id and user.role.value in ("rop", "admin", "methodologist"):
        # Admin can view anyone; ROP/methodologist must be on same team
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
        logger.debug("PvP rating unavailable", exc_info=True)
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
        logger.debug("Cross-module recommendations unavailable", exc_info=True)

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
async def team_knowledge_stats(
    user: User = Depends(require_role("rop", "admin", "methodologist")),
    db: AsyncSession = Depends(get_db),
):
    """Team knowledge stats for ROP dashboard.

    Returns per-member: accuracy, quiz sessions this week, needs_attention flag.
    """
    if not user.team_id and user.role.value not in ("admin", "methodologist"):
        return {"error": err.NO_TEAM_ASSIGNED}

    cache_key = f"dashboard:team_knowledge:{user.team_id or 'all'}"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    from app.models.knowledge import KnowledgeAnswer, KnowledgeQuizSession, QuizSessionStatus

    # Get team members
    if user.role.value in ("admin", "methodologist"):
        team_filter = User.is_active == True  # noqa: E712
    else:
        team_filter = (User.team_id == user.team_id) & (User.is_active == True)  # noqa: E712

    members_result = await db.execute(select(User).where(team_filter))
    members = members_result.scalars().all()

    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    team_stats = []
    for member in members:
        # Per-member accuracy
        ans_result = await db.execute(
            select(
                func.count(KnowledgeAnswer.id).label("total"),
                func.sum(
                    case((KnowledgeAnswer.is_correct == True, 1), else_=0)  # noqa: E712
                ).label("correct"),
            )
            .where(KnowledgeAnswer.user_id == member.id)
        )
        ans_row = ans_result.one()
        total_a = ans_row.total or 0
        correct_a = ans_row.correct or 0
        accuracy = round((correct_a / total_a * 100), 1) if total_a > 0 else 0

        # Sessions this week
        week_count = (await db.execute(
            select(func.count()).where(
                KnowledgeQuizSession.user_id == member.id,
                KnowledgeQuizSession.started_at >= week_ago,
                KnowledgeQuizSession.status == QuizSessionStatus.completed,
            )
        )).scalar() or 0

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
async def rop_heatmap(
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Team skill heatmap: managers x 6 skills matrix with trends."""
    if not user.team_id:
        return {"team_name": "—", "skill_names": [], "rows": [], "team_avg": {}}

    from app.services.team_analytics import get_team_heatmap
    cache_key = f"dashboard:rop_heatmap:{user.team_id}"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    data = await get_team_heatmap(user.team_id, db)
    await _cache_set(cache_key, data)
    return data


@router.get("/rop/weak-links")
async def rop_weak_links(
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Managers needing attention: declining scores, inactivity, low performance."""
    if not user.team_id:
        return {"needs_attention": [], "total_team": 0, "attention_count": 0}

    from app.services.team_analytics import get_weak_links
    cache_key = f"dashboard:rop_weak_links:{user.team_id}"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    data = await get_weak_links(user.team_id, db)
    await _cache_set(cache_key, data)
    return data


@router.get("/rop/benchmark")
async def rop_benchmark(
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Compare managers within team: each vs team average with percentiles."""
    if not user.team_id:
        return {"team_name": "—", "entries": [], "team_avg_score": 0}

    from app.services.team_analytics import compare_managers
    cache_key = f"dashboard:rop_benchmark:{user.team_id}"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    data = await compare_managers(user.team_id, db)
    await _cache_set(cache_key, data)
    return data


@router.get("/rop/roi")
async def rop_roi(
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
async def platform_benchmark(
    user: User = Depends(require_role("rop", "admin", "methodologist")),
    db: AsyncSession = Depends(get_db),
):
    """Team vs platform benchmark with percentiles."""
    if not user.team_id:
        return {"team_name": "—", "skills": [], "team_avg_score": 0, "platform_avg_score": 0}

    from app.services.team_analytics import get_team_vs_platform
    cache_key = f"dashboard:benchmark:{user.team_id}"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    data = await get_team_vs_platform(user.team_id, db)
    await _cache_set(cache_key, data)
    return data


# ═══════════════════════════════════════════════════════════════════════════
# WEEKLY REPORTS
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/weekly-report")
async def get_weekly_report(
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
async def get_weekly_report_history(
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
async def export_weekly_report(
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
async def rop_weekly_digest(
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
async def rop_trends(
    period: str = Query("month", pattern="^(week|month|all)$"),
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Weekly trend data: avg score, sessions, active managers over time."""
    if not user.team_id:
        return {"weeks": [], "period": period}

    from app.services.team_analytics import get_team_trends
    cache_key = f"dashboard:rop_trends:{user.team_id}:{period}"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    data = await get_team_trends(user.team_id, db, period)
    await _cache_set(cache_key, data)
    return data


@router.get("/rop/activity")
async def rop_activity(
    days: int = Query(14, ge=7, le=30),
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Daily session counts for the team over the last N days."""
    if not user.team_id:
        return {"days": [], "total_sessions": 0}

    from app.services.team_analytics import get_daily_activity
    cache_key = f"dashboard:rop_activity:{user.team_id}:{days}"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    data = await get_daily_activity(user.team_id, db, days)
    await _cache_set(cache_key, data)
    return data


@router.get("/rop/alerts")
async def rop_alerts(
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
async def rop_member_sessions(
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
async def rop_export_pdf(
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
async def rag_feedback_summary(
    days: int = Query(30, ge=1, le=365),
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """RAG feedback summary: retrieval stats, accuracy rates, weak chunks."""
    from app.services.rag_feedback import get_feedback_summary
    return await get_feedback_summary(db, days=days)


@router.get("/rag/category-errors")
async def rag_category_errors(
    days: int = Query(30, ge=1, le=365),
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Per-category error rates: which legal topics are hardest for managers."""
    from app.services.rag_feedback import get_category_error_rates
    return await get_category_error_rates(db, days=days)


@router.get("/rag/weak-chunks")
async def rag_weak_chunks(
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Chunks with lowest effectiveness (most user errors). For methodologist review."""
    from app.services.rag_legal import get_weak_chunks
    return await get_weak_chunks(db, limit=limit)


@router.get("/rag/unused-chunks")
async def rag_unused_chunks(
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Active chunks that have never been retrieved. Content gap analysis."""
    from app.services.rag_legal import get_unused_chunks
    return await get_unused_chunks(db, limit=limit)


@router.get("/rag/user-weak-areas/{user_id}")
async def rag_user_weak_areas(
    user_id: uuid.UUID,
    days: int = Query(30, ge=1, le=365),
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Individual manager's weak legal categories based on answer history."""
    from app.services.rag_feedback import get_user_weak_areas
    return await get_user_weak_areas(db, user_id=user_id, days=days)
