"""Manager Wiki API — ADMIN ONLY.

All endpoints require admin role. Admins can view wiki data
for ANY manager (by manager_id) or list all wikis.
"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_role
from app.database import get_db
from app.models.manager_wiki import (
    ManagerPattern,
    ManagerTechnique,
    ManagerWiki,
    WikiPage,
    WikiUpdateLog,
)
from app.models.user import User

logger = logging.getLogger(__name__)

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
    admin: User = Depends(require_role("admin")),
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
    admin: User = Depends(require_role("admin")),
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
                "status": wiki.status.value if wiki.status else "active",
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
# GET /api/wiki/{manager_id} — wiki overview for specific manager (admin only)
# ---------------------------------------------------------------------------

@router.get("/{manager_id}")
async def get_manager_wiki(
    manager_id: uuid.UUID,
    admin: User = Depends(require_role("admin")),
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
        "status": wiki.status.value if wiki.status else "active",
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
    admin: User = Depends(require_role("admin")),
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
                "page_type": p.page_type.value if p.page_type else "overview",
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
    admin: User = Depends(require_role("admin")),
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
        "page_type": page.page_type.value if page.page_type else "overview",
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
    admin: User = Depends(require_role("admin")),
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
                "category": p.category.value if p.category else "weakness",
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
    admin: User = Depends(require_role("admin")),
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
    admin: User = Depends(require_role("admin")),
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
                "action": entry.action.value if entry.action else "ingest_session",
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
    admin: User = Depends(require_role("admin")),
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
