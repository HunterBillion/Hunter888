"""Shared RAG pipeline for legal knowledge base (Agent 2 Scoring + Agent 8 PvP).

Uses Gemini embedding API (gemini-embedding-001) for semantic search.
Fallback: keyword matching from LegalKnowledgeChunk.match_keywords.

Pipeline:
  player_message → embed(gemini-embedding-001) → pgvector cosine similarity (top-5)
  → context injected into AI judge / scoring prompt.

MVP: keyword matching + LLM validation.
Phase 4+: pgvector with real embeddings.
"""

import logging
import re
import uuid
from dataclasses import dataclass, field

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.rag import LegalCategory, LegalKnowledgeChunk

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class RAGResult:
    """Single retrieved legal knowledge chunk with relevance score."""
    chunk_id: uuid.UUID
    category: str
    fact_text: str
    law_article: str
    relevance_score: float  # 0.0-1.0
    common_errors: list[str] = field(default_factory=list)
    correct_response_hint: str | None = None


@dataclass
class RAGContext:
    """Collection of retrieved chunks for prompt injection."""
    query: str
    results: list[RAGResult] = field(default_factory=list)
    method: str = "keyword"  # "keyword" | "embedding"

    @property
    def has_results(self) -> bool:
        return len(self.results) > 0

    def to_prompt_context(self) -> str:
        """Format results as context string for LLM prompt injection."""
        if not self.results:
            return ""

        lines = ["### Правовая база (127-ФЗ «О несостоятельности (банкротстве)»):"]
        for i, r in enumerate(self.results, 1):
            lines.append(
                f"{i}. [{r.category}] {r.fact_text} "
                f"(Основание: {r.law_article})"
            )
            if r.common_errors:
                errors_str = "; ".join(r.common_errors[:3])
                lines.append(f"   ⚠ Частые ошибки: {errors_str}")
            if r.correct_response_hint:
                lines.append(f"   Подсказка: {r.correct_response_hint}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Embedding (Gemini API)
# ---------------------------------------------------------------------------

_embedding_client: httpx.AsyncClient | None = None


def _get_embedding_client() -> httpx.AsyncClient:
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = httpx.AsyncClient(timeout=10.0)
    return _embedding_client


async def get_embedding(text: str) -> list[float] | None:
    """Get embedding vector from Gemini Embedding API.

    Returns None if API is not configured or fails.
    """
    if not settings.gemini_embedding_api_key:
        return None

    try:
        client = _get_embedding_client()
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{settings.gemini_embedding_model}:embedContent"
        )
        resp = await client.post(
            url,
            headers={"x-goog-api-key": settings.gemini_embedding_api_key},
            json={
                "model": f"models/{settings.gemini_embedding_model}",
                "content": {"parts": [{"text": text}]},
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("embedding", {}).get("values")
    except Exception as e:
        logger.warning("Embedding API failed: %s", e)
        return None


async def close_embedding_client() -> None:
    """Gracefully close the shared httpx client. Call once during app shutdown."""
    global _embedding_client
    if _embedding_client is not None:
        await _embedding_client.aclose()
        _embedding_client = None


# ---------------------------------------------------------------------------
# Keyword-based retrieval (MVP fallback)
# ---------------------------------------------------------------------------

def _keyword_score(text: str, keywords: list[str]) -> float:
    """Calculate keyword match score (0.0-1.0)."""
    if not keywords:
        return 0.0

    text_lower = text.lower()
    matches = sum(1 for kw in keywords if kw.lower() in text_lower)
    return matches / len(keywords)


def _query_mentions_article(query: str, law_article: str) -> bool:
    q = query.lower()
    article = law_article.lower()
    return article in q or article.replace(" ", "") in q.replace(" ", "")


async def retrieve_by_keywords(
    query: str,
    db: AsyncSession,
    top_k: int = 5,
    min_score: float = 0.15,
    category: LegalCategory | None = None,
) -> list[RAGResult]:
    """Retrieve relevant legal chunks using keyword matching (MVP).

    Args:
        query: player's message text
        db: database session
        top_k: max results to return
        min_score: minimum relevance score threshold
        category: optional category filter

    Returns:
        List of RAGResult sorted by relevance (descending).
    """
    stmt = select(LegalKnowledgeChunk).where(LegalKnowledgeChunk.is_active.is_(True))
    if category:
        stmt = stmt.where(LegalKnowledgeChunk.category == category)
    stmt = stmt.limit(500)  # Safety limit to prevent memory issues

    result = await db.execute(stmt)
    chunks = result.scalars().all()

    scored: list[tuple[float, LegalKnowledgeChunk]] = []
    for chunk in chunks:
        keywords = chunk.match_keywords or []
        score = _keyword_score(query, keywords)

        # Boost: if query contains the law article reference
        if chunk.law_article and _query_mentions_article(query, chunk.law_article):
            score = min(1.0, score + 0.3)

        # Boost: check common errors against query
        for err in (chunk.common_errors or []):
            if isinstance(err, str) and err.lower() in query.lower():
                score = min(1.0, score + 0.2)
                break

        # Boost: hint phrases act like internal coaching material.
        hint = (chunk.correct_response_hint or "").lower()
        if hint:
            overlap = sum(1 for token in re.findall(r"\w+", hint)[:12] if token and token in query.lower())
            if overlap:
                score = min(1.0, score + min(0.18, overlap * 0.03))

        # High-frequency errors are more useful for coaching and examination.
        if chunk.error_frequency:
            score = min(1.0, score + min(0.12, chunk.error_frequency / 100))

        if score >= min_score:
            scored.append((score, chunk))

    # Sort by relevance (descending)
    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for relevance, chunk in scored[:top_k]:
        results.append(
            RAGResult(
                chunk_id=chunk.id,
                category=chunk.category.value,
                fact_text=chunk.fact_text,
                law_article=chunk.law_article,
                relevance_score=relevance,
                common_errors=chunk.common_errors or [],
                correct_response_hint=chunk.correct_response_hint,
            )
        )

    return results


# ---------------------------------------------------------------------------
# Embedding-based retrieval (Phase 4+)
# ---------------------------------------------------------------------------

async def retrieve_by_embedding(
    query: str,
    db: AsyncSession,
    top_k: int = 5,
) -> list[RAGResult]:
    """Retrieve relevant legal chunks using embedding similarity.

    Uses pgvector cosine similarity if embeddings are available.
    Falls back to keyword search if not.
    """
    embedding = await get_embedding(query)

    if embedding is None:
        logger.debug("Embedding not available, falling back to keyword search")
        return await retrieve_by_keywords(query, db, top_k)

    # Try pgvector cosine similarity search
    try:
        from sqlalchemy import text as sa_text

        # Use raw SQL for pgvector cosine distance operator <=>
        query_sql = sa_text("""
            SELECT id, category, fact_text, law_article, common_errors,
                   correct_response_hint,
                   1 - (embedding <=> :embedding::vector) AS similarity
            FROM legal_knowledge_chunks
            WHERE is_active = true
              AND embedding IS NOT NULL
            ORDER BY embedding <=> :embedding::vector
            LIMIT :top_k
        """)

        result = await db.execute(
            query_sql,
            {"embedding": str(embedding), "top_k": top_k},
        )
        rows = result.fetchall()

        if not rows:
            logger.debug("No embeddings in DB, falling back to keyword search")
            return await retrieve_by_keywords(query, db, top_k)

        results = []
        for row in rows:
            # Filter by minimum similarity threshold
            if row.similarity < 0.3:
                continue
            results.append(
                RAGResult(
                    chunk_id=row.id,
                    category=row.category if isinstance(row.category, str) else row.category.value,
                    fact_text=row.fact_text,
                    law_article=row.law_article,
                    relevance_score=float(row.similarity),
                    common_errors=row.common_errors or [],
                    correct_response_hint=row.correct_response_hint,
                )
            )

        if results:
            return results

        # No results above threshold -- fall back
        logger.debug("No embedding results above threshold, falling back to keyword search")
        return await retrieve_by_keywords(query, db, top_k)

    except Exception as e:
        logger.warning("pgvector query failed (extension may not be installed): %s", e)
        return await retrieve_by_keywords(query, db, top_k)


async def _retrieve_by_embedding_with_method(
    query: str,
    db: AsyncSession,
    top_k: int = 5,
) -> tuple[list[RAGResult], bool]:
    """Wrapper that returns (results, used_embedding_flag).

    Returns True for used_embedding only when results actually came
    from pgvector cosine similarity, not from keyword fallback.
    """
    embedding = await get_embedding(query)

    if embedding is None:
        return await retrieve_by_keywords(query, db, top_k), False

    try:
        from sqlalchemy import text as sa_text

        query_sql = sa_text("""
            SELECT id, category, fact_text, law_article, common_errors,
                   correct_response_hint,
                   1 - (embedding <=> :embedding::vector) AS similarity
            FROM legal_knowledge_chunks
            WHERE is_active = true
              AND embedding IS NOT NULL
            ORDER BY embedding <=> :embedding::vector
            LIMIT :top_k
        """)

        result = await db.execute(
            query_sql,
            {"embedding": str(embedding), "top_k": top_k},
        )
        rows = result.fetchall()

        if not rows:
            return await retrieve_by_keywords(query, db, top_k), False

        results = []
        for row in rows:
            if row.similarity < 0.3:
                continue
            results.append(
                RAGResult(
                    chunk_id=row.id,
                    category=row.category if isinstance(row.category, str) else row.category.value,
                    fact_text=row.fact_text,
                    law_article=row.law_article,
                    relevance_score=float(row.similarity),
                    common_errors=row.common_errors or [],
                    correct_response_hint=row.correct_response_hint,
                )
            )

        if results:
            return results, True

        return await retrieve_by_keywords(query, db, top_k), False

    except Exception as e:
        logger.warning("pgvector query failed (extension may not be installed): %s", e)
        return await retrieve_by_keywords(query, db, top_k), False


# ---------------------------------------------------------------------------
# Unified retrieval interface
# ---------------------------------------------------------------------------

async def retrieve_legal_context(
    query: str,
    db: AsyncSession,
    top_k: int = 5,
    prefer_embedding: bool = True,
) -> RAGContext:
    """Retrieve legal context for a player's message.

    Shared pipeline used by:
    - Agent 2 (Scoring): validates legal claims in training sessions
    - Agent 8 (PvP Judge): validates claims during PvP duels

    Args:
        query: player's message text
        db: database session
        top_k: max results
        prefer_embedding: try embedding search first

    Returns:
        RAGContext with results and prompt-ready context string.
    """
    method = "keyword"

    if prefer_embedding and settings.gemini_embedding_api_key:
        results, used_embedding = await _retrieve_by_embedding_with_method(query, db, top_k)
        if used_embedding:
            method = "embedding"
    else:
        results = await retrieve_by_keywords(query, db, top_k)

    context = RAGContext(query=query, results=results, method=method)

    if context.has_results:
        logger.debug(
            "RAG: retrieved %d chunks for query (method=%s, top_score=%.2f)",
            len(results),
            method,
            results[0].relevance_score if results else 0.0,
        )

    return context


async def validate_legal_claim(
    claim: str,
    db: AsyncSession,
) -> dict:
    """Quick validation: check if a specific legal claim matches known facts.

    Returns:
        {
            "is_valid": bool,
            "accuracy": "correct" | "incorrect" | "partial" | "unknown",
            "matching_fact": str | None,
            "law_article": str | None,
            "explanation": str | None,
        }
    """
    context = await retrieve_legal_context(claim, db, top_k=3)

    if not context.has_results:
        return {
            "is_valid": None,
            "accuracy": "unknown",
            "matching_fact": None,
            "law_article": None,
            "explanation": "Утверждение не соответствует известным юридическим фактам в базе.",
        }

    top = context.results[0]

    # Check if claim matches an error pattern
    claim_lower = claim.lower()
    for err in top.common_errors:
        if isinstance(err, str) and err.lower() in claim_lower:
            return {
                "is_valid": False,
                "accuracy": "incorrect",
                "matching_fact": top.fact_text,
                "law_article": top.law_article,
                "explanation": f"Ошибка: «{err}». Правильно: {top.fact_text}",
            }

    # If high relevance, likely correct or partial
    if top.relevance_score >= 0.5:
        return {
            "is_valid": True,
            "accuracy": "correct",
            "matching_fact": top.fact_text,
            "law_article": top.law_article,
            "explanation": None,
        }

    return {
        "is_valid": None,
        "accuracy": "partial",
        "matching_fact": top.fact_text,
        "law_article": top.law_article,
        "explanation": "Утверждение частично соответствует правовой норме.",
    }


# ---------------------------------------------------------------------------
# Embedding population utility
# ---------------------------------------------------------------------------

async def populate_embeddings(db: AsyncSession, batch_size: int = 10) -> int:
    """Populate embedding vectors for chunks that don't have them.

    Call this after seeding new knowledge chunks.
    Returns the number of chunks updated.
    """
    from sqlalchemy import text as sa_text

    # Get active chunks (embedding=NULL or not yet set)
    stmt = select(LegalKnowledgeChunk).where(
        LegalKnowledgeChunk.is_active.is_(True),
    )
    result = await db.execute(stmt)
    chunks = result.scalars().all()

    updated = 0
    for chunk in chunks:
        embedding = await get_embedding(chunk.fact_text)
        if embedding:
            # Use raw SQL to set pgvector column
            await db.execute(
                sa_text(
                    "UPDATE legal_knowledge_chunks "
                    "SET embedding = :emb::vector WHERE id = :id"
                ),
                {"emb": str(embedding), "id": str(chunk.id)},
            )
            updated += 1

            if updated % batch_size == 0:
                await db.commit()
                logger.info("Populated %d embeddings...", updated)

    if updated % batch_size != 0:
        await db.commit()

    logger.info("Embedding population complete: %d chunks updated", updated)
    return updated
