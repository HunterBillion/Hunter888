"""Production RAG pipeline for 127-ФЗ legal knowledge base.

Multi-strategy retrieval with hybrid reranking:
  1. Embedding search (pgvector cosine similarity via Gemini embeddings)
  2. Keyword matching (DB-level ts_vector + application scoring)
  3. Hybrid Reciprocal Rank Fusion (RRF) — merges both strategies
  4. Feedback loop: usage tracking → chunk stat updates → adaptive boosting

Used by:
  - Knowledge Quiz (question generation + answer evaluation)
  - PvP Arena (judge answer evaluation)
  - Training L10 Scoring (legal claim validation)
  - BlitzQuestionPool (startup loading)
  - Feedback loop (chunk enrichment from user answers)
"""

import asyncio
import hashlib
import json
import logging
import random
import re
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
from sqlalchemy import func, select, text as sa_text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.rag import ChunkUsageLog, LegalCategory, LegalKnowledgeChunk

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# Data structures
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class RAGResult:
    """Single retrieved legal knowledge chunk with relevance score."""
    chunk_id: uuid.UUID
    category: str
    fact_text: str
    law_article: str
    relevance_score: float
    common_errors: list[str] = field(default_factory=list)
    correct_response_hint: str | None = None
    difficulty_level: int = 3
    is_court_practice: bool = False
    court_case_reference: str | None = None
    question_templates: list[dict] | None = None
    follow_up_questions: list[str] | None = None
    blitz_question: str | None = None
    blitz_answer: str | None = None
    tags: list[str] | None = None

    def to_dict(self) -> dict:
        return {"chunk_id": str(self.chunk_id), "category": self.category,
                "fact_text": self.fact_text, "law_article": self.law_article,
                "relevance_score": self.relevance_score, "difficulty_level": self.difficulty_level,
                "is_court_practice": self.is_court_practice}

