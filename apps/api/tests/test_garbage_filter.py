"""Regression tests for `_is_garbage_answer`.

Real-prod bug 2026-05-04: user typed "Алибек" (their own name) on a
blitz quiz question and got "✓ Верно". The threshold was `< 6 chars`,
so any 6-letter name/greeting/gibberish slipped past the filter and
hit the LLM, which then said "верно" because the prompt was lenient.

These tests pin the new threshold and the legal-marker / digit
escape hatches, so a future relax doesn't silently break the floor.
"""
from __future__ import annotations

import pytest

from app.services.knowledge_quiz import _is_garbage_answer


class TestGarbageRejection:
    """Inputs that MUST be rejected as garbage."""

    @pytest.mark.parametrize(
        "answer",
        [
            # Names — the original prod bug
            "Алибек",
            "Иван",
            "Мария",
            "Александр",  # 10 chars but no digits/legal — still garbage
            "Иван Петров",  # 11 chars but no legal markers
            # Greetings
            "Привет",
            "Здравствуй",
            "Спасибо",
            "Добрый день",  # 11 chars, no legal markers
            # Gibberish
            "аоаваов",
            "мамамама",
            "asdfasdf",
            # One-word non-answers
            "Не знаю",
            "Не уверен",
            "Возможно",
        ],
    )
    def test_rejects_short_non_legal(self, answer: str) -> None:
        is_garbage, reason = _is_garbage_answer(answer)
        assert is_garbage, f"Expected garbage for {answer!r}, got pass with reason: {reason!r}"


class TestGarbagePass:
    """Inputs that MUST pass the filter (be evaluated normally)."""

    @pytest.mark.parametrize(
        "answer",
        [
            # Has digits
            "25000 рублей",
            "5 лет",
            "300",
            # Has legal markers
            "ст. 213.4",
            "статья 61.2",
            "банкрот",  # 7 chars but legal-marker → pass
            "управляющий",
            "процедура реализации",
            "ФЗ 127",
            "кредитор",
            # Long enough (>= 12 chars)
            "это длинный ответ на вопрос",
            "абсолютно ничего конкретного",  # 28 chars — passes filter; LLM judges
        ],
    )
    def test_passes_legitimate_answers(self, answer: str) -> None:
        is_garbage, reason = _is_garbage_answer(answer)
        assert not is_garbage, f"Expected pass for {answer!r}, got rejected: {reason!r}"


class TestGarbageEdgeCases:
    """Boundary cases — empty, whitespace, control chars."""

    @pytest.mark.parametrize(
        "answer",
        [
            "",
            "   ",
            "\n\n",
            "...",
            "!!!",
        ],
    )
    def test_empty_and_punctuation_only(self, answer: str) -> None:
        is_garbage, _ = _is_garbage_answer(answer)
        assert is_garbage, f"Expected garbage for empty/punctuation-only: {answer!r}"

    def test_six_chars_no_digits_no_legal_is_garbage(self) -> None:
        """The exact boundary that broke prod 2026-05-04."""
        is_garbage, reason = _is_garbage_answer("Алибек")
        assert is_garbage
        assert "конкретик" in reason.lower() or "коротк" in reason.lower()

    def test_six_chars_with_legal_marker_passes(self) -> None:
        """Legal markers override the length floor."""
        is_garbage, _ = _is_garbage_answer("ст. 13")
        assert not is_garbage

    def test_six_chars_with_digits_passes(self) -> None:
        is_garbage, _ = _is_garbage_answer("213.4")
        assert not is_garbage
