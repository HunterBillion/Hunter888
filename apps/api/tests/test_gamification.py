"""Tests for the gamification engine (services/gamification.py).

Covers XP calculation, level progression, streak tracking,
achievement definitions, and achievement XP. All pure-function tests.
"""

import math
import uuid

import pytest

from app.services.gamification import (
    BASE_XP_PER_SESSION,
    XP_PER_SCORE_POINT,
    STREAK_BONUS_XP,
    STREAK_BONUS_CAP,
    PERFECT_SCORE_BONUS,
    RARITY_XP,
    REPEAT_EARN_MULTIPLIER,
    xp_for_level,
    level_from_xp,
    calculate_session_xp,
    calculate_achievement_xp,
)


# ═════════════════════════════════════════════════════════════════════════════
# XP for level
# ═════════════════════════════════════════════════════════════════════════════


class TestXPForLevel:
    """Total XP required to reach a given level."""

    def test_level_0_returns_zero(self):
        """Level 0 should require 0 XP."""
        assert xp_for_level(0) == 0

    def test_level_1_returns_zero(self):
        """Level 1 should require 0 XP (starting level)."""
        assert xp_for_level(1) == 0

    def test_level_2_calculated_correctly(self):
        """Level 2 XP = 100 * 2^1.5."""
        expected = int(100 * math.pow(2, 1.5))
        assert xp_for_level(2) == expected

    def test_level_10_approximately_3162(self):
        """Level 10 XP = 100 * 10^1.5 ≈ 3162."""
        expected = int(100 * math.pow(10, 1.5))
        assert xp_for_level(10) == expected
        assert expected > 3000  # Sanity check

    def test_levels_increase_monotonically(self):
        """XP requirement should increase monotonically from level 1 to 20."""
        prev = 0
        for lvl in range(1, 21):
            current = xp_for_level(lvl)
            assert current >= prev, f"Level {lvl} not monotonic"
            prev = current

    def test_negative_level(self):
        """Negative levels should return 0."""
        assert xp_for_level(-1) == 0
        assert xp_for_level(-10) == 0


# ═════════════════════════════════════════════════════════════════════════════
# Level from XP
# ═════════════════════════════════════════════════════════════════════════════


class TestLevelFromXP:
    """Calculate level from accumulated XP."""

    def test_zero_xp_gives_level_0(self):
        """0 XP should give level 0 or 1 (implementation dependent)."""
        level = level_from_xp(0)
        assert level >= 0

    def test_100_xp_gives_level_1(self):
        """100 XP should at least reach level 1."""
        level = level_from_xp(100)
        assert level >= 1

    def test_xp_at_level_threshold(self):
        """XP exactly at a level threshold should reach that level."""
        xp_needed = xp_for_level(2)
        level = level_from_xp(xp_needed)
        assert level >= 2

    def test_xp_below_level_threshold(self):
        """XP just below threshold should not reach that level."""
        xp_needed = xp_for_level(2)
        level = level_from_xp(xp_needed - 1)
        assert level < 2

    def test_large_xp_gives_high_level(self):
        """Very high XP should give high level."""
        level = level_from_xp(100000)
        assert level > 20

    def test_roundtrip_xp_for_level(self):
        """xp_for_level(N) → level_from_xp → should give N or higher."""
        for lvl in range(1, 20):
            xp = xp_for_level(lvl)
            calculated_level = level_from_xp(xp)
            assert calculated_level >= lvl


# ═════════════════════════════════════════════════════════════════════════════
# Session XP calculation
# ═════════════════════════════════════════════════════════════════════════════


