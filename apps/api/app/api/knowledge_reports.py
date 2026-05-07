"""User reports about AI quiz verdicts (PR-6, refactored 2026-05-07).

Originally lived inline at the bottom of ``api/knowledge.py`` with a
``# noqa: E402`` to silence ruff. Moved here so the ruff suppression
goes away and the report endpoint sits next to its own router (gets
mounted via ``main.py:include_router(knowledge_reports.router, prefix="/knowledge")``).

Flow:
  - User reads an AI verdict in /pvp/quiz, disagrees, clicks Flag,
    types reason → POST /api/knowledge/answers/{answer_id}/report.
  - Report lands in ``knowledge_answer_reports`` (PR-6 model).
  - Methodologist sees it via /admin/knowledge/queue?source=user_report
    (extended in same PR-6 commit).
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.rate_limit import limiter
from app.database import get_db
from app.models.knowledge import (
    KnowledgeAnswer,
    KnowledgeQuizSession,
    QuizParticipant,
)
from app.models.knowledge_answer_report import KnowledgeAnswerReport
from app.models.user import User
from app.schemas.knowledge import AnswerReportRequest, AnswerReportResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/answers/{answer_id}/report",
    response_model=AnswerReportResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("10/hour")
async def report_answer(
    request: Request,
    answer_id: uuid.UUID,
    body: AnswerReportRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """User flags an AI verdict as wrong.

    Only the user who answered the question can file a report on it.
    Idempotent per (answer_id, reporter_id): a second POST returns the
    existing row with HTTP 201 (FE doesn't need to special-case dups).
    """
    answer = (
        await db.execute(
            select(KnowledgeAnswer).where(KnowledgeAnswer.id == answer_id)
        )
    ).scalar_one_or_none()
    if not answer:
        raise HTTPException(status_code=404, detail="Answer not found")

    # Authorization: only the participant who *answered* the question
    # may report on it. Cross-check via session.user_id (solo) or the
    # QuizParticipant row (PvP). Solo path is the common case.
    session = (
        await db.execute(
            select(KnowledgeQuizSession).where(KnowledgeQuizSession.id == answer.session_id)
        )
    ).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    is_owner = session.user_id == user.id
    if not is_owner:
        in_session = (
            await db.execute(
                select(QuizParticipant.id).where(
                    QuizParticipant.session_id == session.id,
                    QuizParticipant.user_id == user.id,
                ).limit(1)
            )
        ).scalar_one_or_none()
        if not in_session:
            raise HTTPException(status_code=403, detail="Not your answer")

    # Idempotent: return existing report if any (and don't update reason —
    # we trust the first complaint).
    existing = (
        await db.execute(
            select(KnowledgeAnswerReport).where(
                KnowledgeAnswerReport.answer_id == answer_id,
                KnowledgeAnswerReport.reporter_id == user.id,
            ).limit(1)
        )
    ).scalar_one_or_none()
    if existing:
        existing_status = (
            existing.status.value
            if hasattr(existing.status, "value")
            else str(existing.status)
        )
        return AnswerReportResponse(
            id=str(existing.id),
            answer_id=str(existing.answer_id),
            reporter_id=str(existing.reporter_id),
            reason=existing.reason,
            status=existing_status,
            created_at=existing.created_at.isoformat(),
            linked_chunk_ids=existing.linked_chunk_ids or None,
        )

    # Snapshot the chunks AI cited at report time.
    linked: list[str] | None = None
    raw = answer.rag_chunks_used
    if isinstance(raw, list):
        linked = [str(x) for x in raw]

    report = KnowledgeAnswerReport(
        answer_id=answer_id,
        reporter_id=user.id,
        reason=body.reason.strip(),
        linked_chunk_ids=linked,
    )
    db.add(report)
    await db.flush()
    await db.commit()

    logger.info(
        "Knowledge answer reported: report=%s answer=%s reporter=%s chunks=%s",
        report.id, answer_id, user.id, len(linked or []),
    )

    return AnswerReportResponse(
        id=str(report.id),
        answer_id=str(report.answer_id),
        reporter_id=str(report.reporter_id),
        reason=report.reason,
        status=report.status.value,
        created_at=report.created_at.isoformat(),
        linked_chunk_ids=report.linked_chunk_ids or None,
    )
