"""Manager Wiki API — ADMIN & ROP.

All endpoints require admin or rop role. Admins and ROPs can view wiki data
for ANY manager (by manager_id) or list all wikis.

Phase 1 additions:
  PUT    /wiki/{manager_id}/pages/{page_path}       -- edit page content
  POST   /wiki/{manager_id}/ingest-all              -- ingest all un-ingested sessions
  GET    /wiki/{manager_id}/export                  -- export wiki (pdf/csv)
  POST   /wiki/synthesis/daily                      -- trigger daily synthesis
  POST   /wiki/synthesis/weekly                     -- trigger weekly synthesis
  GET    /wiki/scheduler/status                     -- wiki scheduler status
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_role
from app.database import get_db
from app.models.manager_wiki import (
    ManagerPattern,
    ManagerTechnique,
    ManagerWiki,
    WikiAction,
    WikiPage,
    WikiPageType,
    WikiUpdateLog,
)
from app.models.user import User

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/wiki", tags=["wiki"])

# ═══════════════════════════════════════════════════════════════════════════
# SECURITY: Every endpoint requires admin role.
# No manager can access wiki data — only admin.
# ═══════════════════════════════════════════════════════════════════════════


# ---------------------------------------------------------------------------
# GET /api/wiki/global/stats — aggregate stats across all wikis (admin only)
# NOTE: Must be BEFORE /{manager_id} routes to avoid path conflict
# ---------------------------------------------------------------------------

@router.get("/global/stats")
async def global_wiki_stats(
    admin: User = Depends(require_role("admin", "rop")),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate wiki stats across all managers. Admin only."""
    result = await db.execute(
        select(
            func.count(ManagerWiki.id).label("total_wikis"),
            func.sum(ManagerWiki.sessions_ingested).label("total_sessions"),
            func.sum(ManagerWiki.patterns_discovered).label("total_patterns"),
            func.sum(ManagerWiki.pages_count).label("total_pages"),
            func.sum(ManagerWiki.total_tokens_used).label("total_tokens"),
        )
    )
    row = result.one()

    return {
        "total_wikis": row.total_wikis or 0,
        "total_sessions_ingested": row.total_sessions or 0,
        "total_patterns_discovered": row.total_patterns or 0,
        "total_pages": row.total_pages or 0,
        "total_tokens_used": row.total_tokens or 0,
    }


# ---------------------------------------------------------------------------
# GET /api/wiki/managers — list all managers who have wikis (admin only)
# ---------------------------------------------------------------------------

@router.get("/managers")
async def list_all_wikis(
    admin: User = Depends(require_role("admin", "rop")),
    db: AsyncSession = Depends(get_db),
):
    """List all manager wikis with basic stats. Admin only."""
    result = await db.execute(
        select(ManagerWiki, User)
        .join(User, ManagerWiki.manager_id == User.id)
        .order_by(ManagerWiki.last_ingest_at.desc().nullslast())
    )
    rows = result.all()

    return {
        "wikis": [
            {
                "wiki_id": str(wiki.id),
                "manager_id": str(user.id),
                "manager_name": user.full_name or user.email or "—",
                "manager_role": user.role.value if user.role else "manager",
                "status": str(wiki.status) if wiki.status else "active",
                "sessions_ingested": wiki.sessions_ingested,
                "patterns_discovered": wiki.patterns_discovered,
                "pages_count": wiki.pages_count,
                "total_tokens_used": wiki.total_tokens_used,
                "last_ingest_at": wiki.last_ingest_at.isoformat() if wiki.last_ingest_at else None,
                "created_at": wiki.created_at.isoformat() if wiki.created_at else None,
            }
            for wiki, user in rows
        ]
    }


# ---------------------------------------------------------------------------
# POST /api/wiki/synthesis/daily — trigger daily synthesis (admin only)
# NOTE: Static paths MUST be BEFORE /{manager_id} routes
# ---------------------------------------------------------------------------

@router.post("/synthesis/daily")
@limiter.limit("5/minute")
async def trigger_daily_synthesis(
    request: Request,
    manager_id: uuid.UUID | None = Query(None, description="Specific manager, or all if omitted"),
    admin: User = Depends(require_role("admin", "rop")),
    db: AsyncSession = Depends(get_db),
):
    """Trigger daily synthesis for one or all managers. Admin only."""
    from app.services.wiki_synthesis_service import run_daily_synthesis

    results = await run_daily_synthesis(db, manager_id=manager_id)
    return results


