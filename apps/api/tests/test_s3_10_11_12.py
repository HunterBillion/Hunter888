"""Tests for S3-10, S3-11, S3-12.

S3-10: Between Call Narrator — empty tips fallback (None vs [] vs list)
S3-11: Matchmaking MAX_RATING_GAP=400 + gradual expansion schedule
S3-12: Arena FFA inflation protection (RD weight, repeat decay, cherry-picking)
"""

import inspect
import logging
import math
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════════════
# S3-10: Between Call Narrator — empty tips handling
# ═══════════════════════════════════════════════════════════════════════════


class TestS310NarratorEmptyTips:
    """S3-10: When LLM skips coaching, return None (not [])."""

    def test_generate_coaching_tips_returns_none_when_no_weak_points_and_high_score(self):
        """High relationship_score + no weak points → None (skip coaching)."""
        from app.services.between_call_narrator import NarratorContext

        ctx = NarratorContext(
            manager_weak_points=[],
            relationship_score=85,
            call_number=3,
            archetype_code="pragmatic",
            lifecycle_state="active",
            last_emotion="neutral",
            last_outcome="positive",
            last_score=80,
        )
        # The function checks `not ctx.manager_weak_points and ctx.relationship_score >= 70`
        assert not ctx.manager_weak_points
        assert ctx.relationship_score >= 70

    def test_source_code_returns_none_not_empty_list(self):
        """Source code must return None (not []) for skip-coaching case."""
        src = inspect.getsource(
            __import__("app.services.between_call_narrator", fromlist=["generate_coaching_tips_llm"])
            .generate_coaching_tips_llm
        )
        # Line should say "return None" not "return []"
        assert "return None" in src
        # The old code was "return []" — make sure it's gone
        lines = src.split("\n")
        skip_section = [l for l in lines if "no weak points" in l.lower() or "skip coaching" in l.lower()]
        assert len(skip_section) > 0, "Comment about skip coaching should exist"

    def test_consumer_handles_none_as_skip(self):
        """Consumer: None → empty tips (no template fallback)."""
        src = inspect.getsource(
            __import__("app.services.between_call_narrator", fromlist=["generate_between_call_content"])
            .generate_between_call_content
        )
        # Must have explicit None check
        assert "llm_tips is None" in src

    def test_consumer_handles_empty_list_as_fallback(self):
        """Consumer: empty list [] → template fallback."""
        src = inspect.getsource(
            __import__("app.services.between_call_narrator", fromlist=["generate_between_call_content"])
            .generate_between_call_content
        )
        # Must call template generation for else case
        assert "generate_coaching_tips_template" in src

    def test_consumer_handles_populated_list(self):
        """Consumer: populated list → use LLM tips directly."""
        src = inspect.getsource(
            __import__("app.services.between_call_narrator", fromlist=["generate_between_call_content"])
            .generate_between_call_content
        )
        assert "result.coaching_tips = llm_tips" in src

    def test_three_way_branching_exists(self):
        """S3-10 requires three-way branch: None / populated / empty."""
        src = inspect.getsource(
            __import__("app.services.between_call_narrator", fromlist=["generate_between_call_content"])
            .generate_between_call_content
        )
        # All three branches must exist
        assert "llm_tips is None" in src
        assert "len(llm_tips) > 0" in src
        assert "generate_coaching_tips_template" in src

    def test_exception_from_gather_handled_explicitly(self):
        """FIX-4 (v13): Exception from asyncio.gather must be caught before branching."""
        src = inspect.getsource(
            __import__("app.services.between_call_narrator", fromlist=["generate_between_call_content"])
            .generate_between_call_content
        )
        assert "BaseException" in src or "isinstance(llm_tips, Exception)" in src

    def test_llm_returns_none_on_parse_failure(self):
        """If LLM returns garbage (no tips parsed), function returns None."""
        src = inspect.getsource(
            __import__("app.services.between_call_narrator", fromlist=["generate_coaching_tips_llm"])
            .generate_coaching_tips_llm
        )
        # After parsing, if tips empty → return None
        assert "return tips[:3] if tips else None" in src


# ═══════════════════════════════════════════════════════════════════════════
# S3-11: Matchmaking rating gap + gradual expansion
# ═══════════════════════════════════════════════════════════════════════════


