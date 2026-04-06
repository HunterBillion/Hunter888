"""Tests for the Glicko-2 rating system (services/glicko2.py).

Covers pure math functions: rating updates after win/loss/draw,
RD decay for inactivity, placement acceleration, PvE multiplier,
and boundary conditions.
"""

import math
from datetime import datetime, timedelta, timezone

import pytest

from app.services.glicko2 import (
    DEFAULT_RATING,
    DEFAULT_RD,
    DEFAULT_VOL,
    MAX_RD,
    MIN_RD,
    SCALE,
    RD_DECAY_PER_WEEK,
    RD_DECAY_CAP,
    PVE_RATING_MULTIPLIER,
    _to_glicko2,
    _from_glicko2,
    _g,
    _E,
    _compute_variance,
    calculate_glicko2,
    apply_rd_decay,
)


# ---------------------------------------------------------------------------
# Scale conversion
# ---------------------------------------------------------------------------

class TestScaleConversion:
    """Glicko-1 <-> Glicko-2 scale conversion."""

    def test_default_rating_converts_to_zero(self):
        mu, phi = _to_glicko2(DEFAULT_RATING, DEFAULT_RD)
        assert mu == pytest.approx(0.0)

    def test_round_trip(self):
        mu, phi = _to_glicko2(1700.0, 200.0)
        r, rd = _from_glicko2(mu, phi)
        assert r == pytest.approx(1700.0)
        assert rd == pytest.approx(200.0)

    def test_higher_rating_positive_mu(self):
        mu, _ = _to_glicko2(1700.0, DEFAULT_RD)
        assert mu > 0

    def test_lower_rating_negative_mu(self):
        mu, _ = _to_glicko2(1300.0, DEFAULT_RD)
        assert mu < 0


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

class TestHelperFunctions:
    """g() and E() functions."""

    def test_g_is_between_0_and_1(self):
        phi = DEFAULT_RD / SCALE
        val = _g(phi)
        assert 0 < val < 1

    def test_g_decreases_with_uncertainty(self):
        """More uncertain opponent has less impact."""
        g_low = _g(100 / SCALE)
        g_high = _g(350 / SCALE)
        assert g_low > g_high

    def test_expected_score_equal_ratings(self):
        mu = 0.0
        mu_j = 0.0
        phi_j = DEFAULT_RD / SCALE
        e = _E(mu, mu_j, phi_j)
        assert e == pytest.approx(0.5, abs=0.01)

    def test_expected_score_higher_rating(self):
        mu, _ = _to_glicko2(1700.0, DEFAULT_RD)
        mu_j, phi_j = _to_glicko2(1300.0, DEFAULT_RD)
        e = _E(mu, mu_j, phi_j)
        assert e > 0.5

    def test_expected_score_lower_rating(self):
        mu, _ = _to_glicko2(1300.0, DEFAULT_RD)
        mu_j, phi_j = _to_glicko2(1700.0, DEFAULT_RD)
        e = _E(mu, mu_j, phi_j)
        assert e < 0.5


# ---------------------------------------------------------------------------
# calculate_glicko2 — win / loss / draw
# ---------------------------------------------------------------------------

class TestRatingUpdate:
    """Rating update after a single game."""

    def test_win_increases_rating(self):
        new_r, new_rd, new_vol = calculate_glicko2(
            rating=1500, rd=200, volatility=0.06,
            opponent_rating=1500, opponent_rd=200,
            score=1.0,
        )
        assert new_r > 1500

    def test_loss_decreases_rating(self):
        new_r, new_rd, new_vol = calculate_glicko2(
            rating=1500, rd=200, volatility=0.06,
            opponent_rating=1500, opponent_rd=200,
            score=0.0,
        )
        assert new_r < 1500

    def test_draw_minimal_change(self):
        new_r, _, _ = calculate_glicko2(
            rating=1500, rd=200, volatility=0.06,
            opponent_rating=1500, opponent_rd=200,
            score=0.5,
        )
        assert abs(new_r - 1500) < 5

    def test_rd_decreases_after_game(self):
        """Playing a game reduces uncertainty."""
        new_r, new_rd, _ = calculate_glicko2(
            rating=1500, rd=200, volatility=0.06,
            opponent_rating=1500, opponent_rd=200,
            score=1.0,
        )
        assert new_rd < 200

    def test_upset_win_gives_more_rating(self):
        """Beating a stronger opponent gives more rating than beating equal."""
        _, _, _ = calculate_glicko2(
            rating=1500, rd=200, volatility=0.06,
            opponent_rating=1500, opponent_rd=200,
            score=1.0,
        )
        r_vs_strong, _, _ = calculate_glicko2(
            rating=1500, rd=200, volatility=0.06,
            opponent_rating=1800, opponent_rd=200,
            score=1.0,
        )
        r_vs_equal, _, _ = calculate_glicko2(
            rating=1500, rd=200, volatility=0.06,
            opponent_rating=1500, opponent_rd=200,
            score=1.0,
        )
        assert r_vs_strong > r_vs_equal


