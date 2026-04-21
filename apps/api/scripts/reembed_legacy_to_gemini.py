"""Backfill embedding_v2 (gemini-embedding-001@768) for legacy RAG tables.

Target tables (all already have embedding_v2 shadow column via migration 20260417_005):
  - legal_knowledge_chunks  (~375 rows, fact_text)
  - personality_chunks      (~551 rows, content)
  - personality_examples    (~1535 rows, situation + dialogue)
  - wiki_pages              (~7 rows, page_path + content)

Already 100% populated in `embedding` (text-embedding-3-small@768). We write
gemini to `embedding_v2` while RAG keeps reading the legacy column until the
RAG code is switched (PR coming after this).

Safe to re-run: processes only `embedding_v2 IS NULL` rows.

Run (standalone, separate terminal from the dev server):
  cd apps/api
  nohup .venv/bin/python scripts/reembed_legacy_to_gemini.py \
    > scripts/legal_ingest/logs/reembed_$(date +%Y%m%d_%H%M).log 2>&1 &
  tail -f scripts/legal_ingest/logs/reembed_*.log
"""

import asyncio
import logging
import os
import sys
import time
from pathlib import Path

# Allow running from apps/api with `python scripts/...`
_APPS_API_DIR = Path(__file__).resolve().parent.parent
if str(_APPS_API_DIR) not in sys.path:
    sys.path.insert(0, str(_APPS_API_DIR))

from dotenv import load_dotenv
load_dotenv(_APPS_API_DIR.parent.parent / ".env")

import httpx
from sqlalchemy import select, update

# ── Config ──────────────────────────────────────────────────────────────

EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIM = 768
BATCH_SIZE = 10
PAUSE_BETWEEN_BATCHES = 0.2
MAX_INPUT_CHARS = 3000

# ── Logging ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("reembed")


async def embed_batch(client: httpx.AsyncClient, texts: list[str]) -> list[list[float]] | None:
    """Call navy embeddings endpoint."""
    url = os.environ.get("LOCAL_EMBEDDING_URL", "https://api.navy/v1").rstrip("/") + "/embeddings"
    api_key = os.environ.get("LOCAL_EMBEDDING_API_KEY", "")
    if not api_key:
        log.error("LOCAL_EMBEDDING_API_KEY missing")
        return None
    try:
        r = await client.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": EMBEDDING_MODEL, "input": texts, "dimensions": EMBEDDING_DIM},
            timeout=60.0,
        )
        if r.status_code != 200:
            log.warning("embed HTTP %d: %s", r.status_code, r.text[:200])
            return None
        data = r.json()
        return [item["embedding"] for item in data.get("data", [])]
    except Exception as exc:
        log.warning("embed error: %s", exc)
        return None


def _truncate(text: str, max_len: int = MAX_INPUT_CHARS) -> str:
    if len(text) <= max_len:
        return text
    cut = text[:max_len].rfind(".")
    if cut > max_len // 2:
        return text[: cut + 1]
    return text[:max_len]


async def backfill_legal_chunks(http: httpx.AsyncClient) -> int:
    from app.database import async_session
    from app.models.rag import LegalKnowledgeChunk

    tag = f"{EMBEDDING_MODEL}@{EMBEDDING_DIM}"
    total = 0

    async with async_session() as db:
        total_count = (await db.execute(
            select(LegalKnowledgeChunk.id).where(
                LegalKnowledgeChunk.is_active.is_(True),
                LegalKnowledgeChunk.embedding_v2.is_(None),
            )
        )).scalars().all()
    pending = len(total_count)
    log.info("[legal_knowledge_chunks] %d pending", pending)
    if pending == 0:
        return 0

    while True:
        async with async_session() as db:
            rows = (await db.execute(
                select(
                    LegalKnowledgeChunk.id,
                    LegalKnowledgeChunk.fact_text,
                ).where(
                    LegalKnowledgeChunk.is_active.is_(True),
                    LegalKnowledgeChunk.embedding_v2.is_(None),
                ).limit(BATCH_SIZE)
            )).all()
            if not rows:
                break

            texts = [_truncate(r.fact_text) for r in rows]
            vecs = await embed_batch(http, texts)
            if vecs is None or len(vecs) != len(rows):
                await asyncio.sleep(3)
                continue

            for row, vec in zip(rows, vecs):
                await db.execute(
                    update(LegalKnowledgeChunk)
                    .where(LegalKnowledgeChunk.id == row.id)
                    .values(embedding_v2=vec, embedding_v2_model=tag)
                )
            await db.commit()
            total += len(rows)
            if total % 50 == 0 or total == pending:
                log.info("[legal_knowledge_chunks] %d/%d done", total, pending)
        await asyncio.sleep(PAUSE_BETWEEN_BATCHES)
    log.info("[legal_knowledge_chunks] complete: %d", total)
    return total