class TestCalculateSessionXP:
    """XP earned from a single completed session."""

    def test_base_xp_no_score_no_streak(self):
        """Base XP with score=None and streak=0 should be BASE_XP_PER_SESSION."""
        xp = calculate_session_xp(score_total=None, streak_days=0)
        assert xp == BASE_XP_PER_SESSION

    def test_base_xp_score_zero_no_streak(self):
        """Base XP with score=0 and streak=0 should be BASE_XP_PER_SESSION."""
        xp = calculate_session_xp(score_total=0, streak_days=0)
        assert xp == BASE_XP_PER_SESSION

    def test_score_bonus_calculation(self):
        """Score 50 should add 50 * XP_PER_SCORE_POINT to base."""
        xp = calculate_session_xp(score_total=50, streak_days=0)
        expected = BASE_XP_PER_SESSION + int(50 * XP_PER_SCORE_POINT)
        assert xp == expected

    def test_high_score_bonus(self):
        """Score 80 should give significant score bonus."""
        xp = calculate_session_xp(score_total=80, streak_days=0)
        expected = BASE_XP_PER_SESSION + int(80 * XP_PER_SCORE_POINT)
        assert xp == expected
        assert xp > BASE_XP_PER_SESSION + 100

    def test_perfect_score_bonus(self):
        """Score >= 90 should include PERFECT_SCORE_BONUS."""
        xp = calculate_session_xp(score_total=95, streak_days=0)
        expected = BASE_XP_PER_SESSION + int(95 * XP_PER_SCORE_POINT) + PERFECT_SCORE_BONUS
        assert xp == expected

    def test_perfect_score_at_exactly_90(self):
        """Score exactly 90 should include PERFECT_SCORE_BONUS."""
        xp = calculate_session_xp(score_total=90, streak_days=0)
        expected = BASE_XP_PER_SESSION + int(90 * XP_PER_SCORE_POINT) + PERFECT_SCORE_BONUS
        assert xp == expected

    def test_perfect_score_not_below_90(self):
        """Score 89 should not include PERFECT_SCORE_BONUS."""
        xp = calculate_session_xp(score_total=89, streak_days=0)
        expected = BASE_XP_PER_SESSION + int(89 * XP_PER_SCORE_POINT)
        assert xp == expected

    def test_streak_bonus_basic(self):
        """Streak of 1 day should add STREAK_BONUS_XP."""
        xp = calculate_session_xp(score_total=0, streak_days=1)
        expected = BASE_XP_PER_SESSION + STREAK_BONUS_XP
        assert xp == expected

    def test_streak_bonus_multiple_days(self):
        """Streak of 5 days should add 5 * STREAK_BONUS_XP."""
        xp = calculate_session_xp(score_total=0, streak_days=5)
        expected = BASE_XP_PER_SESSION + (5 * STREAK_BONUS_XP)
        assert xp == expected

    def test_streak_bonus_capped(self):
        """Streak bonus should be capped at STREAK_BONUS_CAP."""
        xp = calculate_session_xp(score_total=0, streak_days=100)
        expected = BASE_XP_PER_SESSION + STREAK_BONUS_CAP
        assert xp == expected

    def test_streak_bonus_at_cap_boundary(self):
        """Streak that exactly hits cap should not exceed it."""
        days_for_cap = STREAK_BONUS_CAP // STREAK_BONUS_XP
        xp = calculate_session_xp(score_total=0, streak_days=days_for_cap)
        expected = BASE_XP_PER_SESSION + STREAK_BONUS_CAP
        assert xp == expected

    def test_combined_score_and_streak(self):
        """Score and streak should combine additively."""
        xp = calculate_session_xp(score_total=50, streak_days=3)
        expected = (
            BASE_XP_PER_SESSION
            + int(50 * XP_PER_SCORE_POINT)
            + (3 * STREAK_BONUS_XP)
        )
        assert xp == expected

    def test_perfect_score_with_streak(self):
        """Perfect score (>=90) with streak should combine all bonuses."""
        xp = calculate_session_xp(score_total=95, streak_days=5)
        expected = (
            BASE_XP_PER_SESSION
            + int(95 * XP_PER_SCORE_POINT)
            + PERFECT_SCORE_BONUS
            + (5 * STREAK_BONUS_XP)
        )
        assert xp == expected


# ═════════════════════════════════════════════════════════════════════════════
# Achievement XP calculation
# ═════════════════════════════════════════════════════════════════════════════


class TestCalculateAchievementXP:
    """XP bonus for earning achievements by rarity."""

    def test_common_rarity_first_earn(self):
        """Common rarity on first earn should be RARITY_XP['common']."""
        xp = calculate_achievement_xp(rarity="common", is_first_earn=True)
        assert xp == RARITY_XP["common"]
        assert xp == 50

    def test_rare_rarity_first_earn(self):
        """Rare rarity on first earn should be RARITY_XP['rare']."""
        xp = calculate_achievement_xp(rarity="rare", is_first_earn=True)
        assert xp == RARITY_XP["rare"]
        assert xp == 200

    def test_epic_rarity_first_earn(self):
        """Epic rarity on first earn should be RARITY_XP['epic']."""
        xp = calculate_achievement_xp(rarity="epic", is_first_earn=True)
        assert xp == RARITY_XP["epic"]
        assert xp == 500

    def test_legendary_rarity_first_earn(self):
        """Legendary rarity on first earn should be RARITY_XP['legendary']."""
        xp = calculate_achievement_xp(rarity="legendary", is_first_earn=True)
        assert xp == RARITY_XP["legendary"]
        assert xp == 1000

    def test_common_rarity_repeat_earn(self):
        """Common rarity on repeat should be 20% of first earn (50 * 0.2 = 10)."""
        xp = calculate_achievement_xp(rarity="common", is_first_earn=False)
        expected = int(50 * REPEAT_EARN_MULTIPLIER)
        assert xp == expected
        assert xp == 10

    def test_rare_rarity_repeat_earn(self):
        """Rare rarity on repeat should be 20% of first earn (200 * 0.2 = 40)."""
        xp = calculate_achievement_xp(rarity="rare", is_first_earn=False)
        expected = int(200 * REPEAT_EARN_MULTIPLIER)
        assert xp == expected
        assert xp == 40

    def test_epic_rarity_repeat_earn(self):
        """Epic rarity on repeat should be 20% of first earn (500 * 0.2 = 100)."""
        xp = calculate_achievement_xp(rarity="epic", is_first_earn=False)
        expected = int(500 * REPEAT_EARN_MULTIPLIER)
        assert xp == expected
        assert xp == 100

    def test_legendary_rarity_repeat_earn(self):
        """Legendary rarity on repeat should be 20% of first earn (1000 * 0.2 = 200)."""
        xp = calculate_achievement_xp(rarity="legendary", is_first_earn=False)
        expected = int(1000 * REPEAT_EARN_MULTIPLIER)
        assert xp == expected
        assert xp == 200

    def test_unknown_rarity_defaults_to_common(self):
        """Unknown rarity should fall back to common (50)."""
        xp = calculate_achievement_xp(rarity="unknown", is_first_earn=True)
        assert xp == 50

    def test_unknown_rarity_repeat_defaults(self):
        """Unknown rarity on repeat should fall back to 20% of common."""
        xp = calculate_achievement_xp(rarity="unknown", is_first_earn=False)
        expected = int(50 * REPEAT_EARN_MULTIPLIER)
        assert xp == expected
        assert xp == 10
