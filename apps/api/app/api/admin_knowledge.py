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
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role
from app.database import get_db
from app.models.knowledge import KnowledgeAnswer
from app.models.knowledge_answer_report import (
    KnowledgeAnswerReport,
    ReportStatus,
)
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

    # PR-6 (2026-05-07): «Жалоба на ответ AI» (Variant B). Items now have
    # a source_kind so the FE can render a filter pill ("Все / TTL /
    # Жалобы"). For user_report items we surface the report context
    # (reason, reporter, the answer + chunks AI cited) so the
    # methodologist sees what the user actually disagreed with.
    source_kind: Literal["ttl_expiry", "user_report"] = "ttl_expiry"
    report_id: uuid.UUID | None = None
    report_reason: str | None = None
    reporter_id: uuid.UUID | None = None
    answer_id: uuid.UUID | None = None
    answer_question: str | None = None
    answer_explanation: str | None = None
    answer_user_text: str | None = None
    linked_chunk_ids: list[uuid.UUID] | None = None
    reported_at: datetime | None = None


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
    source: Literal["all", "ttl", "user_report"] = Query(
        default="all",
        description="Filter: 'ttl' = TTL-expired chunks only, "
        "'user_report' = user-filed reports only, 'all' = both merged.",
    ),
    user: User = Depends(_require_review_admin),
    db: AsyncSession = Depends(get_db),
) -> list[ReviewQueueItemResponse]:
    """TTL items (``needs_review``) sorted by ``expires_at`` asc — most
    stale first — merged with PR-6 user reports (``status=open``) sorted
    by ``created_at`` desc. The merged list is capped at ``limit`` total."""
    out: list[ReviewQueueItemResponse] = []

    if source in ("all", "ttl"):
        ttl_items = await krp.list_review_queue(db, limit=limit)
        for it in ttl_items:
            out.append(ReviewQueueItemResponse(
                id=it.id,
                title=it.title,
                knowledge_status=it.knowledge_status,
                expires_at=it.expires_at,
                reviewed_at=it.reviewed_at,
                reviewed_by=it.reviewed_by,
                source_ref=it.source_ref,
                source_kind="ttl_expiry",
            ))

    if source in ("all", "user_report"):
        # Open user reports + the answer they refer to (so methodologist
        # sees what the user disagreed with). Single query, JOIN.
        report_q = (
            select(KnowledgeAnswerReport, KnowledgeAnswer)
            .join(
                KnowledgeAnswer,
                KnowledgeAnswer.id == KnowledgeAnswerReport.answer_id,
            )
            .where(KnowledgeAnswerReport.status == ReportStatus.open)
            .order_by(desc(KnowledgeAnswerReport.created_at))
            .limit(limit)
        )
        rows = (await db.execute(report_q)).all()
        for report, answer in rows:
            out.append(ReviewQueueItemResponse(
                id=report.id,  # use report id as the queue row id
                title=(answer.question_text or "")[:120],
                knowledge_status="user_report",
                source_kind="user_report",
                report_id=report.id,
                report_reason=report.reason,
                reporter_id=report.reporter_id,
                answer_id=answer.id,
                answer_question=answer.question_text,
                answer_explanation=answer.explanation,
                answer_user_text=answer.user_answer,
                linked_chunk_ids=[uuid.UUID(c) for c in (report.linked_chunk_ids or []) if c],
                reported_at=report.created_at,
            ))

    return out[:limit]


# ── PR-6: resolve a user report (accept / reject) ─────────────────────────


class ResolveReportRequest(BaseModel):
    decision: Literal["accepted", "rejected"]
    note: str | None = Field(default=None, max_length=500)


class ResolveReportResponse(BaseModel):
    report_id: uuid.UUID
    status: str
    reviewed_by: uuid.UUID
    reviewed_at: datetime


@router.post(
    "/reports/{report_id}/resolve",
    response_model=ResolveReportResponse,
    summary="Methodologist accepts/rejects a user-filed answer report",
)
async def resolve_answer_report(
    report_id: uuid.UUID,
    body: ResolveReportRequest,
    user: User = Depends(_require_review_admin),
    db: AsyncSession = Depends(get_db),
) -> ResolveReportResponse:
    """Accept or reject a `KnowledgeAnswerReport`.

    Accepted does NOT auto-flip the underlying chunk's status — the
    methodologist still uses ``POST /admin/knowledge/{chunk_id}/review``
    on each linked chunk to choose actual / disputed / outdated /
    needs_review. We separate the two actions intentionally: a single
    user complaint may reference 3 chunks, and only one might actually
    be wrong.
    """
    report = (
        await db.execute(
            select(KnowledgeAnswerReport).where(KnowledgeAnswerReport.id == report_id)
        )
    ).scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.status != ReportStatus.open:
        raise HTTPException(
            status_code=409,
            detail=f"Report already resolved as {report.status.value}",
        )

    report.status = ReportStatus(body.decision)
    report.reviewed_by = user.id
    report.reviewed_at = datetime.now(timezone.utc)
    if body.note:
        report.review_note = body.note
    await db.commit()

    return ResolveReportResponse(
        report_id=report.id,
        status=report.status.value,
        reviewed_by=report.reviewed_by,
        reviewed_at=report.reviewed_at,
    )


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