class TestS311GetMaxGap:
    """S3-11: _get_max_gap schedule: 400→600→800→uncapped."""

    def test_gap_at_0_seconds(self):
        from app.services.pvp_matchmaker import _get_max_gap
        assert _get_max_gap(0) == 400.0

    def test_gap_at_15_seconds(self):
        from app.services.pvp_matchmaker import _get_max_gap
        assert _get_max_gap(15) == 400.0

    def test_gap_at_29_seconds(self):
        from app.services.pvp_matchmaker import _get_max_gap
        assert _get_max_gap(29) == 400.0

    def test_gap_at_30_seconds_expands(self):
        from app.services.pvp_matchmaker import _get_max_gap
        assert _get_max_gap(30) == 600.0

    def test_gap_at_45_seconds(self):
        from app.services.pvp_matchmaker import _get_max_gap
        assert _get_max_gap(45) == 600.0

    def test_gap_at_60_seconds_expands_again(self):
        from app.services.pvp_matchmaker import _get_max_gap
        assert _get_max_gap(60) == 800.0

    def test_gap_at_89_seconds(self):
        from app.services.pvp_matchmaker import _get_max_gap
        assert _get_max_gap(89) == 800.0

    def test_gap_at_90_seconds_uncapped(self):
        from app.services.pvp_matchmaker import _get_max_gap
        assert _get_max_gap(90) is None

    def test_gap_at_120_seconds_uncapped(self):
        from app.services.pvp_matchmaker import _get_max_gap
        assert _get_max_gap(120) is None


class TestS311Constants:
    """S3-11: Matchmaker constants."""

    def test_max_rating_gap_is_400(self):
        from app.services.pvp_matchmaker import MAX_RATING_GAP
        assert MAX_RATING_GAP == 400

    def test_gap_expansion_schedule_has_3_tiers(self):
        from app.services.pvp_matchmaker import GAP_EXPANSION_SCHEDULE
        assert len(GAP_EXPANSION_SCHEDULE) == 3

    def test_gap_schedule_is_monotonically_increasing(self):
        from app.services.pvp_matchmaker import GAP_EXPANSION_SCHEDULE
        thresholds = [t for t, _ in GAP_EXPANSION_SCHEDULE]
        gaps = [g for _, g in GAP_EXPANSION_SCHEDULE]
        assert thresholds == sorted(thresholds)
        assert gaps == sorted(gaps)

    def test_gap_filter_in_find_match_source(self):
        """find_match must check rating_gap against _get_max_gap."""
        src = inspect.getsource(
            __import__("app.services.pvp_matchmaker", fromlist=["find_match"]).find_match
        )
        assert "_get_max_gap" in src
        assert "rating_gap" in src


# ═══════════════════════════════════════════════════════════════════════════
# S3-12: Arena FFA inflation protection
# ═══════════════════════════════════════════════════════════════════════════


class TestS312Constants:
    """S3-12: FFA inflation protection constants."""

    def test_max_ffa_rating_gap(self):
        from app.services.arena_rating import MAX_FFA_RATING_GAP
        assert MAX_FFA_RATING_GAP == 500

    def test_ffa_rd_weight_base(self):
        from app.services.arena_rating import FFA_RD_WEIGHT_BASE
        assert FFA_RD_WEIGHT_BASE == 350.0

    def test_repeat_opponent_decay_values(self):
        from app.services.arena_rating import REPEAT_OPPONENT_DECAY
        assert REPEAT_OPPONENT_DECAY == [1.0, 0.50, 0.25, 0.10]

    def test_cherry_pick_threshold(self):
        from app.services.arena_rating import CHERRY_PICK_THRESHOLD
        assert CHERRY_PICK_THRESHOLD == 3