@dataclass
class RAGContext:
    """Collection of retrieved chunks for prompt injection."""
    query: str
    results: list[RAGResult] = field(default_factory=list)
    method: str = "keyword"
    retrieval_ms: float = 0.0

    @property
    def has_results(self) -> bool:
        return len(self.results) > 0

    def to_prompt_context(self) -> str:
        if not self.results:
            return ""
        lines = ["### Правовая база (127-ФЗ «О несостоятельности (банкротстве)»):"]
        for i, r in enumerate(self.results, 1):
            lines.append(f"{i}. [{r.category}] {r.fact_text} (Основание: {r.law_article})")
            if r.common_errors:
                lines.append(f"   ⚠ Частые ошибки: {'; '.join(r.common_errors[:3])}")
            if r.correct_response_hint:
                lines.append(f"   Подсказка: {r.correct_response_hint}")
            if r.court_case_reference:
                lines.append(f"   Судебная практика: {r.court_case_reference}")
        return "\n".join(lines)

    def to_json(self) -> str:
        return json.dumps({"query": self.query, "method": self.method, "retrieval_ms": self.retrieval_ms,
            "results": [{"chunk_id": str(r.chunk_id), "category": r.category, "fact_text": r.fact_text,
                "law_article": r.law_article, "relevance_score": r.relevance_score,
                "common_errors": r.common_errors, "correct_response_hint": r.correct_response_hint,
                "difficulty_level": r.difficulty_level, "is_court_practice": r.is_court_practice,
                "court_case_reference": r.court_case_reference, "question_templates": r.question_templates,
                "follow_up_questions": r.follow_up_questions, "blitz_question": r.blitz_question,
                "blitz_answer": r.blitz_answer, "tags": r.tags} for r in self.results]}, ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> "RAGContext":
        data = json.loads(raw)
        return cls(query=data["query"], method=data["method"], retrieval_ms=data.get("retrieval_ms", 0),
            results=[RAGResult(chunk_id=uuid.UUID(r["chunk_id"]), category=r["category"],
                fact_text=r["fact_text"], law_article=r["law_article"],
                relevance_score=r["relevance_score"], common_errors=r.get("common_errors", []),
                correct_response_hint=r.get("correct_response_hint"),
                difficulty_level=r.get("difficulty_level", 3),
                is_court_practice=r.get("is_court_practice", False),
                court_case_reference=r.get("court_case_reference"),
                question_templates=r.get("question_templates"),
                follow_up_questions=r.get("follow_up_questions"),
                blitz_question=r.get("blitz_question"), blitz_answer=r.get("blitz_answer"),
                tags=r.get("tags")) for r in data.get("results", [])])

@dataclass
class RetrievalConfig:
    """Per-request retrieval configuration."""
    top_k: int = 5
    min_relevance: float = 0.15
    category: str | None = None
    difficulty_range: tuple[int, int] | None = None
    exclude_chunk_ids: list[uuid.UUID] | None = None
    require_court_practice: bool = False
    prefer_court_practice: bool = False
    tags_filter: list[str] | None = None
    mode: str = "free_dialog"

# ═══════════════════════════════════════════════════════════════════════════════
# Embedding (Gemini API)
# ═══════════════════════════════════════════════════════════════════════════════

_embedding_client: httpx.AsyncClient | None = None
_embedding_client_lock: asyncio.Lock = asyncio.Lock()
_EMBEDDING_CACHE_MAX = 512
_EMBEDDING_CACHE_TTL = 3600
_embedding_cache: OrderedDict[str, tuple[list[float], float]] = OrderedDict()
_embedding_cache_lock: asyncio.Lock = asyncio.Lock()

async def _get_embedding_client() -> httpx.AsyncClient:
    global _embedding_client
    if _embedding_client is not None:
        return _embedding_client
    async with _embedding_client_lock:
        if _embedding_client is None:
            _embedding_client = httpx.AsyncClient(timeout=10.0)
        return _embedding_client

async def _cache_get(text: str) -> list[float] | None:
    async with _embedding_cache_lock:
        entry = _embedding_cache.get(text)
        if entry is None:
            return None
        vec, ts = entry
        if time.monotonic() - ts > _EMBEDDING_CACHE_TTL:
            _embedding_cache.pop(text, None)
            return None
        _embedding_cache.move_to_end(text)
        return vec

async def _cache_put(text: str, vec: list[float]) -> None:
    async with _embedding_cache_lock:
        _embedding_cache[text] = (vec, time.monotonic())
        _embedding_cache.move_to_end(text)
        while len(_embedding_cache) > _EMBEDDING_CACHE_MAX:
            _embedding_cache.popitem(last=False)

async def get_embedding(text: str) -> list[float] | None:
    """Get embedding vector from Gemini Embedding API with LRU cache."""
    if not settings.gemini_embedding_api_key:
        return None
    cached = await _cache_get(text)
    if cached is not None:
        return cached
    try:
        client = await _get_embedding_client()
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{settings.gemini_embedding_model}:embedContent")
        resp = await client.post(url,
            headers={"x-goog-api-key": settings.gemini_embedding_api_key},
            json={"model": f"models/{settings.gemini_embedding_model}",
                  "content": {"parts": [{"text": text}]},
                  "outputDimensionality": 768})
        resp.raise_for_status()
        vec = resp.json().get("embedding", {}).get("values")
        if vec:
            await _cache_put(text, vec)
        return vec
    except Exception as e:
        logger.warning("Embedding API failed: %s", e)
        return None

async def close_embedding_client() -> None:
    global _embedding_client
    async with _embedding_client_lock:
        if _embedding_client is not None:
            await _embedding_client.aclose()
            _embedding_client = None

# ═══════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _build_where_clauses(config: RetrievalConfig) -> tuple[str, dict]:
    """Build parameterized WHERE clauses to prevent SQL injection.

    Returns (where_sql, params_dict) for use with sa_text().bindparams().
    """
    clauses = ["is_active = true"]
    params: dict = {}

    if config.category:
        clauses.append("category = :filter_category")
        params["filter_category"] = str(config.category)
    if config.difficulty_range:
        lo, hi = config.difficulty_range
        clauses.append("difficulty_level BETWEEN :diff_lo AND :diff_hi")
        params["diff_lo"] = int(lo)
        params["diff_hi"] = int(hi)
    if config.require_court_practice:
        clauses.append("is_court_practice = true")
    if config.exclude_chunk_ids:
        # Use numbered params for each excluded ID
        excl_params = []
        for i, cid in enumerate(config.exclude_chunk_ids):
            param_name = f"excl_id_{i}"
            excl_params.append(f":{param_name}")
            params[param_name] = str(cid)
        clauses.append(f"id NOT IN ({','.join(excl_params)})")
    if config.tags_filter:
        # JSONB array containment: tags @> '["tag1","tag2"]'::jsonb
        # All requested tags must be present in the chunk's tags array
        tags_json = json.dumps(config.tags_filter)
        clauses.append(f"tags @> :tags_filter::jsonb")
        params["tags_filter"] = tags_json
    return " AND ".join(clauses), params

def _chunk_to_rag_result(chunk: LegalKnowledgeChunk, relevance: float) -> RAGResult:
    cat = chunk.category
    cat_str = cat.value if hasattr(cat, "value") else str(cat)
    return RAGResult(chunk_id=chunk.id, category=cat_str, fact_text=chunk.fact_text,
        law_article=chunk.law_article, relevance_score=relevance,
        common_errors=chunk.common_errors or [], correct_response_hint=chunk.correct_response_hint,
        difficulty_level=getattr(chunk, "difficulty_level", 3) or 3,
        is_court_practice=getattr(chunk, "is_court_practice", False) or False,
        court_case_reference=getattr(chunk, "court_case_reference", None),
        question_templates=getattr(chunk, "question_templates", None),
        follow_up_questions=getattr(chunk, "follow_up_questions", None),
        blitz_question=getattr(chunk, "blitz_question", None),
        blitz_answer=getattr(chunk, "blitz_answer", None),
        tags=getattr(chunk, "tags", None))

def _row_to_rag_result(row, relevance: float) -> RAGResult:
    cat = row.category
    cat_str = cat.value if hasattr(cat, "value") else str(cat)
    return RAGResult(chunk_id=row.id, category=cat_str, fact_text=row.fact_text,
        law_article=row.law_article, relevance_score=relevance,
        common_errors=row.common_errors or [],
        correct_response_hint=getattr(row, "correct_response_hint", None),
        difficulty_level=getattr(row, "difficulty_level", 3) or 3,
        is_court_practice=getattr(row, "is_court_practice", False) or False,
        court_case_reference=getattr(row, "court_case_reference", None),
        question_templates=getattr(row, "question_templates", None),
        follow_up_questions=getattr(row, "follow_up_questions", None),
        blitz_question=getattr(row, "blitz_question", None),
        blitz_answer=getattr(row, "blitz_answer", None),
        tags=getattr(row, "tags", None))

def _keyword_score(text: str, keywords: list[str]) -> float:
    if not keywords:
        return 0.0
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw.lower() in text_lower) / len(keywords)

