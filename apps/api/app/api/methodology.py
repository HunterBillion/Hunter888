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
    IllegalStatusTransition,
    KnowledgeStatus,
    STATUSES_VISIBLE_IN_RAG,
    validate_transition,
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
from app.services.client_domain import emit_domain_event
from app.services.knowledge_review_policy import KNOWLEDGE_GLOBAL_ANCHOR


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

    # Soft-deleted rows (B5-01) never surface in the list endpoint —
    # they exist only for ChunkUsageLog joins and audit history.
    stmt = select(MethodologyChunk).where(
        MethodologyChunk.is_deleted.is_(False)
    )
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
    """Soft-delete a methodology chunk (B5-01).

    Pre-2026-05-02 this endpoint did ``await db.delete(chunk)`` (hard
    delete). Hard delete on a row referenced by ``chunk_usage_logs``
    (whose FK was relaxed in migration ``20260502_002``) leaves
    orphaned analytics rows and breaks the audit timeline — there
    is no way to ask "why did the team's «Скрипт по дорого»
    disappear?" once the row is gone.

    Now it flips ``is_deleted = True`` + ``knowledge_status =
    outdated`` and emits two events (``knowledge_item.deleted`` for
    the timeline chip + ``knowledge_item.status_changed`` for the
    same fan-out wiki/legal use). The row is invisible to every
    read site (list, single get, RAG retrieval) but the
    ChunkUsageLog joins keep working — the team's history is
    preserved.

    Recovery is intentionally not a flip-back: ``outdated`` is the
    soft-delete terminal per ``KnowledgeStatus`` docstring. To
    restore the chunk, author it again as a fresh INSERT — the
    audit log captures both events.
    """
    chunk = await check_methodology_team_access(
        user, chunk_id=chunk_id, db=db, mode="write"
    )

    previous_status = chunk.knowledge_status
    target_status = KnowledgeStatus.outdated.value

    # Validate: deleting an already-deleted chunk is a no-op via the
    # ``is_deleted=True`` filter in the gate (404). This branch
    # protects against the rare race where two ROPs hit DELETE
    # simultaneously — the second one finds the chunk in `outdated`
    # state but still un-deleted (idempotent). Either way, the
    # transition target is `outdated` so the human transition graph
    # accepts it.
    try:
        validate_transition(
            previous_status, target_status, automated=False
        )
    except IllegalStatusTransition as exc:
        # The only way this fires is if the row is already
        # `outdated` AND somehow has `is_deleted=False` (data
        # inconsistency). Fall through with idempotent flip.
        if previous_status != target_status:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            )

    now = datetime.now(timezone.utc)
    chunk.is_deleted = True
    chunk.knowledge_status = target_status
    chunk.last_reviewed_at = now
    chunk.last_reviewed_by = user.id
    chunk.version += 1

    common_payload = {
        "chunk_id": str(chunk.id),
        "team_id": str(chunk.team_id),
        "title": chunk.title,
        "from_status": previous_status,
        "to_status": target_status,
        "reviewed_by": str(user.id),
        "reviewed_at": now.isoformat(),
    }

    # Emit BEFORE commit so the event lands in the same transaction
    # as the row mutation — TZ-1 §15.1 invariant. The helper itself
    # uses begin_nested + savepoint so a failure here does not
    # roll back the chunk update unless ``client_domain_strict_emit``
    # is on (it is, on prod, so failures bubble — that's the
    # correct behaviour for a critical audit event).
    await emit_domain_event(
        db,
        lead_client_id=KNOWLEDGE_GLOBAL_ANCHOR,
        event_type="knowledge_item.deleted",
        actor_type="user",
        actor_id=user.id,
        source="methodology_api",
        aggregate_type="methodology_chunk",
        aggregate_id=chunk.id,
        payload=common_payload,
        idempotency_key=f"methodology.deleted:{chunk.id}",
    )
    if previous_status != target_status:
        await emit_domain_event(
            db,
            lead_client_id=KNOWLEDGE_GLOBAL_ANCHOR,
            event_type="knowledge_item.status_changed",
            actor_type="user",
            actor_id=user.id,
            source="methodology_api",
            aggregate_type="methodology_chunk",
            aggregate_id=chunk.id,
            payload=common_payload,
            idempotency_key=(
                f"knowledge_item.status_changed:{chunk.id}:"
                f"{previous_status}-to-{target_status}:{now.isoformat()}"
            ),
        )

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
    """Governance transition (B5-02, B5-07).

    Validates the requested transition against the canonical graph in
    :func:`app.models.knowledge_status.validate_transition`. Pre-audit
    this endpoint did ``chunk.knowledge_status = body.status``
    unconditionally — letting a ROP do ``outdated → actual`` (recovery
    from soft-delete) which the docstring explicitly forbids. Now an
    illegal transition returns ``409`` with structured detail.

    Emits paired ``knowledge_item.reviewed`` (audit) and
    ``knowledge_item.status_changed`` (fan-out) events so the FE
    timeline sees the same shape it sees for legal/wiki transitions
    (B5-02). Pre-audit the methodology PATCH was completely silent
    — ROPs could flip statuses without a trace.

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

    previous_status = chunk.knowledge_status
    target_status = body.status

    # Enforce the transition graph (B5-07). DELETE → outdated already
    # validates separately; this is the only other path into status
    # mutation, so once both are guarded the graph holds.
    try:
        validate_transition(previous_status, target_status, automated=False)
    except IllegalStatusTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "illegal_status_transition",
                "message": str(exc),
                "from_status": previous_status,
                "to_status": target_status,
            },
        )

    now = datetime.now(timezone.utc)
    chunk.knowledge_status = target_status
    chunk.last_reviewed_at = now
    chunk.last_reviewed_by = user.id
    # Version bumped on status flips too — the change is reviewable,
    # embedding doesn't need recompute (no body change).
    chunk.version += 1
    chunk.updated_at = now

    common_payload = {
        "chunk_id": str(chunk.id),
        "team_id": str(chunk.team_id),
        "title": chunk.title,
        "from_status": previous_status,
        "to_status": target_status,
        "reviewed_by": str(user.id),
        "reviewed_at": now.isoformat(),
        "reason": (body.note or None),
    }

    # B5-02: emit audit + fan-out events. Mirrors
    # ``knowledge_review_policy.mark_reviewed`` shape exactly so
    # consumers see one event contract across all knowledge
    # surfaces (legal/wiki/methodology).
    await emit_domain_event(
        db,
        lead_client_id=KNOWLEDGE_GLOBAL_ANCHOR,
        event_type="knowledge_item.reviewed",
        actor_type="user",
        actor_id=user.id,
        source="methodology_api",
        aggregate_type="methodology_chunk",
        aggregate_id=chunk.id,
        payload=common_payload,
        idempotency_key=f"knowledge_item.reviewed:{chunk.id}:{now.isoformat()}",
    )
    if previous_status != target_status:
        await emit_domain_event(
            db,
            lead_client_id=KNOWLEDGE_GLOBAL_ANCHOR,
            event_type="knowledge_item.status_changed",
            actor_type="user",
            actor_id=user.id,
            source="methodology_api",
            aggregate_type="methodology_chunk",
            aggregate_id=chunk.id,
            payload=common_payload,
            idempotency_key=(
                f"knowledge_item.status_changed:{chunk.id}:"
                f"{previous_status}-to-{target_status}:{now.isoformat()}"
            ),
        )

    await db.commit()
    await db.refresh(chunk)
    return _to_out(chunk)


# ── Effectiveness panel (B5-08) ─────────────────────────────────────────


@router.get("/effectiveness")
async def get_methodology_effectiveness(
    team_id: Optional[uuid.UUID] = Query(
        None,
        description=(
            "Filter by team. Admin may pass any team_id; ROP is "
            "restricted to their own team."
        ),
    ),
    days: int = Query(30, ge=1, le=365),
    user: User = Depends(require_role("admin", "rop")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Methodology effectiveness summary (TZ-8 PR-D2 panel).

    Wires the existing ``methodology_telemetry.get_team_methodology_stats``
    service into a REST surface so the FE methodology dashboard tab
    can render real numbers ("Скрипт по дорого: использован 47 раз
    в коуч-режиме, 23 положительных") instead of mocks.

    Pre-2026-05-02 (B5-08) the service existed but had no router —
    the panel was blind.
    """
    role = user.role.value
    if role == "admin":
        # Admin must still pick a team — the underlying telemetry
        # service is keyed on ``team_id`` (no global rollup yet,
        # tracked in TZ-8 §13 follow-up). When admin omits the
        # parameter, default to their team_id if any, else 400.
        scope_team = team_id or user.team_id
    else:
        # ROP — must use own team. Cross-team request → 403 via gate.
        scope_team = team_id or user.team_id
        if scope_team is not None:
            await check_methodology_team_access(
                user, team_id=scope_team, mode="read"
            )

    if scope_team is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "team_id is required (admin must pass ?team_id=... when "
                "not assigned to a team)"
            ),
        )

    from app.services.methodology_telemetry import get_team_methodology_stats

    stats = await get_team_methodology_stats(
        db,
        team_id=scope_team,
        days=days,
    )
    return {"team_id": str(scope_team), "days": days, "items": stats}
