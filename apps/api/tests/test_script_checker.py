"""Tests for script checker: keyword similarity and constants."""

from app.services.script_checker import (
    ANTI_PATTERNS,
    SIMILARITY_THRESHOLD,
    KEYWORD_THRESHOLD,
    _keyword_similarity,
)


class TestKeywordSimilarity:
    def test_full_match(self):
        score = _keyword_similarity("кредит банк долг", ["кредит", "банк", "долг"])
        assert score == 1.0

    def test_partial_match(self):
        score = _keyword_similarity("кредит банк", ["кредит", "банк", "долг"])
        assert abs(score - 2 / 3) < 0.01

    def test_no_match(self):
        score = _keyword_similarity("погода сегодня хорошая", ["кредит", "банк"])
        assert score == 0.0

    def test_empty_keywords(self):
        score = _keyword_similarity("любой текст", [])
        assert score == 0.0

    def test_case_insensitive(self):
        score = _keyword_similarity("КРЕДИТ Банк", ["кредит", "банк"])
        assert score == 1.0


class TestConstants:
    def test_similarity_threshold(self):
        assert SIMILARITY_THRESHOLD == 0.72

    def test_keyword_threshold(self):
        assert KEYWORD_THRESHOLD == 0.3


class TestAntiPatterns:
    def test_has_required_categories(self):
        assert "false_promises" in ANTI_PATTERNS
        assert "intimidation" in ANTI_PATTERNS
        assert "incorrect_info" in ANTI_PATTERNS

    def test_each_category_has_phrases(self):
        for category, phrases in ANTI_PATTERNS.items():
            assert len(phrases) >= 3, f"{category} should have at least 3 phrases"
            for phrase in phrases:
                assert isinstance(phrase, str)
                assert len(phrase) > 5
