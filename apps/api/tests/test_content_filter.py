"""Tests for the content filter (services/content_filter.py).

Covers profanity filtering, length limits, and normal text passthrough.
"""

import pytest

from app.services.content_filter import (
    filter_answer_text,
    MAX_ANSWER_LENGTH,
)


# ---------------------------------------------------------------------------
# Normal text passthrough
# ---------------------------------------------------------------------------

class TestNormalText:
    """Normal text passes through unmodified."""

    def test_simple_text(self):
        text = "Банкротство регулируется 127-ФЗ"
        filtered, was_filtered = filter_answer_text(text)
        assert filtered == text
        assert was_filtered is False

    def test_empty_string(self):
        filtered, was_filtered = filter_answer_text("")
        assert filtered == ""
        assert was_filtered is False

    def test_numbers_and_symbols(self):
        text = "Ставка 5.5% годовых, сумма 1 000 000 руб."
        filtered, was_filtered = filter_answer_text(text)
        assert filtered == text
        assert was_filtered is False

    def test_english_text(self):
        text = "The bankruptcy law protects debtors"
        filtered, was_filtered = filter_answer_text(text)
        assert filtered == text
        assert was_filtered is False


# ---------------------------------------------------------------------------
# Profanity filtering
# ---------------------------------------------------------------------------

class TestProfanityFiltering:
    """Profanity is replaced with ***."""

    def test_filtered_text_contains_asterisks(self):
        """We only check that profanity IS filtered, not test specific words."""
        # Use a pattern that matches the regex: хуй
        text = "это хуйня какая-то"
        filtered, was_filtered = filter_answer_text(text)
        assert was_filtered is True
        assert "***" in filtered

    def test_mixed_case_filtered(self):
        """Case-insensitive filtering."""
        text = "Это БЛЯТЬ невозможно"
        filtered, was_filtered = filter_answer_text(text)
        assert was_filtered is True
        assert "***" in filtered

    def test_clean_text_not_filtered(self):
        text = "Процедура банкротства длится от 6 месяцев"
        _, was_filtered = filter_answer_text(text)
        assert was_filtered is False


# ---------------------------------------------------------------------------
# Length limits
# ---------------------------------------------------------------------------

class TestLengthLimits:
    """Text exceeding MAX_ANSWER_LENGTH is truncated."""

    def test_short_text_not_truncated(self):
        text = "A" * 100
        filtered, was_filtered = filter_answer_text(text)
        assert len(filtered) == 100
        assert was_filtered is False

    def test_exact_max_not_truncated(self):
        text = "A" * MAX_ANSWER_LENGTH
        filtered, was_filtered = filter_answer_text(text)
        assert len(filtered) == MAX_ANSWER_LENGTH
        assert was_filtered is False

    def test_over_max_truncated(self):
        text = "A" * (MAX_ANSWER_LENGTH + 100)
        filtered, was_filtered = filter_answer_text(text)
        assert was_filtered is True
        assert len(filtered) == MAX_ANSWER_LENGTH + 3  # + "..."
        assert filtered.endswith("...")

    def test_max_answer_length_is_1000(self):
        assert MAX_ANSWER_LENGTH == 1000
