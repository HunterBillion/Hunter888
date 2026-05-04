"""Canonical-answer fallback for ФЗ-127 quiz.

When `rag_legal.retrieve_legal_context` returns nothing for a question
(sparse-coverage category, fresh phrasing, etc), the LLM judge would
otherwise improvise with `context_str=""` — that's the root cause of
the "verdict feels random" complaint logged 2026-05-04.

This module loads a curated YAML bank of canonical answers (see
`apps/api/app/data/canonical_answers.yaml`) and exposes a tiny lookup:
given a question text + category, return the best-matching canonical
entry or None. The entry is then injected into the LLM judge prompt
as the authoritative reference, AND surfaced as `correct_answer_summary`
when the judge ends up "wrong".

Match strategy is intentionally simple — lowercase substring AND-match
on `q_keywords` — to keep the path debuggable. False matches between
"налог" / "наличные" etc are why entries should pick narrow keywords.

YAML is reloaded on every call in DEBUG mode (so methodology can edit
in /opt/hunter888 and see effect without API restart). In PROD it's
cached on first read.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "canonical_answers.yaml"
)


@dataclass
class CanonicalEntry:
    category: str
    q_keywords: list[str]
    canonical: str
    article: str
    wrong_hints: list[str]


def _is_debug() -> bool:
    return os.environ.get("ENV", "").lower() in {"dev", "development", "local"}


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # PyYAML is already a dependency for fixtures
    except ImportError as exc:  # pragma: no cover
        logger.error("PyYAML missing — canonical_answers disabled: %s", exc)
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning("canonical_answers.yaml not found at %s", path)
        return {}
    except Exception as exc:
        logger.error("canonical_answers.yaml parse failed: %s", exc, exc_info=True)
        return {}


def _flatten(data: dict[str, Any]) -> list[CanonicalEntry]:
    out: list[CanonicalEntry] = []
    cats = data.get("categories") or {}
    for cat_name, entries in cats.items():
        if not isinstance(entries, list):
            continue
        for raw in entries:
            if not isinstance(raw, dict):
                continue
            try:
                out.append(
                    CanonicalEntry(
                        category=str(cat_name),
                        q_keywords=[str(k).lower() for k in raw.get("q_keywords", [])],
                        canonical=str(raw.get("canonical", "")).strip(),
                        article=str(raw.get("article", "")).strip(),
                        wrong_hints=[str(w).lower() for w in raw.get("wrong_hints", [])],
                    )
                )
            except Exception as exc:
                logger.warning("canonical entry skipped (cat=%s): %s", cat_name, exc)
    return out


@lru_cache(maxsize=1)
def _cached_entries(_mtime_token: float) -> list[CanonicalEntry]:
    """Cache keyed on file mtime so prod restarts don't re-parse, but
    edits in dev are picked up automatically."""
    return _flatten(_load_yaml(_DEFAULT_PATH))


def _entries() -> list[CanonicalEntry]:
    try:
        mtime = _DEFAULT_PATH.stat().st_mtime if _DEFAULT_PATH.exists() else 0.0
    except OSError:
        mtime = 0.0
    if _is_debug():
        # Bypass cache in dev so methodology can iterate the YAML.
        return _flatten(_load_yaml(_DEFAULT_PATH))
    return _cached_entries(mtime)


def find_canonical(
    question_text: str,
    category: str | None = None,
) -> CanonicalEntry | None:
    """Return the best-matching canonical entry for this question, or None.

    Strategy:
      1. Filter to entries in the matching category (if provided).
      2. Within those, find entries whose ALL q_keywords appear in the
         lowercased question text.
      3. Tie-break by total keyword length (more specific wins).
    """
    if not question_text:
        return None
    lower_q = question_text.lower()
    pool = _entries()
    if not pool:
        return None
    if category:
        cat_lower = str(category).lower()
        pool = [e for e in pool if e.category == cat_lower] or pool

    matches: list[tuple[int, CanonicalEntry]] = []
    for e in pool:
        if not e.q_keywords:
            continue
        if all(kw in lower_q for kw in e.q_keywords):
            specificity = sum(len(kw) for kw in e.q_keywords)
            matches.append((specificity, e))

    if not matches:
        return None
    matches.sort(key=lambda x: x[0], reverse=True)
    return matches[0][1]


def has_wrong_hint(entry: CanonicalEntry, user_answer: str) -> str | None:
    """If the user's answer matches a known wrong-hint substring, return
    that substring (so the caller can short-circuit a "wrong" verdict
    with a targeted explanation). None otherwise."""
    if not user_answer or not entry.wrong_hints:
        return None
    lower_a = user_answer.lower()
    for hint in entry.wrong_hints:
        if hint and hint in lower_a:
            return hint
    return None
