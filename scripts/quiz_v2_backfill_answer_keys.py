"""One-shot LLM backfill for ``quiz_v2_answer_keys`` (Path A, A1).

Reads every active row from ``legal_knowledge_chunks`` and emits one or
more answer-key rows per chunk. Two flavors per Q-NEW-3:

* **factoid** — ``expected_answer = chunk.fact_text`` (no LLM call).
  Match strategy ``synonyms`` with the canonical answer + 0..3 synonyms
  pulled from common phrasings.

* **strategic** — LLM-generated. The judge model produces a JSON object
  ``{question, expected_answer, synonyms[], match_strategy, confidence}``
  rooted in the chunk text. ``confidence`` becomes ``original_confidence``.

Rows land with ``is_active=False`` and ``knowledge_status='needs_review'``
unless ``original_confidence >= settings.quiz_v2_answer_key_auto_publish_confidence``
(default 0.85), in which case they auto-publish — same gate as
``arena_knowledge_auto_publish`` (``api/rop.py:1683``).

Usage
-----

    docker compose -f docker-compose.yml -f docker-compose.prod.yml \\
        exec -T api python -m scripts.quiz_v2_backfill_answer_keys \\
        [--dry-run] [--limit N] [--only-flavor factoid|strategic]

The script is idempotent: ``question_hash`` is the natural dedup key
(matches ``LegalKnowledgeChunk.content_hash`` shape per Q-bb2). Re-runs
skip rows already present.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_factory
from app.models.quiz_v2 import QuizV2AnswerKey
from app.models.rag import LegalKnowledgeChunk
from app.services.llm import generate_response
from app.services.quiz_v2.answer_keys import question_hash


logger = logging.getLogger("quiz_v2.backfill")


SYSTEM_PROMPT = (
    "Ты — методолог-эксперт по 127-ФЗ (банкротство физлиц). "
    "Тебе дают параграф юридического знания. Твоя задача: сгенерировать "
    "один открытый стратегический вопрос для проверки знаний и "
    "канонический эталонный ответ на него. Ответ должен быть одной фразой "
    "длиной 5-25 слов. Формат вывода — строго JSON, без преамбулы и "
    "комментариев:\n"
    '{"question": "...", "expected_answer": "...", '
    '"synonyms": ["...", "..."], '
    '"match_strategy": "synonyms" | "keyword", '
    '"confidence": 0.0..1.0}'
)


async def _generate_strategic_key(chunk: LegalKnowledgeChunk) -> dict[str, Any] | None:
    """Call the judge model to produce a strategic-flavor answer key."""
    user_msg = (
        f"Параграф знания (статья {chunk.law_article}):\n\n{chunk.fact_text}\n\n"
        "Сгенерируй стратегический вопрос и эталонный ответ."
    )
    try:
        resp = await generate_response(
            system_prompt=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
            task_type="judge",
            prefer_provider="cloud",
            max_tokens=400,
            temperature=0.2,
        )
    except Exception:
        logger.exception("LLM call failed for chunk_id=%s", chunk.id)
        return None

    raw = (resp.text or "").strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        logger.warning("Non-JSON response for chunk_id=%s: %r", chunk.id, raw[:200])
        return None
    try:
        payload = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        logger.warning("JSON decode failed for chunk_id=%s", chunk.id)
        return None

    required = {"question", "expected_answer", "synonyms", "match_strategy", "confidence"}
    if not required.issubset(payload.keys()):
        logger.warning("Missing fields for chunk_id=%s: %s", chunk.id, payload.keys())
        return None

    if payload["match_strategy"] not in ("synonyms", "keyword"):
        payload["match_strategy"] = "synonyms"
    payload["confidence"] = max(0.0, min(1.0, float(payload["confidence"])))
    payload["synonyms"] = [str(s) for s in payload["synonyms"][:8]]
    return payload


async def _factoid_key_for(chunk: LegalKnowledgeChunk) -> dict[str, Any]:
    """Deterministic factoid key — chunk.fact_text is already canonical."""
    return {
        "question": f"Что говорит {chunk.law_article} по теме «{chunk.category}»?",
        "expected_answer": chunk.fact_text,
        "synonyms": [],
        "match_strategy": "synonyms",
        "confidence": 1.0,
    }


async def _upsert_key(
    session: AsyncSession,
    *,
    chunk: LegalKnowledgeChunk,
    payload: dict[str, Any],
    flavor: str,
    auto_publish_threshold: float,
) -> bool:
    """Insert one answer-key row; skip if (chunk_id, hash, NULL) already exists."""
    qhash = question_hash(payload["question"], payload["expected_answer"])
    confidence = float(payload["confidence"])
    auto_publish = confidence >= auto_publish_threshold

    stmt = pg_insert(QuizV2AnswerKey).values(
        id=uuid.uuid4(),
        chunk_id=chunk.id,
        team_id=None,
        question_hash=qhash,
        flavor=flavor,
        expected_answer=payload["expected_answer"],
        match_strategy=payload["match_strategy"],
        match_config={},
        synonyms=payload["synonyms"],
        article_ref=chunk.law_article,
        knowledge_status="actual" if auto_publish else "needs_review",
        is_active=auto_publish,
        source="llm_backfill" if flavor == "strategic" else "seed_loader",
        original_confidence=confidence,
        generated_by="claude-judge" if flavor == "strategic" else "deterministic",
    ).on_conflict_do_nothing(constraint="uq_quiz_v2_answer_keys_chunk_hash_team")

    result = await session.execute(stmt)
    return result.rowcount > 0


async def run(
    *,
    dry_run: bool,
    limit: int | None,
    only_flavor: str | None,
) -> dict[str, int]:
    threshold = settings.quiz_v2_answer_key_auto_publish_confidence
    counts = {"chunks_seen": 0, "factoid_inserted": 0, "strategic_inserted": 0, "skipped": 0}

    async with async_session_factory() as session:
        stmt = select(LegalKnowledgeChunk).where(LegalKnowledgeChunk.is_active.is_(True))
        if limit:
            stmt = stmt.limit(limit)
        chunks = (await session.execute(stmt)).scalars().all()

        for chunk in chunks:
            counts["chunks_seen"] += 1

            if only_flavor in (None, "factoid"):
                payload = await _factoid_key_for(chunk)
                if dry_run:
                    logger.info("[dry-run] factoid for chunk_id=%s", chunk.id)
                    counts["factoid_inserted"] += 1
                else:
                    inserted = await _upsert_key(
                        session,
                        chunk=chunk,
                        payload=payload,
                        flavor="factoid",
                        auto_publish_threshold=threshold,
                    )
                    if inserted:
                        counts["factoid_inserted"] += 1
                    else:
                        counts["skipped"] += 1

            if only_flavor in (None, "strategic"):
                payload = await _generate_strategic_key(chunk)
                if payload is None:
                    counts["skipped"] += 1
                    continue
                if dry_run:
                    logger.info("[dry-run] strategic for chunk_id=%s conf=%.2f", chunk.id, payload["confidence"])
                    counts["strategic_inserted"] += 1
                else:
                    inserted = await _upsert_key(
                        session,
                        chunk=chunk,
                        payload=payload,
                        flavor="strategic",
                        auto_publish_threshold=threshold,
                    )
                    if inserted:
                        counts["strategic_inserted"] += 1
                    else:
                        counts["skipped"] += 1

        if not dry_run:
            await session.commit()

    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="Skip DB writes; print plan only.")
    parser.add_argument("--limit", type=int, default=None, help="Process at most N chunks (smoke test).")
    parser.add_argument(
        "--only-flavor",
        choices=("factoid", "strategic"),
        default=None,
        help="Generate only one flavor (default: both).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    counts = asyncio.run(
        run(dry_run=args.dry_run, limit=args.limit, only_flavor=args.only_flavor)
    )

    logger.info("Backfill complete: %s", counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
