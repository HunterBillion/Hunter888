"""Analytics API: weak spots, progress, archetype scores, recommendations, insights.

All endpoints are per-user (manager sees own data).
ROP/admin can view any user's analytics via user_id parameter.
"""

import uuid
from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.analytics import (
    AnalyticsSnapshot,
    analyze_weak_spots,
    build_full_snapshot,
    build_progress_chart,
    generate_insights,
    generate_recommendations,
    get_archetype_scores,
)

router = APIRouter()


# ── Response schemas ─────────────────────────────────────────────────────────


class WeakSpotResponse(BaseModel):
    skill: str
    sub_skill: str | None
    avg_score: float
    max_possible: float
    pct: float
    trend: str
    trend_delta: float
    archetype: str | None
    recommendation: str


class ProgressPointResponse(BaseModel):
    period_start: date
    period_end: date
    sessions_count: int
    avg_total: float
    avg_script: float
    avg_objection: float
    avg_communication: float
    avg_anti_patterns: float
    avg_result: float
    best_score: float
    worst_score: float


class ArchetypeScoreResponse(BaseModel):
    archetype_slug: str
    archetype_name: str
    sessions_count: int
    avg_score: float
    best_score: float
    worst_score: float
    avg_script: float
    avg_objection: float
    avg_communication: float
    avg_anti_patterns: float
    avg_result: float
    last_played: str | None  # ISO timestamp
    mastery_level: str


class RecommendationResponse(BaseModel):
    scenario_id: str
    scenario_title: str
    archetype_slug: str
    scenario_type: str
    difficulty: int
    reason: str
    priority: int


class FullSnapshotResponse(BaseModel):
    weak_spots: list[WeakSpotResponse]
    progress: list[ProgressPointResponse]
    archetype_scores: list[ArchetypeScoreResponse]
    recommendations: list[RecommendationResponse]
    insights: list[str]
    meta: dict


# ── Helper ───────────────────────────────────────────────────────────────────


