"""Batch dashboard API: one request per role, Redis-cached.

GET /api/dashboard/manager — stats + progress + assignments + recommendations + gamification
GET /api/dashboard/rop — team stats + all members + leaderboard + tournament
"""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import redis.asyncio as aioredis

from app.config import settings
from app.core.deps import get_current_user, require_role
from app.database import get_db
from app.models.training import SessionStatus, TrainingSession
from app.models.user import Team, User

logger = logging.getLogger(__name__)

router = APIRouter()

CACHE_TTL = 30  # seconds


async def _cache_get(key: str) -> dict | None:
    """Get cached dashboard data from Redis."""
    try:
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        raw = await r.get(key)
        await r.aclose()
        if raw:
            return json.loads(raw)
    except Exception:
        logger.debug("Cache miss/error for key %s", key)
    return None


async def _cache_set(key: str, data: dict) -> None:
    """Cache dashboard data in Redis."""
    try:
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        await r.set(key, json.dumps(data, default=str), ex=CACHE_TTL)
        await r.aclose()
    except Exception:
        logger.debug("Dashboard sub-query failed", exc_info=True)


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
        return {"error": "No team assigned"}

    cache_key = f"dashboard:rop:{user.team_id}"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    # ── Team info ──
    team_result = await db.execute(select(Team).where(Team.id == user.team_id))
    team = team_result.scalar_one_or_none()
    team_name = team.name if team else "Команда"

    # ── Members ──
    members_result = await db.execute(
        select(User)
        .where(User.team_id == user.team_id)
        .order_by(User.full_name)
    )
    members = members_result.scalars().all()

    team_user_ids = [m.id for m in members]

    # ── Per-member stats (batched in ONE query) ──
    member_stats_result = await db.execute(
        select(
            TrainingSession.user_id,
            func.count(TrainingSession.id).label("total"),
            func.avg(TrainingSession.score_total).label("avg"),
            func.max(TrainingSession.score_total).label("best"),
        )
        .where(
            TrainingSession.user_id.in_(team_user_ids),
            TrainingSession.status == SessionStatus.completed,
        )
        .group_by(TrainingSession.user_id)
    )
    stats_by_user = {
        row[0]: {"total": row[1], "avg": round(float(row[2] or 0), 1), "best": round(float(row[3] or 0), 1)}
        for row in member_stats_result.all()
    }

    # Week activity (also batched)
    week_result = await db.execute(
        select(
            TrainingSession.user_id,
            func.count(TrainingSession.id),
        )
        .where(
            TrainingSession.user_id.in_(team_user_ids),
            TrainingSession.started_at >= week_ago,
        )
        .group_by(TrainingSession.user_id)
    )
    week_by_user = {row[0]: row[1] for row in week_result.all()}

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