def _query_mentions_article(query: str, law_article: str) -> bool:
    q = query.lower()
    a = law_article.lower()
    return a in q or a.replace(" ", "") in q.replace(" ", "")

# ═══════════════════════════════════════════════════════════════════════════════
# Retrieval strategies
# ═══════════════════════════════════════════════════════════════════════════════

async def _retrieve_by_keywords(query: str, db: AsyncSession, config: RetrievalConfig) -> list[RAGResult]:
    """Keyword-based retrieval with DB-level pre-filtering and boosted scoring.

    Strategy:
      1. Extract query tokens → build ILIKE pre-filter to shrink candidate set
      2. Apply config filters (category, difficulty, court_practice, tags, exclusions)
      3. Score candidates in Python with multi-signal boosting
      4. Return top_k * 2 results for downstream RRF merge
    """
    # Extract meaningful tokens from query (min 2 chars to avoid noise)
    query_lower = query.lower()
    query_tokens = [t for t in re.findall(r"[а-яёa-z0-9]{2,}", query_lower) if len(t) >= 3]

    stmt = select(LegalKnowledgeChunk).where(LegalKnowledgeChunk.is_active.is_(True))

    # DB-level pre-filter: at least one query token must appear in fact_text or match_keywords
    # This replaces the old `.limit(500)` blanket load
    if query_tokens:
        # Build OR condition: fact_text ILIKE any of top-5 longest tokens
        # Longer tokens are more discriminative
        filter_tokens = sorted(query_tokens, key=len, reverse=True)[:5]
        from sqlalchemy import or_, cast, String as SAString
        text_filters = []
        for token in filter_tokens:
            text_filters.append(LegalKnowledgeChunk.fact_text.ilike(f"%{token}%"))
            # Also search in match_keywords (JSONB array → cast to text)
            text_filters.append(
                cast(LegalKnowledgeChunk.match_keywords, SAString).ilike(f"%{token}%")
            )
        stmt = stmt.where(or_(*text_filters))

    if config.category:
        try:
            stmt = stmt.where(LegalKnowledgeChunk.category == LegalCategory(config.category))
        except ValueError:
            pass
    if config.difficulty_range:
        lo, hi = config.difficulty_range
        stmt = stmt.where(LegalKnowledgeChunk.difficulty_level.between(lo, hi))
    if config.require_court_practice:
        stmt = stmt.where(LegalKnowledgeChunk.is_court_practice.is_(True))
    if config.exclude_chunk_ids:
        stmt = stmt.where(LegalKnowledgeChunk.id.notin_(config.exclude_chunk_ids))
    if config.tags_filter:
        # JSONB containment: chunk.tags must contain all requested tags
        from sqlalchemy import type_coerce
        from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
        stmt = stmt.where(
            type_coerce(LegalKnowledgeChunk.tags, PG_JSONB).op("@>")(
                type_coerce(config.tags_filter, PG_JSONB)
            )
        )
    # Safety limit — still cap at 200 to prevent runaway on broad queries
    stmt = stmt.limit(200)

    result = await db.execute(stmt)
    chunks = result.scalars().all()
    scored: list[tuple[float, LegalKnowledgeChunk]] = []

    for chunk in chunks:
        score = _keyword_score(query, chunk.match_keywords or [])

        # Boost: query mentions specific law article
        if chunk.law_article and _query_mentions_article(query, chunk.law_article):
            score = min(1.0, score + 0.3)

        # Boost: query matches a known common error pattern
        for err in (chunk.common_errors or []):
            if isinstance(err, str) and err.lower() in query_lower:
                score = min(1.0, score + 0.2)
                break

        # Boost: hint keyword overlap
        hint = (chunk.correct_response_hint or "").lower()
        if hint:
            overlap = sum(1 for t in re.findall(r"\w+", hint)[:12] if t and t in query_lower)
            if overlap:
                score = min(1.0, score + min(0.18, overlap * 0.03))

        # Boost: error_frequency (dynamic, updated by feedback loop)
        # Scale: ef=5(default) → +0.025, ef=20(high errors) → +0.10, ef=50 → +0.12 (capped)
        if chunk.error_frequency and chunk.error_frequency > 0:
            ef_boost = min(0.12, chunk.error_frequency / 200)
            score = min(1.0, score + ef_boost)

        # Boost: court practice preference
        if config.prefer_court_practice and getattr(chunk, "is_court_practice", False):
            score = min(1.0, score + 0.1)

        # Boost: effectiveness_score — prefer chunks that lead to correct answers
        eff = getattr(chunk, "effectiveness_score", None)
        if eff is not None and eff > 0.7:
            score = min(1.0, score + 0.05)

        if score >= config.min_relevance:
            scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [_chunk_to_rag_result(c, s) for s, c in scored[:config.top_k * 2]]

