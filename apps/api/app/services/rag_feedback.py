"""RAG Feedback Loop Service — enriches knowledge base from user performance.

Collects outcomes from all AI interaction modes and feeds them back to
update RAG chunk statistics, discover new error patterns, and improve
retrieval quality over time.

Data flow:
  Training session → scoring.py → record_training_feedback()
  PvP duel → pvp_judge.py → record_pvp_feedback()
  Knowledge quiz → knowledge_quiz.py → record_quiz_feedback()
  L10 legal validation → scoring.py → record_validation_feedback()

Aggregation:
  recalculate_chunk_effectiveness() — periodic job (e.g. daily via scheduler)
  Recalculates effectiveness_score, discovers new common_errors from logs.

Analytics:
  get_feedback_summary() — overview for admin/methodologist dashboard
  get_category_stats() — per-category breakdown of error rates
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag import (
    ChunkUsageLog,
    LegalCategory,
    LegalKnowledgeChunk,
    LegalValidationResult,
)
from app.services.rag_legal import (
    log_chunk_usage,
    record_chunk_outcome,
    recalculate_chunk_effectiveness,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Per-mode feedback collectors — called by respective services
# ═══════════════════════════════════════════════════════════════════════════════

async def record_training_feedback(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    validation_results: list[dict],
    rag_chunks_used: list[uuid.UUID] | None = None,
) -> int:
    """Record feedback from a completed training session.

    Args:
        validation_results: list of LegalValidationResult-like dicts with:
            - chunk_id (optional): matched knowledge chunk
            - accuracy: "correct" | "incorrect" | "partial" | "correct_cited"
            - manager_statement: what the user said
            - explanation: why it was wrong (if applicable)
    Returns:
        Number of outcomes recorded.
    """
    recorded = 0

    # Log chunk retrievals (if we know which chunks were used)
    if rag_chunks_used:
        await log_chunk_usage(
            db,
            chunk_ids=rag_chunks_used,
            user_id=user_id,
            source_type="training",
            source_id=session_id,
            retrieval_method="training_context",
        )

    # Record outcomes from validation results
    for vr in validation_results:
        chunk_id = vr.get("chunk_id") or vr.get("knowledge_chunk_id")
        if not chunk_id:
            continue

        if isinstance(chunk_id, str):
            try:
                chunk_id = uuid.UUID(chunk_id)
            except ValueError:
                continue

        accuracy = vr.get("accuracy", "")
        is_correct = accuracy in ("correct", "correct_cited")

        # Detect new error patterns (with injection filtering)
        discovered_error = None
        if not is_correct and vr.get("manager_statement"):
            stmt_excerpt = vr["manager_statement"][:200]
            explanation = vr.get("explanation", "")
            if explanation and len(explanation) > 20:
                from app.services.content_filter import detect_jailbreak
                raw_error = f"Ошибка менеджера: {stmt_excerpt[:100]}"
                if detect_jailbreak(raw_error):
                    logger.warning(
                        "Injection attempt in discovered_error blocked: user_id=%s, text=%s",
                        user_id, raw_error[:80],
                    )
                else:
                    discovered_error = raw_error

        await record_chunk_outcome(
            db,
            chunk_id=chunk_id,
            user_id=user_id,
            source_type="training",
            source_id=session_id,
            answer_correct=is_correct,
            user_answer_excerpt=vr.get("manager_statement", "")[:500],
            score_delta=vr.get("score_delta"),
            discovered_error=discovered_error,
        )
        recorded += 1

    return recorded


async def record_pvp_feedback(
    db: AsyncSession,
    *,
    duel_id: uuid.UUID,
    user_id: uuid.UUID,
    round_number: int,
    judge_results: list[dict],
) -> int:
    """Record feedback from PvP duel judge evaluation.

    Args:
        judge_results: list with keys:
            - chunk_id: knowledge chunk the question was based on
            - score: numerical score (0-10)
            - legal_accuracy: how legally accurate the answer was
            - feedback: judge's textual feedback
    Returns:
        Number of outcomes recorded.
    """
    recorded = 0

    for jr in judge_results:
        chunk_id = jr.get("chunk_id")
        if not chunk_id:
            continue
        if isinstance(chunk_id, str):
            try:
                chunk_id = uuid.UUID(chunk_id)
            except ValueError:
                continue

        score = jr.get("score", 0)
        is_correct = score >= 6  # 6+ out of 10 = considered correct

        await record_chunk_outcome(
            db,
            chunk_id=chunk_id,
            user_id=user_id,
            source_type="pvp_duel",
            source_id=duel_id,
            answer_correct=is_correct,
            score_delta=float(score),
            user_answer_excerpt=jr.get("feedback", "")[:500],
        )
        recorded += 1

    return recorded


async def record_quiz_feedback(
    db: AsyncSession,
    *,
    quiz_session_id: uuid.UUID,
    user_id: uuid.UUID,
    answers: list[dict],
) -> int:
    """Record feedback from knowledge quiz answers.

    Args:
        answers: list with keys:
            - chunk_id: source knowledge chunk
            - is_correct: bool
            - user_answer: what the user answered
            - score_delta: points awarded
            - question_text: the question asked
    Returns:
        Number of outcomes recorded.
    """
    recorded = 0

    # First log the chunk retrievals
    chunk_ids = []
    for a in answers:
        cid = a.get("chunk_id")
        if cid:
            if isinstance(cid, str):
                try:
                    cid = uuid.UUID(cid)
                except ValueError:
                    continue
            chunk_ids.append(cid)

    if chunk_ids:
        await log_chunk_usage(
            db,
            chunk_ids=chunk_ids,
            user_id=user_id,
            source_type="quiz",
            source_id=quiz_session_id,
            retrieval_method="quiz_generation",
        )

    # Record outcomes
    for a in answers:
        chunk_id = a.get("chunk_id")
        if not chunk_id:
            continue
        if isinstance(chunk_id, str):
            try:
                chunk_id = uuid.UUID(chunk_id)
            except ValueError:
                continue

        is_correct = a.get("is_correct", False)

        await record_chunk_outcome(
            db,
            chunk_id=chunk_id,
            user_id=user_id,
            source_type="quiz",
            source_id=quiz_session_id,
            answer_correct=is_correct,
            user_answer_excerpt=a.get("user_answer", "")[:500],
            score_delta=a.get("score_delta"),
        )
        recorded += 1

    return recorded


async def record_blitz_feedback(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    source_id: uuid.UUID | None = None,
    chunk_id: uuid.UUID,
    is_correct: bool,
    user_answer: str | None = None,
) -> None:
    """Record feedback from a single blitz question."""
    await log_chunk_usage(
        db,
        chunk_ids=[chunk_id],
        user_id=user_id,
        source_type="blitz",
        source_id=source_id,
        retrieval_method="blitz_pool",
    )
    await record_chunk_outcome(
        db,
        chunk_id=chunk_id,
        user_id=user_id,
        source_type="blitz",
        source_id=source_id,
        answer_correct=is_correct,
        user_answer_excerpt=(user_answer or "")[:500],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Analytics — for admin dashboard and methodologist review
# ═══════════════════════════════════════════════════════════════════════════════

async def get_feedback_summary(db: AsyncSession, days: int = 30) -> dict:
    """Overall feedback summary for the last N days."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        # S4-09: All queries filter out soft-deleted records
        not_deleted = ChunkUsageLog.is_deleted.is_(False)

        # Total usage logs
        total_logs = await db.scalar(
            select(func.count()).select_from(ChunkUsageLog)
            .where(ChunkUsageLog.created_at >= since, not_deleted)
        ) or 0

        # Answered logs
        answered_logs = await db.scalar(
            select(func.count()).select_from(ChunkUsageLog)
            .where(ChunkUsageLog.created_at >= since, ChunkUsageLog.was_answered.is_(True), not_deleted)
        ) or 0

        # Correct answers
        correct_logs = await db.scalar(
            select(func.count()).select_from(ChunkUsageLog)
            .where(
                ChunkUsageLog.created_at >= since,
                ChunkUsageLog.answer_correct.is_(True),
                not_deleted,
            )
        ) or 0

        # Source type breakdown
        source_result = await db.execute(
            select(
                ChunkUsageLog.source_type,
                func.count().label("cnt"),
            )
            .where(ChunkUsageLog.created_at >= since, not_deleted)
            .group_by(ChunkUsageLog.source_type)
        )
        by_source = {row.source_type: row.cnt for row in source_result}

        # Discovered errors count
        new_errors = await db.scalar(
            select(func.count()).select_from(ChunkUsageLog)
            .where(
                ChunkUsageLog.created_at >= since,
                ChunkUsageLog.discovered_error.isnot(None),
                not_deleted,
            )
        ) or 0

        # Chunks with low effectiveness
        weak_chunks = await db.scalar(
            select(func.count()).select_from(LegalKnowledgeChunk)
            .where(
                LegalKnowledgeChunk.is_active.is_(True),
                LegalKnowledgeChunk.effectiveness_score.isnot(None),
                LegalKnowledgeChunk.effectiveness_score < 0.5,
            )
        ) or 0

        return {
            "period_days": days,
            "total_chunk_retrievals": total_logs,
            "answered_retrievals": answered_logs,
            "correct_answers": correct_logs,
            "accuracy_rate": round(correct_logs / answered_logs, 3) if answered_logs else None,
            "by_source_type": by_source,
            "new_errors_discovered": new_errors,
            "weak_chunks_count": weak_chunks,
        }

    except Exception as e:
        logger.error("get_feedback_summary failed: %s", e)
        return {"error": str(e)}


