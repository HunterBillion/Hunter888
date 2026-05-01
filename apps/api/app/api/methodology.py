"""Methodology REST API (TZ-8 PR-B).

CRUD + status PATCH for ``methodology_chunks``. The full authz
matrix lives in :func:`app.core.deps.check_methodology_team_access`;
this module is mostly a thin shell wiring HTTP verbs to it,
schema validation, the live-backfill enqueue after each write,
and a structured error response.

Endpoints
---------

  * ``GET    /methodology/chunks``                    — list, scoped to caller's team
                                                        unless caller is admin
  * ``GET    /methodology/chunks/{chunk_id}``         — single chunk
  * ``POST   /methodology/chunks``                    — create
  * ``PUT    /methodology/chunks/{chunk_id}``         — full or partial update
  * ``DELETE /methodology/chunks/{chunk_id}``         — hard delete
                                                        (preferred soft via PATCH status=outdated)
  * ``PATCH  /methodology/chunks/{chunk_id}/status``  — governance transition

Live-backfill
-------------

Every successful create/update enqueues the chunk id onto the
methodology backfill queue (TZ-8 §3.5). The user-facing PUT/POST
returns 200/201 even if Redis is down — the enqueue is best-effort
and the cold-sweep on next API restart picks up the gap.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import (
    check_methodology_team_access,
    get_current_user,
    require_role,
)
from app.database import get_db
from app.models.knowledge_status import (
    KnowledgeStatus,
    STATUSES_VISIBLE_IN_RAG,
)
from app.models.methodology import MethodologyChunk
from app.models.user import User
from app.schemas.methodology import (
    KnowledgeStatusLiteral,
    MethodologyChunkCreate,
    MethodologyChunkListOut,
    MethodologyChunkOut,
    MethodologyChunkUpdate,
    MethodologyStatusUpdate,
)


router = APIRouter(prefix="/methodology", tags=["methodology"])


def _to_out(chunk: MethodologyChunk) -> MethodologyChunkOut:
    """Pydantic serialiser. Adds the synthetic ``embedding_pending``
    flag (NULL embedding = backfill not yet completed) so the UI
    can render an "indexing…" indicator."""
    return MethodologyChunkOut(
        id=chunk.id,
        team_id=chunk.team_id,
        author_id=chunk.author_id,
        title=chunk.title,
        body=chunk.body,
        kind=chunk.kind,
        tags=list(chunk.tags or []),
        keywords=list(chunk.keywords or []),
        knowledge_status=chunk.knowledge_status,
        last_reviewed_at=chunk.last_reviewed_at,
        last_reviewed_by=chunk.last_reviewed_by,
        review_due_at=chunk.review_due_at,
        embedding_pending=chunk.embedding is None,
        version=chunk.version,
        created_at=chunk.created_at,
        updated_at=chunk.updated_at,
    )


# ── List + filters ──────────────────────────────────────────────────────


@router.get("/chunks", response_model=MethodologyChunkListOut)
async def list_methodology_chunks(
    team_id: Optional[uuid.UUID] = Query(
        None,
        description=(
            "Filter by team. Admin may pass any team_id; ROP/manager "
            "are restricted to their own team regardless of this "
            "parameter."
        ),
    ),
    kind: Optional[str] = Query(None),
    knowledge_status_filter: Optional[KnowledgeStatusLiteral] = Query(
        None,
        alias="status",
        description="Optional filter by knowledge_status.",
    ),
    visible_only: bool = Query(
        False,
        description=(
            "Convenience: when true, return only rows that would "
            "surface in RAG (actual + disputed). Equivalent to "
            "the SQL filter STATUSES_VISIBLE_IN_RAG. Default false "
            "so the methodology UI shows the full lifecycle."
        ),
    ),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MethodologyChunkListOut:
    """List methodology chunks the caller is allowed to see.

    Authorisation is structural: ``check_methodology_team_access``
    resolves ``user`` + (optional) ``team_id`` against the
    role/team rules and returns the team scope to query against.
    Even an admin call without team_id falls into the "admin sees
    all teams" branch — paginate carefully.
    """
    role = user.role.value

    if role == "admin" and team_id is None:
        # Admin without team filter → all teams.
        scope_team = None
    else:
        # All other branches must have a team scope; ROP/manager fall
        # back to their own team if the caller didn't pass one.
        effective_team_id = team_id or user.team_id
        if effective_team_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="team_id is required for non-admin callers without a team",
            )
        # Reuse the gate to enforce cross-team isolation.
        await check_methodology_team_access(
            user, team_id=effective_team_id, mode="read"
        )
        scope_team = effective_team_id

    stmt = select(MethodologyChunk)
    if scope_team is not None:
        stmt = stmt.where(MethodologyChunk.team_id == scope_team)
    if kind is not None:
        stmt = stmt.where(MethodologyChunk.kind == kind)
    if knowledge_status_filter is not None:
        stmt = stmt.where(
            MethodologyChunk.knowledge_status == knowledge_status_filter
        )
    elif visible_only:
        stmt = stmt.where(
            MethodologyChunk.knowledge_status.in_(list(STATUSES_VISIBLE_IN_RAG))
        )

    # Total count for pagination indicator.
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    rows = (
        await db.execute(stmt.order_by(MethodologyChunk.updated_at.desc()))
    ).scalars().all()

    return MethodologyChunkListOut(
        items=[_to_out(r) for r in rows], total=total
    )


# ── Single + create + update + delete ───────────────────────────────────


@router.get("/chunks/{chunk_id}", response_model=MethodologyChunkOut)
async def get_methodology_chunk(
    chunk_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MethodologyChunkOut:
    chunk = await check_methodology_team_access(
        user, chunk_id=chunk_id, db=db, mode="read"
    )
    return _to_out(chunk)


@router.post(
    "/chunks",
    response_model=MethodologyChunkOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_methodology_chunk(
    body: MethodologyChunkCreate,
    user: User = Depends(require_role("admin", "rop")),
    db: AsyncSession = Depends(get_db),
) -> MethodologyChunkOut:
    """Create a methodology chunk for the caller's team.

    Admin can create on any team via the future ``POST /methodology/chunks?team_id=X``
    parameter, but the v1 contract is "ROP creates for own team" —
    cross-team admin authoring is rare enough to defer to PR-C UI.
    """
    if user.team_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ROP is not assigned to a team",
        )

    chunk = MethodologyChunk(
        team_id=user.team_id,
        author_id=user.id,
        title=body.title,
        body=body.body,
        kind=body.kind,
        tags=body.tags or [],
        keywords=body.keywords or [],
        knowledge_status=KnowledgeStatus.actual.value,
    )
    db.add(chunk)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        # Most likely ``uq_methodology_team_title``. The error is
        # actionable from the form ("title already exists") — surface
        # cleanly rather than leaking the raw SQL message.
        if "uq_methodology_team_title" in str(exc.orig):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "A methodology chunk with this title already exists "
                    "in your team. Mark the old one as 'outdated' first "
                    "or pick a different title."
                ),
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Database integrity error: {exc.orig}",
        )

    await db.refresh(chunk)

    # Live-backfill enqueue (TZ-8 §3.5). Best-effort.
    from app.services.embedding_live_backfill import enqueue_methodology_chunk

    await enqueue_methodology_chunk(chunk.id)

    return _to_out(chunk)


@router.put("/chunks/{chunk_id}", response_model=MethodologyChunkOut)
async def update_methodology_chunk(
    chunk_id: uuid.UUID,
    body: MethodologyChunkUpdate,
    user: User = Depends(require_role("admin", "rop")),
    db: AsyncSession = Depends(get_db),
) -> MethodologyChunkOut:
    chunk = await check_methodology_team_access(
        user, chunk_id=chunk_id, db=db, mode="write"
    )

    # Apply only set fields. PATCH-shape semantics — ``None`` means
    # don't touch, an explicit value (including empty list) overwrites.
    body_changed = False
    title_or_body_changed = False
    if body.title is not None and body.title != chunk.title:
        chunk.title = body.title
        body_changed = True
        title_or_body_changed = True
    if body.body is not None and body.body != chunk.body:
        chunk.body = body.body
        body_changed = True
        title_or_body_changed = True
    if body.kind is not None and body.kind != chunk.kind:
        chunk.kind = body.kind
        body_changed = True
    if body.tags is not None:
        chunk.tags = body.tags
        body_changed = True
    if body.keywords is not None:
        chunk.keywords = body.keywords
        body_changed = True

    if body_changed:
        chunk.version += 1
        chunk.updated_at = datetime.now(timezone.utc)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if "uq_methodology_team_title" in str(exc.orig):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Title collides with another chunk in your team",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Database integrity error: {exc.orig}",
        )

    await db.refresh(chunk)

    # Re-embed only when title or body changed — kind/tags don't
    # affect the vector and the worker is not free.
    if title_or_body_changed:
        from app.services.embedding_live_backfill import enqueue_methodology_chunk

        await enqueue_methodology_chunk(chunk.id)

    return _to_out(chunk)


@router.delete(
    "/chunks/{chunk_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_methodology_chunk(
    chunk_id: uuid.UUID,
    user: User = Depends(require_role("admin", "rop")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Hard delete. Prefer PATCH status=outdated for soft delete —
    keeps history + ChunkUsageLog joins. This endpoint exists for
    "I created a chunk by mistake" cases."""
    chunk = await check_methodology_team_access(
        user, chunk_id=chunk_id, db=db, mode="write"
    )
    await db.delete(chunk)
    await db.commit()