async def _retrieve_by_embedding(query: str, db: AsyncSession, config: RetrievalConfig) -> list[RAGResult]:
    """Embedding-based retrieval via pgvector cosine similarity."""
    embedding = await get_embedding(query)
    if embedding is None:
        return []
    where, where_params = _build_where_clauses(config)
    where += " AND embedding IS NOT NULL"
    emb_literal = "[" + ",".join(str(float(v)) for v in embedding) + "]"
    sql = sa_text(f"""
        SELECT id, category, fact_text, law_article, common_errors,
               correct_response_hint, difficulty_level, is_court_practice,
               court_case_reference, question_templates, follow_up_questions,
               blitz_question, blitz_answer, tags,
               1 - (embedding <=> :emb_vector::vector) AS similarity
        FROM legal_knowledge_chunks WHERE {where}
        ORDER BY embedding <=> :emb_vector::vector LIMIT :top_k
    """)
    query_params = {**where_params, "top_k": config.top_k * 2, "emb_vector": emb_literal}
    try:
        result = await db.execute(sql, query_params)
        rows = result.fetchall()
    except Exception as e:
        logger.warning("pgvector query failed: %s", e)
        return []

    min_sim = 0.25 if config.mode == "blitz" else 0.20
    results = []
    for row in rows:
        sim = float(row.similarity)
        if sim < min_sim:
            continue
        if config.prefer_court_practice and getattr(row, "is_court_practice", False):
            sim = min(1.0, sim + 0.1)
        results.append(_row_to_rag_result(row, sim))
    return results

# Backward-compatible aliases
retrieve_by_keywords = _retrieve_by_keywords
retrieve_by_embedding = _retrieve_by_embedding

# ═══════════════════════════════════════════════════════════════════════════════
# Hybrid reranking (Reciprocal Rank Fusion)
# ═══════════════════════════════════════════════════════════════════════════════

def _hybrid_rerank(emb_results: list[RAGResult], kw_results: list[RAGResult],
                   config: RetrievalConfig) -> list[RAGResult]:
    """Merge results using RRF. score = sum(1/(k+rank)) across lists, k=60."""
    K = 60
    rrf: dict[uuid.UUID, float] = {}
    best: dict[uuid.UUID, RAGResult] = {}
    for rank, r in enumerate(emb_results):
        rrf[r.chunk_id] = rrf.get(r.chunk_id, 0) + 1.0 / (K + rank + 1)
        if r.chunk_id not in best or r.relevance_score > best[r.chunk_id].relevance_score:
            best[r.chunk_id] = r
    for rank, r in enumerate(kw_results):
        rrf[r.chunk_id] = rrf.get(r.chunk_id, 0) + 1.0 / (K + rank + 1)
        if r.chunk_id not in best or r.relevance_score > best[r.chunk_id].relevance_score:
            best[r.chunk_id] = r
    ranked = sorted(rrf.items(), key=lambda x: x[1], reverse=True)
    merged = []
    for cid, score in ranked[:config.top_k]:
        r = best[cid]
        merged.append(RAGResult(chunk_id=r.chunk_id, category=r.category, fact_text=r.fact_text,
            law_article=r.law_article, relevance_score=min(1.0, score * 30),
            common_errors=r.common_errors, correct_response_hint=r.correct_response_hint,
            difficulty_level=r.difficulty_level, is_court_practice=r.is_court_practice,
            court_case_reference=r.court_case_reference, question_templates=r.question_templates,
            follow_up_questions=r.follow_up_questions, blitz_question=r.blitz_question,
            blitz_answer=r.blitz_answer, tags=r.tags))
    return merged

# ═══════════════════════════════════════════════════════════════════════════════
# Redis caching
# ═══════════════════════════════════════════════════════════════════════════════

_RAG_CACHE_TTL = 300

def _make_cache_key(query: str, config: RetrievalConfig) -> str:
    raw = f"{query}:{config.category}:{config.difficulty_range}:{config.mode}:{config.require_court_practice}"
    return f"rag:ctx:{hashlib.md5(raw.encode()).hexdigest()}"

async def _cache_get_context(key: str) -> RAGContext | None:
    try:
        from app.core.redis_pool import get_redis
        r = get_redis()
        if r is None:
            return None
        cached = await r.get(key)
        return RAGContext.from_json(cached) if cached else None
    except Exception:
        return None

async def _cache_set_context(key: str, ctx: RAGContext) -> None:
    try:
        from app.core.redis_pool import get_redis
        r = get_redis()
        if r is None:
            return
        await r.setex(key, _RAG_CACHE_TTL, ctx.to_json())
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════════════════════════
# Unified retrieval interface (PUBLIC API)
# ═══════════════════════════════════════════════════════════════════════════════