async def get_category_error_rates(db: AsyncSession, days: int = 30) -> list[dict]:
    """Per-category breakdown: which legal categories have highest error rates."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        result = await db.execute(
            sa_text("""
                SELECT
                    lkc.category,
                    COUNT(cul.id) AS total_answers,
                    SUM(CASE WHEN cul.answer_correct = true THEN 1 ELSE 0 END) AS correct,
                    SUM(CASE WHEN cul.answer_correct = false THEN 1 ELSE 0 END) AS incorrect,
                    ROUND(
                        SUM(CASE WHEN cul.answer_correct = true THEN 1 ELSE 0 END)::numeric /
                        NULLIF(COUNT(cul.id), 0), 3
                    ) AS accuracy_rate
                FROM chunk_usage_logs cul
                JOIN legal_knowledge_chunks lkc ON lkc.id = cul.chunk_id
                WHERE cul.was_answered = true AND cul.created_at >= :since
                  AND cul.is_deleted = false
                GROUP BY lkc.category
                ORDER BY accuracy_rate ASC NULLS LAST
            """),
            {"since": since},
        )
        rows = result.fetchall()
        return [
            {
                "category": row.category,
                "total_answers": row.total_answers,
                "correct": row.correct,
                "incorrect": row.incorrect,
                "accuracy_rate": float(row.accuracy_rate) if row.accuracy_rate else None,
            }
            for row in rows
        ]
    except Exception as e:
        logger.error("get_category_error_rates failed: %s", e)
        return []


async def get_user_weak_areas(
    db: AsyncSession, user_id: uuid.UUID, days: int = 30
) -> list[dict]:
    """Find which legal categories a specific user struggles with most."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        result = await db.execute(
            sa_text("""
                SELECT
                    lkc.category,
                    COUNT(cul.id) AS total,
                    SUM(CASE WHEN cul.answer_correct = false THEN 1 ELSE 0 END) AS errors,
                    ROUND(
                        SUM(CASE WHEN cul.answer_correct = false THEN 1 ELSE 0 END)::numeric /
                        NULLIF(COUNT(cul.id), 0), 3
                    ) AS error_rate
                FROM chunk_usage_logs cul
                JOIN legal_knowledge_chunks lkc ON lkc.id = cul.chunk_id
                WHERE cul.user_id = :uid AND cul.was_answered = true AND cul.created_at >= :since
                  AND cul.is_deleted = false
                GROUP BY lkc.category
                HAVING COUNT(cul.id) >= 3
                ORDER BY error_rate DESC
            """),
            {"uid": str(user_id), "since": since},
        )
        rows = result.fetchall()
        return [
            {
                "category": row.category,
                "total_answers": row.total,
                "errors": row.errors,
                "error_rate": float(row.error_rate) if row.error_rate else 0,
            }
            for row in rows
        ]
    except Exception as e:
        logger.error("get_user_weak_areas failed: %s", e)
        return []


# ═══════════════════════════════════════════════════════════════════════════════
# Scheduler hook — to be called by periodic job
# ═══════════════════════════════════════════════════════════════════════════════

async def run_feedback_aggregation() -> dict:
    """Entry point for scheduled feedback aggregation job.

    Call this daily (e.g. from scheduler.py or a cron endpoint).
    1. Recalculates effectiveness_score for all chunks
    2. Discovers new common_errors from user mistakes
    3. Returns summary stats
    """
    from app.database import async_session

    try:
        async with async_session() as db:
            updated = await recalculate_chunk_effectiveness(db)
            summary = await get_feedback_summary(db, days=7)
            summary["chunks_recalculated"] = updated
            logger.info(
                "Feedback aggregation complete: %d chunks updated, %d retrievals in last 7d",
                updated, summary.get("total_chunk_retrievals", 0),
            )
            return summary
    except Exception as e:
        logger.error("run_feedback_aggregation failed: %s", e)
        return {"error": str(e)}
