"""Manager Wiki API — read wiki pages, patterns, techniques, and trigger manual ingest."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
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


# ---------------------------------------------------------------------------
# GET /api/wiki/me — wiki overview for current user
# ---------------------------------------------------------------------------


@router.get("/me")
async def get_my_wiki(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's wiki overview (metadata + stats)."""
    result = await db.execute(
        select(ManagerWiki).where(ManagerWiki.manager_id == user.id)
    )
    wiki = result.scalar_one_or_none()
    if not wiki:
        return {
            "exists": False,
            "sessions_ingested": 0,
            "patterns_discovered": 0,
            "pages_count": 0,
        }
    return {
        "exists": True,
        "id": str(wiki.id),
        "status": wiki.status.value if wiki.status else "active",
        "sessions_ingested": wiki.sessions_ingested,
        "patterns_discovered": wiki.patterns_discovered,
        "pages_count": wiki.pages_count,
        "total_tokens_used": wiki.total_tokens_used,
        "last_ingest_at": wiki.last_ingest_at.isoformat() if wiki.last_ingest_at else None,
        "created_at": wiki.created_at.isoformat() if wiki.created_at else None,
    }


# ---------------------------------------------------------------------------
# GET /api/wiki/me/pages — list all wiki pages
# ---------------------------------------------------------------------------


@router.get("/me/pages")
async def list_my_wiki_pages(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all wiki pages for the current user."""
    result = await db.execute(
        select(ManagerWiki).where(ManagerWiki.manager_id == user.id)
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
# GET /api/wiki/me/pages/{page_path:path} — get specific page content
# ---------------------------------------------------------------------------


@router.get("/me/pages/{page_path:path}")
async def get_wiki_page(
    page_path: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific wiki page by path."""
    result = await db.execute(
        select(ManagerWiki).where(ManagerWiki.manager_id == user.id)
    )
    wiki = result.scalar_one_or_none()
    if not wiki:
        raise HTTPException(status_code=404, detail="Wiki not found")

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
# GET /api/wiki/me/patterns — discovered patterns
# ---------------------------------------------------------------------------


@router.get("/me/patterns")
async def list_my_patterns(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all discovered behavioral patterns for the current user."""
    result = await db.execute(
        select(ManagerPattern)
        .where(ManagerPattern.manager_id == user.id)
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
# GET /api/wiki/me/techniques — effective techniques
# ---------------------------------------------------------------------------


@router.get("/me/techniques")
async def list_my_techniques(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all discovered techniques for the current user."""
    result = await db.execute(
        select(ManagerTechnique)
        .where(ManagerTechnique.manager_id == user.id)
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
# GET /api/wiki/me/log — update history
# ---------------------------------------------------------------------------


@router.get("/me/log")
async def list_my_wiki_log(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 20,
):
    """Get wiki update history for the current user."""
    result = await db.execute(
        select(ManagerWiki).where(ManagerWiki.manager_id == user.id)
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
                "id": str(l.id),
                "action": l.action.value if l.action else "ingest_session",
                "description": l.description,
                "pages_modified": l.pages_modified,
                "pages_created": l.pages_created,
                "patterns_discovered": l.patterns_discovered or [],
                "tokens_used": l.tokens_used,
                "status": l.status,
                "started_at": l.started_at.isoformat() if l.started_at else None,
                "completed_at": l.completed_at.isoformat() if l.completed_at else None,
                "error_msg": l.error_msg,
            }
            for l in logs
        ]
    }


# ---------------------------------------------------------------------------
# POST /api/wiki/me/ingest/{session_id} — manual ingest trigger
# ---------------------------------------------------------------------------


@router.post("/me/ingest/{session_id}")
async def trigger_ingest(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger wiki ingest for a specific training session."""
    from app.models.training import TrainingSession

    # Verify session belongs to user
    session = await db.get(TrainingSession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    from app.services.wiki_ingest_service import ingest_session

    result = await ingest_session(session_id, db)
    return result