@router.post("/synthesis/weekly")
@limiter.limit("3/minute")
async def trigger_weekly_synthesis(
    request: Request,
    manager_id: uuid.UUID | None = Query(None, description="Specific manager, or all if omitted"),
    admin: User = Depends(require_role("admin", "rop")),
    db: AsyncSession = Depends(get_db),
):
    """Trigger weekly synthesis for one or all managers. Admin only."""
    from app.services.wiki_synthesis_service import run_weekly_synthesis

    results = await run_weekly_synthesis(db, manager_id=manager_id)
    return results


# ---------------------------------------------------------------------------
# GET /api/wiki/scheduler/status — wiki scheduler status (admin only)
# ---------------------------------------------------------------------------

@router.get("/scheduler/status")
async def get_scheduler_status(
    admin: User = Depends(require_role("admin", "rop")),
):
    """Get wiki scheduler status. Admin only."""
    from app.services.wiki_scheduler import wiki_scheduler

    return wiki_scheduler.get_status()


# ---------------------------------------------------------------------------
# GET /api/wiki/dashboard/charts — aggregated chart data (admin only)
# ---------------------------------------------------------------------------

@router.get("/dashboard/charts")
async def get_wiki_dashboard_charts(
    days: int = Query(30, ge=7, le=90),
    admin: User = Depends(require_role("admin", "rop")),
    db: AsyncSession = Depends(get_db),
):
    """Get chart data for wiki dashboard: activity timeline, pattern distribution, score trends."""
    from app.models.training import TrainingSession, SessionStatus
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)

    # 1. Sessions per day (for activity chart)
    sessions_r = await db.execute(
        select(
            func.date(TrainingSession.started_at).label("day"),
            func.count(TrainingSession.id).label("count"),
            func.avg(TrainingSession.score_total).label("avg_score"),
        )
        .where(
            TrainingSession.status == SessionStatus.completed,
            TrainingSession.started_at >= since,
        )
        .group_by(func.date(TrainingSession.started_at))
        .order_by(func.date(TrainingSession.started_at))
    )
    daily_sessions = [
        {
            "date": str(row.day),
            "sessions": row.count,
            "avg_score": round(float(row.avg_score or 0), 1),
        }
        for row in sessions_r.all()
    ]

    # 2. Pattern distribution by category
    from app.models.manager_wiki import ManagerPattern
    patterns_r = await db.execute(
        select(
            ManagerPattern.category,
            func.count(ManagerPattern.id),
        )
        .group_by(ManagerPattern.category)
    )
    pattern_distribution = [
        {"category": str(row[0]) if row[0] else "unknown", "count": row[1]}
        for row in patterns_r.all()
    ]

    # 3. Wiki growth over time (ingests per day)
    ingests_r = await db.execute(
        select(
            func.date(WikiUpdateLog.started_at).label("day"),
            func.count(WikiUpdateLog.id).label("count"),
            func.sum(WikiUpdateLog.pages_created).label("pages_new"),
            func.sum(WikiUpdateLog.pages_modified).label("pages_mod"),
        )
        .where(WikiUpdateLog.started_at >= since)
        .group_by(func.date(WikiUpdateLog.started_at))
        .order_by(func.date(WikiUpdateLog.started_at))
    )
    wiki_activity = [
        {
            "date": str(row.day),
            "ingests": row.count,
            "pages_created": row.pages_new or 0,
            "pages_modified": row.pages_mod or 0,
        }
        for row in ingests_r.all()
    ]

    # 4. Top managers by patterns
    top_managers_r = await db.execute(
        select(
            ManagerWiki.manager_id,
            ManagerWiki.sessions_ingested,
            ManagerWiki.patterns_discovered,
            ManagerWiki.pages_count,
            User.full_name,
        )
        .join(User, User.id == ManagerWiki.manager_id)
        .order_by(ManagerWiki.patterns_discovered.desc())
        .limit(10)
    )
    top_managers = [
        {
            "manager_id": str(row.manager_id),
            "name": row.full_name or "—",
            "sessions": row.sessions_ingested,
            "patterns": row.patterns_discovered,
            "pages": row.pages_count,
        }
        for row in top_managers_r.all()
    ]

    return {
        "period_days": days,
        "daily_sessions": daily_sessions,
        "pattern_distribution": pattern_distribution,
        "wiki_activity": wiki_activity,
        "top_managers": top_managers,
    }


# ---------------------------------------------------------------------------
# GET /api/wiki/compare — side-by-side manager comparison (Feature 9)
# ---------------------------------------------------------------------------

