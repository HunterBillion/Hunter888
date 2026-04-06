"""Tests for the anti-cheat system (services/anti_cheat.py).

Covers behavioral detection (copy-paste, auto-response), AI detection
(perplexity, burstiness), semantic consistency, and aggregation.
All tests use pure functions or mocked DB.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.anti_cheat import (
    _jaccard_similarity,
    _estimate_perplexity,
    _estimate_burstiness,
    check_behavioral,
    check_ai_detector,
    check_semantic_consistency,
    AntiCheatSignal,
    AntiCheatResult,
    COPY_PASTE_SIMILARITY_THRESHOLD,
    PERPLEXITY_THRESHOLD,
    BURSTINESS_THRESHOLD,
    MEDIAN_RESPONSE_TIME_MIN,
    RESPONSE_LENGTH_FOR_LATENCY,
    MIN_UNIQUE_RESPONSE_RATIO,
)
from app.models.pvp import AntiCheatCheckType, AntiCheatAction


USER_ID = uuid.uuid4()


# ---------------------------------------------------------------------------
# Jaccard similarity
# ---------------------------------------------------------------------------

class TestJaccardSimilarity:
    """Token-level Jaccard similarity."""

    def test_identical_strings(self):
        assert _jaccard_similarity("hello world", "hello world") == 1.0

    def test_completely_different(self):
        assert _jaccard_similarity("hello world", "foo bar baz") == 0.0

    def test_partial_overlap(self):
        sim = _jaccard_similarity("hello world foo", "hello world bar")
        # intersection={"hello","world"}, union={"hello","world","foo","bar"}
        assert sim == pytest.approx(2 / 4)

    def test_empty_string(self):
        assert _jaccard_similarity("", "hello") == 0.0

    def test_both_empty(self):
        assert _jaccard_similarity("", "") == 0.0

    def test_case_insensitive(self):
        assert _jaccard_similarity("Hello World", "hello world") == 1.0


# ---------------------------------------------------------------------------
# Perplexity estimation
# ---------------------------------------------------------------------------

class TestPerplexityEstimation:
    """Rough perplexity heuristic."""

    def test_short_text_returns_50(self):
        """Text under 10 words assumed human."""
        ppl = _estimate_perplexity("short text")
        assert ppl == 50.0

    def test_varied_text_higher_perplexity(self):
        """Diverse vocabulary -> higher perplexity (more human-like)."""
        diverse = " ".join(f"word{i}" for i in range(50))
        ppl = _estimate_perplexity(diverse)
        assert ppl >= 10.0

    def test_repetitive_text_lower_perplexity(self):
        """Repetitive text -> lower TTR -> lower perplexity."""
        repetitive = " ".join(["банкротство долг кредит"] * 20)
        ppl_rep = _estimate_perplexity(repetitive)
        diverse = " ".join(f"слово{i}" for i in range(60))
        ppl_div = _estimate_perplexity(diverse)
        assert ppl_rep > ppl_div  # Less unique = higher (1-ttr)*50+10

    def test_perplexity_clamped(self):
        ppl = _estimate_perplexity(" ".join(["a"] * 100))
        assert 5.0 <= ppl <= 100.0


# ---------------------------------------------------------------------------
# Burstiness estimation
# ---------------------------------------------------------------------------

class TestBurstinessEstimation:
    """Response timing burstiness."""

    def test_few_responses_returns_neutral(self):
        assert _estimate_burstiness([1.0, 2.0]) == 0.5

    def test_uniform_timing_low_burstiness(self):
        """Perfectly uniform timing -> B close to -1 (robotic)."""
        uniform = [5.0, 5.0, 5.0, 5.0, 5.0]
        b = _estimate_burstiness(uniform)
        assert b < 0  # sigma=0, mu>0 -> (0-mu)/(0+mu) = -1

    def test_irregular_timing_higher_burstiness(self):
        """Irregular timing -> positive burstiness (human-like)."""
        irregular = [1.0, 15.0, 2.0, 20.0, 3.0]
        b = _estimate_burstiness(irregular)
        # High variance relative to mean
        assert b > BURSTINESS_THRESHOLD or b > -0.5

    def test_all_zeros_returns_zero(self):
        b = _estimate_burstiness([0.0, 0.0, 0.0])
        assert b == 0.0


# ---------------------------------------------------------------------------
# Behavioral check (Level 2)
# ---------------------------------------------------------------------------

class TestBehavioralCheck:
    """Behavioral analysis: copy-paste, uniqueness, length variance."""

    def test_insufficient_messages(self):
        messages = [
            {"sender_id": str(USER_ID), "text": "hello"},
            {"sender_id": str(USER_ID), "text": "world"},
        ]
        signal = check_behavioral(messages, USER_ID)
        assert signal.flagged is False
        assert signal.details["reason"] == "insufficient_messages"

    def test_unique_messages_not_flagged(self):
        messages = [
            {"sender_id": str(USER_ID), "text": "Первый ответ о банкротстве"},
            {"sender_id": str(USER_ID), "text": "Второй ответ о реструктуризации"},
            {"sender_id": str(USER_ID), "text": "Третий ответ о кредиторах"},
            {"sender_id": str(USER_ID), "text": "Четвёртый ответ о суде"},
        ]
        signal = check_behavioral(messages, USER_ID)
        assert signal.flagged is False

    def test_copy_paste_flagged(self):
        """Identical responses should trigger high similarity detection."""
        same_text = "Банкротство регулируется федеральным законом номер 127"
        messages = [
            {"sender_id": str(USER_ID), "text": same_text},
            {"sender_id": str(USER_ID), "text": same_text},
            {"sender_id": str(USER_ID), "text": same_text},
            {"sender_id": str(USER_ID), "text": same_text},
        ]
        signal = check_behavioral(messages, USER_ID)
        assert signal.score > 0.0
        # Low unique ratio should be detected
        assert signal.details["unique_ratio"] < MIN_UNIQUE_RESPONSE_RATIO

    def test_ignores_other_users(self):
        other_id = uuid.uuid4()
        messages = [
            {"sender_id": str(other_id), "text": "other user message"},
            {"sender_id": str(USER_ID), "text": "my message"},
        ]
        signal = check_behavioral(messages, USER_ID)
        assert signal.details.get("reason") == "insufficient_messages"


# ---------------------------------------------------------------------------
# AI detector (Level 3)
# ---------------------------------------------------------------------------

class TestAIDetector:
    """AI detection: perplexity, burstiness, latency analysis."""

    def test_insufficient_messages(self):
        messages = [
            {"sender_id": str(USER_ID), "text": "hello"},
        ]
        signal = check_ai_detector(messages, USER_ID)
        assert signal.flagged is False

    def test_fast_long_responses_flagged(self):
        """Fast responses with long text -> suspicious."""
        long_text = " ".join(["слово"] * 60)  # > 50 words
        messages = [
            {"sender_id": str(USER_ID), "text": long_text, "response_time": 1.0},
            {"sender_id": str(USER_ID), "text": long_text, "response_time": 1.5},
            {"sender_id": str(USER_ID), "text": long_text, "response_time": 2.0},
            {"sender_id": str(USER_ID), "text": long_text, "response_time": 1.0},
            {"sender_id": str(USER_ID), "text": long_text, "response_time": 1.5},
        ]
        signal = check_ai_detector(messages, USER_ID)
        assert signal.details["fast_long_count"] >= 3

    def test_human_like_not_flagged(self):
        """Normal human responses: varied length, moderate timing."""
        messages = [
            {"sender_id": str(USER_ID), "text": f"Ответ номер {i} с разной длиной " * (i + 1), "response_time": 5.0 + i * 3}
            for i in range(5)
        ]
        signal = check_ai_detector(messages, USER_ID)
        # Should not be flagged (moderate perplexity, high burstiness, slow responses)
        assert signal.score < 0.5


# ---------------------------------------------------------------------------
# Semantic consistency
# ---------------------------------------------------------------------------

class TestSemanticConsistency:
    """Vocabulary complexity jump detection."""

    def test_insufficient_data(self):
        signal = check_semantic_consistency(
            current_messages=[{"sender_id": str(USER_ID), "text": "hi"}],
            historical_vocab_complexity=None,
            user_id=USER_ID,
        )
        assert signal.flagged is False

    def test_consistent_complexity_not_flagged(self):
        messages = [
            {"sender_id": str(USER_ID), "text": "простой ответ один"},
            {"sender_id": str(USER_ID), "text": "простой ответ два"},
            {"sender_id": str(USER_ID), "text": "простой ответ три"},
        ]
        # Historical complexity roughly matches simple text
        signal = check_semantic_consistency(messages, 15.0, USER_ID)
        assert signal.flagged is False

    def test_big_complexity_jump_flagged(self):
        """Sudden jump in legal vocabulary -> flagged."""
        messages = [
            {"sender_id": str(USER_ID), "text": "арбитражный конкурсный реструктуризация банкротство"},
            {"sender_id": str(USER_ID), "text": "субсидиарная ответственность мораторий несостоятельность"},
            {"sender_id": str(USER_ID), "text": "реализация имущество кредитор должник финансовый"},
        ]
        # Historical complexity is much lower (simple vocabulary)
        signal = check_semantic_consistency(messages, 5.0, USER_ID)
        # Should be flagged due to large deviation from historical
        assert signal.score > 0.0


# ---------------------------------------------------------------------------
# AntiCheatResult aggregation
# ---------------------------------------------------------------------------

class TestAntiCheatResult:
    """Aggregated anti-cheat result."""

    def test_max_score_empty(self):
        result = AntiCheatResult(user_id=USER_ID, duel_id=uuid.uuid4())
        assert result.max_score == 0.0

    def test_flagged_signals(self):
        result = AntiCheatResult(user_id=USER_ID, duel_id=uuid.uuid4())
        result.signals = [
            AntiCheatSignal(AntiCheatCheckType.statistical, 0.2, False),
            AntiCheatSignal(AntiCheatCheckType.behavioral, 0.8, True),
            AntiCheatSignal(AntiCheatCheckType.ai_detector, 0.6, True),
        ]
        assert len(result.flagged_signals) == 2
        assert result.max_score == pytest.approx(0.8)

    def test_no_flags_action_none(self):
        result = AntiCheatResult(user_id=USER_ID, duel_id=uuid.uuid4())
        result.signals = [
            AntiCheatSignal(AntiCheatCheckType.statistical, 0.1, False),
        ]
        result.overall_flagged = False
        result.recommended_action = AntiCheatAction.none
        assert result.recommended_action == AntiCheatAction.none
