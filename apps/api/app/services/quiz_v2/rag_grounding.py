"""RAG grounding helpers for case generation.

Tier B/C LLM can hallucinate article references ("ст. 999.9 127-ФЗ") that
don't exist. We solve that two ways:

  1. PRE-generation: retrieve real 127-FZ chunks relevant to the complexity
     bucket and pass them as "allowed article pool" in the prompt.
  2. POST-generation: validate that every `ст. 213.X` mentioned in the
     generated case actually appears in the RAG index. Strip fabricated refs.

Keeps Tier B/C output legally accurate + traceable to source.
"""

from __future__ import annotations

import logging
import re
from typing import Literal

logger = logging.getLogger(__name__)

# Article-prefix regex — catches "ст.", "ст.ст.", "ст. ст.", "статья" and all
# its inflections (статьи, статье, статью, статьёй, статьям, статьях, etc.),
# plus English "art.". 2026-04-18: `стать\w*` handles any Russian inflection.
_ARTICLE_PREFIX_RE = re.compile(
    r"(?:ст\.\s*ст\.?|ст\.|стать\w*|art\.?)\s*([0-9]{1,3}(?:\.[0-9]+)*)",
    re.IGNORECASE,
)
# After the first number we may have a comma-separated list, e.g. "ст. 61.2, 61.3".
# This secondary pattern picks up those "continuation" numbers.
_CONT_NUMBER_RE = re.compile(r",\s*([0-9]{1,3}(?:\.[0-9]+)*)")


def extract_article_refs(text: str) -> list[str]:
    """Pull all article references out of freeform text.

    Handles:
      • "ст. 213.4"
      • "по статье 213.28"
      • "согласно статьям 61.2, 61.3"  (continuation numbers after comma)
      • "в соответствии со ст.ст. 213.4, 213.9"
      • "статьёй 213.28 предусмотрено"

    Returns list like ["213.4", "213.28", "61.2"]. Deduplicates, preserves order.
    """
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []

    # Walk through the text, find prefix-anchored refs; after each hit, scan
    # for ",<number>" continuations until a non-comma-number break.
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
        # Look for ",N[.M]" continuations immediately following
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


# Seed topic queries per complexity bucket — used to pull RAG context.
_TOPIC_QUERIES: dict[str, list[str]] = {
    "simple": [
        "порог суммы долга банкротство физлица",
        "обязанность подачи заявления 213.4",
        "освобождение от обязательств 213.28",
        "единственное жильё 446 ГПК",
    ],
    "tangled": [
        "брачный договор банкротство супругов",
        "ипотечная квартира реализация",
        "оспаривание сделок 61.2",
        "созаёмщик солидарная ответственность",
    ],
    "adversarial": [
        "субсидиарная ответственность 213.28",
        "фиктивное банкротство 197 УК",
        "оспаривание сделок с заинтересованными лицами 61.2 61.3",
        "отказ в освобождении от обязательств недобросовестность",
    ],
}