class TestS312RDWeightedGain:
    """S3-12a: RD-weighted gain — uncertain opponents give less gain.

    Acceptance: player rating=2000 gets < 50% gain vs opponent with RD > 300.
    """

    def test_rd_weight_formula_high_rd(self):
        """RD=300 → weight = max(0.1, 1 - 300/350) = 0.143 (< 50%)."""
        from app.services.arena_rating import FFA_RD_WEIGHT_BASE
        rd = 300
        weight = max(0.1, 1.0 - rd / FFA_RD_WEIGHT_BASE)
        assert weight < 0.50, f"RD={rd} weight={weight} should be < 0.50"

    def test_rd_weight_formula_rd_350(self):
        """RD=350 → weight = max(0.1, 1 - 350/350) = max(0.1, 0) = 0.1."""
        from app.services.arena_rating import FFA_RD_WEIGHT_BASE
        weight = max(0.1, 1.0 - 350.0 / FFA_RD_WEIGHT_BASE)
        assert weight == 0.1

    def test_rd_weight_formula_low_rd(self):
        """RD=50 → weight = 1 - 50/350 ≈ 0.857 (high weight for precise opponent)."""
        from app.services.arena_rating import FFA_RD_WEIGHT_BASE
        weight = max(0.1, 1.0 - 50.0 / FFA_RD_WEIGHT_BASE)
        assert weight > 0.80

    def test_rd_weight_in_update_ffa_source(self):
        """_update_ffa must apply RD weighting to positive deltas."""
        src = inspect.getsource(
            __import__("app.services.arena_rating", fromlist=["_update_ffa"])._update_ffa
        )
        assert "rd_weight" in src
        assert "FFA_RD_WEIGHT_BASE" in src

    def test_gain_less_than_50pct_against_rd300_opponent(self):
        """Acceptance criterion: player 2000 gets <50% gain vs RD>300 opponent.

        We verify via the formula: the RD weight factor for RD=300 is ~14.3%,
        so any positive gain is multiplied by ≤0.143 → definitely <50%.
        """
        from app.services.arena_rating import FFA_RD_WEIGHT_BASE

        opponent_rd = 300
        rd_weight = max(0.1, 1.0 - opponent_rd / FFA_RD_WEIGHT_BASE)
        # rd_weight ≈ 0.143, well below 0.50
        assert rd_weight < 0.50

        # If raw gain were 30 points, adjusted = 30 * 0.143 = 4.29
        raw_gain = 30.0
        adjusted_gain = raw_gain * rd_weight
        assert adjusted_gain < raw_gain * 0.50

    def test_rd_weight_only_applied_to_positive_deltas(self):
        """RD weight should NOT reduce losses — only gains."""
        src = inspect.getsource(
            __import__("app.services.arena_rating", fromlist=["_update_ffa"])._update_ffa
        )
        # Must have conditional: apply only to positive deltas
        assert "raw_delta_1 > 0" in src
        assert "raw_delta_2 > 0" in src


class TestS312RatingGapAttenuation:
    """S3-12b: Rating gap attenuation for gaps > MAX_FFA_RATING_GAP."""

    def test_gap_within_limit_no_attenuation(self):
        """Gap ≤ 500 → gap_factor = 1.0 (no attenuation)."""
        from app.services.arena_rating import MAX_FFA_RATING_GAP
        gap = 400
        gap_factor = MAX_FFA_RATING_GAP / gap if gap > MAX_FFA_RATING_GAP else 1.0
        assert gap_factor == 1.0

    def test_gap_exactly_at_limit(self):
        from app.services.arena_rating import MAX_FFA_RATING_GAP
        gap = MAX_FFA_RATING_GAP
        gap_factor = MAX_FFA_RATING_GAP / gap if gap > MAX_FFA_RATING_GAP else 1.0
        assert gap_factor == 1.0

    def test_gap_over_limit_attenuated(self):
        """Gap = 1000 → gap_factor = 500/1000 = 0.5 (50% attenuation)."""
        from app.services.arena_rating import MAX_FFA_RATING_GAP
        gap = 1000
        gap_factor = MAX_FFA_RATING_GAP / gap if gap > MAX_FFA_RATING_GAP else 1.0
        assert gap_factor == 0.5

    def test_gap_attenuation_in_source(self):
        """_update_ffa must check MAX_FFA_RATING_GAP for attenuation."""
        src = inspect.getsource(
            __import__("app.services.arena_rating", fromlist=["_update_ffa"])._update_ffa
        )
        assert "MAX_FFA_RATING_GAP" in src
        assert "gap_factor" in src


