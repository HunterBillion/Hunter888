"""Embedding backfill for all RAG tables.

Populates missing embedding vectors for:
  - personality_chunks (content → embedding)
  - personality_examples (situation + dialogue → embedding)
  - wiki_pages (content[:500] → embedding)
  - legal_knowledge_chunks (50 missing, handled by rag_legal.py but we cover gaps)

Runs as background task on API startup. Batch processing with rate limiting
to avoid overwhelming the embedding provider (Ollama local / Gemini cloud).
"""

import asyncio
import logging
import time

from sqlalchemy import select, update, func, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

BATCH_SIZE = 5           # Texts per embedding API call
COMMIT_EVERY = 10        # Commit after N individual updates
PAUSE_BETWEEN_BATCHES = 0.2  # Seconds between batches (rate limit protection)
MAX_TEXT_LENGTH = 1000   # Truncate long texts before embedding (saves tokens)


def _truncate(text: str, max_len: int = MAX_TEXT_LENGTH) -> str:
    """Truncate text for embedding, cutting at last sentence boundary."""
    if len(text) <= max_len:
        return text
    cut = text[:max_len].rfind(".")
    if cut > max_len // 2:
        return text[: cut + 1]
    return text[:max_len]


# ── Personality Chunks ────────────────────────────────────────────────────────


async def populate_personality_chunk_embeddings(db: AsyncSession) -> int:
    """Populate embeddings for personality_chunks that lack them."""
    from app.models.rag import PersonalityChunk
    from app.services.llm import get_embeddings_batch

    result = await db.execute(
        select(PersonalityChunk.id, PersonalityChunk.content)
        .where(PersonalityChunk.is_active.is_(True))
        .where(PersonalityChunk.embedding.is_(None))
    )
    rows = result.fetchall()

    if not rows:
        logger.info("personality_chunks: all embeddings populated")
        return 0

    logger.info("personality_chunks: populating %d embeddings...", len(rows))
    updated = 0

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i: i + BATCH_SIZE]
        texts = [_truncate(row.content) for row in batch]

        embeddings = await get_embeddings_batch(texts)
        if not embeddings:
            logger.warning("personality_chunks: embedding batch failed at offset %d", i)
            await asyncio.sleep(2)
            continue

        for row, emb in zip(batch, embeddings):
            if emb and len(emb) > 0:
                await db.execute(
                    update(PersonalityChunk)
                    .where(PersonalityChunk.id == row.id)
                    .values(embedding=emb)
                )
                updated += 1

        if updated % COMMIT_EVERY == 0 and updated > 0:
            await db.commit()
            logger.info("personality_chunks: %d/%d done", updated, len(rows))

        await asyncio.sleep(PAUSE_BETWEEN_BATCHES)

    await db.commit()
    logger.info("personality_chunks: embedding complete — %d/%d updated", updated, len(rows))
    return updated


# ── Personality Examples ──────────────────────────────────────────────────────


async def populate_personality_example_embeddings(db: AsyncSession) -> int:
    """Populate embeddings for personality_examples that lack them."""
    from app.models.rag import PersonalityExample
    from app.services.llm import get_embeddings_batch

    result = await db.execute(
        select(PersonalityExample.id, PersonalityExample.situation, PersonalityExample.dialogue)
        .where(PersonalityExample.is_active.is_(True))
        .where(PersonalityExample.embedding.is_(None))
    )
    rows = result.fetchall()

    if not rows:
        logger.info("personality_examples: all embeddings populated")
        return 0

    logger.info("personality_examples: populating %d embeddings...", len(rows))
    updated = 0

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i: i + BATCH_SIZE]
        # Combine situation + dialogue for richer embedding
        texts = [_truncate(f"{row.situation} {row.dialogue}") for row in batch]

        embeddings = await get_embeddings_batch(texts)
        if not embeddings:
            logger.warning("personality_examples: embedding batch failed at offset %d", i)
            await asyncio.sleep(2)
            continue

        for row, emb in zip(batch, embeddings):
            if emb and len(emb) > 0:
                await db.execute(
                    update(PersonalityExample)
                    .where(PersonalityExample.id == row.id)
                    .values(embedding=emb)
                )
                updated += 1

        if updated % COMMIT_EVERY == 0 and updated > 0:
            await db.commit()
            logger.info("personality_examples: %d/%d done", updated, len(rows))

        await asyncio.sleep(PAUSE_BETWEEN_BATCHES)

    await db.commit()
    logger.info("personality_examples: embedding complete — %d/%d updated", updated, len(rows))
    return updated


# ── Wiki Pages ────────────────────────────────────────────────────────────────


async def populate_wiki_page_embeddings(db: AsyncSession) -> int:
    """Populate embeddings for wiki_pages that lack them."""
    from app.models.manager_wiki import WikiPage
    from app.services.llm import get_embeddings_batch

    result = await db.execute(
        select(WikiPage.id, WikiPage.content, WikiPage.page_path)
        .where(WikiPage.embedding.is_(None))
    )
    rows = result.fetchall()

    if not rows:
        logger.info("wiki_pages: all embeddings populated")
        return 0

    logger.info("wiki_pages: populating %d embeddings...", len(rows))
    updated = 0

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i: i + BATCH_SIZE]
        # Use page_path as prefix for context
        texts = [_truncate(f"{row.page_path}: {row.content}", 500) for row in batch]

        embeddings = await get_embeddings_batch(texts)
        if not embeddings:
            logger.warning("wiki_pages: embedding batch failed at offset %d", i)
            await asyncio.sleep(2)
            continue

        for row, emb in zip(batch, embeddings):
            if emb and len(emb) > 0:
                await db.execute(
                    update(WikiPage)
                    .where(WikiPage.id == row.id)
                    .values(embedding=emb)
                )
                updated += 1

        if updated % COMMIT_EVERY == 0 and updated > 0:
            await db.commit()

        await asyncio.sleep(PAUSE_BETWEEN_BATCHES)

    await db.commit()
    logger.info("wiki_pages: embedding complete — %d/%d updated", updated, len(rows))
    return updated


