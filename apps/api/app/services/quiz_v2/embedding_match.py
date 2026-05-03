"""quiz_v2.embedding_match — cosine similarity helper for the embedding strategy.

Thin wrapper around the existing pgvector + embedding-service infrastructure
(``LegalKnowledgeChunk.embedding`` is populated by
``services.embedding_live_backfill``). Computes cosine similarity between
two texts on demand for the grader's embedding strategy.

Returns ``None`` when the embedding service is unavailable so the grader
can degrade gracefully rather than crash. The caller flags this as
``degraded=True`` and the verdict still ships (validator_v2 may still
upgrade it).

A2 ships the wiring; production behavior depends on the embeddings
service being reachable from the api container (configured via
``settings.embeddings_service_url`` / ``settings.local_embedding_url``).
"""

from __future__ import annotations

import logging
import math


logger = logging.getLogger("quiz_v2.embedding_match")


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _norm(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def _cosine_from_vectors(a: list[float], b: list[float]) -> float | None:
    if not a or not b or len(a) != len(b):
        return None
    na = _norm(a)
    nb = _norm(b)
    if na == 0 or nb == 0:
        return None
    return _dot(a, b) / (na * nb)


async def _embed_text(text: str) -> list[float] | None:
    """Compute an embedding vector for a single text.

    Defers to whatever the existing embedding service exposes. If the
    service or its client wrapper is unavailable, returns ``None`` so
    the caller can degrade gracefully.
    """
    try:
        from app.services.embedding_service import embed_text
    except ImportError:
        logger.debug("embedding_service.embed_text not importable")
        return None
    try:
        vec = await embed_text(text)
    except Exception:
        logger.exception("embed_text failed")
        return None
    return list(vec) if vec is not None else None


async def cosine_similarity(text_a: str, text_b: str) -> float | None:
    """Return cosine similarity in [-1, 1] or ``None`` on any failure.

    Both texts are embedded fresh (no caching at this layer; pgvector
    similarity vs stored chunk embeddings is the responsibility of the
    chunk-retrieval layer, not this hot-path comparator).
    """
    if not text_a or not text_b:
        return None
    a = await _embed_text(text_a)
    if a is None:
        return None
    b = await _embed_text(text_b)
    if b is None:
        return None
    return _cosine_from_vectors(a, b)