async def build_rag_grounded_prompt_suffix(
    complexity: Literal["simple", "tangled", "adversarial"],
    max_snippets: int = 5,
    max_chars_per_snippet: int = 320,
) -> tuple[str, set[str]]:
    """Pull RAG snippets relevant to the complexity and format as prompt suffix.

    Returns (suffix_text, allowed_articles_set).

      suffix_text — formatted block to append to LLM user-message:
                    "## Правовой контекст (используй ТОЛЬКО эти статьи):
                     - ст. 213.4 — ...
                     - ст. 213.28 — ..."
      allowed_articles_set — {"213.4", "213.28", ...} for post-validation.

    Best-effort: returns ("", set()) on any RAG failure so caller falls back
    to ungrounded generation.
    """
    try:
        from app.database import async_session
        from app.services.rag_legal import retrieve_legal_context, RetrievalConfig

        queries = _TOPIC_QUERIES.get(complexity, _TOPIC_QUERIES["simple"])
        # Aggregate top-3 from each topic, dedupe by chunk_id
        snippets: list[tuple[str, str]] = []  # (article, text)
        seen_chunk_ids: set[str] = set()
        allowed_articles: set[str] = set()

        async with async_session() as db:
            for q in queries:
                try:
                    ctx = await retrieve_legal_context(
                        q, db,
                        config=RetrievalConfig(top_k=3),
                    )
                    if not ctx or not ctx.has_results:
                        continue
                    for r in ctx.results[:3]:
                        cid = str(getattr(r, "chunk_id", "") or "")
                        if cid and cid in seen_chunk_ids:
                            continue
                        seen_chunk_ids.add(cid)
                        article = (getattr(r, "law_article", "") or "").strip()
                        text = (getattr(r, "fact_text", "") or getattr(r, "text", "") or "").strip()
                        if not text:
                            continue
                        # Extract article number from law_article (e.g. "ст. 213.4")
                        nums = extract_article_refs(article)
                        for n in nums:
                            allowed_articles.add(n)
                        snippets.append((article, text[:max_chars_per_snippet]))
                        if len(snippets) >= max_snippets:
                            break
                except Exception as inner_exc:
                    logger.debug("rag_grounding: topic query '%s' failed: %s", q, inner_exc)
                if len(snippets) >= max_snippets:
                    break

        if not snippets:
            return "", set()

        suffix_lines = [
            "",
            "## Правовой контекст (ИСПОЛЬЗУЙ ТОЛЬКО эти статьи и факты):",
        ]
        for art, txt in snippets[:max_snippets]:
            suffix_lines.append(f"- {art}: {txt}")
        suffix_lines.append(
            "\nВАЖНО: expected_beats должны ссылаться на статьи ИЗ ЭТОГО СПИСКА. "
            "Не выдумывай номера статей, которых нет в контексте выше."
        )
        return "\n".join(suffix_lines), allowed_articles

    except Exception as exc:
        logger.warning("rag_grounding: failed to build suffix: %s", exc)
        return "", set()


def validate_case_articles(
    case_data: dict,
    allowed_articles: set[str],
) -> tuple[dict, list[str]]:
    """Strip fabricated article references from a generated case.

    Scans narrative_hook + expected_beats[*] for `ст. X.Y` patterns. Any
    reference NOT in allowed_articles is dropped from lists / replaced
    with "(ссылка уточняется)" in prose.

    Returns (cleaned_case_data, list_of_removed_refs).
    """
    if not allowed_articles:
        # No grounding available — return as-is, caller logs warning
        return case_data, []

    removed: list[str] = []

    def _clean_text(text: str) -> str:
        """Replace references to non-allowed articles with a neutral placeholder."""
        if not text:
            return text
        def _repl(m: re.Match[str]) -> str:
            ref = m.group(1)
            if ref in allowed_articles:
                return m.group(0)
            removed.append(ref)
            return "(ссылка уточняется)"
        return _ARTICLE_PREFIX_RE.sub(_repl, text)

    # Clean narrative_hook
    if "narrative_hook" in case_data and isinstance(case_data["narrative_hook"], str):
        case_data["narrative_hook"] = _clean_text(case_data["narrative_hook"])

    # Clean expected_beats[*] lists (drop items that reference non-allowed)
    eb = case_data.get("expected_beats")
    if isinstance(eb, dict):
        cleaned_beats: dict[str, list[str]] = {}
        for beat_key, hints in eb.items():
            if not isinstance(hints, list):
                cleaned_beats[beat_key] = hints
                continue
            cleaned_hints = []
            for h in hints:
                if not isinstance(h, str):
                    cleaned_hints.append(h)
                    continue
                # Check if this hint mentions ANY non-allowed article → drop entirely
                refs_in_hint = extract_article_refs(h)
                bad = [r for r in refs_in_hint if r not in allowed_articles]
                if bad:
                    removed.extend(bad)
                    # Skip this hint (too tainted) instead of keeping a stub
                    continue
                cleaned_hints.append(h)
            cleaned_beats[beat_key] = cleaned_hints
        case_data["expected_beats"] = cleaned_beats

    return case_data, removed