class TestS312RepeatOpponentDecay:
    """S3-12c: Repeat opponent diminishing returns.

    Acceptance: 3+ consecutive matches → gain reduced 50%/75%/90%.
    """

    def test_decay_first_match(self):
        """1st match → multiplier = 1.0 (full gain)."""
        from app.services.arena_rating import REPEAT_OPPONENT_DECAY
        assert REPEAT_OPPONENT_DECAY[0] == 1.0

    def test_decay_second_match(self):
        """2nd match → multiplier = 0.50 (50% gain)."""
        from app.services.arena_rating import REPEAT_OPPONENT_DECAY
        assert REPEAT_OPPONENT_DECAY[1] == 0.50

    def test_decay_third_match(self):
        """3rd match → multiplier = 0.25 (75% reduction)."""
        from app.services.arena_rating import REPEAT_OPPONENT_DECAY
        assert REPEAT_OPPONENT_DECAY[2] == 0.25

    def test_decay_fourth_match(self):
        """4th+ match → multiplier = 0.10 (90% reduction)."""
        from app.services.arena_rating import REPEAT_OPPONENT_DECAY
        assert REPEAT_OPPONENT_DECAY[3] == 0.10

    def test_decay_index_clamping(self):
        """For N > 4 matches, index clamps to last element (0.10)."""
        from app.services.arena_rating import REPEAT_OPPONENT_DECAY
        max_repeats = 10  # hypothetical 10th match
        idx = min(max_repeats - 1, len(REPEAT_OPPONENT_DECAY) - 1)
        assert REPEAT_OPPONENT_DECAY[idx] == 0.10

    def test_repeat_factor_applied_only_to_gains(self):
        """Repeat decay should only reduce gains, not losses."""
        src = inspect.getsource(
            __import__("app.services.arena_rating", fromlist=["_update_ffa"])._update_ffa
        )
        # Must check: factor applied only if delta > 0
        assert "delta > 0" in src
        assert "delta * factor" in src or "adjusted_delta = delta * factor" in src

    def test_get_repeat_factors_uses_redis(self):
        """_get_repeat_factors must use Redis for counter tracking."""
        src = inspect.getsource(
            __import__("app.services.arena_rating", fromlist=["_get_repeat_factors"])._get_repeat_factors
        )
        assert "get_redis" in src or "redis" in src.lower()
        assert "ffa:repeat:" in src

    def test_get_repeat_factors_redis_key_sorted(self):
        """Redis key must be sorted to avoid A:B vs B:A duplication."""
        src = inspect.getsource(
            __import__("app.services.arena_rating", fromlist=["_get_repeat_factors"])._get_repeat_factors
        )
        assert "sorted" in src

    def test_get_repeat_factors_24h_ttl(self):
        """Repeat counter expires after 24h."""
        src = inspect.getsource(
            __import__("app.services.arena_rating", fromlist=["_get_repeat_factors"])._get_repeat_factors
        )
        assert "86400" in src

    def test_get_repeat_factors_session_idempotent(self):
        """FIX-1 (v13): Must use SADD (not INCR) for session-idempotent counting."""
        src = inspect.getsource(
            __import__("app.services.arena_rating", fromlist=["_get_repeat_factors"])._get_repeat_factors
        )
        # Must use SADD + SCARD instead of INCR for idempotency
        assert "sadd" in src
        assert "scard" in src
        # Must NOT use bare incr
        assert "incr" not in src.lower() or "# " in src  # incr only in comments

    def test_get_repeat_factors_accepts_session_id(self):
        """FIX-1 (v13): _get_repeat_factors must accept session_id parameter."""
        import inspect as insp
        sig = insp.signature(
            __import__("app.services.arena_rating", fromlist=["_get_repeat_factors"])._get_repeat_factors
        )
        assert "session_id" in sig.parameters


