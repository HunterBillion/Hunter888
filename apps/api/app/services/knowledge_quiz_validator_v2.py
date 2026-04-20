"""Semantic second-opinion validator for knowledge-quiz answers.

Phase 3.6 (2026-04-19). Motivation: the primary ``evaluate_answer`` path
in ``knowledge_quiz.py`` is strict — it's tuned to reject garbage, not to
recognise obscure-but-correct answers. When a manager writes a compact
but factually-sound reply (``"ст. 213.4, 90 дней"``) the primary judge
sometimes returns ``is_correct=false`` because the phrasing is short.

This module provides ``validate_semantic`` — a cheap, focused LLM call
that takes (question, canonical correct answer, manager answer, optional
RAG context) and returns a structured ``ValidationResult`` with:
  - ``equivalent`` — yes/no semantically equivalent to correct
  - ``partial`` — yes/no partially covers the answer
  - ``score`` — 0.0…1.0
  - ``missing`` — list of missing facets
  - ``reason`` — short Russian explanation

Used as an override when the primary judge says false: if validator v2
says ``equivalent=true`` or ``partial=true``, the feedback is upgraded.

Gated behind ``settings.rollout_relaxed_validation`` (default False for
safety). Call is skipped if disabled.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from app.config import settings
from app.services.knowledge_quiz import normalize_for_comparison

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of the second-opinion pass."""

    skipped: bool = False
    """True when the feature flag is off — callers should ignore the rest."""

    equivalent: bool = False
    """Manager answer is semantically equivalent to reference."""

    partial: bool = False
    """Manager answer covers part of the reference fact."""

    score: float = 0.0
    """Normalised 0.0 (fully wrong) → 1.0 (fully equivalent)."""

    missing: list[str] = field(default_factory=list)
    """Short phrases describing what the manager did NOT cover."""

    reason: str = ""
    """One-sentence Russian explanation for UI feedback."""


_PROMPT_TEMPLATE = (
    "Ты — строгий экзаменатор по 127-ФЗ. Оцени, является ли ответ менеджера "
    "семантически эквивалентным эталону ИЛИ охватывает ли часть эталона.\n\n"
    "Учитывай синонимы: «субсидиарка» ≈ «субсидиарная ответственность», "
    "«финуправляющий» ≈ «финансовый управляющий», «мфц» ≈ «внесудебное банкротство», "
    "«90 дней» ≈ «девяносто дней», «ст. 213.4» ≈ «статья 213.4».\n\n"
    "Вопрос: {question}\n"
    "Эталон: {correct}\n"
    "Ответ менеджера: {manager}\n"
    "Правовой контекст (выдержки):\n{rag_context}\n\n"
    "Верни СТРОГО JSON без префикса:\n"
    "{{\"equivalent\": true|false, \"partial\": true|false, "
    "\"score\": 0.0..1.0, \"missing\": [\"…\"], \"reason\": \"1 предложение\"}}"
)


def _fast_accept(
    correct_answer: str, manager_answer: str,
) -> ValidationResult | None:
    """Cheap pre-pass: if normalized forms contain each other, skip LLM.

    This catches the common case of "ст. 213.4" ≈ "статья 213.4" without
    spending tokens. Only used when normalized correct answer is short
    enough that a substring check is meaningful (<= 160 chars).
    """

    nc = normalize_for_comparison(correct_answer)
    nm = normalize_for_comparison(manager_answer)
    if not nc or not nm:
        return None
    if len(nc) > 160:
        return None  # too long for substring heuristic

    if nm == nc or nm in nc or nc in nm:
        score = 1.0 if nm == nc else 0.85
        return ValidationResult(
            equivalent=True,
            partial=False,
            score=score,
            missing=[],
            reason=(
                "Ответ совпадает с эталоном после нормализации синонимов и "
                "форматов (цифры, сокращения статей)."
            ),
        )
    return None