@router.get("/compare")
async def compare_managers(
    ids: str = Query(..., description="Comma-separated manager IDs (2-5)"),
    admin: User = Depends(require_role("admin", "rop")),
    db: AsyncSession = Depends(get_db),
):
    """Compare patterns, techniques, scores and skills for 2-5 managers side-by-side."""
    from app.models.training import TrainingSession, SessionStatus
    from app.models.progress import ManagerProgress

    manager_ids = [uuid.UUID(mid.strip()) for mid in ids.split(",") if mid.strip()]
    if len(manager_ids) < 2 or len(manager_ids) > 5:
        raise HTTPException(status_code=400, detail="Provide 2-5 manager IDs")

    managers_data = []
    for mid in manager_ids:
        # Basic info
        mgr = await db.get(User, mid)
        if not mgr:
            continue

        # Wiki stats
        wiki_r = await db.execute(select(ManagerWiki).where(ManagerWiki.manager_id == mid))
        wiki = wiki_r.scalar_one_or_none()

        # Patterns
        patterns_r = await db.execute(
            select(ManagerPattern).where(ManagerPattern.manager_id == mid)
        )
        patterns = patterns_r.scalars().all()

        # Techniques
        techs_r = await db.execute(
            select(ManagerTechnique).where(ManagerTechnique.manager_id == mid)
        )
        techniques = techs_r.scalars().all()

        # Training stats
        sessions_r = await db.execute(
            select(
                func.count(TrainingSession.id).label("total"),
                func.avg(TrainingSession.score_total).label("avg_score"),
                func.max(TrainingSession.score_total).label("best_score"),
                func.min(TrainingSession.score_total).label("worst_score"),
                func.avg(TrainingSession.score_script_adherence).label("avg_script"),
                func.avg(TrainingSession.score_objection_handling).label("avg_objection"),
                func.avg(TrainingSession.score_communication).label("avg_communication"),
                func.avg(TrainingSession.score_anti_patterns).label("avg_anti_patterns"),
                func.avg(TrainingSession.score_result).label("avg_result"),
            ).where(
                TrainingSession.user_id == mid,
                TrainingSession.status == SessionStatus.completed,
            )
        )
        stats = sessions_r.one()

        # Skills from progress
        progress_r = await db.execute(
            select(ManagerProgress).where(ManagerProgress.user_id == mid)
        )
        progress = progress_r.scalar_one_or_none()

        skills = {}
        if progress:
            skills = {
                "empathy": progress.skill_empathy,
                "knowledge": progress.skill_knowledge,
                "objection_handling": progress.skill_objection_handling,
                "stress_resistance": progress.skill_stress_resistance,
                "closing": progress.skill_closing,
                "qualification": progress.skill_qualification,
            }

        # Pattern breakdown by category
        pattern_cats = {}
        for p in patterns:
            cat = str(p.category) if p.category else "unknown"
            pattern_cats[cat] = pattern_cats.get(cat, 0) + 1

        managers_data.append({
            "manager_id": str(mid),
            "name": mgr.full_name or mgr.email or "—",
            "sessions_total": stats.total or 0,
            "avg_score": round(float(stats.avg_score or 0), 1),
            "best_score": round(float(stats.best_score or 0), 1),
            "worst_score": round(float(stats.worst_score or 0), 1),
            "score_layers": {
                "script_adherence": round(float(stats.avg_script or 0), 1),
                "objection_handling": round(float(stats.avg_objection or 0), 1),
                "communication": round(float(stats.avg_communication or 0), 1),
                "anti_patterns": round(float(stats.avg_anti_patterns or 0), 1),
                "result": round(float(stats.avg_result or 0), 1),
            },
            "skills": skills,
            "patterns_total": len(patterns),
            "patterns_by_category": pattern_cats,
            "patterns": [
                {
                    "code": p.pattern_code,
                    "category": str(p.category) if p.category else "unknown",
                    "description": p.description,
                    "sessions_count": p.sessions_in_pattern,
                    "confirmed": p.confirmed_at is not None,
                }
                for p in patterns[:10]
            ],
            "techniques_total": len(techniques),
            "techniques": [
                {
                    "code": t.technique_code,
                    "name": t.technique_name,
                    "success_rate": round(t.success_rate, 2),
                    "attempts": t.attempt_count,
                }
                for t in techniques[:10]
            ],
            "wiki_pages": wiki.pages_count if wiki else 0,
            "wiki_sessions_ingested": wiki.sessions_ingested if wiki else 0,
        })

    return {
        "managers": managers_data,
        "count": len(managers_data),
    }


# ---------------------------------------------------------------------------
# GET /api/wiki/manager/{manager_id}/enriched — enriched profile (Feature 8)
# ---------------------------------------------------------------------------