# ---------------------------------------------------------------------------
# PvE multiplier
# ---------------------------------------------------------------------------

class TestPvEMultiplier:
    """PvE games give 50% rating change."""

    def test_pve_gives_half_rating_change(self):
        r_pvp, _, _ = calculate_glicko2(
            rating=1500, rd=200, volatility=0.06,
            opponent_rating=1500, opponent_rd=200,
            score=1.0, is_pve=False,
        )
        r_pve, _, _ = calculate_glicko2(
            rating=1500, rd=200, volatility=0.06,
            opponent_rating=1500, opponent_rd=200,
            score=1.0, is_pve=True,
        )
        pvp_delta = r_pvp - 1500
        pve_delta = r_pve - 1500
        assert pve_delta == pytest.approx(pvp_delta * PVE_RATING_MULTIPLIER, abs=1)


# ---------------------------------------------------------------------------
# Placement acceleration
# ---------------------------------------------------------------------------

class TestPlacement:
    """Placement matches: RD decreases at 2x rate."""

    def test_placement_rd_lower(self):
        _, rd_normal, _ = calculate_glicko2(
            rating=1500, rd=350, volatility=0.06,
            opponent_rating=1500, opponent_rd=200,
            score=1.0, is_placement=False,
        )
        _, rd_placement, _ = calculate_glicko2(
            rating=1500, rd=350, volatility=0.06,
            opponent_rating=1500, opponent_rd=200,
            score=1.0, is_placement=True,
        )
        assert rd_placement < rd_normal


# ---------------------------------------------------------------------------
# Clamping
# ---------------------------------------------------------------------------

class TestClamping:
    """Rating and RD are clamped to valid ranges."""

    def test_rating_cannot_go_below_zero(self):
        """Extreme loss from very low rating stays >= 0."""
        r, _, _ = calculate_glicko2(
            rating=50, rd=350, volatility=0.06,
            opponent_rating=2500, opponent_rd=30,
            score=0.0,
        )
        assert r >= 0.0

    def test_rating_cannot_exceed_3000(self):
        r, _, _ = calculate_glicko2(
            rating=2950, rd=350, volatility=0.06,
            opponent_rating=500, opponent_rd=30,
            score=1.0,
        )
        assert r <= 3000.0

    def test_rd_at_least_min(self):
        _, rd, _ = calculate_glicko2(
            rating=1500, rd=MIN_RD, volatility=0.06,
            opponent_rating=1500, opponent_rd=200,
            score=1.0,
        )
        assert rd >= MIN_RD

    def test_rd_at_most_max(self):
        _, rd, _ = calculate_glicko2(
            rating=1500, rd=MAX_RD, volatility=0.06,
            opponent_rating=1500, opponent_rd=200,
            score=1.0,
        )
        assert rd <= MAX_RD


# ---------------------------------------------------------------------------
# RD decay for inactivity
# ---------------------------------------------------------------------------

class TestRDDecay:
    """RD increases when a player is inactive."""

    def test_no_decay_within_first_week(self):
        last_played = datetime.now(timezone.utc) - timedelta(hours=12)
        new_rd = apply_rd_decay(100.0, last_played)
        assert new_rd == 100.0

    def test_decay_after_one_week(self):
        last_played = datetime.now(timezone.utc) - timedelta(weeks=1, hours=1)
        new_rd = apply_rd_decay(100.0, last_played)
        assert new_rd > 100.0
        expected = 100.0 + RD_DECAY_PER_WEEK * 1.0
        assert new_rd == pytest.approx(expected, abs=2)

    def test_decay_capped_at_250(self):
        last_played = datetime.now(timezone.utc) - timedelta(weeks=100)
        new_rd = apply_rd_decay(100.0, last_played)
        assert new_rd == RD_DECAY_CAP

    def test_no_decay_if_never_played(self):
        new_rd = apply_rd_decay(100.0, None)
        assert new_rd == 100.0


# ---------------------------------------------------------------------------
# Convergence
# ---------------------------------------------------------------------------

class TestConvergence:
    """Rating should converge after many games."""

    def test_rating_converges_on_repeated_wins(self):
        """After many wins, rating should stabilize."""
        r, rd, vol = 1500.0, 350.0, 0.06
        for _ in range(50):
            r, rd, vol = calculate_glicko2(
                rating=r, rd=rd, volatility=vol,
                opponent_rating=1500, opponent_rd=200,
                score=1.0,
            )
        # RD should be relatively small (converged)
        assert rd < 120
        # Rating should be well above 1500
        assert r > 1700
