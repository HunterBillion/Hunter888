"""Extract article references ("ст. 213.4") from free-form Russian text.

Phase 3.7 (2026-04-19). Moved out of ``quiz_v2/rag_grounding`` so the
main ``rag_legal_v2`` pipeline can force-fetch exact article matches
before doing the general semantic search.

The implementation is identical to the quiz_v2 version — kept in one
place now so updates don't drift between call-sites. The old path
``quiz_v2.rag_grounding.extract_article_refs`` delegates to this module.
"""

from __future__ import annotations

import re


# Prefix forms that anchor the start of an article reference. Covers all
# likely Russian cases: nominative/genitive/dative/accusative/instrumental
# singular AND plural, plus the abbreviated "ст." / "ст.ст." variants.
# Followed by a number matching N or N.M (dotted subsections).
_ARTICLE_PREFIX_RE = re.compile(
    r"(?:\b(?:ст(?:атья|атьи|атью|атьёй|атье|атьям|атьями|атьях)?|ст\.ст)\.?\s+)"
    r"([0-9]{1,3}(?:\.[0-9]+)*)",
    re.IGNORECASE,
)

# Continuation: after the first number we may have ",N.M" OR " и N.M" OR
# " или N.M" — all three connectors are idiomatic in Russian legal prose
# ("статьи 213.4, 213.9 и 213.28").
_CONT_NUMBER_RE = re.compile(
    r"\s*(?:,|\sи\s|\sили\s)\s*([0-9]{1,3}(?:\.[0-9]+)*)"
)


def extract_article_refs(text: str) -> list[str]:
    """Pull all article references out of freeform text.

    Handles:
      * ``"ст. 213.4"``
      * ``"по статье 213.28"``
      * ``"согласно статьям 61.2, 61.3"`` (continuation after comma)
      * ``"в соответствии со ст.ст. 213.4, 213.9"``
      * ``"статьёй 213.28 предусмотрено"``

    Returns a list like ``["213.4", "213.28", "61.2"]`` — deduplicated,
    order preserved.
    """

    if not text:
        return []

    seen: set[str] = set()
    out: list[str] = []
    pos = 0
    while pos < len(text):
        m = _ARTICLE_PREFIX_RE.search(text, pos)
        if not m:
            break
        first = m.group(1)
        if first not in seen:
            seen.add(first)
            out.append(first)
        cursor = m.end()
        while True:
            cm = _CONT_NUMBER_RE.match(text, cursor)
            if not cm:
                break
            num = cm.group(1)
            if num not in seen:
                seen.add(num)
                out.append(num)
            cursor = cm.end()
        pos = cursor
    return out