@router.get("/manager/{manager_id}/enriched")
async def get_manager_enriched_profile(
    manager_id: uuid.UUID,
    admin: User = Depends(require_role("admin", "rop")),
    db: AsyncSession = Depends(get_db),
):
    """Get enriched manager profile with pipeline stats, progress data, and wiki combined."""
    from app.models.training import TrainingSession, SessionStatus
    from app.models.progress import ManagerProgress
    from app.models.client import RealClient
    from datetime import timedelta

    mgr = await db.get(User, manager_id)
    if not mgr:
        raise HTTPException(status_code=404, detail="Manager not found")

    now = datetime.now(timezone.utc)

    # Wiki data
    wiki_r = await db.execute(select(ManagerWiki).where(ManagerWiki.manager_id == manager_id))
    wiki = wiki_r.scalar_one_or_none()

    # Training stats (all time + last 14 days)
    all_stats_r = await db.execute(
        select(
            func.count(TrainingSession.id),
            func.avg(TrainingSession.score_total),
            func.max(TrainingSession.score_total),
            func.sum(TrainingSession.duration_seconds),
        ).where(
            TrainingSession.user_id == manager_id,
            TrainingSession.status == SessionStatus.completed,
        )
    )
    all_stats = all_stats_r.one()

    recent_stats_r = await db.execute(
        select(
            func.count(TrainingSession.id),
            func.avg(TrainingSession.score_total),
        ).where(
            TrainingSession.user_id == manager_id,
            TrainingSession.status == SessionStatus.completed,
            TrainingSession.started_at >= now - timedelta(days=14),
        )
    )
    recent_stats = recent_stats_r.one()

    # Skills
    progress_r = await db.execute(
        select(ManagerProgress).where(ManagerProgress.user_id == manager_id)
    )
    progress = progress_r.scalar_one_or_none()

    skills = {}
    if progress:
        skills = {
            "empathy": progress.skill_empathy,
            "knowledge": progress.skill_knowledge,
            "objection_handling": progress.skill_objection_handling,
            "stress_resistance": progress.skill_stress_resistance,
            "closing": progress.skill_closing,
            "qualification": progress.skill_qualification,
            "level": progress.current_level,
            "total_xp": progress.total_xp,
            "hunter_score": progress.hunter_score,
        }

    # Pipeline stats
    pipeline = {}
    try:
        pipeline_r = await db.execute(
            select(
                RealClient.status,
                func.count(RealClient.id),
                func.sum(RealClient.debt_amount),
            ).where(
                RealClient.manager_id == manager_id,
                RealClient.is_active == True,
            ).group_by(RealClient.status)
        )
        for row in pipeline_r.all():
            status_str = row[0].value if hasattr(row[0], 'value') else str(row[0])
            pipeline[status_str] = {
                "count": row[1],
                "total_debt": float(row[2] or 0),
            }
    except Exception:
        pass  # Client module may not have data

    # Patterns summary
    patterns_r = await db.execute(
        select(ManagerPattern).where(ManagerPattern.manager_id == manager_id)
    )
    patterns = patterns_r.scalars().all()
    weaknesses = [p for p in patterns if str(p.category) == "weakness"]
    strengths = [p for p in patterns if str(p.category) == "strength"]

    # Techniques
    techs_r = await db.execute(
        select(ManagerTechnique).where(ManagerTechnique.manager_id == manager_id)
        .order_by(ManagerTechnique.success_rate.desc())
    )
    techniques = techs_r.scalars().all()

    # Score trend (last 10 sessions)
    trend_r = await db.execute(
        select(TrainingSession.score_total, TrainingSession.started_at)
        .where(
            TrainingSession.user_id == manager_id,
            TrainingSession.status == SessionStatus.completed,
        )
        .order_by(TrainingSession.started_at.desc())
        .limit(10)
    )
    score_trend = [
        {"score": round(float(r.score_total or 0), 1), "date": r.started_at.isoformat()}
        for r in trend_r.all()
    ][::-1]  # Reverse to chronological

    return {
        "manager_id": str(manager_id),
        "name": mgr.full_name or mgr.email or "—",
        "training": {
            "total_sessions": all_stats[0] or 0,
            "avg_score": round(float(all_stats[1] or 0), 1),
            "best_score": round(float(all_stats[2] or 0), 1),
            "total_hours": round(float(all_stats[3] or 0) / 3600, 1),
            "recent_14d_sessions": recent_stats[0] or 0,
            "recent_14d_avg_score": round(float(recent_stats[1] or 0), 1),
            "score_trend": score_trend,
        },
        "skills": skills,
        "pipeline": pipeline,
        "wiki": {
            "exists": wiki is not None,
            "pages_count": wiki.pages_count if wiki else 0,
            "sessions_ingested": wiki.sessions_ingested if wiki else 0,
            "patterns_discovered": wiki.patterns_discovered if wiki else 0,
        },
        "patterns_summary": {
            "total": len(patterns),
            "weaknesses": len(weaknesses),
            "strengths": len(strengths),
            "top_weaknesses": [
                {"code": p.pattern_code, "description": p.description, "count": p.sessions_in_pattern}
                for p in weaknesses[:5]
            ],
            "top_strengths": [
                {"code": p.pattern_code, "description": p.description, "count": p.sessions_in_pattern}
                for p in strengths[:5]
            ],
        },
        "techniques_summary": {
            "total": len(techniques),
            "best": [
                {"name": t.technique_name, "success_rate": round(t.success_rate, 2), "attempts": t.attempt_count}
                for t in techniques[:5]
            ],
        },
    }