def _resolve_user_id(
    current_user: User,
    target_user_id: uuid.UUID | None,
) -> uuid.UUID:
    """Resolve target user ID with permission checks."""
    if target_user_id is None:
        return current_user.id
    if target_user_id == current_user.id:
        return current_user.id
    if current_user.role.value not in ("rop", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own analytics",
        )
    return target_user_id


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/me/weak-spots", response_model=list[WeakSpotResponse])
async def get_weak_spots(
    user_id: uuid.UUID | None = Query(None, description="Target user (ROP/admin only)"),
    last_n: int = Query(15, ge=5, le=50, description="Sessions to analyze"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Identify specific weaknesses from recent sessions.

    Analyzes macro skills (script, objections, communication, anti-patterns, result),
    sub-skills (acknowledged, clarified, argued, etc.), and archetype-specific weaknesses.
    Each weak spot comes with a trend indicator and actionable recommendation in Russian.
    """
    target = _resolve_user_id(user, user_id)
    spots = await analyze_weak_spots(target, db, last_n=last_n)
    return [
        WeakSpotResponse(
            skill=s.skill,
            sub_skill=s.sub_skill,
            avg_score=s.avg_score,
            max_possible=s.max_possible,
            pct=s.pct,
            trend=s.trend,
            trend_delta=s.trend_delta,
            archetype=s.archetype,
            recommendation=s.recommendation,
        )
        for s in spots
    ]


@router.get("/me/progress", response_model=list[ProgressPointResponse])
async def get_progress_chart(
    user_id: uuid.UUID | None = Query(None),
    weeks: int = Query(12, ge=4, le=52, description="Weeks of history"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Weekly progress data for chart rendering.

    Returns one data point per calendar week with all 5 scoring layers.
    Empty weeks are included (sessions_count=0) for consistent charting.
    """
    target = _resolve_user_id(user, user_id)
    points = await build_progress_chart(target, db, weeks=weeks)
    return [
        ProgressPointResponse(
            period_start=p.period_start,
            period_end=p.period_end,
            sessions_count=p.sessions_count,
            avg_total=p.avg_total,
            avg_script=p.avg_script,
            avg_objection=p.avg_objection,
            avg_communication=p.avg_communication,
            avg_anti_patterns=p.avg_anti_patterns,
            avg_result=p.avg_result,
            best_score=p.best_score,
            worst_score=p.worst_score,
        )
        for p in points
    ]


@router.get("/me/archetype-scores", response_model=list[ArchetypeScoreResponse])
async def get_archetype_scores_endpoint(
    user_id: uuid.UUID | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Performance breakdown per character archetype.

    Includes all active archetypes — untrained ones appear with sessions_count=0.
    Mastery levels: untrained → beginner → intermediate → advanced → mastered.
    """
    target = _resolve_user_id(user, user_id)
    scores = await get_archetype_scores(target, db)
    return [
        ArchetypeScoreResponse(
            archetype_slug=s.archetype_slug,
            archetype_name=s.archetype_name,
            sessions_count=s.sessions_count,
            avg_score=s.avg_score,
            best_score=s.best_score,
            worst_score=s.worst_score,
            avg_script=s.avg_script,
            avg_objection=s.avg_objection,
            avg_communication=s.avg_communication,
            avg_anti_patterns=s.avg_anti_patterns,
            avg_result=s.avg_result,
            last_played=s.last_played.isoformat() if s.last_played else None,
            mastery_level=s.mastery_level,
        )
        for s in scores
    ]


@router.get("/me/recommendations", response_model=list[RecommendationResponse])
async def get_recommendations(
    user_id: uuid.UUID | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Smart scenario recommendations based on analytics.

    Algorithm priorities:
    1. Untrained archetypes (explore)
    2. Weakest archetype below 60 (train weakness)
    3. Not played in 7+ days (rotation to prevent avoidance)
    4. Push to mastery (harder scenarios for strong archetypes)
    5. Random variety
    """
    target = _resolve_user_id(user, user_id)
    recs = await generate_recommendations(target, db)
    return [
        RecommendationResponse(
            scenario_id=str(r.scenario_id),
            scenario_title=r.scenario_title,
            archetype_slug=r.archetype_slug,
            scenario_type=r.scenario_type,
            difficulty=r.difficulty,
            reason=r.reason,
            priority=r.priority,
        )
        for r in recs
    ]


@router.get("/me/insights", response_model=list[str])
async def get_insights(
    user_id: uuid.UUID | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Human-readable performance insights in Russian.

    Detects: improvement streaks, regression warnings, plateaus,
    fear avoidance patterns, speed issues, anti-pattern trends.
    """
    target = _resolve_user_id(user, user_id)
    return await generate_insights(target, db)


@router.get("/me/snapshot", response_model=FullSnapshotResponse)
async def get_full_snapshot(
    user_id: uuid.UUID | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Complete analytics snapshot — all data in one request.

    Use this instead of calling 5 separate endpoints.
    Ideal for the analytics dashboard page.
    """
    target = _resolve_user_id(user, user_id)
    snap = await build_full_snapshot(target, db)
    return FullSnapshotResponse(
        weak_spots=[
            WeakSpotResponse(
                skill=s.skill, sub_skill=s.sub_skill,
                avg_score=s.avg_score, max_possible=s.max_possible,
                pct=s.pct, trend=s.trend, trend_delta=s.trend_delta,
                archetype=s.archetype, recommendation=s.recommendation,
            )
            for s in snap.weak_spots
        ],
        progress=[
            ProgressPointResponse(
                period_start=p.period_start, period_end=p.period_end,
                sessions_count=p.sessions_count,
                avg_total=p.avg_total, avg_script=p.avg_script,
                avg_objection=p.avg_objection, avg_communication=p.avg_communication,
                avg_anti_patterns=p.avg_anti_patterns, avg_result=p.avg_result,
                best_score=p.best_score, worst_score=p.worst_score,
            )
            for p in snap.progress
        ],
        archetype_scores=[
            ArchetypeScoreResponse(
                archetype_slug=s.archetype_slug, archetype_name=s.archetype_name,
                sessions_count=s.sessions_count,
                avg_score=s.avg_score, best_score=s.best_score, worst_score=s.worst_score,
                avg_script=s.avg_script, avg_objection=s.avg_objection,
                avg_communication=s.avg_communication, avg_anti_patterns=s.avg_anti_patterns,
                avg_result=s.avg_result,
                last_played=s.last_played.isoformat() if s.last_played else None,
                mastery_level=s.mastery_level,
            )
            for s in snap.archetype_scores
        ],
        recommendations=[
            RecommendationResponse(
                scenario_id=str(r.scenario_id), scenario_title=r.scenario_title,
                archetype_slug=r.archetype_slug, scenario_type=r.scenario_type,
                difficulty=r.difficulty, reason=r.reason, priority=r.priority,
            )
            for r in snap.recommendations
        ],
        insights=snap.insights,
        meta=snap.meta,
    )
