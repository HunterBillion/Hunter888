"""Admin endpoints for the TZ-4 §8 knowledge review workflow.

Two endpoints, both gated to ``rop|admin``:

* ``GET  /admin/knowledge/queue`` — list of items waiting for manual
  review (``knowledge_status='needs_review'``), oldest TTL first.
  Powers the future :file:`KnowledgeReviewQueue.tsx` admin tab in D6.
* ``POST /admin/knowledge/{id}/review`` — perform a manual review.
  Accepts the new status (any of the four canonical values) and a
  human-readable reason. The new status MAY be ``outdated`` — this is
  the only sanctioned path to the ``outdated`` value per spec §8.3.1.

The endpoints are thin wrappers over
:mod:`app.services.knowledge_review_policy`. Business rules
(transition validity, dual-event emission, reviewed_by/_at write,
audit trail) all live there.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role
from app.database import get_db
from app.models.user import User
from app.services import knowledge_review_policy as krp


router = APIRouter(prefix="/admin/knowledge", tags=["admin", "knowledge"])

_require_review_admin = require_role("rop", "admin")


# ── Schemas ──────────────────────────────────────────────────────────────


class ReviewQueueItemResponse(BaseModel):
    id: uuid.UUID
    title: str | None = None
    knowledge_status: str
    expires_at: datetime | None = None
    reviewed_at: datetime | None = None
    reviewed_by: uuid.UUID | None = None
    source_ref: str | None = None


class ReviewActionRequest(BaseModel):
    new_status: str = Field(
        ...,
        description="Target knowledge_status. One of "
        "'actual', 'disputed', 'outdated', 'needs_review'.",
    )
    reason: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional human-readable rationale stored in "
        "status_reason and the knowledge_item.reviewed event payload.",
    )


class ReviewActionResponse(BaseModel):
    chunk_id: uuid.UUID
    knowledge_status: str
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    events_emitted: list[str]


# ── Endpoints ────────────────────────────────────────────────────────────


@router.get(
    "/queue",
    response_model=list[ReviewQueueItemResponse],
    summary="List knowledge items waiting for manual review",
)
async def get_review_queue(
    limit: int = 50,
    user: User = Depends(_require_review_admin),
    db: AsyncSession = Depends(get_db),
) -> list[ReviewQueueItemResponse]:
    """Items in ``needs_review``, sorted by ``expires_at`` ascending so
    the most-stale items rise first. ``limit`` defaults to 50 — the FE
    paginates by re-querying with a higher cap if the queue is dense."""
    items = await krp.list_review_queue(db, limit=limit)
    return [
        ReviewQueueItemResponse(
            id=it.id,
            title=it.title,
            knowledge_status=it.knowledge_status,
            expires_at=it.expires_at,
            reviewed_at=it.reviewed_at,
            reviewed_by=it.reviewed_by,
            source_ref=it.source_ref,
        )
        for it in items
    ]


@router.post(
    "/{chunk_id}/review",
    response_model=ReviewActionResponse,
    summary="Manually review a knowledge item — the only path to 'outdated'",
)
async def review_knowledge_item(
    chunk_id: uuid.UUID,
    body: ReviewActionRequest,
    user: User = Depends(_require_review_admin),
    db: AsyncSession = Depends(get_db),
) -> ReviewActionResponse:
    """Manual review action.

    Per §8.3.1 this is the **only** path that may write
    ``knowledge_status='outdated'``. The TTL cron is forbidden from
    that transition because flipping a popular chunk silently breaks
    every RAG retrieval that touches it.
    """
    try:
        chunk, events = await krp.mark_reviewed(
            db,
            chunk_id=chunk_id,
            new_status=body.new_status,
            reviewed_by=user.id,
            reason=body.reason,
        )
    except krp.InvalidKnowledgeStatus as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    return ReviewActionResponse(
        chunk_id=chunk.id,
        knowledge_status=chunk.knowledge_status,
        reviewed_by=chunk.reviewed_by,
        reviewed_at=chunk.reviewed_at,
        events_emitted=[ev.event_type for ev in events],
    )