# ---------------------------------------------------------------------------
# PUT /api/wiki/{manager_id}/status — pause/resume wiki
# Must be BEFORE /{manager_id} generic route
# ---------------------------------------------------------------------------

@router.put("/manager/{manager_id}/status")
@limiter.limit("10/minute")
async def update_wiki_status(
    request: Request,
    manager_id: uuid.UUID,
    data: dict,
    admin: User = Depends(require_role("admin", "rop")),
    db: AsyncSession = Depends(get_db),
):
    """Pause, resume, or archive a manager's wiki. Admin only."""
    result = await db.execute(
        select(ManagerWiki).where(ManagerWiki.manager_id == manager_id)
    )
    wiki = result.scalar_one_or_none()
    if not wiki:
        raise HTTPException(status_code=404, detail="Wiki not found")

    new_status = data.get("status")
    if new_status not in ("active", "paused", "archived"):
        raise HTTPException(status_code=400, detail="Invalid status. Must be: active, paused, archived")

    old_status = wiki.status
    wiki.status = new_status
    await db.commit()

    return {
        "manager_id": str(manager_id),
        "old_status": old_status,
        "new_status": new_status,
        "message": f"Wiki status changed: {old_status} → {new_status}",
    }


# ---------------------------------------------------------------------------
# POST /api/wiki/{manager_id}/reanalyze — re-analyze all sessions (admin only)
# Must be BEFORE /{manager_id} generic route
# ---------------------------------------------------------------------------

@router.post("/manager/{manager_id}/reanalyze")
@limiter.limit("2/minute")
async def reanalyze_wiki(
    request: Request,
    manager_id: uuid.UUID,
    admin: User = Depends(require_role("admin", "rop")),
    db: AsyncSession = Depends(get_db),
):
    """Wipe wiki pages and re-analyze all sessions from scratch. Admin only."""
    result = await db.execute(
        select(ManagerWiki).where(ManagerWiki.manager_id == manager_id)
    )
    wiki = result.scalar_one_or_none()
    if not wiki:
        raise HTTPException(status_code=404, detail="Wiki not found")

    from app.models.manager_wiki import WikiPage as _WP

    # Delete all existing pages
    pages_r = await db.execute(select(_WP).where(_WP.wiki_id == wiki.id))
    old_pages = pages_r.scalars().all()
    for p in old_pages:
        await db.delete(p)

    # Reset counters
    wiki.pages_count = 0
    wiki.sessions_ingested = 0
    wiki.patterns_discovered = 0

    # Add audit log
    log_entry = WikiUpdateLog(
        wiki_id=wiki.id,
        action="manual_edit",
        description=f"Full re-analyze triggered by admin {admin.full_name or admin.email}",
        pages_modified=0,
        pages_created=0,
        status="completed",
        completed_at=datetime.now(timezone.utc),
    )
    db.add(log_entry)
    await db.commit()

    # Now ingest all sessions
    from app.models.training import TrainingSession, SessionStatus
    from app.services.wiki_ingest_service import ingest_session

    sessions_r = await db.execute(
        select(TrainingSession.id).where(
            TrainingSession.user_id == manager_id,
            TrainingSession.status == SessionStatus.completed,
        ).order_by(TrainingSession.started_at)
    )
    session_ids = [row[0] for row in sessions_r.all()]

    results = []
    for sid in session_ids[:20]:  # Cap at 20
        try:
            r = await ingest_session(sid, db)
            results.append({"session_id": str(sid), **r})
        except Exception as e:
            results.append({"session_id": str(sid), "status": "error", "error": str(e)[:200]})

    return {
        "message": f"Re-analysis started: {len(old_pages)} old pages deleted, {len(session_ids)} sessions to process",
        "old_pages_deleted": len(old_pages),
        "sessions_total": len(session_ids),
        "processed": len(results),
        "results": results,
    }


# ---------------------------------------------------------------------------
# GET /api/wiki/{manager_id} — wiki overview for specific manager (admin only)
# ---------------------------------------------------------------------------