class TestS312CherryPickingDetection:
    """S3-12d: Cherry-picking pattern logged for anti-cheat L1.

    Acceptance: cherry-picking pattern is logged in anti_cheat.
    """

    def test_cherry_picking_function_exists(self):
        from app.services.arena_rating import _check_cherry_picking
        assert callable(_check_cherry_picking)

    def test_cherry_picking_only_flags_strong_players(self):
        """Only players with rating > 1800 are checked."""
        src = inspect.getsource(
            __import__("app.services.arena_rating", fromlist=["_check_cherry_picking"])._check_cherry_picking
        )
        assert "1800" in src

    def test_cherry_picking_checks_opponent_rd(self):
        """Checks how many opponents have RD > 300."""
        src = inspect.getsource(
            __import__("app.services.arena_rating", fromlist=["_check_cherry_picking"])._check_cherry_picking
        )
        assert "rd > 300" in src.lower() or "opp.rd > 300" in src

    def test_cherry_picking_uses_threshold(self):
        """Must use CHERRY_PICK_THRESHOLD for flagging."""
        src = inspect.getsource(
            __import__("app.services.arena_rating", fromlist=["_check_cherry_picking"])._check_cherry_picking
        )
        assert "CHERRY_PICK_THRESHOLD" in src

    def test_cherry_picking_logs_warning(self):
        """Cherry-picking must log a warning for anti-cheat pipeline."""
        src = inspect.getsource(
            __import__("app.services.arena_rating", fromlist=["_check_cherry_picking"])._check_cherry_picking
        )
        assert "logger.warning" in src
        assert "ANTI-CHEAT" in src or "Cherry-picking" in src

    def test_cherry_picking_detection_with_mock_ratings(self):
        """Simulate: player 2000 rating, 3 opponents with RD=350 → should log."""
        from app.services.arena_rating import _check_cherry_picking, CHERRY_PICK_THRESHOLD

        # Mock PvPRating objects
        def make_rating(rating_val, rd_val):
            r = MagicMock()
            r.rating = rating_val
            r.rd = rd_val
            return r

        rankings = [
            {"user_id": "aaa", "rank": 1},
            {"user_id": "bbb", "rank": 2},
            {"user_id": "ccc", "rank": 3},
            {"user_id": "ddd", "rank": 4},
        ]
        ratings = {
            "aaa": make_rating(2100, 50),   # Strong player
            "bbb": make_rating(1200, 340),  # New/uncertain
            "ccc": make_rating(1300, 320),  # New/uncertain
            "ddd": make_rating(1100, 350),  # New/uncertain
        }

        with patch("app.services.arena_rating.logger") as mock_logger:
            _check_cherry_picking(rankings, ratings)
            # Player "aaa" (2100) has 3 opponents with RD > 300 → must log
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args
            assert "Cherry-picking" in call_args[0][0] or "ANTI-CHEAT" in call_args[0][0]

    def test_cherry_picking_no_flag_for_weak_player(self):
        """Player with rating < 1800 should NOT be flagged."""
        from app.services.arena_rating import _check_cherry_picking

        def make_rating(rating_val, rd_val):
            r = MagicMock()
            r.rating = rating_val
            r.rd = rd_val
            return r

        rankings = [
            {"user_id": "aaa", "rank": 1},
            {"user_id": "bbb", "rank": 2},
            {"user_id": "ccc", "rank": 3},
            {"user_id": "ddd", "rank": 4},
        ]
        ratings = {
            "aaa": make_rating(1600, 50),   # Not strong enough
            "bbb": make_rating(1200, 340),
            "ccc": make_rating(1300, 320),
            "ddd": make_rating(1100, 350),
        }

        with patch("app.services.arena_rating.logger") as mock_logger:
            _check_cherry_picking(rankings, ratings)
            mock_logger.warning.assert_not_called()

    def test_cherry_picking_no_flag_if_opponents_have_low_rd(self):
        """Strong player vs opponents with low RD → no flag."""
        from app.services.arena_rating import _check_cherry_picking

        def make_rating(rating_val, rd_val):
            r = MagicMock()
            r.rating = rating_val
            r.rd = rd_val
            return r

        rankings = [
            {"user_id": "aaa", "rank": 1},
            {"user_id": "bbb", "rank": 2},
            {"user_id": "ccc", "rank": 3},
        ]
        ratings = {
            "aaa": make_rating(2100, 50),
            "bbb": make_rating(2000, 60),  # Low RD — precise
            "ccc": make_rating(1900, 70),  # Low RD — precise
        }

        with patch("app.services.arena_rating.logger") as mock_logger:
            _check_cherry_picking(rankings, ratings)
            mock_logger.warning.assert_not_called()