async def retrieve_legal_context(
    query: str, db: AsyncSession, top_k: int = 5, prefer_embedding: bool = True,
    *, config: RetrievalConfig | None = None,
) -> RAGContext:
    """Retrieve legal context with hybrid multi-strategy pipeline.

    Backward-compatible: old callers use (query, db, top_k, prefer_embedding).
    New callers pass config=RetrievalConfig(...) for full control.

    Pipeline: cache check → parallel (embedding + keyword) → RRF rerank → cache set.
    """
    if config is None:
        config = RetrievalConfig(top_k=top_k, mode="free_dialog")

    t0 = time.monotonic()

    # Cache check (skip if session-dedup active)
    cache_key = None
    if not config.exclude_chunk_ids:
        cache_key = _make_cache_key(query, config)
        cached = await _cache_get_context(cache_key)
        if cached is not None:
            cached.retrieval_ms = (time.monotonic() - t0) * 1000
            return cached

    # Parallel retrieval
    use_emb = prefer_embedding and bool(settings.gemini_embedding_api_key)
    if use_emb:
        emb_r, kw_r = await asyncio.gather(
            _retrieve_by_embedding(query, db, config),
            _retrieve_by_keywords(query, db, config))
    else:
        emb_r, kw_r = [], await _retrieve_by_keywords(query, db, config)

    # Merge
    # Track whether embedding retrieval was requested but returned empty (API failure).
    # In that case, keyword-only results are degraded and should NOT be cached,
    # because the embedding service may recover within seconds.
    _embedding_degraded = use_emb and not emb_r
    if emb_r and kw_r:
        merged, method = _hybrid_rerank(emb_r, kw_r, config), "hybrid"
    elif emb_r:
        merged, method = emb_r[:config.top_k], "embedding"
    elif kw_r:
        merged, method = kw_r[:config.top_k], "keyword"
    else:
        merged, method = [], "none"

    ms = (time.monotonic() - t0) * 1000
    ctx = RAGContext(query=query, results=merged, method=method, retrieval_ms=ms)

    # Only cache full-quality results. Degraded keyword-only results (when embedding
    # was requested but failed) would poison the cache for up to TTL seconds.
    if cache_key and ctx.has_results and not _embedding_degraded:
        await _cache_set_context(cache_key, ctx)

    if ctx.has_results:
        logger.debug("RAG: %d chunks (method=%s, top=%.2f, ms=%.0f)",
                      len(merged), method, merged[0].relevance_score, ms)
    return ctx

# ═══════════════════════════════════════════════════════════════════════════════
# Legal claim validation (L10 scoring)
# ═══════════════════════════════════════════════════════════════════════════════

async def validate_legal_claim(claim: str, db: AsyncSession) -> dict:
    """Quick validation: check if a legal claim matches known facts."""
    context = await retrieve_legal_context(claim, db, top_k=3)
    if not context.has_results:
        return {"is_valid": None, "accuracy": "unknown", "matching_fact": None,
                "law_article": None, "explanation": "Утверждение не соответствует известным юридическим фактам в базе."}
    top = context.results[0]
    for err in top.common_errors:
        if isinstance(err, str) and err.lower() in claim.lower():
            return {"is_valid": False, "accuracy": "incorrect", "matching_fact": top.fact_text,
                    "law_article": top.law_article, "explanation": f"Ошибка: «{err}». Правильно: {top.fact_text}"}
    if top.relevance_score >= 0.5:
        return {"is_valid": True, "accuracy": "correct", "matching_fact": top.fact_text,
                "law_article": top.law_article, "explanation": None}
    return {"is_valid": None, "accuracy": "partial", "matching_fact": top.fact_text,
            "law_article": top.law_article, "explanation": "Утверждение частично соответствует правовой норме."}

# ═══════════════════════════════════════════════════════════════════════════════
# Embedding management
# ═══════════════════════════════════════════════════════════════════════════════

async def verify_embeddings_health(db: AsyncSession) -> dict:
    """Check embedding population and model compatibility."""
    current_model = settings.gemini_embedding_model
    try:
        total = await db.scalar(select(func.count()).select_from(LegalKnowledgeChunk)
            .where(LegalKnowledgeChunk.is_active.is_(True))) or 0
        embedded = await db.scalar(select(func.count()).select_from(LegalKnowledgeChunk)
            .where(LegalKnowledgeChunk.is_active.is_(True), LegalKnowledgeChunk.embedding.isnot(None))) or 0
        stale, stale_model = 0, None
        if embedded > 0:
            stale = await db.scalar(select(func.count()).select_from(LegalKnowledgeChunk)
                .where(LegalKnowledgeChunk.is_active.is_(True), LegalKnowledgeChunk.embedding.isnot(None),
                       LegalKnowledgeChunk.embedding_model.isnot(None),
                       LegalKnowledgeChunk.embedding_model != current_model)) or 0
            if stale > 0:
                row = await db.execute(select(LegalKnowledgeChunk.embedding_model)
                    .where(LegalKnowledgeChunk.embedding_model.isnot(None),
                           LegalKnowledgeChunk.embedding_model != current_model).limit(1))
                stale_model = row.scalar_one_or_none()
        null_count = total - embedded
        if total == 0: health = "empty"
        elif stale > 0: health = "stale"
        elif null_count > total * 0.2: health = "partial"
        else: health = "ok"
        return {"total_chunks": total, "embedded_count": embedded, "null_count": null_count,
                "stale_count": stale, "stale_model": stale_model, "current_model": current_model, "health": health}
    except Exception as e:
        logger.warning("verify_embeddings_health failed: %s", e)
        return {"total_chunks": 0, "embedded_count": 0, "null_count": 0, "stale_count": 0,
                "stale_model": None, "current_model": current_model, "health": "error"}

