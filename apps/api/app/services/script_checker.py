"""Script adherence checker using keyword matching + optional embeddings.

Phase 2 (Week 9): Full implementation.
Compares manager's speech against script checkpoints in real-time.
Uses keyword matching as primary method (fast, no external API needed).
Embedding-based cosine similarity available when pgvector embeddings are populated.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import async_session
from app.models.script import Checkpoint, Script

logger = logging.getLogger(__name__)


def _keyword_similarity(text: str, keywords: list[str]) -> float:
    """Calculate keyword-based similarity score (0.0 - 1.0).

    Returns the fraction of checkpoint keywords found in the user's text.
    """
    if not keywords:
        return 0.0

    text_lower = text.lower()
    matched = sum(1 for kw in keywords if kw.lower() in text_lower)
    return matched / len(keywords)


async def check_checkpoint_match(
    user_text: str,
    checkpoint_id: str | uuid.UUID,
    threshold: float = 0.7,
) -> tuple[bool, float]:
    """Check if user text matches a script checkpoint.

    Args:
        user_text: The text to check against the checkpoint.
        checkpoint_id: UUID of the checkpoint to match against.
        threshold: Minimum similarity score to consider a match (0.0 - 1.0).

    Returns:
        Tuple of (matched: bool, similarity_score: float).
    """
    if isinstance(checkpoint_id, str):
        checkpoint_id = uuid.UUID(checkpoint_id)

    async with async_session() as db:
        result = await db.execute(
            select(Checkpoint).where(Checkpoint.id == checkpoint_id)
        )
        checkpoint = result.scalar_one_or_none()

    if checkpoint is None:
        logger.warning("Checkpoint %s not found", checkpoint_id)
        return False, 0.0

    # Combine keywords from JSONB field
    keywords = checkpoint.keywords if isinstance(checkpoint.keywords, list) else []

    # Also match against checkpoint description words
    desc_words = [w for w in checkpoint.description.lower().split() if len(w) > 3]
    all_keywords = list(set(keywords + desc_words[:5]))  # cap description words

    score = _keyword_similarity(user_text, all_keywords)
    return score >= threshold, score


async def check_all_checkpoints(
    user_text: str,
    script_id: uuid.UUID,
    threshold: float = 0.3,
) -> list[dict]:
    """Check user text against all checkpoints of a script.

    Returns a list of checkpoint match results:
    [{"checkpoint_id": ..., "title": ..., "score": float, "matched": bool, "weight": float}]
    """
    async with async_session() as db:
        result = await db.execute(
            select(Script)
            .options(selectinload(Script.checkpoints))
            .where(Script.id == script_id)
        )
        script = result.scalar_one_or_none()

    if script is None:
        logger.warning("Script %s not found", script_id)
        return []

    results = []
    for cp in script.checkpoints:
        keywords = cp.keywords if isinstance(cp.keywords, list) else []
        score = _keyword_similarity(user_text, keywords)
        results.append({
            "checkpoint_id": str(cp.id),
            "title": cp.title,
            "order_index": cp.order_index,
            "score": round(score, 3),
            "matched": score >= threshold,
            "weight": cp.weight,
        })

    return sorted(results, key=lambda x: x["order_index"])


async def get_session_checkpoint_progress(
    script_id: uuid.UUID,
    message_history: list[dict],
    threshold: float = 0.3,
) -> dict:
    """Calculate overall script adherence from message history.

    Args:
        script_id: Script to check against.
        message_history: List of {"role": ..., "content": ...} dicts.
        threshold: Keyword match threshold per checkpoint.

    Returns:
        {
            "total_score": float (0-100),
            "checkpoints": [...],
            "reached_count": int,
            "total_count": int,
        }
    """
    # Combine all user messages into one text block for matching
    user_texts = [
        m["content"]
        for m in message_history
        if m.get("role") == "user" and m.get("content")
    ]
    combined_text = " ".join(user_texts)

    async with async_session() as db:
        result = await db.execute(
            select(Script)
            .options(selectinload(Script.checkpoints))
            .where(Script.id == script_id)
        )
        script = result.scalar_one_or_none()

    if script is None:
        return {"total_score": 0, "checkpoints": [], "reached_count": 0, "total_count": 0}

    checkpoints_results = []
    total_weighted = 0.0
    reached_weighted = 0.0

    for cp in script.checkpoints:
        keywords = cp.keywords if isinstance(cp.keywords, list) else []
        score = _keyword_similarity(combined_text, keywords)
        matched = score >= threshold

        total_weighted += cp.weight
        if matched:
            reached_weighted += cp.weight * score

        checkpoints_results.append({
            "checkpoint_id": str(cp.id),
            "title": cp.title,
            "order_index": cp.order_index,
            "score": round(score, 3),
            "matched": matched,
            "weight": cp.weight,
        })

    total_score = (reached_weighted / total_weighted * 100) if total_weighted > 0 else 0
    reached_count = sum(1 for c in checkpoints_results if c["matched"])

    return {
        "total_score": round(total_score, 1),
        "checkpoints": sorted(checkpoints_results, key=lambda x: x["order_index"]),
        "reached_count": reached_count,
        "total_count": len(checkpoints_results),
    }