# ── Legal Chunks (gap fill for the 50 missed by rag_legal.py backfill) ────────


async def populate_legal_chunk_embeddings(db: AsyncSession) -> int:
    """Populate embeddings for legal_knowledge_chunks that lack them."""
    from app.models.rag import LegalKnowledgeChunk
    from app.services.llm import get_embeddings_batch

    current_model = "gemini-embedding-001"
    result = await db.execute(
        select(LegalKnowledgeChunk.id, LegalKnowledgeChunk.fact_text)
        .where(LegalKnowledgeChunk.is_active.is_(True))
        .where(LegalKnowledgeChunk.embedding.is_(None))
    )
    rows = result.fetchall()

    if not rows:
        logger.info("legal_knowledge_chunks: all embeddings populated")
        return 0

    logger.info("legal_knowledge_chunks: populating %d embeddings...", len(rows))
    updated = 0

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i: i + BATCH_SIZE]
        texts = [_truncate(row.fact_text) for row in batch]

        embeddings = await get_embeddings_batch(texts)
        if not embeddings:
            await asyncio.sleep(2)
            continue

        for row, emb in zip(batch, embeddings):
            if emb and len(emb) > 0:
                await db.execute(
                    update(LegalKnowledgeChunk)
                    .where(LegalKnowledgeChunk.id == row.id)
                    .values(embedding=emb, embedding_model=current_model)
                )
                updated += 1

        if updated % COMMIT_EVERY == 0 and updated > 0:
            await db.commit()

        await asyncio.sleep(PAUSE_BETWEEN_BATCHES)

    await db.commit()
    logger.info("legal_knowledge_chunks: embedding complete — %d/%d updated", updated, len(rows))
    return updated


# ── S2-08: Stale embedding detection ─────────────────────────────────────────


async def invalidate_stale_legal_embeddings(db: AsyncSession) -> int:
    """Detect legal chunks where content changed but embedding wasn't invalidated.

    Finds chunks where updated_at > created_at AND embedding IS NOT NULL,
    recomputes content_hash, and sets embedding = NULL for re-processing.
    Handles cases where the before_update hook wasn't active (e.g., raw SQL updates).
    """
    import hashlib

    from app.models.rag import LegalKnowledgeChunk

    result = await db.execute(
        select(
            LegalKnowledgeChunk.id,
            LegalKnowledgeChunk.fact_text,
            LegalKnowledgeChunk.law_article,
            LegalKnowledgeChunk.content_hash,
        )
        .where(
            LegalKnowledgeChunk.is_active.is_(True),
            LegalKnowledgeChunk.embedding.isnot(None),
            LegalKnowledgeChunk.updated_at.isnot(None),
        )
    )
    rows = result.fetchall()

    invalidated = 0
    for row in rows:
        expected_hash = hashlib.md5(
            f"{row.fact_text}::{row.law_article}".encode()
        ).hexdigest()
        if row.content_hash != expected_hash:
            await db.execute(
                update(LegalKnowledgeChunk)
                .where(LegalKnowledgeChunk.id == row.id)
                .values(
                    content_hash=expected_hash,
                    embedding=None,
                    embedding_model=None,
                )
            )
            invalidated += 1

    if invalidated > 0:
        await db.commit()
        logger.info(
            "legal_knowledge_chunks: invalidated %d stale embeddings", invalidated
        )
    return invalidated


# ── Main entry point ──────────────────────────────────────────────────────────


async def populate_all_embeddings() -> dict:
    """Populate embeddings for ALL tables. Returns stats dict."""
    from app.database import async_session

    stats = {}

    # S2-08: Detect and invalidate stale embeddings before populating
    try:
        async with async_session() as db:
            stale = await invalidate_stale_legal_embeddings(db)
            stats["stale_invalidated"] = stale
    except Exception as e:
        logger.warning("Stale embedding check failed: %s", e)
        stats["stale_invalidated"] = f"error: {e}"

    tables = [
        ("personality_chunks", populate_personality_chunk_embeddings),
        ("personality_examples", populate_personality_example_embeddings),
        ("wiki_pages", populate_wiki_page_embeddings),
        ("legal_knowledge_chunks", populate_legal_chunk_embeddings),
    ]

    for name, func in tables:
        try:
            async with async_session() as db:
                count = await func(db)
                stats[name] = count
                logger.info("Backfill [%s]: %d embeddings created", name, count)
        except Exception as e:
            logger.warning("Backfill [%s] failed: %s", name, e)
            stats[name] = f"error: {e}"

    return stats


async def safe_populate_all_embeddings() -> None:
    """Background task with retry. Called from main.py lifespan."""
    delays = [15, 30, 60]

    for attempt in range(len(delays) + 1):
        try:
            stats = await populate_all_embeddings()
            total = sum(v for v in stats.values() if isinstance(v, int))
            if total > 0:
                logger.info("Embedding backfill complete: %s", stats)
            else:
                logger.info("Embedding backfill: nothing to do (all populated)")
            return
        except Exception as e:
            if attempt < len(delays):
                delay = delays[attempt]
                logger.warning(
                    "Embedding backfill attempt %d failed: %s. Retry in %ds...",
                    attempt + 1, e, delay,
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "Embedding backfill failed after %d attempts: %s",
                    attempt + 1, e,
                )
