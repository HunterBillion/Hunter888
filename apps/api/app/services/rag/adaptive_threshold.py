"""Pick a safe min-similarity threshold based on query classification.

Phase 3.9 (2026-04-19). Problem: ``MIN_SIMILARITY = 0.30`` is fine for
clearly legal queries but filters out legitimate hits on looser
formulations ("что будет с квартирой"). Cranking the constant down hurts
precision. Solution: classify the query on cheap heuristics and pick a
threshold per class.

Classes:
  - ``"article_specific"`` — query contains "ст. N.M" or explicit
    article ref. Strong match expected — keep threshold high (0.40).
  - ``"legal_specific"`` — contains legal/procedural nouns. High
    precision needed — threshold 0.30 (matches legacy default).
  - ``"conversational"`` — general phrasing, colloquial terms. Relax
    threshold to 0.22 so synonyms don't fall off.
  - ``"opinion"`` — subjective framing. Lowest threshold 0.18 — the
    user is exploring, RAG should cast a wider net.

All thresholds are floors — reranker still does the heavy lifting; this
just controls which rows are even considered for reranking.
"""

from __future__ import annotations

from typing import Literal

QueryClass = Literal[
    "article_specific",
    "legal_specific",
    "conversational",
    "opinion",
]


_LEGAL_NOUNS: frozenset[str] = frozenset({
    "банкротство", "несостоятельность", "должник", "кредитор",
    "арбитражный", "финансовый управляющий", "финуправляющий",
    "реструктуризация", "конкурсное производство", "конкурсная масса",
    "реализация имущества", "мфц", "внесудебное",
    "мораторий", "отсрочка", "реестр требований",
    "субсидиарная", "субсидиарка", "кдл",
    "приставы", "исполнительное производство", "взыскание",
    "порог", "минимальный долг",
    "127-фз", "127фз", "127 фз",
    "статья", "ст.",
})


_OPINION_MARKERS: frozenset[str] = frozenset({
    "думаю", "считаю", "как мне кажется", "мне кажется",
    "честно говоря", "по-моему", "по моему мнению",
    "расскажи", "объясни",
})


def classify_query(text: str) -> QueryClass:
    """Return the class of ``text`` using cheap lowercased keyword checks."""

    if not text:
        return "conversational"
    low = text.lower()

    # Article-specific: explicit "ст. 213.4" or similar.
    # Late-import to avoid cycles (rag/__init__ imports us).
    from app.services.rag.article_extractor import extract_article_refs

    if extract_article_refs(low):
        return "article_specific"

    # Opinion framing takes precedence over legal nouns when both present.
    if any(marker in low for marker in _OPINION_MARKERS):
        return "opinion"

    # Any known legal noun → legal_specific.
    for noun in _LEGAL_NOUNS:
        if noun in low:
            return "legal_specific"

    return "conversational"


_THRESHOLD_BY_CLASS: dict[QueryClass, float] = {
    "article_specific": 0.40,
    "legal_specific": 0.30,
    "conversational": 0.22,
    "opinion": 0.18,
}


def min_similarity_for(
    text: str,
    *,
    floor: float | None = None,
) -> tuple[float, QueryClass]:
    """Return (threshold, classified_kind) for ``text``.

    ``floor`` lets callers enforce a lower bound — e.g. a retrieval
    pipeline may refuse to drop below 0.20 no matter the class. When
    specified, the returned threshold is ``max(floor, class_threshold)``.
    """

    kind = classify_query(text)
    thr = _THRESHOLD_BY_CLASS[kind]
    if floor is not None:
        thr = max(thr, floor)
    return thr, kind