async def check_embeddings_populated(db: AsyncSession) -> bool:
    health = await verify_embeddings_health(db)
    return health["health"] in ("ok", "empty")

async def populate_embeddings(db: AsyncSession, batch_size: int = 10) -> int:
    """Populate embedding vectors for chunks that need them."""
    current_model = settings.gemini_embedding_model
    try:
        result = await db.execute(sa_text(
            "SELECT id, fact_text FROM legal_knowledge_chunks "
            "WHERE is_active = true AND (embedding IS NULL OR embedding_model IS NULL "
            "OR embedding_model != :current_model)"), {"current_model": current_model})
        rows = result.fetchall()
    except Exception as e:
        logger.warning("Cannot query chunks for embedding population: %s", e)
        return 0
    if not rows:
        logger.info("All chunks have up-to-date embeddings (model=%s)", current_model)
        return 0
    logger.info("Populating embeddings for %d chunks (model=%s)...", len(rows), current_model)
    updated = 0
    for row in rows:
        embedding = await get_embedding(row.fact_text)
        if embedding:
            # Use ORM update to avoid asyncpg raw SQL vector cast issues
            from sqlalchemy import update
            stmt = (
                update(LegalKnowledgeChunk)
                .where(LegalKnowledgeChunk.id == row.id)
                .values(embedding=embedding, embedding_model=current_model)
            )
            await db.execute(stmt)
            updated += 1
            if updated % batch_size == 0:
                await db.commit()
                logger.info("Populated %d/%d embeddings...", updated, len(rows))
                await asyncio.sleep(0.05)
    if updated % batch_size != 0:
        await db.commit()
    logger.info("Embedding population complete: %d/%d chunks updated", updated, len(rows))
    return updated

async def safe_populate_embeddings() -> None:
    """Background task: populate embeddings with exponential backoff retry."""
    from app.database import async_session
    delays = [30, 60, 120]
    for attempt in range(len(delays) + 1):
        try:
            async with async_session() as db:
                if await check_embeddings_populated(db):
                    logger.info("Legal embeddings already populated — skipping")
                    return
                logger.info("Populating legal embeddings (attempt %d)...", attempt + 1)
                count = await populate_embeddings(db)
                if count > 0:
                    logger.info("Legal embeddings populated: %d chunks", count)
                return
        except Exception as e:
            if attempt < len(delays):
                delay = delays[attempt]
                logger.warning("Embedding population attempt %d failed: %s. Retrying in %ds...", attempt + 1, e, delay)
                await asyncio.sleep(delay)
            else:
                logger.error("Embedding population failed after %d attempts: %s. Using keyword-only.", attempt + 1, e)

# ═══════════════════════════════════════════════════════════════════════════════
# Content hashing (idempotent seed upserts)
# ═══════════════════════════════════════════════════════════════════════════════

def compute_content_hash(fact_text: str, law_article: str) -> str:
    """Generate deterministic hash for chunk deduplication."""
    return hashlib.md5(f"{fact_text}::{law_article}".encode()).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════════
# BlitzQuestionPool — pre-loaded questions for zero-latency blitz mode
# ═══════════════════════════════════════════════════════════════════════════════

class BlitzQuestionPool:
    """Pre-loaded pool of blitz Q&A from DB. Eliminates LLM latency for blitz."""

    def __init__(self) -> None:
        self._questions: list[dict] = []
        self._loaded = False

    async def load(self, db: AsyncSession) -> int:
        """Load all chunks with blitz_question from DB."""
        result = await db.execute(
            select(LegalKnowledgeChunk).where(
                LegalKnowledgeChunk.is_active.is_(True),
                LegalKnowledgeChunk.blitz_question.isnot(None),
            )
        )
        chunks = result.scalars().all()

        self._questions.clear()
        for chunk in chunks:
            cat = chunk.category
            self._questions.append({
                "chunk_id": chunk.id,
                "category": cat.value if hasattr(cat, "value") else str(cat),
                "question": chunk.blitz_question,
                "answer": chunk.blitz_answer,
                "article": chunk.law_article,
                "difficulty": chunk.difficulty_level or 3,
                "fact_text": chunk.fact_text,
            })

        self._loaded = True
        logger.info("BlitzQuestionPool loaded: %d questions", len(self._questions))
        return len(self._questions)

    def get_question(
        self,
        *,
        category: str | None = None,
        difficulty_range: tuple[int, int] | None = None,
        exclude_ids: set[uuid.UUID] | None = None,
    ) -> dict | None:
        """Get random unused blitz question matching filters."""
        if not self._loaded or not self._questions:
            return None

        candidates = []
        for q in self._questions:
            if exclude_ids and q["chunk_id"] in exclude_ids:
                continue
            if category and q["category"] != category:
                continue
            if difficulty_range:
                if not (difficulty_range[0] <= q["difficulty"] <= difficulty_range[1]):
                    continue
            candidates.append(q)

        if not candidates:
            return None
        return random.choice(candidates)

    @property
    def total(self) -> int:
        return len(self._questions)

    @property
    def loaded(self) -> bool:
        return self._loaded


