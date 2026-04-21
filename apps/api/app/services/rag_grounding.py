"""Citation enforcement: post-generation check that LLM answer cites an
allowed source from the retrieval set.

Failure modes this catches:
  1. **Invented article numbers** — LLM hallucinates "ст. 213.25" when the
     actual retrieved context only contains ст. 213.4 and ст. 213.6.
  2. **Wrong law cited** — model references "ст. 10 ГК РФ" when context is
     strictly 127-ФЗ.
  3. **No citation at all** — model gives generic advice without grounding.

How it works:
  - Extract all "ст. N" / "статья N" mentions from the LLM answer (regex).
  - Extract all law_article values from retrieved context's RAGResult list.
  - Compute allowed_set (article numbers mentioned in ≥1 retrieved chunk).
  - Classify the answer as:
      "grounded"     — every cited article appears in allowed_set
      "partial"      — some cited articles match, some don't
      "ungrounded"   — no citations at all
      "hallucinated" — cites articles NOT in allowed_set (most dangerous)

Usage:
    from app.services.rag_grounding import check_citations

    answer = await llm.chat(...)
    check = check_citations(answer, retrieved_chunks)
    if check.status == "hallucinated":
        # Either reject + regenerate, or annotate with warning
        answer = f"⚠️ Сверьтесь с первоисточником: {answer}"
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.rag_legal import RAGResult

logger = logging.getLogger(__name__)


# ─── Patterns ────────────────────────────────────────────────────────────
#
# Match Russian legal citation patterns:
#   ст. 213.4
#   Статья 213.4
#   ст.213.4
#   статьи 213 и 214
#   ст. 213.4 127-ФЗ
#   п. 1 ст. 213.4
#
# We normalize to just the article number.

ARTICLE_RE = re.compile(
    r"(?:^|\W)(?:ст(?:\.|атья|атьи|атье|атью|атей)?|статьями)\s*(\d+(?:\.\d+)*)",
    re.IGNORECASE | re.UNICODE,
)

# Also catch explicit law references. Presence of these alongside an article
# number is informative for cross-checking law correctness.
LAW_FZ_RE = re.compile(r"127[-\s]?[ФфFf][Зз]", re.UNICODE)
LAW_GK_RE = re.compile(r"[ГгG][КкK]\s*[РрR][ФфF]", re.UNICODE)
LAW_GPK_RE = re.compile(r"[ГгG][ПпP][КкK]\s*[РрR][ФфF]", re.UNICODE)


# ─── Result ──────────────────────────────────────────────────────────────


@dataclass
class CitationCheck:
    """Result of a grounding check."""
    status: str  # "grounded" | "partial" | "ungrounded" | "hallucinated" | "no_context"
    cited_articles: list[str] = field(default_factory=list)
    allowed_articles: list[str] = field(default_factory=list)
    unsupported_articles: list[str] = field(default_factory=list)
    has_foreign_law: bool = False  # cites non-127-ФЗ laws (ГК, ГПК, etc.)

    @property
    def is_safe(self) -> bool:
        """True if the answer can be shown to the user without warning."""
        return self.status in ("grounded", "no_context")

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "cited_articles": self.cited_articles,
            "allowed_articles": self.allowed_articles,
            "unsupported_articles": self.unsupported_articles,
            "has_foreign_law": self.has_foreign_law,
        }


# ─── Extractors ──────────────────────────────────────────────────────────


def extract_article_numbers(text: str) -> list[str]:
    """Extract distinct article numbers mentioned in `text`.

    Normalized: "ст. 213.4" → "213.4", "Статья 213" → "213".
    Returns unique values in order of first appearance.
    """
    if not text:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for m in ARTICLE_RE.finditer(text):
        num = m.group(1)
        if num not in seen:
            seen.add(num)
            found.append(num)
    return found


def extract_allowed_articles(results: list["RAGResult"]) -> list[str]:
    """Collect the set of article numbers spanned by retrieved chunks.

    Extracted from RAGResult.law_article strings like "ст. 213.4 127-ФЗ" or
    "ст. 127 127-ФЗ". Uses the same regex so citation forms are comparable.
    """
    collected: list[str] = []
    seen: set[str] = set()
    for r in results:
        if not r.law_article:
            continue
        for num in extract_article_numbers(r.law_article):
            if num not in seen:
                seen.add(num)
                collected.append(num)
    return collected


# ─── Main check ──────────────────────────────────────────────────────────


def check_citations(
    answer: str,
    retrieved: list["RAGResult"],
) -> CitationCheck:
    """Classify `answer` relative to citations allowed by `retrieved` context.

    Special case: if `retrieved` is empty (refusal / no context), status is
    "no_context" — caller decides what to do (typically: LLM was asked not
    to cite specific statutes, so no enforcement possible).
    """
    cited = extract_article_numbers(answer)
    allowed = extract_allowed_articles(retrieved)
    has_foreign = bool(LAW_GK_RE.search(answer) or LAW_GPK_RE.search(answer))

    # No retrieved context → can't enforce citations
    if not retrieved:
        return CitationCheck(
            status="no_context",
            cited_articles=cited,
            allowed_articles=[],
            unsupported_articles=[],
            has_foreign_law=has_foreign,
        )

    if not cited:
        return CitationCheck(
            status="ungrounded",
            cited_articles=[],
            allowed_articles=allowed,
            unsupported_articles=[],
            has_foreign_law=has_foreign,
        )

    allowed_set = set(allowed)
    supported = [c for c in cited if c in allowed_set]
    unsupported = [c for c in cited if c not in allowed_set]

    if not unsupported:
        status = "grounded"
    elif supported:
        status = "partial"
    else:
        status = "hallucinated"

    return CitationCheck(
        status=status,
        cited_articles=cited,
        allowed_articles=allowed,
        unsupported_articles=unsupported,
        has_foreign_law=has_foreign,
    )


# ─── Convenience: annotate an answer based on check result ───────────────


def annotate_answer(answer: str, check: CitationCheck) -> str:
    """Prepend a user-visible warning if the answer is not fully grounded.

    Use for Coach / training / quiz paths that display the answer raw.
    Safe no-op if status is 'grounded' or 'no_context'.
    """
    if check.is_safe:
        return answer
    if check.status == "hallucinated":
        return (
            "⚠️ Ответ ссылается на статьи, которых нет в проверенном "
            "наборе источников. Сверьтесь с первоисточником.\n\n"
            + answer
        )
    if check.status == "partial":
        bad = ", ".join(f"ст. {x}" for x in check.unsupported_articles[:3])
        return (
            f"⚠️ Проверьте ссылки: {bad} не подтверждены retrieved-контекстом.\n\n"
            + answer
        )
    if check.status == "ungrounded":
        return (
            "ℹ️ Ответ без прямых ссылок на статьи закона — уточните у юриста.\n\n"
            + answer
        )
    return answer
