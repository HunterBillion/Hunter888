"""Behavioral Intelligence API endpoints.

Provides access to behavioral profiles, trends, daily advice,
and team alerts for ROP.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.models.behavior import BehaviorSnapshot, EmotionProfile, ProgressTrend, DailyAdvice
from app.services.behavior_tracker import get_user_behavior_history
from app.services.manager_emotion_profiler import get_or_create_profile
from app.services.progress_detector import detect_trends, get_user_trend_history, get_team_alerts
from app.services.daily_advice import get_today_advice
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/behavior", tags=["behavior"])


@router.get("/profile")
async def get_behavior_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID | None = Query(None, description="Override user_id (ROP/admin only)"),
):
    """Get behavioral + emotional profile for a user.

    Returns composite scores, OCEAN traits, archetype performance.
    """
    target_id = user_id if (user_id and user.role in ("rop", "admin", "methodologist")) else user.id

    profile = await get_or_create_profile(target_id, db)
    recent_snapshots = await get_user_behavior_history(target_id, db, limit=5)

    return {
        "user_id": str(target_id),
        "composite_scores": {
            "confidence": profile.overall_confidence,
            "stress_resistance": profile.overall_stress_resistance,
            "adaptability": profile.overall_adaptability,
            "empathy": profile.overall_empathy,
        },
        "ocean": {
            "openness": profile.openness,
            "conscientiousness": profile.conscientiousness,
            "extraversion": profile.extraversion,
            "agreeableness": profile.agreeableness,
            "neuroticism": profile.neuroticism,
        },
        "performance_by_emotion": {
            "under_hostility": profile.performance_under_hostility,
            "under_stress": profile.performance_under_stress,
            "with_empathy": profile.performance_with_empathy,
        },
        "archetype_scores": profile.archetype_scores or {},
        "sessions_analyzed": profile.sessions_analyzed,
        "recent_snapshots": [
            {
                "session_id": str(s.session_id),
                "session_type": s.session_type,
                "confidence": s.confidence_score,
                "stress": s.stress_level,
                "adaptability": s.adaptability_score,
                "messages": s.total_messages,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in recent_snapshots
        ],
    }


@router.get("/trends")
async def get_trends(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID | None = Query(None),
    limit: int = Query(12, ge=1, le=52),
):
    """Get progress/regression trend history."""
    target_id = user_id if (user_id and user.role in ("rop", "admin")) else user.id
    trends = await get_user_trend_history(target_id, db, limit=limit)

    return {
        "user_id": str(target_id),
        "trends": [
            {
                "period_start": t.period_start.isoformat() if t.period_start else None,
                "period_end": t.period_end.isoformat() if t.period_end else None,
                "direction": t.direction.value,
                "score_delta": t.score_delta,
                "skill_trends": t.skill_trends,
                "alert_severity": t.alert_severity.value if t.alert_severity else None,
                "alert_message": t.alert_message,
                "sessions_count": t.sessions_count,
                "predicted_score_7d": t.predicted_score_in_7d,
            }
            for t in trends
        ],
    }


@router.get("/daily-advice")
async def get_daily_advice(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get today's personalized advice ("Совет дня").

    Generates automatically if not yet created for today.
    """
    advice = await get_today_advice(user.id, db)
    await db.commit()

    if advice is None:
        return {"advice": None, "message": "Нет данных для формирования совета. Пройдите первую тренировку!"}

    # Mark as viewed
    advice.was_viewed = True
    await db.commit()

    return {
        "advice": {
            "id": str(advice.id),
            "title": advice.title,
            "body": advice.body,
            "category": advice.category,
            "priority": advice.priority,
            "action_type": advice.action_type,
            "action_data": advice.action_data,
            "source_analysis": advice.source_analysis,
            "date": advice.advice_date.isoformat() if advice.advice_date else None,
        },
    }


@limiter.limit("20/minute")
@router.post("/daily-advice/{advice_id}/acted")
async def mark_advice_acted(
    request: Request,
    advice_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark advice as acted upon (user clicked action link)."""
    result = await db.execute(
        select(DailyAdvice).where(DailyAdvice.id == advice_id, DailyAdvice.user_id == user.id)
    )
    advice = result.scalar_one_or_none()
    if advice is None:
        raise HTTPException(404, "Advice not found")
    advice.was_acted_on = True
    await db.commit()
    return {"status": "ok"}


@router.get("/team-alerts")
async def get_team_alerts_endpoint(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    unseen_only: bool = Query(True),
):
    """Get behavioral alerts for ROP — team members needing attention."""
    if user.role not in ("rop", "admin", "methodologist"):
        raise HTTPException(403, "Only ROP/Admin can view team alerts")

    # Get team member IDs
    from app.models.user import User as UserModel
    if user.role == "rop":
        result = await db.execute(
            select(UserModel.id).where(UserModel.team_id == user.team_id, UserModel.is_active.is_(True))
        )
    else:
        result = await db.execute(select(UserModel.id).where(UserModel.is_active.is_(True)))
    team_ids = [row[0] for row in result.all()]

    alerts = await get_team_alerts(team_ids, db, unseen_only=unseen_only)

    return {
        "alerts": [
            {
                "user_id": str(a.user_id),
                "direction": a.direction.value,
                "severity": a.alert_severity.value if a.alert_severity else None,
                "message": a.alert_message,
                "score_delta": a.score_delta,
                "sessions_count": a.sessions_count,
                "period_end": a.period_end.isoformat() if a.period_end else None,
                "seen": a.alert_seen_by_rop,
            }
            for a in alerts
        ],
        "total": len(alerts),
    }


@limiter.limit("20/minute")
@router.post("/team-alerts/{alert_id}/seen")
async def mark_alert_seen(
    request: Request,
    alert_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a team alert as seen by ROP."""
    if user.role not in ("rop", "admin"):
        raise HTTPException(403, "Only ROP/Admin")
    result = await db.execute(select(ProgressTrend).where(ProgressTrend.id == alert_id))
    trend = result.scalar_one_or_none()
    if trend is None:
        raise HTTPException(404, "Alert not found")
    trend.alert_seen_by_rop = True
    await db.commit()
    return {"status": "ok"}
