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
            f"?key={settings.gemini_embedding_api_key}"
        )
        resp = await client.post(
            url,
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

    result = await db.execute(stmt)
    chunks = result.scalars().all()

    scored: list[tuple[float, LegalKnowledgeChunk]] = []
    for chunk in chunks:
        keywords = chunk.match_keywords or []
        score = _keyword_score(query, keywords)

        # Boost: if query contains the law article reference
        if chunk.law_article and chunk.law_article.lower() in query.lower():
            score = min(1.0, score + 0.3)

        # Boost: check common errors against query
        for err in (chunk.common_errors or []):
            if isinstance(err, str) and err.lower() in query.lower():
                score = min(1.0, score + 0.2)
                break

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

    Phase 4+: requires pgvector extension and embedding column on LegalKnowledgeChunk.
    Falls back to keyword search if embeddings not available.
    """
    embedding = await get_embedding(query)

    if embedding is None:
        logger.debug("Embedding not available, falling back to keyword search")
        return await retrieve_by_keywords(query, db, top_k)

    # Phase 4 TODO: pgvector cosine similarity query
    # For now, fall back to keyword matching
    logger.debug(
        "Embedding retrieved (%d dims), but pgvector not yet configured. "
        "Falling back to keyword search.",
        len(embedding),
    )
    return await retrieve_by_keywords(query, db, top_k)


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
        results = await retrieve_by_embedding(query, db, top_k)
        if results:
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
