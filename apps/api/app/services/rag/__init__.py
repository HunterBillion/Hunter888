"""Shared RAG utilities used by multiple retrieval pipelines.

Phase 3 (2026-04-19). Centralises three pre-retrieval steps that both
``rag_legal_v2`` and ``quiz_v2/rag_grounding`` should reuse:

    - ``article_extractor`` — pull "ст. 213.4" refs out of freeform text
    - ``url_fetcher`` — download allowed legal sources on-the-fly
    - ``adaptive_threshold`` — classify query and pick a safe min-similarity

Keeping these in a package lets ``rag_legal_v2`` import them without
pulling in the quiz-specific code path, and lets future retrievers do
the same.
"""

from app.services.rag.article_extractor import extract_article_refs
from app.services.rag.adaptive_threshold import classify_query, min_similarity_for

__all__ = [
    "extract_article_refs",
    "classify_query",
    "min_similarity_for",
]