# Singleton instance
blitz_pool = BlitzQuestionPool()


# ═══════════════════════════════════════════════════════════════════════════════
# Usage tracking — records which chunks are retrieved and by whom
# ═══════════════════════════════════════════════════════════════════════════════

async def log_chunk_usage(
    db: AsyncSession,
    *,
    chunk_ids: list[uuid.UUID],
    user_id: uuid.UUID,
    source_type: str,
    source_id: uuid.UUID | None = None,
    query_text: str | None = None,
    retrieval_method: str | None = None,
    relevance_scores: dict[uuid.UUID, float] | None = None,
    ranks: dict[uuid.UUID, int] | None = None,
) -> None:
    """Log retrieval of chunks for feedback tracking.

    Call this from consumers (quiz, pvp, training) after retrieve_legal_context().
    Lightweight: does not block the main flow.
    """
    try:
        now = datetime.now(timezone.utc)
        for cid in chunk_ids:
            log = ChunkUsageLog(
                chunk_id=cid,
                user_id=user_id,
                source_type=source_type,
                source_id=source_id,
                query_text=(query_text or "")[:500],
                retrieval_method=retrieval_method,
                relevance_score=(relevance_scores or {}).get(cid),
                retrieval_rank=(ranks or {}).get(cid),
            )
            db.add(log)

        # Bump retrieval_count and last_used_at on chunks (bulk)
        if chunk_ids:
            await db.execute(
                update(LegalKnowledgeChunk)
                .where(LegalKnowledgeChunk.id.in_(chunk_ids))
                .values(
                    retrieval_count=LegalKnowledgeChunk.retrieval_count + 1,
                    last_used_at=now,
                )
            )
        await db.commit()  # Was flush() — changes were never persisted!
    except Exception as e:
        logger.warning("log_chunk_usage failed (non-critical): %s", e)


async def record_chunk_outcome(
    db: AsyncSession,
    *,
    chunk_id: uuid.UUID,
    user_id: uuid.UUID,
    source_type: str,
    source_id: uuid.UUID | None = None,
    answer_correct: bool,
    user_answer_excerpt: str | None = None,
    score_delta: float | None = None,
    discovered_error: str | None = None,
) -> None:
    """Record the outcome of a user's answer against a specific chunk.

    Call this after evaluating a user's answer (quiz, pvp judge, L10 scoring).
    Updates both the usage log and the chunk's aggregated stats.
    """
    try:
        # Try to find and update existing usage log for this chunk+source
        if source_id:
            existing = await db.execute(
                select(ChunkUsageLog).where(
                    ChunkUsageLog.chunk_id == chunk_id,
                    ChunkUsageLog.user_id == user_id,
                    ChunkUsageLog.source_id == source_id,
                    ChunkUsageLog.was_answered.is_(False),
                ).limit(1)
            )
            log_entry = existing.scalar_one_or_none()
            if log_entry:
                log_entry.was_answered = True
                log_entry.answer_correct = answer_correct
                log_entry.user_answer_excerpt = (user_answer_excerpt or "")[:500]
                log_entry.score_delta = score_delta
                if discovered_error:
                    log_entry.discovered_error = discovered_error[:500]

        # Update chunk aggregate stats
        if answer_correct:
            await db.execute(
                update(LegalKnowledgeChunk)
                .where(LegalKnowledgeChunk.id == chunk_id)
                .values(correct_answer_count=LegalKnowledgeChunk.correct_answer_count + 1)
            )
        else:
            await db.execute(
                update(LegalKnowledgeChunk)
                .where(LegalKnowledgeChunk.id == chunk_id)
                .values(incorrect_answer_count=LegalKnowledgeChunk.incorrect_answer_count + 1)
            )
            # Auto-increment error_frequency when users get it wrong
            await db.execute(
                update(LegalKnowledgeChunk)
                .where(LegalKnowledgeChunk.id == chunk_id)
                .values(error_frequency=LegalKnowledgeChunk.error_frequency + 1)
            )

        await db.commit()  # Was flush() — changes were never persisted!
    except Exception as e:
        logger.warning("record_chunk_outcome failed (non-critical): %s", e)


# ═══════════════════════════════════════════════════════════════════════════════
# Feedback aggregation — periodic recalculation of chunk effectiveness
# ═══════════════════════════════════════════════════════════════════════════════