@router.get("/{manager_id}")
async def get_manager_wiki(
    manager_id: uuid.UUID,
    admin: User = Depends(require_role("admin", "rop")),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific manager's wiki overview. Admin only."""
    result = await db.execute(
        select(ManagerWiki).where(ManagerWiki.manager_id == manager_id)
    )
    wiki = result.scalar_one_or_none()
    if not wiki:
        return {
            "exists": False,
            "manager_id": str(manager_id),
            "sessions_ingested": 0,
            "patterns_discovered": 0,
            "pages_count": 0,
        }

    # Also fetch manager name
    manager = await db.get(User, manager_id)
    manager_name = manager.full_name if manager else "—"

    return {
        "exists": True,
        "id": str(wiki.id),
        "manager_id": str(manager_id),
        "manager_name": manager_name,
        "status": str(wiki.status) if wiki.status else "active",
        "sessions_ingested": wiki.sessions_ingested,
        "patterns_discovered": wiki.patterns_discovered,
        "pages_count": wiki.pages_count,
        "total_tokens_used": wiki.total_tokens_used,
        "last_ingest_at": wiki.last_ingest_at.isoformat() if wiki.last_ingest_at else None,
        "created_at": wiki.created_at.isoformat() if wiki.created_at else None,
    }


# ---------------------------------------------------------------------------
# GET /api/wiki/{manager_id}/pages — all wiki pages for a manager (admin only)
# ---------------------------------------------------------------------------

@router.get("/{manager_id}/pages")
async def list_manager_wiki_pages(
    manager_id: uuid.UUID,
    admin: User = Depends(require_role("admin", "rop")),
    db: AsyncSession = Depends(get_db),
):
    """List all wiki pages for a given manager. Admin only."""
    result = await db.execute(
        select(ManagerWiki).where(ManagerWiki.manager_id == manager_id)
    )
    wiki = result.scalar_one_or_none()
    if not wiki:
        return {"pages": []}

    pages_result = await db.execute(
        select(WikiPage)
        .where(WikiPage.wiki_id == wiki.id)
        .order_by(WikiPage.page_path)
    )
    pages = pages_result.scalars().all()

    return {
        "pages": [
            {
                "id": str(p.id),
                "page_path": p.page_path,
                "page_type": str(p.page_type) if p.page_type else "overview",
                "version": p.version,
                "tags": p.tags or [],
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            }
            for p in pages
        ]
    }


# ---------------------------------------------------------------------------
# GET /api/wiki/{manager_id}/pages/{page_path:path} — specific page (admin only)
# ---------------------------------------------------------------------------

@router.get("/{manager_id}/pages/{page_path:path}")
async def get_manager_wiki_page(
    manager_id: uuid.UUID,
    page_path: str,
    admin: User = Depends(require_role("admin", "rop")),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific wiki page content. Admin only."""
    result = await db.execute(
        select(ManagerWiki).where(ManagerWiki.manager_id == manager_id)
    )
    wiki = result.scalar_one_or_none()
    if not wiki:
        raise HTTPException(status_code=404, detail="Wiki not found for this manager")

    page_result = await db.execute(
        select(WikiPage).where(
            WikiPage.wiki_id == wiki.id,
            WikiPage.page_path == page_path,
        )
    )
    page = page_result.scalar_one_or_none()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    return {
        "id": str(page.id),
        "page_path": page.page_path,
        "content": page.content,
        "page_type": str(page.page_type) if page.page_type else "overview",
        "version": page.version,
        "tags": page.tags or [],
        "source_sessions": page.source_sessions or [],
        "created_at": page.created_at.isoformat() if page.created_at else None,
        "updated_at": page.updated_at.isoformat() if page.updated_at else None,
    }


# ---------------------------------------------------------------------------
# GET /api/wiki/{manager_id}/patterns — patterns for a manager (admin only)
# ---------------------------------------------------------------------------

@router.get("/{manager_id}/patterns")
async def list_manager_patterns(
    manager_id: uuid.UUID,
    admin: User = Depends(require_role("admin", "rop")),
    db: AsyncSession = Depends(get_db),
):
    """List all discovered behavioral patterns for a manager. Admin only."""
    result = await db.execute(
        select(ManagerPattern)
        .where(ManagerPattern.manager_id == manager_id)
        .order_by(ManagerPattern.discovered_at.desc())
    )
    patterns = result.scalars().all()

    return {
        "patterns": [
            {
                "id": str(p.id),
                "pattern_code": p.pattern_code,
                "category": str(p.category) if p.category else "weakness",
                "description": p.description,
                "sessions_in_pattern": p.sessions_in_pattern,
                "impact_on_score_delta": p.impact_on_score_delta,
                "archetype_filter": p.archetype_filter,
                "mitigation_technique": p.mitigation_technique,
                "discovered_at": p.discovered_at.isoformat() if p.discovered_at else None,
                "confirmed_at": p.confirmed_at.isoformat() if p.confirmed_at else None,
                "is_confirmed": p.confirmed_at is not None,
            }
            for p in patterns
        ]
    }


# ---------------------------------------------------------------------------
# GET /api/wiki/{manager_id}/techniques — techniques for a manager (admin only)
# ---------------------------------------------------------------------------

@router.get("/{manager_id}/techniques")
async def list_manager_techniques(
    manager_id: uuid.UUID,
    admin: User = Depends(require_role("admin", "rop")),
    db: AsyncSession = Depends(get_db),
):
    """List all effective techniques for a manager. Admin only."""
    result = await db.execute(
        select(ManagerTechnique)
        .where(ManagerTechnique.manager_id == manager_id)
        .order_by(ManagerTechnique.success_rate.desc())
    )
    techniques = result.scalars().all()

    return {
        "techniques": [
            {
                "id": str(t.id),
                "technique_code": t.technique_code,
                "technique_name": t.technique_name,
                "description": t.description,
                "applicable_to_archetype": t.applicable_to_archetype,
                "success_count": t.success_count,
                "attempt_count": t.attempt_count,
                "success_rate": round(t.success_rate, 2),
                "how_to_apply": t.how_to_apply,
                "discovered_at": t.discovered_at.isoformat() if t.discovered_at else None,
            }
            for t in techniques
        ]
    }


# ---------------------------------------------------------------------------
# GET /api/wiki/{manager_id}/log — update history for a manager (admin only)
# ---------------------------------------------------------------------------

@router.get("/{manager_id}/log")
async def list_manager_wiki_log(
    manager_id: uuid.UUID,
    admin: User = Depends(require_role("admin", "rop")),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
):
    """Get wiki update history for a manager. Admin only."""
    result = await db.execute(
        select(ManagerWiki).where(ManagerWiki.manager_id == manager_id)
    )
    wiki = result.scalar_one_or_none()
    if not wiki:
        return {"log": []}

    log_result = await db.execute(
        select(WikiUpdateLog)
        .where(WikiUpdateLog.wiki_id == wiki.id)
        .order_by(WikiUpdateLog.started_at.desc())
        .limit(limit)
    )
    logs = log_result.scalars().all()

    return {
        "log": [
            {
                "id": str(entry.id),
                "action": str(entry.action) if entry.action else "ingest_session",
                "description": entry.description,
                "pages_modified": entry.pages_modified,
                "pages_created": entry.pages_created,
                "patterns_discovered": entry.patterns_discovered or [],
                "tokens_used": entry.tokens_used,
                "status": entry.status,
                "started_at": entry.started_at.isoformat() if entry.started_at else None,
                "completed_at": entry.completed_at.isoformat() if entry.completed_at else None,
                "error_msg": entry.error_msg,
            }
            for entry in logs
        ]
    }


# ---------------------------------------------------------------------------
# POST /api/wiki/{manager_id}/ingest/{session_id} — manual ingest (admin only)
# ---------------------------------------------------------------------------

@router.post("/{manager_id}/ingest/{session_id}")
async def trigger_ingest(
    manager_id: uuid.UUID,
    session_id: uuid.UUID,
    admin: User = Depends(require_role("admin", "rop")),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger wiki ingest for a specific training session. Admin only."""
    from app.models.training import TrainingSession

    # Verify session belongs to the specified manager
    session = await db.get(TrainingSession, session_id)
    if not session or session.user_id != manager_id:
        raise HTTPException(status_code=404, detail="Session not found for this manager")

    from app.services.wiki_ingest_service import ingest_session

    result = await ingest_session(session_id, db)
    return result


# ---------------------------------------------------------------------------
# PUT /api/wiki/{manager_id}/pages/{page_path:path} — edit page (admin only)
# ---------------------------------------------------------------------------

@router.put("/{manager_id}/pages/{page_path:path}")
@limiter.limit("20/minute")
async def update_wiki_page(
    request: Request,
    manager_id: uuid.UUID,
    page_path: str,
    data: dict,
    admin: User = Depends(require_role("admin", "rop")),
    db: AsyncSession = Depends(get_db),
):
    """Edit a wiki page content. Admin only. Logs as manual_edit."""
    result = await db.execute(
        select(ManagerWiki).where(ManagerWiki.manager_id == manager_id)
    )
    wiki = result.scalar_one_or_none()
    if not wiki:
        raise HTTPException(status_code=404, detail="Wiki not found for this manager")

    page_result = await db.execute(
        select(WikiPage).where(
            WikiPage.wiki_id == wiki.id,
            WikiPage.page_path == page_path,
        )
    )
    page = page_result.scalar_one_or_none()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    new_content = data.get("content")
    if not new_content or not new_content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")

    old_version = page.version
    page.content = new_content.strip()
    page.version += 1
    page.updated_at = datetime.now(timezone.utc)

    # Audit log entry
    log_entry = WikiUpdateLog(
        wiki_id=wiki.id,
        action=WikiAction.manual_edit,
        description=f"Manual edit by admin {admin.full_name or admin.email}: page '{page_path}' v{old_version} → v{page.version}",
        pages_modified=1,
        pages_created=0,
        status="completed",
        completed_at=datetime.now(timezone.utc),
    )
    db.add(log_entry)
    await db.commit()

    return {
        "id": str(page.id),
        "page_path": page.page_path,
        "version": page.version,
        "message": "Page updated",
    }


# ---------------------------------------------------------------------------
# POST /api/wiki/{manager_id}/ingest-all — ingest all un-ingested sessions
# ---------------------------------------------------------------------------

@router.post("/{manager_id}/ingest-all")
@limiter.limit("3/minute")
async def ingest_all_sessions(
    request: Request,
    manager_id: uuid.UUID,
    admin: User = Depends(require_role("admin", "rop")),
    db: AsyncSession = Depends(get_db),
):
    """Ingest all completed sessions that haven't been ingested yet. Admin only."""
    from app.models.training import TrainingSession, SessionStatus

    # Verify manager exists
    manager = await db.get(User, manager_id)
    if not manager:
        raise HTTPException(status_code=404, detail="Manager not found")

    # Get wiki (or it will be created during first ingest)
    wiki_r = await db.execute(
        select(ManagerWiki).where(ManagerWiki.manager_id == manager_id)
    )
    wiki = wiki_r.scalar_one_or_none()

    # Get IDs of already-ingested sessions from log
    ingested_ids = set()
    if wiki:
        log_r = await db.execute(
            select(WikiUpdateLog.triggered_by_session_id).where(
                WikiUpdateLog.wiki_id == wiki.id,
                WikiUpdateLog.action == WikiAction.ingest_session,
                WikiUpdateLog.status == "completed",
            )
        )
        ingested_ids = {row[0] for row in log_r.all() if row[0]}

    # Get all completed sessions for this manager
    sessions_r = await db.execute(
        select(TrainingSession.id).where(
            TrainingSession.user_id == manager_id,
            TrainingSession.status == SessionStatus.completed,
        ).order_by(TrainingSession.started_at)
    )
    all_session_ids = [row[0] for row in sessions_r.all()]
    to_ingest = [sid for sid in all_session_ids if sid not in ingested_ids]

    if not to_ingest:
        return {"message": "All sessions already ingested", "ingested": 0, "total": len(all_session_ids)}

    from app.services.wiki_ingest_service import ingest_session

    results = []
    for sid in to_ingest[:20]:  # Cap at 20 per request to avoid timeout
        try:
            r = await ingest_session(sid, db)
            results.append({"session_id": str(sid), **r})
        except Exception as e:
            results.append({"session_id": str(sid), "status": "error", "error": str(e)[:200]})

    return {
        "message": f"Ingested {len(results)} sessions",
        "ingested": len([r for r in results if r.get("status") == "ingested"]),
        "total_pending": len(to_ingest),
        "capped_at": 20,
        "results": results,
    }


# ---------------------------------------------------------------------------
# GET /api/wiki/{manager_id}/export — export wiki (pdf/csv)
# ---------------------------------------------------------------------------

@router.get("/{manager_id}/export")
async def export_wiki(
    manager_id: uuid.UUID,
    format: str = Query("pdf", regex="^(pdf|csv)$"),
    admin: User = Depends(require_role("admin", "rop")),
    db: AsyncSession = Depends(get_db),
):
    """Export wiki data for a manager. Formats: pdf, csv. Admin only."""
    from app.services.wiki_export_service import export_wiki_pdf, export_wiki_csv

    # Verify wiki exists
    result = await db.execute(
        select(ManagerWiki).where(ManagerWiki.manager_id == manager_id)
    )
    wiki = result.scalar_one_or_none()
    if not wiki:
        raise HTTPException(status_code=404, detail="Wiki not found for this manager")

    # Get manager name
    manager = await db.get(User, manager_id)
    manager_name = manager.full_name if manager else "manager"

    # Use ASCII-safe filename for Content-Disposition header
    safe_name = str(manager_id)[:8]

    if format == "pdf":
        pdf_bytes = await export_wiki_pdf(wiki.id, manager_name, db)
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="wiki_{safe_name}.pdf"'},
        )
    else:  # csv
        csv_bytes = await export_wiki_csv(wiki.id, manager_name, db)
        return StreamingResponse(
            iter([csv_bytes]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="wiki_{safe_name}.csv"'},
        )