async def validate_semantic(
    *,
    question: str,
    correct_answer: str,
    manager_answer: str,
    rag_context: str = "",
) -> ValidationResult:
    """Run the second-opinion validator. Returns ``skipped=True`` when off.

    The manager answer is stripped to a hard cap of 500 chars; the RAG
    context is clipped to 1500 chars so the overall prompt stays under
    2k tokens (cheap-model budget).
    """

    if not getattr(settings, "rollout_relaxed_validation", False):
        return ValidationResult(skipped=True)

    if not manager_answer or not correct_answer:
        return ValidationResult(skipped=False)

    # Fast accept path — skip LLM entirely if normalised forms match.
    fast = _fast_accept(correct_answer, manager_answer)
    if fast is not None:
        logger.debug("validator_v2: fast_accept hit (score=%.2f)", fast.score)
        return fast

    # Trim inputs to reasonable bounds.
    q = (question or "")[:500]
    c = correct_answer[:500]
    m = manager_answer[:500]
    r = (rag_context or "")[:1500]

    prompt = _PROMPT_TEMPLATE.format(question=q, correct=c, manager=m, rag_context=r)

    try:
        from app.services.llm import generate_response, LLMResponse

        resp: LLMResponse = await generate_response(
            system_prompt=prompt,
            messages=[{"role": "user", "content": "Оцени ответ."}],
            task_type="judge",
            prefer_provider="cloud",
            max_tokens=220,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("validator_v2: LLM call failed: %s", exc)
        return ValidationResult(skipped=False, reason="LLM недоступен")

    return _parse_response(resp.content if resp else "")


def _parse_response(raw: str) -> ValidationResult:
    """Parse the JSON body from the LLM; tolerate extra text around it."""

    if not raw or not raw.strip():
        return ValidationResult(skipped=False, reason="Пустой ответ LLM")

    # Tolerate ``{"…"} trailing commentary`` — slice first balanced object.
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return ValidationResult(skipped=False, reason="Не JSON")

    try:
        payload = json.loads(raw[start : end + 1])
    except json.JSONDecodeError as exc:
        logger.debug("validator_v2: json parse failed (%s): %r", exc, raw[:200])
        return ValidationResult(skipped=False, reason="Ошибка парсинга")

    try:
        equivalent = bool(payload.get("equivalent", False))
        partial = bool(payload.get("partial", False))
        score = max(0.0, min(1.0, float(payload.get("score", 0.0))))
        missing = [str(m)[:80] for m in payload.get("missing") or []][:6]
        reason = str(payload.get("reason") or "")[:280]
    except (TypeError, ValueError) as exc:
        logger.debug("validator_v2: malformed payload: %s", exc)
        return ValidationResult(skipped=False, reason="Некорректная структура")

    return ValidationResult(
        equivalent=equivalent,
        partial=partial,
        score=score,
        missing=missing,
        reason=reason,
    )


def apply_upgrade(
    *,
    primary_is_correct: bool,
    primary_score_delta: float,
    validation: ValidationResult,
) -> tuple[bool, float, str | None]:
    """Decide final verdict given the primary judge and validator v2.

    Returns ``(is_correct, score_delta, upgrade_note)``.

    Only the "false → upgrade" direction is allowed — the v2 validator
    cannot turn a true into false. This keeps the strict guard-rails of
    RULE 1/3/5 in charge for clearly-wrong answers.
    """

    if validation.skipped:
        return primary_is_correct, primary_score_delta, None

    if primary_is_correct:
        return primary_is_correct, primary_score_delta, None

    if validation.equivalent:
        # Upgrade to full correct. Use a positive score baseline; caller
        # re-applies difficulty weighting if needed.
        return True, max(primary_score_delta, 6.0), (
            "Ответ признан эквивалентным эталону после проверки синонимов."
        )

    if validation.partial and validation.score >= 0.4:
        # Promote penalty into partial credit. Baseline 0.5× correct.
        new_delta = max(primary_score_delta, 3.0)
        miss = ", ".join(validation.missing[:3]) if validation.missing else ""
        note = (
            f"Засчитан как частичный ответ ({int(validation.score * 100)}%)."
            + (f" Упущено: {miss}." if miss else "")
        )
        return False, new_delta, note

    return primary_is_correct, primary_score_delta, None
