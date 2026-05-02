"""Per-team methodology RAG (TZ-8 PR-B).

The third RAG retriever alongside :func:`rag_legal.retrieve_legal_context`
(global facts) and :func:`rag_wiki.retrieve_wiki_context` (per-manager
auto-wiki). Methodology is *per-team*: a query for "objection handling"
on session of a manager from team A returns team A's playbooks, never
team B's. Cross-team isolation is enforced at the SQL layer (the
required ``team_id`` filter is the first clause of the WHERE), so
even a buggy caller that forgets to scope can't surface another
team's content.

Core shape (matches ``rag_wiki``):

  * Adaptive similarity threshold from the team's chunk count
    (small teams need more permissive thresholds; busy teams
    benefit from suppression).
  * 3× over-fetch into the candidate pool, lightweight reranker
    on top:
      - ``+0.04`` per query-keyword overlap with ``keywords``
      - ``+0.06`` for high-value kinds (``opener`` / ``objection`` /
        ``closing``) — TZ-8 §3.6 simple-heuristic default. An
        intent classifier lives in TZ-9 if pilot quality demands it.
      - ``-0.04`` for ``disputed`` rows (visible-with-warning
        contract, mirrors :mod:`rag_wiki`).
  * SQL filter ``knowledge_status IN STATUSES_VISIBLE_IN_RAG`` so
    ``outdated`` and ``needs_review`` rows never enter the pool.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_status import STATUSES_VISIBLE_IN_RAG
from app.models.methodology import MethodologyChunk
from app.services.llm import get_embedding

logger = logging.getLogger(__name__)


# Reranker constants — kept module-level so unit tests can import
# and observe drift instead of duplicating the values.
KEYWORD_OVERLAP_BONUS = 0.04
HIGH_VALUE_KINDS: frozenset[str] = frozenset({"opener", "objection", "closing"})
HIGH_VALUE_BONUS = 0.06
DISPUTED_PENALTY = -0.04


async def retrieve_methodology_context(
    query: str,
    team_id: uuid.UUID,
    db: AsyncSession,
    top_k: int = 4,
    min_similarity: float | None = None,
    *,
    user_id: uuid.UUID | None = None,
    source_type: str = "methodology_retrieval",
    source_id: uuid.UUID | None = None,
    log_usage: bool = True,
) -> list[dict]:
    """Per-team RAG search over ``methodology_chunks``.

    Args:
        query: User message / scenario seed used for the embedding.
        team_id: REQUIRED. Methodology has no notion of "global" so
            a NULL team_id is a programming error — the function
            returns ``[]`` and logs a warning rather than risk
            cross-team leakage.
        db: AsyncSession.
        top_k: Final result count after rerank.
        min_similarity: Override the adaptive threshold. When
            ``None``, the threshold is derived from the team's
            visible chunk count.

    Returns:
        list[dict] each carrying the keys the prompt builder and
        the UI consume: ``id``, ``title``, ``body``, ``kind``,
        ``tags``, ``knowledge_status``, ``similarity``,
        ``rerank_score``. ``body`` is truncated to 500 chars (same
        cap rag_wiki uses), the full text is one PUT away.
    """
    if team_id is None:
        logger.warning(
            "rag_methodology: called with team_id=None — refusing to "
            "scan global methodology, returning empty result"
        )
        return []

    try:
        query_emb = await get_embedding(query)
    except Exception:
        logger.debug(
            "rag_methodology: embedding lookup failed for query, returning empty",
            exc_info=True,
        )
        return []
    if not query_emb:
        return []

    visible_statuses = list(STATUSES_VISIBLE_IN_RAG)

    # Adaptive threshold by team chunk count. Same shape as
    # rag_wiki — buckets tuned for the methodology size profile
    # (smaller teams write fewer playbooks, so the lowest bucket
    # is more permissive than for legal).
    if min_similarity is None:
        chunk_count = (
            await db.execute(
                select(func.count(MethodologyChunk.id))
                .where(MethodologyChunk.team_id == team_id)
                .where(MethodologyChunk.embedding.isnot(None))
                .where(MethodologyChunk.knowledge_status.in_(visible_statuses))
                # B5-01 — soft-deleted rows never surface in retrieval.
                # The status filter above already excludes ``outdated``,
                # but ``is_deleted=True`` is the authoritative flag and
                # the two are independent (a chunk could in theory be
                # soft-deleted while in another status during a botched
                # transition; this filter catches that).
                .where(MethodologyChunk.is_deleted.is_(False))
            )
        ).scalar() or 0
        if chunk_count < 5:
            min_similarity = 0.15
        elif chunk_count <= 20:
            min_similarity = 0.25
        elif chunk_count <= 100:
            min_similarity = 0.32
        else:
            min_similarity = 0.40

    fetch_n = top_k * 3
    rows = await db.execute(
        select(
            MethodologyChunk.id,
            MethodologyChunk.title,
            MethodologyChunk.body,
            MethodologyChunk.kind,
            MethodologyChunk.tags,
            MethodologyChunk.keywords,
            MethodologyChunk.knowledge_status,
            MethodologyChunk.embedding.cosine_distance(query_emb).label("distance"),
        )
        .where(MethodologyChunk.team_id == team_id)
        .where(MethodologyChunk.embedding.isnot(None))
        .where(MethodologyChunk.knowledge_status.in_(visible_statuses))
        # B5-01 — match the count filter above. Without this, the
        # candidate pool could include soft-deleted rows (with valid
        # embeddings but ``outdated`` status hidden via the in_
        # filter — but the column may drift independently in future).
        .where(MethodologyChunk.is_deleted.is_(False))
        .order_by("distance")
        .limit(fetch_n)
    )

    candidates: list[dict] = []
    for row in rows:
        similarity = 1.0 - row.distance
        if similarity < min_similarity:
            continue
        candidates.append(
            {
                "id": str(row.id),
                "title": row.title,
                "body": row.body[:500] if row.body else "",
                "kind": row.kind,
                "tags": list(row.tags or []),
                "keywords": list(row.keywords or []),
                "knowledge_status": row.knowledge_status,
                "similarity": round(similarity, 3),
            }
        )

    # Reranker
    q_words = {w.lower() for w in query.split() if len(w) >= 3}
    for c in candidates:
        kw_hits = sum(
            1 for k in c["keywords"] if k and k.lower() in q_words
        )
        kind_boost = HIGH_VALUE_BONUS if c["kind"] in HIGH_VALUE_KINDS else 0.0
        status_penalty = (
            DISPUTED_PENALTY if c["knowledge_status"] == "disputed" else 0.0
        )
        c["rerank_score"] = round(
            c["similarity"]
            + KEYWORD_OVERLAP_BONUS * kw_hits
            + kind_boost
            + status_penalty,
            4,
        )

    candidates.sort(key=lambda r: r["rerank_score"], reverse=True)
    final = candidates[:top_k]

    # TZ-8 PR-D telemetry: log every chunk surfaced to the prompt so
    # the methodology effectiveness panel knows what fired. Best-effort
    # — wrapped in its own try/except inside the helper, never raises.
    # Skip logging when user_id is unknown (e.g. system-level retrieval
    # for diagnostics) — caller can opt out via ``log_usage=False`` too.
    if log_usage and user_id is not None and final:
        from app.services.methodology_telemetry import (
            log_methodology_retrieval,
        )

        for rank, c in enumerate(final, start=1):
            log_id = await log_methodology_retrieval(
                db,
                user_id=user_id,
                chunk_id=uuid.UUID(c["id"]),
                source_type=source_type,
                source_id=source_id,
                query_text=query[:500],
                relevance_score=c.get("rerank_score") or c.get("similarity"),
                retrieval_rank=rank,
            )
            # Surface the log id back to the caller so it can later
            # patch the outcome (judge result) onto the right row.
            if log_id is not None:
                c["_usage_log_id"] = str(log_id)

    logger.info(
        "Methodology RAG | team=%s | query='%s' | threshold=%.2f | returned=%d/%d",
        team_id, query[:50], min_similarity, len(final), len(candidates),
    )
    return final


__all__ = [
    "retrieve_methodology_context",
    "KEYWORD_OVERLAP_BONUS",
    "HIGH_VALUE_KINDS",
    "HIGH_VALUE_BONUS",
    "DISPUTED_PENALTY",
]