# ── Status transitions ──────────────────────────────────────────────────


_DISPUTE_OR_OUTDATE = {"disputed", "outdated"}


@router.patch(
    "/chunks/{chunk_id}/status",
    response_model=MethodologyChunkOut,
)
async def patch_methodology_status(
    chunk_id: uuid.UUID,
    body: MethodologyStatusUpdate,
    user: User = Depends(require_role("admin", "rop")),
    db: AsyncSession = Depends(get_db),
) -> MethodologyChunkOut:
    """Governance transition.

    The note field is required for transitions into ``disputed`` /
    ``outdated`` so future reviewers see why. ``actual`` /
    ``needs_review`` transitions accept an optional note.
    """
    chunk = await check_methodology_team_access(
        user, chunk_id=chunk_id, db=db, mode="write"
    )

    if body.status in _DISPUTE_OR_OUTDATE and not (body.note or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "A note is required when transitioning to "
                f"'{body.status}' so future reviewers see the reason."
            ),
        )

    chunk.knowledge_status = body.status
    chunk.last_reviewed_at = datetime.now(timezone.utc)
    chunk.last_reviewed_by = user.id
    # Version is bumped on status changes too — the change is
    # reviewable, embedding doesn't need recompute.
    chunk.version += 1
    chunk.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(chunk)
    return _to_out(chunk)
