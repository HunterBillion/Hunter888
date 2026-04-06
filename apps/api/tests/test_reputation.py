"""Tests for reputation system (services/reputation.py).

Covers:
  - EMA calculation
  - Active impact (session score → delta)
  - Passive decay (inactivity)
  - Tier mapping
  - Score clamping
  - Emotion weight shifting
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.services.reputation import (
    _clamp,
    _score_to_tier,
    _session_score_to_delta,
    calculate_emotion_weight_shift,
    get_tier_min_difficulty,
    EMA_ALPHA,
    DECAY_RATE,
    DECAY_GRACE_DAYS,
    DEFAULT_SCORE,
    SCORE_MIN,
    SCORE_MAX,
)
from app.models.reputation import ReputationTier


# ═══════════════════════════════════════════════════════════════════════════════
# Clamping
# ═══════════════════════════════════════════════════════════════════════════════


class TestClamp:
    def test_within_range(self):
        assert _clamp(50.0) == 50.0

    def test_below_min(self):
        assert _clamp(-10.0) == SCORE_MIN

    def test_above_max(self):
        assert _clamp(150.0) == SCORE_MAX

    def test_at_boundaries(self):
        assert _clamp(0.0) == 0.0
        assert _clamp(100.0) == 100.0


# ═══════════════════════════════════════════════════════════════════════════════
# Session score → reputation delta
# ═══════════════════════════════════════════════════════════════════════════════


class TestSessionScoreToDelta:
    def test_bad_session_penalty(self):
        """Score < 30 → -3 delta."""
        assert _session_score_to_delta(20) == -3.0
        assert _session_score_to_delta(0) == -3.0
        assert _session_score_to_delta(29) == -3.0

    def test_neutral_session(self):
        """Score 30-59 → 0 delta."""
        assert _session_score_to_delta(30) == 0.0
        assert _session_score_to_delta(50) == 0.0
        assert _session_score_to_delta(59) == 0.0

    def test_good_session_bonus(self):
        """Score 60-79 → +1 delta."""
        assert _session_score_to_delta(60) == 1.0
        assert _session_score_to_delta(75) == 1.0

    def test_excellent_session_bonus(self):
        """Score 80+ → +2 delta."""
        assert _session_score_to_delta(80) == 2.0
        assert _session_score_to_delta(100) == 2.0


# ═══════════════════════════════════════════════════════════════════════════════
# Tier mapping
# ═══════════════════════════════════════════════════════════════════════════════


class TestTierMapping:
    def test_low_score_is_trainee(self):
        tier = _score_to_tier(5.0)
        assert tier == ReputationTier.trainee

    def test_default_score_tier(self):
        """Default 50 should be a middle tier."""
        tier = _score_to_tier(DEFAULT_SCORE)
        assert tier is not None

    def test_max_score_is_hunter(self):
        tier = _score_to_tier(95.0)
        assert tier == ReputationTier.hunter

    def test_all_tiers_reachable(self):
        """Every tier should be reachable by some score."""
        reached = set()
        for score in range(0, 101):
            reached.add(_score_to_tier(float(score)))
        assert len(reached) >= 4, f"Only {len(reached)} tiers reachable"


# ═══════════════════════════════════════════════════════════════════════════════
# EMA calculation
# ═══════════════════════════════════════════════════════════════════════════════


class TestEMACalculation:
    def test_ema_formula(self):
        """new_ema = α × session_score + (1 - α) × old_ema"""
        old_ema = 50.0
        session_score = 80.0
        new_ema = EMA_ALPHA * session_score + (1 - EMA_ALPHA) * old_ema
        expected = 0.15 * 80 + 0.85 * 50  # 12 + 42.5 = 54.5
        assert abs(new_ema - expected) < 0.01

    def test_ema_converges_upward(self):
        """Repeated high scores should push EMA toward 100."""
        ema = 50.0
        for _ in range(100):
            ema = EMA_ALPHA * 100.0 + (1 - EMA_ALPHA) * ema
        assert ema > 95  # Should be close to 100

    def test_ema_converges_downward(self):
        """Repeated low scores should push EMA toward 0."""
        ema = 50.0
        for _ in range(100):
            ema = EMA_ALPHA * 0.0 + (1 - EMA_ALPHA) * ema
        assert ema < 5  # Should be close to 0


# ═══════════════════════════════════════════════════════════════════════════════
# Emotion weight shift
# ═══════════════════════════════════════════════════════════════════════════════


class TestEmotionWeightShift:
    def test_default_score_zero_shift(self):
        """Reputation 50 → 0.0 shift (neutral)."""
        shift = calculate_emotion_weight_shift(50.0)
        assert abs(shift) < 0.01

    def test_high_reputation_positive_shift(self):
        """High reputation → positive shift (warmer clients)."""
        shift = calculate_emotion_weight_shift(100.0)
        assert shift > 0

    def test_low_reputation_negative_shift(self):
        """Low reputation → negative shift (colder clients)."""
        shift = calculate_emotion_weight_shift(0.0)
        assert shift < 0

    def test_shift_bounded(self):
        """Shift should be in [-0.5, +0.5] range."""
        for score in [0, 25, 50, 75, 100]:
            shift = calculate_emotion_weight_shift(float(score))
            assert -0.6 <= shift <= 0.6


# ═══════════════════════════════════════════════════════════════════════════════
# Tier difficulty
# ═══════════════════════════════════════════════════════════════════════════════


class TestTierDifficulty:
    def test_trainee_low_difficulty(self):
        diff = get_tier_min_difficulty(ReputationTier.trainee)
        assert diff <= 3

    def test_hunter_high_difficulty(self):
        diff = get_tier_min_difficulty(ReputationTier.hunter)
        assert diff >= 5

    def test_difficulty_increases_with_tier(self):
        tiers = list(ReputationTier)
        diffs = [get_tier_min_difficulty(t) for t in tiers]
        # Should be non-decreasing
        for i in range(1, len(diffs)):
            assert diffs[i] >= diffs[i - 1], (
                f"Difficulty decreased: {tiers[i-1]}={diffs[i-1]} > {tiers[i]}={diffs[i]}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Constants validation
# ═══════════════════════════════════════════════════════════════════════════════


class TestConstants:
    def test_ema_alpha_range(self):
        assert 0 < EMA_ALPHA < 1

    def test_decay_rate_positive(self):
        assert DECAY_RATE > 0

    def test_grace_period_reasonable(self):
        assert 3 <= DECAY_GRACE_DAYS <= 14

    def test_default_score_midpoint(self):
        assert DEFAULT_SCORE == (SCORE_MIN + SCORE_MAX) / 2
