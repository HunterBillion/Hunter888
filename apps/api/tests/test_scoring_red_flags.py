"""Regression tests for the BUG B3 scoring red-flag additions.

We test the two new behaviours in `scoring._score_anti_patterns` without
spinning up a full session:

1. The `disrespect_to_client` category appears in `category_penalties`
   with a heavier weight than the misleading-client categories.
2. The zero-open-questions penalty fires when a 4+ turn user transcript
   has no open-ended question.

The detection itself (which calls `_llm_batch_similarity` against the
`disrespect_to_client` phrase list) is exercised by `script_checker`'s
own tests; here we lock the SCORING rules so a future weights tweak
can't silently regress this surface.
"""
from __future__ import annotations

import asyncio
import re

import pytest

from app.services import scoring


def test_disrespect_to_client_in_category_penalties() -> None:
    """The category exists with a -7.0 weight (heavier than the other -5.0
    misleading-client categories). If this changes, write a new test
    case for the user-visible behaviour you intend to enable."""
    # Re-execute the scoring layer literal — the only sane way to read
    # an inline dict without exposing private state.
    src = open(scoring.__file__).read()
    assert '"disrespect_to_client": -7.0' in src, (
        "disrespect_to_client weight changed — write a new test case for "
        "the user-visible behaviour you intend before adjusting"
    )


def test_zero_open_q_regex_matches_real_examples() -> None:
    """The regex used inside _score_anti_patterns must catch the kinds
    of open-ended questions managers should ask. Pinning a few real
    examples keeps the regex honest if someone tweaks it."""
    src = open(scoring.__file__).read()
    # Extract the exact regex literal — guards against accidental edit.
    m = re.search(r"_OPEN_Q_RE = re\.compile\(\s*r\"([^\"]+)\"", src)
    assert m, "could not locate _OPEN_Q_RE in scoring.py"
    pattern = re.compile(m.group(1), flags=re.IGNORECASE)

    must_match = [
        "Какая у вас сейчас ситуация",
        "Расскажите о своих долгах",
        "Сколько у вас кредиторов?",
        "Как давно проблема",
        "Почему именно сейчас обратились",
        "В чём основная сложность",
    ]
    for q in must_match:
        assert pattern.search(q), f"open-Q regex must match: {q!r}"

    must_not_match = [
        "Понятно",
        "Хорошо",
        "Я готов помочь",
        "Это серьёзный вопрос",  # noun "вопрос", no interrogative
    ]
    for s in must_not_match:
        assert not pattern.search(s), f"open-Q regex must NOT match: {s!r}"


@pytest.mark.asyncio
async def test_zero_open_q_penalty_fires_on_long_session_without_questions(monkeypatch) -> None:
    """End-to-end through _score_anti_patterns with a stubbed
    detect_anti_patterns (so the LLM embeddings call is bypassed).
    Asserts the zero_open_questions detection appears in the breakdown."""
    async def _no_anti(text: str) -> list[dict]:
        return []  # no anti-patterns detected → only zero-OQ branch matters
    monkeypatch.setattr(scoring, "detect_anti_patterns", _no_anti)

    user_msgs = [
        "Здравствуйте, это Иван из БФЛ.",
        "У нас есть услуга списания долгов.",
        "Многим клиентам помогли.",
        "Заходите к нам.",
        "Согласны?",   # closed question, doesn't count
    ]
    penalty, details = await scoring._score_anti_patterns(user_msgs, [], {})
    cats = [d.get("category") for d in details.get("detected", [])]
    assert "zero_open_questions" in cats, f"expected zero_open_questions in {cats}"
    assert penalty < 0


@pytest.mark.asyncio
async def test_zero_open_q_penalty_does_not_fire_when_question_exists(monkeypatch) -> None:
    async def _no_anti(text: str) -> list[dict]:
        return []
    monkeypatch.setattr(scoring, "detect_anti_patterns", _no_anti)

    user_msgs = [
        "Здравствуйте.",
        "Расскажите, какая у вас сейчас ситуация с долгами?",
        "Понятно.",
        "Сколько у вас кредиторов?",
    ]
    penalty, details = await scoring._score_anti_patterns(user_msgs, [], {})
    cats = [d.get("category") for d in details.get("detected", [])]
    assert "zero_open_questions" not in cats, f"unexpected zero_open_questions in {cats}"


@pytest.mark.asyncio
async def test_zero_open_q_does_not_fire_for_short_session(monkeypatch) -> None:
    """Short sessions (<4 turns) shouldn't be punished for not having
    asked an open question yet — they may have ended early for other
    reasons."""
    async def _no_anti(text: str) -> list[dict]:
        return []
    monkeypatch.setattr(scoring, "detect_anti_patterns", _no_anti)

    user_msgs = ["Здравствуйте.", "Готовы?"]
    penalty, details = await scoring._score_anti_patterns(user_msgs, [], {})
    cats = [d.get("category") for d in details.get("detected", [])]
    assert "zero_open_questions" not in cats
    assert penalty == 0.0
