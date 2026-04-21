"""Stage 08 — embed legal_document rows with gemini-embedding-001@768.

Targets:
  - ВСЕ rows в legal_document с embedding_v2 IS NULL
  - Приоритет: law_item > court_paragraph > law_article > court_case
    (child rows важнее для retrieval, parent для контекста)

Использует navy.api (LOCAL_EMBEDDING_URL / LOCAL_EMBEDDING_API_KEY из .env).

Батчи по EMBEDDING_BATCH_SIZE (10), пауза 0.2s между батчами.

Resumable: можно прервать и перезапустить, обработает только NULL.

Run:
  .venv/bin/python -m scripts.legal_ingest.08_embed_gemini
"""

import asyncio
import os
import sys
from pathlib import Path

if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from scripts.legal_ingest import config as cfg, common  # noqa: E402
else:
    from . import config as cfg, common

import httpx
from sqlalchemy import select, update

log = common.make_logger("08_embed_gemini")

PRIORITY_ORDER = ["law_item", "court_paragraph", "law_article", "court_case", "law_chapter", "law_fz"]


async def embed_batch(client: httpx.AsyncClient, texts: list[str]) -> list[list[float]] | None:
    """Call navy embeddings endpoint for a batch."""
    url = os.environ.get("LOCAL_EMBEDDING_URL", "https://api.navy/v1").rstrip("/") + "/embeddings"
    api_key = os.environ.get("LOCAL_EMBEDDING_API_KEY", "")
    if not api_key:
        log.error("LOCAL_EMBEDDING_API_KEY not set in environment")
        return None
    try:
        r = await client.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": cfg.EMBEDDING_MODEL,
                "input": texts,
                "dimensions": cfg.EMBEDDING_DIMENSIONS,
            },
            timeout=60.0,
        )
        if r.status_code != 200:
            log.warning("embed batch HTTP %d: %s", r.status_code, r.text[:300])
            return None
        data = r.json()
        embeddings = [item["embedding"] for item in data.get("data", [])]
        # Verify dimensions
        if embeddings and len(embeddings[0]) != cfg.EMBEDDING_DIMENSIONS:
            log.warning("Unexpected dim=%d (wanted %d)", len(embeddings[0]), cfg.EMBEDDING_DIMENSIONS)
        return embeddings
    except Exception as e:
        log.warning("embed batch error: %s", e)
        return None


async def main() -> int:
    # Load .env manually (script can be launched outside uvicorn)
    try:
        from dotenv import load_dotenv
        # .env lives at Hunter888-main/.env — 4 levels up from this file
        root_env = Path(__file__).resolve().parents[4] / ".env"
        load_dotenv(root_env)
        log.info("Loaded env from %s (exists=%s)", root_env, root_env.exists())
    except ImportError:
        log.info("python-dotenv not installed — relying on exported env vars")

    log.info("Stage 08: embedding legal_document rows with %s@%d",
             cfg.EMBEDDING_MODEL, cfg.EMBEDDING_DIMENSIONS)

    from app.database import async_session
    from app.models.legal_document import LegalDocument

    model_tag = f"{cfg.EMBEDDING_MODEL}@{cfg.EMBEDDING_DIMENSIONS}"

    total_ok = 0
    total_fail = 0

    async with httpx.AsyncClient() as http:
        for doc_type in PRIORITY_ORDER:
            async with async_session() as db:
                # Count pending
                pending_count = (await db.execute(
                    select(LegalDocument).where(
                        LegalDocument.doc_type == doc_type,
                        LegalDocument.is_active.is_(True),
                        LegalDocument.embedding_v2.is_(None),
                    )
                )).scalars().all()
                total = len(pending_count)
                if total == 0:
                    log.info("  %s: all embedded already", doc_type)
                    continue
                log.info("  %s: %d rows to embed", doc_type, total)

            processed = 0
            while True:
                async with async_session() as db:
                    rows = (await db.execute(
                        select(LegalDocument.id, LegalDocument.content).where(
                            LegalDocument.doc_type == doc_type,
                            LegalDocument.is_active.is_(True),
                            LegalDocument.embedding_v2.is_(None),
                        ).limit(cfg.EMBEDDING_BATCH_SIZE)
                    )).all()
                    if not rows:
                        break

                    ids = [r.id for r in rows]
                    texts = [r.content[:3000] for r in rows]  # safe ceiling for embedding input

                    vecs = await embed_batch(http, texts)
                    if vecs is None or len(vecs) != len(rows):
                        total_fail += len(rows)
                        log.warning("  batch failed — waiting 5s before retry")
                        await asyncio.sleep(5)
                        continue

                    for row_id, vec in zip(ids, vecs):
                        await db.execute(
                            update(LegalDocument)
                            .where(LegalDocument.id == row_id)
                            .values(embedding_v2=vec, embedding_model=model_tag)
                        )
                    await db.commit()

                    processed += len(rows)
                    total_ok += len(rows)

                    if processed % (cfg.EMBEDDING_BATCH_SIZE * 5) == 0:
                        log.info("    %s: %d/%d", doc_type, processed, total)

                await asyncio.sleep(0.2)

            log.info("  %s: done (processed %d)", doc_type, processed)

    log.info("Stage 08 done: ok=%d fail=%d", total_ok, total_fail)
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
