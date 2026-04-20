"""Dual-table legal retrieval with gemini-embedding-001@768.

Works alongside rag_legal.py (which still uses the legacy text-embedding-3-small
→ legal_knowledge_chunks.embedding column).

This new layer queries BOTH:
  - legal_knowledge_chunks.embedding_v2  (curated facts, 375 rows)
  - legal_document.embedding_v2          (raw 127-ФЗ + court practice, ~5-7k rows)

Both columns are populated by gemini-embedding-001@768 (same embedding space),
so vector similarity is directly comparable and results can be RRF-merged.

Pipeline:
  1. Query embedding via navy (gemini-embedding-001@768)
  2. Parallel pgvector cosine similarity on both tables
  3. RRF merge (K=60) — preserves top candidates from each source
  4. Optional reranker (rag_reranker.py)
  5. Confidence gate: if top-1 < threshold → return empty (refusal)
  6. Return RAGContext (rag_legal.RAGResult shape) for compatibility

Once migration is complete (embedding_v2 100% on both tables), this can replace
the legacy `retrieve_legal_context()` in rag_legal.py.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

import httpx
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.rag_legal import RAGContext, RAGResult

logger = logging.getLogger(__name__)

# ─── Config ──────────────────────────────────────────────────────────────

GEMINI_EMBEDDING_MODEL = "gemini-embedding-001"
GEMINI_EMBEDDING_DIM = 768
RRF_K = 60
DEFAULT_CANDIDATE_POOL = 20  # fetch per table, merge, then top_k
DEFAULT_TOP_K = 5
MIN_SIMILARITY = 0.30        # pre-filter; after reranker the confidence gate is stricter


# ─── Query embedding via navy ────────────────────────────────────────────


_EMBEDDING_CLIENT: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    global _EMBEDDING_CLIENT
    if _EMBEDDING_CLIENT is None or _EMBEDDING_CLIENT.is_closed:
        _EMBEDDING_CLIENT = httpx.AsyncClient(timeout=20.0)
    return _EMBEDDING_CLIENT


async def get_query_embedding_gemini(text: str) -> list[float] | None:
    """Fetch gemini-embedding-001@768 for the query.

    Uses LOCAL_EMBEDDING_URL / LOCAL_EMBEDDING_API_KEY (navy) from env.
    Independent of the shared `get_embedding()` helper which may still
    point at text-embedding-3-small during the transition.
    """
    url_base = os.environ.get("LOCAL_EMBEDDING_URL", "https://api.navy/v1").rstrip("/")
    api_key = os.environ.get("LOCAL_EMBEDDING_API_KEY", "")
    if not api_key:
        logger.warning("rag_legal_v2: LOCAL_EMBEDDING_API_KEY missing — cannot query")
        return None
    try:
        r = await _get_http_client().post(
            f"{url_base}/embeddings",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": GEMINI_EMBEDDING_MODEL,
                "input": text[:3000],
                "dimensions": GEMINI_EMBEDDING_DIM,
            },
        )
        if r.status_code != 200:
            logger.warning("rag_legal_v2 embed HTTP %d: %s", r.status_code, r.text[:200])
            return None
        data = r.json()
        items = data.get("data", [])
        if items and "embedding" in items[0]:
            return items[0]["embedding"]
    except Exception as exc:
        logger.warning("rag_legal_v2 embed failed: %s", exc)
    return None


# ─── Retrieval: legal_knowledge_chunks (curated facts) ───────────────────


async def _retrieve_legal_kc_v2(
    emb_literal: str,
    db: AsyncSession,
    top_k: int,
) -> list[RAGResult]:
    """Vector search on legal_knowledge_chunks.embedding_v2."""
    sql = sa_text(
        f"""
        SELECT
            id,
            category,
            fact_text,
            law_article,
            common_errors,
            correct_response_hint,
            difficulty_level,
            is_court_practice,
            court_case_reference,
            question_templates,
            follow_up_questions,
            blitz_question,
            blitz_answer,
            tags,
            1 - (embedding_v2 <=> '{emb_literal}'::vector) AS similarity
        FROM legal_knowledge_chunks
        WHERE is_active = true
          AND embedding_v2 IS NOT NULL
        ORDER BY embedding_v2 <=> '{emb_literal}'::vector
        LIMIT :top_k
        """
    )
    try:
        result = await db.execute(sql, {"top_k": top_k})
        rows = result.fetchall()
    except Exception as exc:
        logger.warning("legal_kc_v2 query failed: %s", exc)
        return []

    out: list[RAGResult] = []
    for row in rows:
        sim = float(row.similarity)
        if sim < MIN_SIMILARITY:
            continue
        out.append(RAGResult(
            chunk_id=row.id,
            category=str(row.category) if row.category else "other",
            fact_text=row.fact_text,
            law_article=row.law_article or "",
            relevance_score=sim,
            common_errors=list(row.common_errors or []) if row.common_errors else [],
            correct_response_hint=row.correct_response_hint,
            difficulty_level=row.difficulty_level or 3,
            is_court_practice=bool(row.is_court_practice),
            court_case_reference=row.court_case_reference,
            question_templates=row.question_templates,
            follow_up_questions=row.follow_up_questions,
            blitz_question=row.blitz_question,
            blitz_answer=row.blitz_answer,
            tags=row.tags,
        ))
    return out


# ─── Retrieval: legal_document (raw 127-ФЗ + court practice) ─────────────


async def _retrieve_legal_document(
    emb_literal: str,
    db: AsyncSession,
    top_k: int,
) -> list[RAGResult]:
    """Vector search on legal_document.embedding_v2.

    Prefers finer-grained `law_item` and `court_paragraph` rows (higher
    retrieval precision), but law_article / court_case are also allowed
    for direct article-level hits.
    """
    # Filter out coarse rows (law_fz root and law_chapter) — they don't
    # carry substantive content for retrieval.
    sql = sa_text(
        f"""
        SELECT
            id,
            doc_type,
            doc_source,
            number,
            title,
            content,
            metadata_json,
            source_url,
            1 - (embedding_v2 <=> '{emb_literal}'::vector) AS similarity
        FROM legal_document
        WHERE is_active = true
          AND embedding_v2 IS NOT NULL
          AND doc_type IN ('law_item', 'law_article', 'court_paragraph', 'court_case')
        ORDER BY embedding_v2 <=> '{emb_literal}'::vector
        LIMIT :top_k
        """
    )
    try:
        result = await db.execute(sql, {"top_k": top_k})
        rows = result.fetchall()
    except Exception as exc:
        logger.warning("legal_document query failed: %s", exc)
        return []

    out: list[RAGResult] = []
    for row in rows:
        sim = float(row.similarity)
        if sim < MIN_SIMILARITY:
            continue

        # Build law_article string from doc_type + number
        if row.doc_type == "law_item":
            law_article = f"ст. {row.number} 127-ФЗ" if row.number else "127-ФЗ"
        elif row.doc_type == "law_article":
            law_article = f"ст. {row.number} 127-ФЗ" if row.number else "127-ФЗ"
        elif row.doc_type in ("court_paragraph", "court_case"):
            # Court case number from metadata or fallback to number
            meta = row.metadata_json or {}
            court = row.doc_source.replace("_sudact", "").upper()
            case_num = row.number or ""
            law_article = f"{court} {case_num}".strip()
        else:
            law_article = row.number or ""

        is_court = row.doc_type in ("court_paragraph", "court_case")
        category = "court_practice" if is_court else "law"

        out.append(RAGResult(
            chunk_id=row.id,
            category=category,
            fact_text=row.content[:2000],  # cap for prompt budget
            law_article=law_article,
            relevance_score=sim,
            common_errors=[],
            correct_response_hint=None,
            difficulty_level=3,
            is_court_practice=is_court,
            court_case_reference=law_article if is_court else None,
            question_templates=None,
            follow_up_questions=None,
            blitz_question=None,
            blitz_answer=None,
            tags=None,
        ))
    return out


# ─── RRF merge of N result lists ──────────────────────────────────────────


def rrf_merge(
    *result_lists: list[RAGResult],
    top_k: int,
    k: int = RRF_K,
) -> list[RAGResult]:
    """Reciprocal Rank Fusion across any number of ranked lists.

    Each chunk_id accumulates 1/(k+rank) across all lists. Final ranking
    picks top_k by total RRF score. Preserves the highest-similarity
    variant of each chunk (in case the same id appears in multiple lists —
    not expected across legal_kc vs legal_document, but safe).
    """
    scores: dict[uuid.UUID, float] = {}
    best: dict[uuid.UUID, RAGResult] = {}

    for results in result_lists:
        for rank, r in enumerate(results):
            scores[r.chunk_id] = scores.get(r.chunk_id, 0.0) + 1.0 / (k + rank + 1)
            prev = best.get(r.chunk_id)
            if prev is None or r.relevance_score > prev.relevance_score:
                best[r.chunk_id] = r

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    merged: list[RAGResult] = []
    for cid, score in ranked[:top_k]:
        r = best[cid]
        # Project RRF score into [0, 1] for downstream consumers that treat
        # relevance_score as probability-ish. Empirical: RRF scores of 0.033
        # (top) scale to ~1.0 after ×30 clamp. Keep original similarity if
        # higher (helps confidence gate after a single-source hit).
        boosted = min(1.0, max(r.relevance_score, score * 30))
        merged.append(RAGResult(
            chunk_id=r.chunk_id,
            category=r.category,
            fact_text=r.fact_text,
            law_article=r.law_article,
            relevance_score=boosted,
            common_errors=r.common_errors,
            correct_response_hint=r.correct_response_hint,
            difficulty_level=r.difficulty_level,
            is_court_practice=r.is_court_practice,
            court_case_reference=r.court_case_reference,
            question_templates=r.question_templates,
            follow_up_questions=r.follow_up_questions,
            blitz_question=r.blitz_question,
            blitz_answer=r.blitz_answer,
            tags=r.tags,
        ))
    return merged


# ─── Public API ──────────────────────────────────────────────────────────


@dataclass
class RetrieveV2Options:
    top_k: int = DEFAULT_TOP_K
    candidate_pool: int = DEFAULT_CANDIDATE_POOL
    use_reranker: bool = True
    confidence_threshold: float = 0.55  # P0: refusal if top-1 < this after rerank
    include_legal_kc: bool = True
    include_legal_document: bool = True


async def retrieve_legal_context_v2(
    query: str,
    db: AsyncSession,
    options: Optional[RetrieveV2Options] = None,
) -> RAGContext:
    """Dual-table legal retrieval with optional reranker + confidence gate.

    Returns RAGContext with `method` field indicating:
      - "v2_rrf"          — normal dual-table RRF result
      - "v2_rrf_reranked" — RRF + cross-encoder reranker
      - "v2_refused"      — confidence below threshold → empty results
      - "v2_empty"        — both tables returned nothing
      - "v2_embedding_fail" — query embedding failed (provider down)

    Phase 3.10 (2026-04-19) enhancements — all additive, degrade cleanly:
      - **Article-ref short-circuit.** If the query explicitly cites
        "ст. 213.4" etc., we look up matching rows in legal_document
        before running the semantic search and prepend them with a +0.25
        relevance boost. The semantic search still runs so paraphrased
        queries keep working.
      - **URL fetch overlay.** If the query contains a URL from a
        trusted legal publisher (``services.rag.url_fetcher``), we fetch
        and sanitise the page, chunk it, and inject the chunks as
        high-confidence RAGResult rows. No embedding needed — the user
        *asked* us to look at this page.
      - **Adaptive confidence gate.** The hard-coded 0.55 floor is
        overridden per query class (``article_specific`` keeps 0.55,
        ``conversational`` drops to 0.45) so loose phrasing doesn't get
        eaten by the refusal logic.
    """
    opts = options or RetrieveV2Options()
    t0 = time.monotonic()

    # Phase 3.10 pre-retrieval: direct hits from article refs + user URLs.
    # These run BEFORE embedding so a failure here is cheap (no tokens spent).
    direct_hits: list[RAGResult] = []
    try:
        direct_hits.extend(await _fetch_url_overlay(query))
    except Exception:  # noqa: BLE001
        logger.debug("rag_legal_v2: URL overlay skipped", exc_info=True)
    try:
        direct_hits.extend(await _article_ref_overlay(query))
    except Exception:  # noqa: BLE001
        logger.debug("rag_legal_v2: article-ref overlay skipped", exc_info=True)

    # 1. Query embedding
    qvec = await get_query_embedding_gemini(query)
    if qvec is None:
        # Even if embedding fails we can still return direct hits.
        if direct_hits:
            return RAGContext(
                query=query,
                results=direct_hits[: opts.top_k],
                method="v2_direct_only",
                retrieval_ms=(time.monotonic() - t0) * 1000,
            )
        return RAGContext(query=query, method="v2_embedding_fail",
                          retrieval_ms=(time.monotonic() - t0) * 1000)
    emb_literal = "[" + ",".join(str(float(v)) for v in qvec) + "]"

    # 2. Parallel vector search on both tables.
    # NOTE: SQLAlchemy AsyncSession is NOT safe for concurrent operations,
    # so each task gets its own session from the factory.
    from app.database import async_session as _make_session

    async def _kc_task() -> list[RAGResult]:
        async with _make_session() as s:
            return await _retrieve_legal_kc_v2(emb_literal, s, opts.candidate_pool)

    async def _doc_task() -> list[RAGResult]:
        async with _make_session() as s:
            return await _retrieve_legal_document(emb_literal, s, opts.candidate_pool)

    tasks: list[asyncio.Task] = []
    sources: list[str] = []
    if opts.include_legal_kc:
        tasks.append(asyncio.create_task(_kc_task()))
        sources.append("legal_kc")
    if opts.include_legal_document:
        tasks.append(asyncio.create_task(_doc_task()))
        sources.append("legal_document")

    per_source = await asyncio.gather(*tasks)
    # Log coverage per source
    for src, rs in zip(sources, per_source):
        logger.debug("rag_legal_v2 [%s]: %d candidates (top_sim=%.3f)",
                     src, len(rs), rs[0].relevance_score if rs else 0.0)

    # 3. RRF merge
    merged = rrf_merge(*per_source, top_k=opts.candidate_pool)

    # Phase 3.10: prepend direct hits (URL chunks + article lookups) so the
    # reranker sees them alongside the semantic candidates. They come in
    # at 0.92 which is already above the 0.55 gate, but the reranker can
    # still demote them if the query shifts away.
    if direct_hits:
        # Avoid duplicates by (fact_text[:60]) signature.
        seen_sigs = {(r.fact_text or "")[:60] for r in merged}
        for dh in direct_hits:
            sig = (dh.fact_text or "")[:60]
            if sig and sig in seen_sigs:
                continue
            seen_sigs.add(sig)
            merged.insert(0, dh)

    if not merged:
        return RAGContext(query=query, results=[], method="v2_empty",
                          retrieval_ms=(time.monotonic() - t0) * 1000)

    # 4. Reranker (if enabled)
    method = "v2_rrf"
    if opts.use_reranker and len(merged) > 1:
        try:
            from app.services.rag_reranker import rerank_with_llm
            merged = await rerank_with_llm(query, merged, target_top_k=opts.top_k)
            method = "v2_rrf_reranked"
        except Exception as exc:
            logger.warning("rag_reranker failed, using RRF ranking: %s", exc)

    # 5. Adaptive confidence gate — per query class instead of a constant.
    try:
        from app.services.rag.adaptive_threshold import min_similarity_for
        adaptive_floor, qclass = min_similarity_for(query, floor=0.18)
        # For article-specific queries keep the historical 0.55 rigor;
        # for conversational/opinion relax to ~0.45 so we don't refuse
        # borderline-useful hits.
        adaptive_gate = max(
            adaptive_floor,
            {
                "article_specific": 0.55,
                "legal_specific": 0.50,
                "conversational": 0.45,
                "opinion": 0.40,
            }.get(qclass, opts.confidence_threshold),
        )
    except Exception:  # noqa: BLE001
        adaptive_gate = opts.confidence_threshold
        qclass = "unknown"

    top1 = merged[0].relevance_score if merged else 0.0
    if top1 < adaptive_gate:
        logger.info(
            "rag_legal_v2: confidence gate rejected query "
            "(top1=%.3f < %.3f, class=%s): %s",
            top1, adaptive_gate, qclass, query[:80],
        )
        return RAGContext(
            query=query,
            results=[],
            method="v2_refused",
            retrieval_ms=(time.monotonic() - t0) * 1000,
        )

    # 6. Final top_k
    final = merged[: opts.top_k]
    return RAGContext(
        query=query,
        results=final,
        method=method,
        retrieval_ms=(time.monotonic() - t0) * 1000,
    )


# ──────────────────────────────────────────────────────────────────────
# Phase 3.10 (2026-04-19) pre-retrieval overlays
# ──────────────────────────────────────────────────────────────────────


async def _fetch_url_overlay(query: str) -> list[RAGResult]:
    """Return RAGResult rows for any allow-listed URL in ``query``.

    Each URL is fetched via ``services.rag.url_fetcher.fetch_and_chunk``
    with Redis cache. Chunks come back sanitised; we wrap each as a
    ``RAGResult`` with ``relevance_score=0.92`` so the downstream gate
    lets them through and the reranker can still re-order by actual
    relevance to the query text.
    """

    try:
        from app.config import settings

        if not getattr(settings, "rag_url_fetch_enabled", True):
            return []
        from app.services.rag.url_fetcher import extract_urls, fetch_and_chunk
    except Exception:  # noqa: BLE001
        return []

    urls = extract_urls(query)
    if not urls:
        return []

    # Bound the work per query — no more than 3 URLs.
    urls = urls[:3]
    results: list[RAGResult] = []
    for url in urls:
        chunks = await fetch_and_chunk(url)
        for ch in chunks:
            results.append(
                RAGResult(
                    fact_text=ch.text,
                    law_article=f"user_url:{ch.host}#{ch.chunk_index}",
                    relevance_score=0.92,
                    common_errors=None,
                    correct_response_hint=None,
                    difficulty_level=None,
                    is_court_practice=ch.host == "sudact.ru",
                    court_case_reference=None,
                    question_templates=None,
                    follow_up_questions=None,
                    blitz_question=None,
                    blitz_answer=None,
                    tags=["user_url", ch.host],
                )
            )
    if results:
        logger.info(
            "rag_legal_v2: URL overlay injected %d chunks from %d URLs",
            len(results), len(urls),
        )
    return results


async def _article_ref_overlay(query: str) -> list[RAGResult]:
    """Return RAGResult rows by direct ``law_article`` lookup in legal_document.

    When the user writes "ст. 213.4" we force-include the law_document row
    for that article at the top of the pool. The reranker can still move
    it down if the surrounding context doesn't actually want it, but the
    initial injection guarantees it isn't lost to a low embedding score.
    """

    try:
        from app.services.rag.article_extractor import extract_article_refs
    except Exception:  # noqa: BLE001
        return []

    refs = extract_article_refs(query)
    if not refs:
        return []
    refs = refs[:5]  # bound the SQL cost

    try:
        from app.database import async_session as _make_session
        from sqlalchemy import select, or_

        # Late import to avoid potential circular issues with the
        # legal_document model. Module path is ``legal_document`` (singular
        # file per model), NOT ``legal`` — fixed 2026-04-19 during audit.
        from app.models.legal_document import LegalDocument

        async with _make_session() as s:
            stmt = select(LegalDocument).where(
                or_(*[LegalDocument.law_article == ref for ref in refs])
            ).limit(len(refs) * 2)
            rows = (await s.execute(stmt)).scalars().all()
    except Exception as exc:  # noqa: BLE001
        logger.debug("rag_legal_v2 article overlay: SQL failed (%s)", exc)
        return []

    out: list[RAGResult] = []
    for row in rows:
        text = getattr(row, "fact_text", None) or getattr(row, "content", None) or ""
        if not text:
            continue
        out.append(RAGResult(
            fact_text=text,
            law_article=getattr(row, "law_article", None) or "",
            relevance_score=0.90,
            common_errors=None,
            correct_response_hint=None,
            difficulty_level=None,
            is_court_practice=bool(getattr(row, "is_court_practice", False)),
            court_case_reference=None,
            question_templates=None,
            follow_up_questions=None,
            blitz_question=None,
            blitz_answer=None,
            tags=["article_ref_overlay"],
        ))
    if out:
        logger.info(
            "rag_legal_v2: article-ref overlay injected %d rows for refs %s",
            len(out), refs,
        )
    return out


async def close_v2_clients() -> None:
    """Cleanup — call on app shutdown."""
    global _EMBEDDING_CLIENT
    if _EMBEDDING_CLIENT and not _EMBEDDING_CLIENT.is_closed:
        await _EMBEDDING_CLIENT.aclose()
    _EMBEDDING_CLIENT = None
