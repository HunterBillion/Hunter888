"""quiz_v2.grader — deterministic answer matcher (Path A, A2).

Owns the verdict layer of the v2 quiz pipeline. Replaces the legacy
LLM-streamed verdict in ``services/knowledge_quiz.evaluate_answer_streaming``
with a fast, deterministic match against a pre-computed answer key.

Strategies (first match wins):
  1. exact     — normalised string equality
  2. synonyms  — membership in pre-computed synonym list
  3. regex     — pattern from ``match_config.regex``
  4. keyword   — keyword AND/OR over normalised tokens
  5. embedding — cosine similarity ≥ threshold (default 0.85);
                  uses pgvector + ``LegalKnowledgeChunk.embedding`` pool

After every verdict, ``services.knowledge_quiz_validator_v2.validate_semantic``
runs as the LLM-second-opinion safety net (Q-NEW-1 (b) decision: always
fire, regardless of strategy). ``apply_upgrade`` is one-direction —
never demotes a deterministic-correct verdict.

Design doc: docs/QUIZ_V2_ARENA_DESIGN.md §7.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.services.knowledge_quiz import normalize_for_comparison
from app.services.quiz_v2.answer_keys import AnswerKey


logger = logging.getLogger("quiz_v2.grader")


@dataclass(frozen=True)
class GradeResult:
    """Outcome of grading one user answer against an answer-key.

    Mirrors the on-the-wire ``quiz_v2.verdict.emitted`` payload (§5.1).
    """

    correct: bool
    score_delta: int
    expected_answer: str
    article_ref: str | None
    fast_path: str
    """One of: 'exact' | 'synonyms' | 'regex' | 'keyword' | 'embedding'
    | 'no_key' | 'validator_upgrade' | 'no_match'."""

    strategy: str
    """The strategy that decided the deterministic verdict (independent
    of any post-hoc validator_v2 upgrade)."""

    similarity: float | None
    """Populated for 'embedding' / 'validator_upgrade' paths."""

    degraded: bool = False
    """True when the embedding strategy fell back due to missing
    embeddings, or when validator_v2 swallowed an exception."""


# ── Score deltas (mirrors knowledge_quiz.py legacy values) ───────────

_SCORE_CORRECT = 10
_SCORE_INCORRECT = -2


# ── Strategies ───────────────────────────────────────────────────────


def _match_exact(submitted: str, key: AnswerKey) -> bool:
    a = normalize_for_comparison(submitted)
    b = normalize_for_comparison(key.expected_answer)
    return bool(a) and a == b


def _match_synonyms(submitted: str, key: AnswerKey) -> bool:
    a = normalize_for_comparison(submitted)
    if not a:
        return False
    candidates = [key.expected_answer, *key.synonyms]
    for cand in candidates:
        b = normalize_for_comparison(cand)
        if not b:
            continue
        if a == b:
            return True
        # Containment-rescue: user paraphrases ("через судебный порядок"
        # vs canonical "через суд"). Mirror the rescue from
        # knowledge_quiz.py:704 so existing edge cases stay covered.
        if b in a or a in b:
            return True
    return False


def _match_regex(submitted: str, key: AnswerKey) -> bool:
    pattern = (key.match_config or {}).get("regex")
    if not pattern:
        return False
    try:
        return bool(re.search(pattern, submitted, flags=re.IGNORECASE))
    except re.error:
        logger.warning(
            "quiz_v2.grader regex compile failed key_id=%s pattern=%r",
            key.id,
            pattern,
        )
        return False


def _match_keyword(submitted: str, key: AnswerKey) -> bool:
    cfg = key.match_config or {}
    keywords = cfg.get("keywords") or []
    mode = (cfg.get("mode") or "all").lower()
    if not keywords:
        return False
    a = normalize_for_comparison(submitted)
    matches = [normalize_for_comparison(k) in a for k in keywords if k]
    if mode == "any":
        return any(matches)
    return all(matches)


async def _match_embedding(
    submitted: str,
    key: AnswerKey,
) -> tuple[bool, float | None, bool]:
    """Cosine-similarity match. Returns (matched, similarity, degraded).

    A2 implements the algorithmic surface but defers actual embedding
    computation to a thin helper that the integration in A4 wires to
    the existing pgvector pool. For now the path returns
    ``(False, None, True)`` so the caller is free to fall through to
    later strategies without crashing — this keeps the unit tests
    deterministic without requiring a live embeddings service.
    """
    threshold = (key.match_config or {}).get("threshold", 0.85)
    try:
        from app.services.quiz_v2.embedding_match import cosine_similarity
    except ImportError:
        logger.debug("quiz_v2.grader embedding helper unavailable; degraded path")
        return False, None, True
    try:
        sim = await cosine_similarity(submitted, key.expected_answer)
    except Exception:
        logger.exception("quiz_v2.grader embedding compute failed key_id=%s", key.id)
        return False, None, True
    if sim is None:
        return False, None, True
    return sim >= threshold, float(sim), False


# ── Strategy router ──────────────────────────────────────────────────


_STRATEGY_ORDER = ("exact", "synonyms", "regex", "keyword", "embedding")


async def _run_strategy(
    submitted: str,
    key: AnswerKey,
    strategy: str,
) -> tuple[bool, float | None, bool]:
    """Run one named strategy. Returns (matched, similarity, degraded)."""
    if strategy == "exact":
        return _match_exact(submitted, key), None, False
    if strategy == "synonyms":
        return _match_synonyms(submitted, key), None, False
    if strategy == "regex":
        return _match_regex(submitted, key), None, False
    if strategy == "keyword":
        return _match_keyword(submitted, key), None, False
    if strategy == "embedding":
        return await _match_embedding(submitted, key)
    raise ValueError(f"unknown strategy: {strategy!r}")


# ── Validator v2 second-opinion (Q-NEW-1 (b): always fire) ──────────


async def _maybe_validator_upgrade(
    *,
    submitted: str,
    key: AnswerKey,
    primary_correct: bool,
    primary_score_delta: int,
) -> tuple[bool, int, bool, float | None, bool]:
    """Invoke validator_v2 unconditionally per Q-NEW-1 (b).

    Returns (correct, score_delta, upgraded, similarity, degraded).
    Upgrade is one-direction: if the deterministic verdict was already
    True, validator_v2 cannot demote it (apply_upgrade contract).
    Exceptions are swallowed and surface as ``degraded=True``.
    """
    try:
        from app.services.knowledge_quiz_validator_v2 import (
            apply_upgrade,
            validate_semantic,
        )
    except ImportError:
        logger.debug("validator_v2 module not available; skipping upgrade")
        return primary_correct, primary_score_delta, False, None, False

    try:
        validation = await validate_semantic(
            question="",  # filled in by caller in A4 via context
            correct_answer=key.expected_answer,
            manager_answer=submitted,
            rag_context="",
        )
    except Exception:
        logger.exception("validator_v2 raised; swallow per knowledge_quiz precedent")
        return primary_correct, primary_score_delta, False, None, True

    is_correct, score_delta, _note = apply_upgrade(
        primary_is_correct=primary_correct,
        primary_score_delta=primary_score_delta,
        validation=validation,
    )
    upgraded = (is_correct != primary_correct) or (score_delta != primary_score_delta)
    similarity = getattr(validation, "score", None)
    return is_correct, score_delta, upgraded, similarity, False


# ── Public entry point ───────────────────────────────────────────────


async def grade_answer(
    *,
    answer_id: str,
    question_id: str,
    submitted_text: str,
    key: AnswerKey | None,
) -> GradeResult:
    """Grade one user answer against the loaded answer-key.

    Strategy order: declared strategy first; on miss fall through the
    rest of ``_STRATEGY_ORDER`` so misconfigured keys still produce a
    sane verdict. After the deterministic round, ``validator_v2.validate_semantic``
    runs unconditionally (Q-NEW-1 (b)) and may upgrade ``False → True``.
    Never demotes ``True → False`` (apply_upgrade invariant).
    """
    if key is None:
        return GradeResult(
            correct=False,
            score_delta=_SCORE_INCORRECT,
            expected_answer="",
            article_ref=None,
            fast_path="no_key",
            strategy="none",
            similarity=None,
            degraded=True,
        )

    deciding_strategy = key.match_strategy
    matched = False
    similarity: float | None = None
    degraded = False

    # Try the declared strategy first.
    matched, similarity, degraded = await _run_strategy(
        submitted_text, key, deciding_strategy
    )

    # On miss, walk the remaining strategies. Skip the one already tried.
    if not matched:
        for s in _STRATEGY_ORDER:
            if s == deciding_strategy:
                continue
            m, sim, deg = await _run_strategy(submitted_text, key, s)
            if m:
                deciding_strategy = s
                matched = True
                similarity = sim
                degraded = deg
                break

    primary_correct = matched
    primary_score_delta = _SCORE_CORRECT if matched else _SCORE_INCORRECT

    # Validator v2 — always fire (Q-NEW-1 (b)).
    correct, score_delta, upgraded, val_sim, val_degraded = (
        await _maybe_validator_upgrade(
            submitted=submitted_text,
            key=key,
            primary_correct=primary_correct,
            primary_score_delta=primary_score_delta,
        )
    )

    fast_path = (
        "validator_upgrade"
        if upgraded
        else (deciding_strategy if matched else "no_match")
    )
    final_similarity = val_sim if upgraded else similarity
    final_degraded = degraded or val_degraded

    return GradeResult(
        correct=correct,
        score_delta=score_delta,
        expected_answer=key.expected_answer,
        article_ref=key.article_ref,
        fast_path=fast_path,
        strategy=deciding_strategy if matched else "none",
        similarity=final_similarity,
        degraded=final_degraded,
    )