async def recalculate_chunk_effectiveness(db: AsyncSession) -> int:
    """Recalculate effectiveness_score for all chunks with enough answer data.

    effectiveness_score = correct_answer_count / (correct + incorrect)
    Only set when total answers >= 3 to avoid noise from small samples.

    Also discovers new common_errors from ChunkUsageLog.discovered_error.
    Returns number of chunks updated.
    """
    MIN_ANSWERS = 3
    updated = 0

    try:
        # 1. Update effectiveness_score for chunks with enough data
        result = await db.execute(
            select(LegalKnowledgeChunk).where(
                LegalKnowledgeChunk.is_active.is_(True),
                (LegalKnowledgeChunk.correct_answer_count + LegalKnowledgeChunk.incorrect_answer_count) >= MIN_ANSWERS,
            )
        )
        chunks = result.scalars().all()

        for chunk in chunks:
            total = chunk.correct_answer_count + chunk.incorrect_answer_count
            if total >= MIN_ANSWERS:
                new_eff = chunk.correct_answer_count / total
                chunk.effectiveness_score = round(new_eff, 3)
                updated += 1

        # 2. Discover new common_errors from usage logs
        # Find discovered_errors that aren't already in chunk.common_errors
        error_result = await db.execute(
            sa_text("""
                SELECT chunk_id, discovered_error, COUNT(*) as cnt
                FROM chunk_usage_logs
                WHERE discovered_error IS NOT NULL
                  AND answer_correct = false
                GROUP BY chunk_id, discovered_error
                HAVING COUNT(*) >= 2
                ORDER BY cnt DESC
                LIMIT 100
            """)
        )
        error_rows = error_result.fetchall()

        for row in error_rows:
            chunk = await db.get(LegalKnowledgeChunk, row.chunk_id)
            if chunk and chunk.common_errors:
                existing = [e.lower() for e in chunk.common_errors if isinstance(e, str)]
                if row.discovered_error.lower() not in existing:
                    new_errors = list(chunk.common_errors) + [row.discovered_error]
                    chunk.common_errors = new_errors
                    logger.info(
                        "Auto-discovered common_error for chunk %s: %s (seen %d times)",
                        chunk.id, row.discovered_error[:80], row.cnt,
                    )

        await db.commit()
        logger.info("Chunk effectiveness recalculated: %d chunks updated", updated)

    except Exception as e:
        logger.error("recalculate_chunk_effectiveness failed: %s", e)
        await db.rollback()

    return updated


async def get_chunk_analytics(db: AsyncSession, chunk_id: uuid.UUID) -> dict:
    """Get analytics for a specific chunk (admin dashboard)."""
    chunk = await db.get(LegalKnowledgeChunk, chunk_id)
    if not chunk:
        return {"error": "chunk_not_found"}

    total_answers = chunk.correct_answer_count + chunk.incorrect_answer_count
    return {
        "chunk_id": str(chunk_id),
        "category": chunk.category.value if hasattr(chunk.category, "value") else str(chunk.category),
        "law_article": chunk.law_article,
        "retrieval_count": chunk.retrieval_count,
        "correct_answers": chunk.correct_answer_count,
        "incorrect_answers": chunk.incorrect_answer_count,
        "total_answers": total_answers,
        "effectiveness_score": chunk.effectiveness_score,
        "error_frequency": chunk.error_frequency,
        "last_used_at": chunk.last_used_at.isoformat() if chunk.last_used_at else None,
        "common_errors_count": len(chunk.common_errors) if chunk.common_errors else 0,
    }


async def get_weak_chunks(db: AsyncSession, limit: int = 20) -> list[dict]:
    """Find chunks with lowest effectiveness (most errors). For methodologist review."""
    result = await db.execute(
        select(LegalKnowledgeChunk)
        .where(
            LegalKnowledgeChunk.is_active.is_(True),
            LegalKnowledgeChunk.effectiveness_score.isnot(None),
            LegalKnowledgeChunk.effectiveness_score < 0.5,
        )
        .order_by(LegalKnowledgeChunk.effectiveness_score.asc())
        .limit(limit)
    )
    chunks = result.scalars().all()
    return [
        {
            "chunk_id": str(c.id),
            "category": c.category.value if hasattr(c.category, "value") else str(c.category),
            "law_article": c.law_article,
            "fact_text": c.fact_text[:200],
            "effectiveness_score": c.effectiveness_score,
            "error_frequency": c.error_frequency,
            "incorrect_answers": c.incorrect_answer_count,
            "common_errors": c.common_errors,
        }
        for c in chunks
    ]


async def get_unused_chunks(db: AsyncSession, limit: int = 20) -> list[dict]:
    """Find active chunks that have never been retrieved. For content gap analysis."""
    result = await db.execute(
        select(LegalKnowledgeChunk)
        .where(
            LegalKnowledgeChunk.is_active.is_(True),
            LegalKnowledgeChunk.retrieval_count == 0,
        )
        .order_by(LegalKnowledgeChunk.created_at.asc())
        .limit(limit)
    )
    chunks = result.scalars().all()
    return [
        {
            "chunk_id": str(c.id),
            "category": c.category.value if hasattr(c.category, "value") else str(c.category),
            "law_article": c.law_article,
            "fact_text": c.fact_text[:200],
            "difficulty_level": c.difficulty_level,
            "tags": c.tags,
        }
        for c in chunks
    ]