async def backfill_personality_chunks(http: httpx.AsyncClient) -> int:
    from app.database import async_session
    from app.models.rag import PersonalityChunk

    tag = f"{EMBEDDING_MODEL}@{EMBEDDING_DIM}"
    total = 0

    async with async_session() as db:
        pending = len((await db.execute(
            select(PersonalityChunk.id).where(
                PersonalityChunk.is_active.is_(True),
                PersonalityChunk.embedding_v2.is_(None),
            )
        )).scalars().all())
    log.info("[personality_chunks] %d pending", pending)
    if pending == 0:
        return 0

    while True:
        async with async_session() as db:
            rows = (await db.execute(
                select(PersonalityChunk.id, PersonalityChunk.content).where(
                    PersonalityChunk.is_active.is_(True),
                    PersonalityChunk.embedding_v2.is_(None),
                ).limit(BATCH_SIZE)
            )).all()
            if not rows:
                break

            vecs = await embed_batch(http, [_truncate(r.content) for r in rows])
            if vecs is None or len(vecs) != len(rows):
                await asyncio.sleep(3)
                continue

            for row, vec in zip(rows, vecs):
                await db.execute(
                    update(PersonalityChunk)
                    .where(PersonalityChunk.id == row.id)
                    .values(embedding_v2=vec, embedding_v2_model=tag)
                )
            await db.commit()
            total += len(rows)
            if total % 100 == 0:
                log.info("[personality_chunks] %d/%d done", total, pending)
        await asyncio.sleep(PAUSE_BETWEEN_BATCHES)
    log.info("[personality_chunks] complete: %d", total)
    return total


async def backfill_personality_examples(http: httpx.AsyncClient) -> int:
    from app.database import async_session
    from app.models.rag import PersonalityExample

    tag = f"{EMBEDDING_MODEL}@{EMBEDDING_DIM}"
    total = 0

    async with async_session() as db:
        pending = len((await db.execute(
            select(PersonalityExample.id).where(
                PersonalityExample.is_active.is_(True),
                PersonalityExample.embedding_v2.is_(None),
            )
        )).scalars().all())
    log.info("[personality_examples] %d pending", pending)
    if pending == 0:
        return 0

    while True:
        async with async_session() as db:
            rows = (await db.execute(
                select(
                    PersonalityExample.id,
                    PersonalityExample.situation,
                    PersonalityExample.dialogue,
                ).where(
                    PersonalityExample.is_active.is_(True),
                    PersonalityExample.embedding_v2.is_(None),
                ).limit(BATCH_SIZE)
            )).all()
            if not rows:
                break

            texts = [_truncate(f"{r.situation} {r.dialogue}") for r in rows]
            vecs = await embed_batch(http, texts)
            if vecs is None or len(vecs) != len(rows):
                await asyncio.sleep(3)
                continue

            for row, vec in zip(rows, vecs):
                await db.execute(
                    update(PersonalityExample)
                    .where(PersonalityExample.id == row.id)
                    .values(embedding_v2=vec, embedding_v2_model=tag)
                )
            await db.commit()
            total += len(rows)
            if total % 200 == 0:
                log.info("[personality_examples] %d/%d done", total, pending)
        await asyncio.sleep(PAUSE_BETWEEN_BATCHES)
    log.info("[personality_examples] complete: %d", total)
    return total


async def backfill_wiki_pages(http: httpx.AsyncClient) -> int:
    from app.database import async_session
    from app.models.manager_wiki import WikiPage

    tag = f"{EMBEDDING_MODEL}@{EMBEDDING_DIM}"
    total = 0

    while True:
        async with async_session() as db:
            rows = (await db.execute(
                select(WikiPage.id, WikiPage.page_path, WikiPage.content).where(
                    WikiPage.embedding_v2.is_(None),
                ).limit(BATCH_SIZE)
            )).all()
            if not rows:
                break

            texts = [_truncate(f"{r.page_path}: {r.content}", 1000) for r in rows]
            vecs = await embed_batch(http, texts)
            if vecs is None or len(vecs) != len(rows):
                await asyncio.sleep(3)
                continue

            for row, vec in zip(rows, vecs):
                await db.execute(
                    update(WikiPage)
                    .where(WikiPage.id == row.id)
                    .values(embedding_v2=vec, embedding_v2_model=tag)
                )
            await db.commit()
            total += len(rows)
        await asyncio.sleep(PAUSE_BETWEEN_BATCHES)
    log.info("[wiki_pages] complete: %d", total)
    return total


async def main() -> int:
    log.info("Reembed legacy RAG tables → %s@%d", EMBEDDING_MODEL, EMBEDDING_DIM)
    started = time.time()
    stats = {}

    async with httpx.AsyncClient() as http:
        for name, fn in (
            ("wiki_pages",           backfill_wiki_pages),
            ("legal_knowledge_chunks", backfill_legal_chunks),
            ("personality_chunks",   backfill_personality_chunks),
            ("personality_examples", backfill_personality_examples),
        ):
            try:
                stats[name] = await fn(http)
            except Exception as exc:
                log.error("[%s] failed: %s", name, exc)
                stats[name] = f"error: {exc}"

    elapsed = time.time() - started
    log.info("Done in %.1fs. Stats: %s", elapsed, stats)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
