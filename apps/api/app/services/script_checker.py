"""Script adherence checker using sentence-transformers embeddings.

Phase 2: Full implementation with cosine similarity via embeddings microservice.
Primary: cosine similarity via embeddings service (>= 0.72 = match).
Fallback: keyword matching if embeddings service unavailable.
"""

import logging
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import async_session
from app.models.script import Checkpoint, Script

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.72
KEYWORD_THRESHOLD = 0.3
ANTI_PATTERN_THRESHOLD = 0.65

ANTI_PATTERNS = {
    "false_promises": [
        "гарантирую списание всех долгов",
        "точно спишут все долги",
        "сто процентов спишут",
        "гарантированное списание",
    ],
    "intimidation": [
        "вас посадят в тюрьму",
        "приставы придут к вам домой",
        "вас арестуют",
        "заберут всё имущество",
    ],
    "incorrect_info": [
        "банкротство абсолютно бесплатно",
        "кредитная история не пострадает",
        "никаких последствий банкротства нет",
    ],
}


async def _get_similarity(text1: str, text2: str) -> float | None:
    url = f"{settings.embeddings_service_url.rstrip('/')}/similarity"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json={"text1": text1, "text2": text2})
        if resp.status_code == 200:
            return resp.json().get("score", 0.0)
        return None
    except (httpx.ConnectError, httpx.TimeoutException):
        return None


def _keyword_similarity(text: str, keywords: list[str]) -> float:
    if not keywords:
        return 0.0
    text_lower = text.lower()
    matched = sum(1 for kw in keywords if kw.lower() in text_lower)
    return matched / len(keywords)


async def check_checkpoint_match(
    user_text: str,
    checkpoint_id: str | uuid.UUID,
    threshold: float = SIMILARITY_THRESHOLD,
) -> tuple[bool, float]:
    if isinstance(checkpoint_id, str):
        checkpoint_id = uuid.UUID(checkpoint_id)

    async with async_session() as db:
        result = await db.execute(
            select(Checkpoint).where(Checkpoint.id == checkpoint_id)
        )
        checkpoint = result.scalar_one_or_none()

    if checkpoint is None:
        return False, 0.0

    ref_text = checkpoint.description
    if hasattr(checkpoint, "ideal_phrasing") and checkpoint.ideal_phrasing:
        ref_text = checkpoint.ideal_phrasing

    score = await _get_similarity(user_text, ref_text)
    if score is not None:
        return score >= threshold, round(score, 3)

    keywords = checkpoint.keywords if isinstance(checkpoint.keywords, list) else []
    desc_words = [w for w in checkpoint.description.lower().split() if len(w) > 3]
    all_keywords = list(set(keywords + desc_words[:5]))
    score = _keyword_similarity(user_text, all_keywords)
    return score >= KEYWORD_THRESHOLD, round(score, 3)


async def check_all_checkpoints(
    user_text: str,
    script_id: uuid.UUID,
    threshold: float = SIMILARITY_THRESHOLD,
) -> list[dict]:
    async with async_session() as db:
        result = await db.execute(
            select(Script)
            .options(selectinload(Script.checkpoints))
            .where(Script.id == script_id)
        )
        script = result.scalar_one_or_none()

    if script is None:
        return []

    results = []
    for cp in script.checkpoints:
        ref_text = cp.description
        if hasattr(cp, "ideal_phrasing") and cp.ideal_phrasing:
            ref_text = cp.ideal_phrasing

        score = await _get_similarity(user_text, ref_text)
        if score is not None:
            matched = score >= threshold
        else:
            keywords = cp.keywords if isinstance(cp.keywords, list) else []
            score = _keyword_similarity(user_text, keywords)
            matched = score >= KEYWORD_THRESHOLD

        results.append({
            "checkpoint_id": str(cp.id),
            "title": cp.title,
            "order_index": cp.order_index,
            "score": round(score, 3),
            "matched": matched,
            "weight": cp.weight,
        })

    return sorted(results, key=lambda x: x["order_index"])


async def detect_anti_patterns(user_text: str) -> list[dict]:
    detected = []
    for category, phrases in ANTI_PATTERNS.items():
        max_score = 0.0
        for phrase in phrases:
            score = await _get_similarity(user_text, phrase)
            if score is None:
                words = phrase.lower().split()
                score = _keyword_similarity(user_text, words)
            if score > max_score:
                max_score = score
        if max_score >= ANTI_PATTERN_THRESHOLD:
            detected.append({"category": category, "score": round(max_score, 3)})
    return detected


async def get_session_checkpoint_progress(
    script_id: uuid.UUID,
    message_history: list[dict],
    threshold: float = SIMILARITY_THRESHOLD,
) -> dict:
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
        ref_text = cp.description
        if hasattr(cp, "ideal_phrasing") and cp.ideal_phrasing:
            ref_text = cp.ideal_phrasing

        score = await _get_similarity(combined_text, ref_text)
        if score is not None:
            matched = score >= threshold
        else:
            keywords = cp.keywords if isinstance(cp.keywords, list) else []
            score = _keyword_similarity(combined_text, keywords)
            matched = score >= KEYWORD_THRESHOLD

        total_weighted += cp.weight
        if matched:
            reached_weighted += cp.weight * min(score / threshold, 1.0)

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
