"""Tests for Glicko-2 rating system (services/glicko2.py).

Covers:
  - Glicko-2 scale conversions
  - Rating calculation (win/loss/draw)
  - PvE multiplier
  - Placement acceleration
  - Rating clamping (0-3000)
  - RD decay for inactivity
  - Helper functions (_g, _E, variance, delta)
"""

import math
from datetime import datetime, timedelta, timezone

import pytest

from app.services.glicko2 import (
    calculate_glicko2,
    apply_rd_decay,
    _to_glicko2,
    _from_glicko2,
    _g,
    _E,
    DEFAULT_RATING,
    DEFAULT_RD,
    DEFAULT_VOL,
    MIN_RD,
    MAX_RD,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Scale conversions
# ═══════════════════════════════════════════════════════════════════════════════


class TestScaleConversions:
    def test_roundtrip(self):
        """Converting to Glicko-2 and back should give original values."""
        mu, phi = _to_glicko2(1500, 200)
        rating, rd = _from_glicko2(mu, phi)
        assert abs(rating - 1500) < 0.01
        assert abs(rd - 200) < 0.01

    def test_default_rating_converts(self):
        mu, phi = _to_glicko2(DEFAULT_RATING, DEFAULT_RD)
        assert isinstance(mu, float)
        assert isinstance(phi, float)

    def test_high_rating_converts(self):
        mu, phi = _to_glicko2(2500, 50)
        rating, rd = _from_glicko2(mu, phi)
        assert abs(rating - 2500) < 0.01


# ═══════════════════════════════════════════════════════════════════════════════
# Helper functions
# ═══════════════════════════════════════════════════════════════════════════════


class TestHelperFunctions:
    def test_g_decreases_with_phi(self):
        """_g(phi) should decrease as phi increases (more uncertainty = less weight)."""
        g_low = _g(0.5)
        g_high = _g(2.0)
        assert g_low > g_high

    def test_g_is_positive(self):
        assert _g(1.0) > 0

    def test_E_returns_probability(self):
        """Expected score should be between 0 and 1."""
        e = _E(0.0, 0.0, 1.0)
        assert 0 <= e <= 1

    def test_E_equal_players(self):
        """Equal players should have E ≈ 0.5."""
        e = _E(0.0, 0.0, 1.0)
        assert abs(e - 0.5) < 0.01

    def test_E_stronger_player(self):
        """Higher-rated player should have E > 0.5."""
        e = _E(2.0, 0.0, 1.0)
        assert e > 0.5

    def test_E_weaker_player(self):
        """Lower-rated player should have E < 0.5."""
        e = _E(-2.0, 0.0, 1.0)
        assert e < 0.5


# ═══════════════════════════════════════════════════════════════════════════════
# Rating calculation
# ═══════════════════════════════════════════════════════════════════════════════


class TestCalculateGlicko2:
    def test_win_increases_rating(self):
        new_r, new_rd, new_v = calculate_glicko2(
            rating=1500, rd=200, volatility=DEFAULT_VOL,
            opponent_rating=1500, opponent_rd=200, score=1.0,
        )
        assert new_r > 1500

    def test_loss_decreases_rating(self):
        new_r, new_rd, new_v = calculate_glicko2(
            rating=1500, rd=200, volatility=DEFAULT_VOL,
            opponent_rating=1500, opponent_rd=200, score=0.0,
        )
        assert new_r < 1500

    def test_draw_against_equal(self):
        """Draw against equal opponent: minimal change."""
        new_r, new_rd, new_v = calculate_glicko2(
            rating=1500, rd=200, volatility=DEFAULT_VOL,
            opponent_rating=1500, opponent_rd=200, score=0.5,
        )
        assert abs(new_r - 1500) < 50  # Small change

    def test_win_against_stronger_gives_more(self):
        """Beating a stronger opponent should give more rating."""
        r_vs_equal, _, _ = calculate_glicko2(
            1500, 200, DEFAULT_VOL, 1500, 200, 1.0,
        )
        r_vs_strong, _, _ = calculate_glicko2(
            1500, 200, DEFAULT_VOL, 2000, 200, 1.0,
        )
        assert (r_vs_strong - 1500) > (r_vs_equal - 1500)

    def test_rd_decreases_after_game(self):
        """RD should decrease (more certainty) after playing."""
        _, new_rd, _ = calculate_glicko2(
            1500, 200, DEFAULT_VOL, 1500, 200, 1.0,
        )
        assert new_rd < 200

    def test_rating_clamped_at_zero(self):
        """Rating should never go below 0."""
        new_r, _, _ = calculate_glicko2(
            100, 50, DEFAULT_VOL, 3000, 50, 0.0,
        )
        assert new_r >= 0

    def test_rating_clamped_at_3000(self):
        """Rating should never exceed 3000."""
        new_r, _, _ = calculate_glicko2(
            2900, 50, DEFAULT_VOL, 100, 50, 1.0,
        )
        assert new_r <= 3000

    def test_rd_clamped_within_bounds(self):
        _, new_rd, _ = calculate_glicko2(
            1500, 200, DEFAULT_VOL, 1500, 200, 1.0,
        )
        assert MIN_RD <= new_rd <= MAX_RD

    def test_pve_half_rating_change(self):
        """PvE games should give only 50% rating change."""
        r_pvp, _, _ = calculate_glicko2(
            1500, 200, DEFAULT_VOL, 1500, 200, 1.0, is_pve=False,
        )
        r_pve, _, _ = calculate_glicko2(
            1500, 200, DEFAULT_VOL, 1500, 200, 1.0, is_pve=True,
        )
        pvp_delta = r_pvp - 1500
        pve_delta = r_pve - 1500
        assert abs(pve_delta - pvp_delta * 0.5) < 5  # ~50% with rounding

    def test_placement_faster_rd_decrease(self):
        """Placement games should decrease RD faster."""
        _, rd_normal, _ = calculate_glicko2(
            1500, 200, DEFAULT_VOL, 1500, 200, 1.0, is_placement=False,
        )
        _, rd_placement, _ = calculate_glicko2(
            1500, 200, DEFAULT_VOL, 1500, 200, 1.0, is_placement=True,
        )
        assert rd_placement < rd_normal

    def test_volatility_stays_positive(self):
        _, _, new_v = calculate_glicko2(
            1500, 200, DEFAULT_VOL, 1500, 200, 1.0,
        )
        assert new_v > 0

    def test_symmetric_win_loss(self):
        """Winner gains ≈ what loser loses (for equal opponents)."""
        r_win, _, _ = calculate_glicko2(1500, 200, DEFAULT_VOL, 1500, 200, 1.0)
        r_loss, _, _ = calculate_glicko2(1500, 200, DEFAULT_VOL, 1500, 200, 0.0)
        win_delta = r_win - 1500
        loss_delta = 1500 - r_loss
        # Should be approximately equal (not exact due to clamping)
        assert abs(win_delta - loss_delta) < 10


# ═══════════════════════════════════════════════════════════════════════════════
# RD decay
# ═══════════════════════════════════════════════════════════════════════════════


class TestRDDecay:
    def test_no_decay_under_one_week(self):
        last_played = datetime.now(timezone.utc) - timedelta(days=3)
        new_rd = apply_rd_decay(100, last_played)
        assert new_rd == 100

    def test_decay_after_one_week(self):
        last_played = datetime.now(timezone.utc) - timedelta(weeks=2)
        new_rd = apply_rd_decay(100, last_played)
        assert new_rd > 100

    def test_decay_capped_at_max_rd(self):
        last_played = datetime.now(timezone.utc) - timedelta(weeks=52)
        new_rd = apply_rd_decay(100, last_played)
        assert new_rd <= MAX_RD

    def test_no_decay_if_never_played(self):
        new_rd = apply_rd_decay(200, None)
        assert new_rd == 200


# ═══════════════════════════════════════════════════════════════════════════════
# Default values
# ═══════════════════════════════════════════════════════════════════════════════


class TestDefaults:
    def test_default_rating_is_1500(self):
        assert DEFAULT_RATING == 1500

    def test_default_rd_is_reasonable(self):
        assert 200 <= DEFAULT_RD <= 400

    def test_default_volatility_is_small(self):
        assert 0 < DEFAULT_VOL < 0.1
