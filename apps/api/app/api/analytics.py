"""Analytics API: weak spots, progress, archetype scores, recommendations, insights.

All endpoints are per-user (manager sees own data).
ROP/admin can view any user's analytics via user_id parameter.

This module also hosts the FE-telemetry collector at
``POST /analytics/events`` — see :func:`collect_events` for the
batch-ingest contract. It accepts anonymous (pre-login) traffic, so
it does NOT require an auth dep; rate-limit is per-IP.
"""

import logging
import uuid
from dataclasses import asdict
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors as err
from app.core.deps import get_current_user, get_current_user_optional
from app.core.rate_limit import limiter
from app.database import get_db
from app.models.analytics_event import AnalyticsEvent
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

logger = logging.getLogger(__name__)
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
            detail=err.OWN_ANALYTICS_ONLY,
        )
    return target_user_id


# ── FE telemetry collector ───────────────────────────────────────────────────


# Whitelist of accepted event names. Mirrors the FE EventName union in
# apps/web/src/lib/telemetry.ts. Adding new events requires updating
# both files. We reject unknowns rather than silently accepting any
# string so a typo on the FE doesn't poison the analytics table with
# garbage event_name values.
ALLOWED_EVENTS: frozenset[str] = frozenset({
    "script_panel_toggle",
    "script_example_copied",
    "script_drawer_auto_open",
    "stage_skipped",
    "whisper_script_clicked",
    "retrain_widget_shown",
    "retrain_widget_clicked",
    "coaching_mistake",
})

# Hard caps. Both bound the worst-case write — `MAX_EVENTS_PER_BATCH`
# matches the FE-side flush threshold; `MAX_PAYLOAD_BYTES` guards
# against a single oversized event tying up the JSONB write path.
MAX_EVENTS_PER_BATCH = 100
MAX_PAYLOAD_BYTES = 4 * 1024  # 4 KB per event payload


class TelemetryEventIn(BaseModel):
    name: str = Field(..., max_length=64)
    payload: dict = Field(default_factory=dict)
    occurred_at: datetime  # ISO 8601 with timezone — pydantic handles parse


class CollectEventsIn(BaseModel):
    events: list[TelemetryEventIn] = Field(..., min_length=1, max_length=MAX_EVENTS_PER_BATCH)
    # Anonymous session id: client-generated UUID stored in localStorage.
    # Lets us stitch one-browser sessions of events without identifying
    # the underlying user. Optional; some events (e.g. server-rendered
    # error pages) can't carry one.
    anon_session_id: uuid.UUID | None = None
    # Build-time SHA stamped into the FE bundle (NEXT_PUBLIC_RELEASE_SHA).
    # Useful for correlating event spikes / drops with a specific deploy.
    release_sha: str | None = Field(None, max_length=40)


class CollectEventsOut(BaseModel):
    accepted: int
    rejected: int


@router.post("/events", response_model=CollectEventsOut, status_code=status.HTTP_202_ACCEPTED)
# Per-IP cap. 120/min = 2 events/sec sustained per browser, well above
# normal usage (most users fire < 1 event/sec) and low enough that a
# misbehaving client can't flood the table. Anonymous traffic counts
# against the same bucket — we don't have a more specific identifier
# for unauthed callers anyway.
@limiter.limit("120/minute")
async def collect_events(
    request: Request,
    body: CollectEventsIn,
    user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
) -> CollectEventsOut:
    """Bulk-ingest FE telemetry events.

    Anonymous-OK: pre-login pages (login, register, reset-password)
    can fire events without auth. When the caller IS authed, we stamp
    `user_id` so per-user trails work; otherwise we rely on
    `anon_session_id` for stitching.

    Validation strategy:
      * Whitelist `name` against ALLOWED_EVENTS — typos are rejected,
        not silently stored. The whitelist mirrors the FE EventName
        union so adding a new event requires touching both sides.
      * Cap `payload` size at 4 KB. A 100-event batch with maxed-out
        payloads is ~400 KB, fine for a single JSONB write.
      * Cap batch length at 100 (Pydantic validator). FE flushes at 50.

    Errors are partial-tolerant: rejected events are skipped (counted
    in the response), accepted events still land. We don't want one
    bad event to drop a whole batch — that'd encourage clients to
    swallow rejections.
    """
    if len(body.events) > MAX_EVENTS_PER_BATCH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="too many events in batch",
        )

    user_agent = request.headers.get("user-agent", "")[:256] or None

    rows: list[dict] = []
    rejected = 0
    for evt in body.events:
        if evt.name not in ALLOWED_EVENTS:
            rejected += 1
            continue
        # Size-bound the payload. Use len() of repr as a cheap
        # approximation; exact UTF-8 byte size would require
        # serialising twice.
        if len(repr(evt.payload)) > MAX_PAYLOAD_BYTES:
            rejected += 1
            continue
        rows.append({
            "user_id": user.id if user else None,
            "anon_session_id": body.anon_session_id,
            "event_name": evt.name,
            "payload": evt.payload,
            "occurred_at": evt.occurred_at,
            "release_sha": body.release_sha,
            "user_agent": user_agent,
        })

    if rows:
        try:
            await db.execute(insert(AnalyticsEvent), rows)
            await db.commit()
        except Exception as exc:
            # Telemetry must never break the user flow. Log + roll back +
            # report all-rejected so the client doesn't retry forever
            # on a row that DB will keep refusing.
            logger.warning(
                "Analytics insert failed; dropping batch",
                extra={"count": len(rows), "error": str(exc)},
            )
            await db.rollback()
            return CollectEventsOut(accepted=0, rejected=rejected + len(rows))

    return CollectEventsOut(accepted=len(rows), rejected=rejected)


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
