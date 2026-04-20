"""Generate multiple-choice options for legal_knowledge_chunks.

For every active chunk that has a blitz_question + blitz_answer but no
`choices` yet, ask navy.api (gpt-5.4) to produce 3 plausible wrong options
+ place the correct answer at a random index. The result is persisted to
`choices` (JSONB) + `correct_choice_index` (int).

Run manually:

    cd apps/api
    .venv/bin/python -m scripts.seed_mc_choices --limit 50

Flags:
    --limit N      process at most N chunks (default 30)
    --force        re-generate even if `choices` is already set
    --dry-run      print what would change, don't write

The script is idempotent: re-running without --force skips filled rows.
On any LLM failure we just skip that chunk and continue — no row is
partially written.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import re
import sys
from pathlib import Path

# Allow `python -m scripts.seed_mc_choices` from apps/api root
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402
from sqlalchemy import select, update  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import async_session  # noqa: E402
from app.models.rag import LegalKnowledgeChunk  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("seed_mc_choices")


MODEL = "gpt-5.4"
TIMEOUT = 20.0

SYSTEM_PROMPT = (
    "Ты — эксперт по 127-ФЗ (банкротство физлиц). Твоя задача — сгенерировать "
    "3 НЕВЕРНЫХ, но правдоподобных варианта ответа для теста. Варианты должны "
    "быть короткими (≤14 слов), одной тематики с правильным ответом и "
    "реалистичными — такими, которые менеджер-новичок мог бы принять за истину. "
    "Избегай абсурда. Верни строго JSON: "
    '{"distractors":["…","…","…"]} — без markdown, без комментариев.'
)


async def _call_navy(question: str, correct_answer: str) -> list[str] | None:
    if not settings.local_llm_api_key or not settings.local_llm_url:
        logger.error("navy.api not configured (LOCAL_LLM_URL / LOCAL_LLM_API_KEY).")
        return None
    url = settings.local_llm_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"ВОПРОС: {question}\n"
                    f"ПРАВИЛЬНЫЙ ОТВЕТ: {correct_answer}\n"
                    "Сгенерируй 3 неверных дистрактора."
                ),
            },
        ],
        "temperature": 0.5,
        "max_tokens": 220,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {settings.local_llm_api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(url, headers=headers, json=payload)
    except (httpx.TimeoutException, httpx.HTTPError) as e:
        logger.warning("network error: %s", e)
        return None
    if resp.status_code >= 400:
        logger.warning("upstream %d: %s", resp.status_code, resp.text[:200])
        return None
    try:
        raw = resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as e:
        logger.warning("malformed response: %s", e)
        return None
    # Parse JSON — strip fences if model added them.
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    distractors = data.get("distractors") if isinstance(data, dict) else None
    if not isinstance(distractors, list):
        return None
    cleaned = [str(d).strip() for d in distractors if str(d).strip()]
    if len(cleaned) < 3:
        return None
    return cleaned[:3]


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    processed = 0
    updated = 0
    skipped = 0
    failed = 0

    async with async_session() as db:
        q = select(LegalKnowledgeChunk).where(
            LegalKnowledgeChunk.is_active.is_(True),
            LegalKnowledgeChunk.blitz_question.isnot(None),
            LegalKnowledgeChunk.blitz_answer.isnot(None),
        )
        if not args.force:
            q = q.where(LegalKnowledgeChunk.choices.is_(None))
        q = q.limit(args.limit)
        rows = (await db.execute(q)).scalars().all()

        logger.info("eligible chunks: %d", len(rows))

        for chunk in rows:
            processed += 1
            question = chunk.blitz_question or ""
            correct = chunk.blitz_answer or ""
            if not question.strip() or not correct.strip():
                skipped += 1
                continue

            distractors = await _call_navy(question, correct)
            if not distractors:
                failed += 1
                logger.info("skip %s — grader returned no distractors", chunk.id)
                continue

            # Place the correct answer at a random index (0..3).
            options = list(distractors[:3])
            correct_index = random.randint(0, len(options))
            options.insert(correct_index, correct.strip())

            if args.dry_run:
                logger.info(
                    "DRY-RUN %s: correct_index=%d\n   %s",
                    chunk.id,
                    correct_index,
                    "\n   ".join(f"{i}. {o}" for i, o in enumerate(options)),
                )
                continue

            await db.execute(
                update(LegalKnowledgeChunk)
                .where(LegalKnowledgeChunk.id == chunk.id)
                .values(choices=options, correct_choice_index=correct_index)
            )
            updated += 1
            logger.info("updated %s (correct_index=%d)", chunk.id, correct_index)

        if not args.dry_run:
            await db.commit()

    logger.info(
        "done — processed=%d updated=%d skipped=%d failed=%d",
        processed,
        updated,
        skipped,
        failed,
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