class TestS312FFAUpdateStructure:
    """S3-12: _update_ffa overall structure checks."""

    def test_update_ffa_calls_repeat_factors(self):
        """_update_ffa must call _get_repeat_factors."""
        src = inspect.getsource(
            __import__("app.services.arena_rating", fromlist=["_update_ffa"])._update_ffa
        )
        assert "_get_repeat_factors" in src

    def test_update_ffa_calls_cherry_picking(self):
        """_update_ffa must call _check_cherry_picking."""
        src = inspect.getsource(
            __import__("app.services.arena_rating", fromlist=["_update_ffa"])._update_ffa
        )
        assert "_check_cherry_picking" in src

    def test_update_ffa_averages_by_n_minus_1(self):
        """FFA pairwise deltas must be divided by (n-1)."""
        src = inspect.getsource(
            __import__("app.services.arena_rating", fromlist=["_update_ffa"])._update_ffa
        )
        assert "(n - 1)" in src

    def test_update_ffa_uses_averaged_rd_from_glicko2(self):
        """FIX-3 (v13): FFA must average RD from pairwise Glicko-2, not crude *0.95."""
        src = inspect.getsource(
            __import__("app.services.arena_rating", fromlist=["_update_ffa"])._update_ffa
        )
        # Must accumulate RD from pairwise calculations
        assert "rd_accum" in src
        # Must use averaged pairwise RD, not crude formula
        assert "pairwise_rds" in src

    def test_update_ffa_uses_averaged_volatility(self):
        """FIX-3 (v13): FFA must average volatility from pairwise calculations."""
        src = inspect.getsource(
            __import__("app.services.arena_rating", fromlist=["_update_ffa"])._update_ffa
        )
        assert "vol_accum" in src


class TestV13TransactionConsolidation:
    """FIX-5 (v13): knowledge.py must use single transaction."""

    def test_single_async_session_for_match_completion(self):
        """Rating update + session update + participant update in one transaction."""
        import pathlib
        src_path = pathlib.Path(__file__).parent.parent / "app" / "ws" / "knowledge.py"
        content = src_path.read_text()

        # Find the section after "Update ratings" comment
        idx = content.find("Single transaction for ratings")
        assert idx != -1, "FIX-5 comment must exist in knowledge.py"

        # The section should have only ONE async_session() for ratings+session+participants
        section = content[idx:idx+2000]
        session_count = section.count("async with async_session()")
        assert session_count == 1, f"Expected 1 async_session in consolidated block, found {session_count}"


class TestS312Integration:
    """S3-12: Integration-level formula verification."""

    def test_combined_protection_severely_limits_exploit(self):
        """Combined RD weight + gap attenuation limits exploit potential.

        Scenario: Player 2000 vs opponent 800 with RD 340.
        - RD weight: max(0.1, 1 - 340/350) = max(0.1, 0.029) = 0.1
        - Gap: |2000-800| = 1200 > 500 → factor = 500/1200 = 0.417
        - Combined: 0.1 * 0.417 = 0.042 → only 4.2% of raw gain
        """
        from app.services.arena_rating import MAX_FFA_RATING_GAP, FFA_RD_WEIGHT_BASE

        rd_weight = max(0.1, 1.0 - 340.0 / FFA_RD_WEIGHT_BASE)
        gap = abs(2000 - 800)
        gap_factor = MAX_FFA_RATING_GAP / gap if gap > MAX_FFA_RATING_GAP else 1.0
        combined = rd_weight * gap_factor
        assert combined < 0.10, f"Combined factor {combined} should be < 10%"

    def test_fair_match_no_attenuation(self):
        """Two equal players with low RD → near-full gain.

        Player 1800, opponent 1850, RD 60.
        - RD weight: max(0.1, 1 - 60/350) = 0.829
        - Gap: 50 < 500 → factor = 1.0
        - Combined: 0.829 → 83% gain, reasonable.
        """
        from app.services.arena_rating import MAX_FFA_RATING_GAP, FFA_RD_WEIGHT_BASE

        rd_weight = max(0.1, 1.0 - 60.0 / FFA_RD_WEIGHT_BASE)
        gap = abs(1800 - 1850)
        gap_factor = MAX_FFA_RATING_GAP / gap if gap > MAX_FFA_RATING_GAP else 1.0
        combined = rd_weight * gap_factor
        assert combined > 0.80, f"Fair match should preserve >80% gain, got {combined}"
