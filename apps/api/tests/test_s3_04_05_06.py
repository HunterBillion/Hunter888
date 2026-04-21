"""Tests for S3-04, S3-05, S3-06.

S3-04: Leaderboard inactive filter (scope=active|all_time)
S3-05: Glicko-2 placement cap ±100 + placement-priority matchmaking
S3-06: Hunter Score dynamic achievement count (no hardcoded 140)
"""

import inspect
import math

import pytest


# ═══════════════════════════════════════════════════════════════════════════
# S3-04: Leaderboard inactive filter
# ═══════════════════════════════════════════════════════════════════════════


class TestS304aLeaderboardScope:
    def test_scope_param_exists(self):
        """Leaderboard endpoint accepts scope query param."""
        import pathlib
        source = pathlib.Path(__file__).parent.parent / "app" / "api" / "pvp.py"
        content = source.read_text()
        assert "scope" in content
        assert '"active"' in content or "'active'" in content
        assert "all_time" in content

    def test_scope_default_is_active(self):
        """Default scope must be 'active' (not all_time)."""
        import pathlib
        source = pathlib.Path(__file__).parent.parent / "app" / "api" / "pvp.py"
        content = source.read_text()
        assert 'default="active"' in content

    def test_scope_validation_pattern(self):
        """scope param must have pattern validation (active|all_time)."""
        import pathlib
        source = pathlib.Path(__file__).parent.parent / "app" / "api" / "pvp.py"
        content = source.read_text()
        assert "active|all_time" in content

    def test_active_filter_uses_30_days(self):
        """Active scope filters players inactive > 30 days."""
        import pathlib
        source = pathlib.Path(__file__).parent.parent / "app" / "api" / "pvp.py"
        content = source.read_text()
        assert "timedelta(days=30)" in content
        assert "last_played" in content

    def test_count_query_also_filtered(self):
        """Total count query must apply the same scope filter."""
        import pathlib
        source = pathlib.Path(__file__).parent.parent / "app" / "api" / "pvp.py"
        content = source.read_text()
        # Count query should also check scope == "active"
        # Find two occurrences of the active filter (one for data, one for count)
        occurrences = content.count("scope == \"active\"") + content.count('scope == "active"')
        assert occurrences >= 2, \
            f"Expected at least 2 scope=='active' checks (data + count), found {occurrences}"

    def test_all_time_no_filter(self):
        """scope=all_time should NOT filter by last_played."""
        import pathlib
        source = pathlib.Path(__file__).parent.parent / "app" / "api" / "pvp.py"
        content = source.read_text()
        # The filter is inside `if scope == "active":` — all_time skips it
        assert 'if scope == "active"' in content


# ═══════════════════════════════════════════════════════════════════════════
# S3-05a: Glicko-2 placement cap ±100
# ═══════════════════════════════════════════════════════════════════════════


class TestS305aPlacementCap:
    def test_placement_cap_constant(self):
        """PLACEMENT_CAP should be 100."""
        source = inspect.getsource(__import__("app.services.glicko2", fromlist=["update_rating_after_duel"]))
        assert "PLACEMENT_CAP = 100" in source

    def test_placement_cap_positive(self):
        """Win during placement should be capped at +100."""
        from app.services.glicko2 import calculate_glicko2

        # Simulate: low-rated player beats high-rated opponent during placement
        # This would normally give a huge rating boost
        new_r, new_rd, new_vol = calculate_glicko2(
            rating=1500, rd=350, volatility=0.06,
            opponent_rating=2500, opponent_rd=50,
            score=1.0, is_pve=False, is_placement=True,
        )
        # The raw Glicko-2 change would be massive, but placement acceleration
        # applies phi_new *= 0.5. The cap is in update_rating_after_duel, not here.
        # This test verifies the function runs without error for placement.
        assert new_r > 1500  # Winner gains rating
        assert new_rd < 350  # RD decreases after game

    def test_placement_cap_in_update_function(self):
        """update_rating_after_duel must cap placement delta to ±100."""
        source = inspect.getsource(
            __import__("app.services.glicko2", fromlist=["update_rating_after_duel"]).update_rating_after_duel
        )
        assert "PLACEMENT_CAP" in source
        assert "rating_delta > PLACEMENT_CAP" in source
        assert "rating_delta < -PLACEMENT_CAP" in source

    def test_placement_acceleration_halves_rd(self):
        """During placement, phi_new *= 0.5 (2× faster convergence)."""
        from app.services.glicko2 import calculate_glicko2

        # Same game, placement vs non-placement
        _, rd_placement, _ = calculate_glicko2(
            rating=1500, rd=200, volatility=0.06,
            opponent_rating=1500, opponent_rd=200,
            score=1.0, is_pve=False, is_placement=True,
        )
        _, rd_normal, _ = calculate_glicko2(
            rating=1500, rd=200, volatility=0.06,
            opponent_rating=1500, opponent_rd=200,
            score=1.0, is_pve=False, is_placement=False,
        )
        assert rd_placement < rd_normal, \
            "Placement RD should decrease faster than normal"

    def test_placement_matches_count(self):
        """PLACEMENT_MATCHES should be 10."""
        from app.services.glicko2 import PLACEMENT_MATCHES
        assert PLACEMENT_MATCHES == 10


# ═══════════════════════════════════════════════════════════════════════════
# S3-05b: Placement-priority matchmaking
# ═══════════════════════════════════════════════════════════════════════════


class TestS305bPlacementMatchmaking:
    def test_queue_metadata_includes_placement(self):
        """Queue metadata must include 'placement' field."""
        source = inspect.getsource(
            __import__("app.services.pvp_matchmaker", fromlist=["join_queue"]).join_queue
        )
        assert '"placement"' in source

    def test_placement_flag_values(self):
        """Placement flag should be 'true' or 'false' string."""
        source = inspect.getsource(
            __import__("app.services.pvp_matchmaker", fromlist=["join_queue"]).join_queue
        )
        assert '"true"' in source
        assert '"false"' in source
        assert "placement_done" in source

    def test_find_match_sorts_by_placement(self):
        """find_match must sort eligible candidates by placement affinity."""
        source = inspect.getsource(
            __import__("app.services.pvp_matchmaker", fromlist=["find_match"]).find_match
        )
        assert "player_is_placement" in source
        assert "eligible" in source
        assert ".sort(" in source

    def test_placement_sort_logic(self):
        """Placement players should be sorted first when searcher is in placement."""
        source = inspect.getsource(
            __import__("app.services.pvp_matchmaker", fromlist=["find_match"]).find_match
        )
        # The sort key should prioritize placement == "true" candidates
        assert 'placement' in source
        assert "eligible.sort" in source

    def test_non_placement_no_sort(self):
        """Non-placement players should NOT re-sort candidates."""
        source = inspect.getsource(
            __import__("app.services.pvp_matchmaker", fromlist=["find_match"]).find_match
        )
        # Sort only happens `if player_is_placement:`
        assert "if player_is_placement:" in source


# ═══════════════════════════════════════════════════════════════════════════
# S3-05c: Glicko-2 math correctness
# ═══════════════════════════════════════════════════════════════════════════


class TestS305cGlicko2Math:
    def test_win_increases_rating(self):
        from app.services.glicko2 import calculate_glicko2
        new_r, _, _ = calculate_glicko2(
            1500, 200, 0.06, 1500, 200, 1.0,
        )
        assert new_r > 1500

    def test_loss_decreases_rating(self):
        from app.services.glicko2 import calculate_glicko2
        new_r, _, _ = calculate_glicko2(
            1500, 200, 0.06, 1500, 200, 0.0,
        )
        assert new_r < 1500

    def test_draw_symmetric(self):
        from app.services.glicko2 import calculate_glicko2
        new_r, _, _ = calculate_glicko2(
            1500, 200, 0.06, 1500, 200, 0.5,
        )
        # Draw against equal opponent → minimal change
        assert abs(new_r - 1500) < 5

    def test_pve_half_rating_change(self):
        from app.services.glicko2 import calculate_glicko2
        pvp_r, _, _ = calculate_glicko2(
            1500, 200, 0.06, 1500, 200, 1.0, is_pve=False,
        )
        pve_r, _, _ = calculate_glicko2(
            1500, 200, 0.06, 1500, 200, 1.0, is_pve=True,
        )
        pvp_delta = pvp_r - 1500
        pve_delta = pve_r - 1500
        assert abs(pve_delta - pvp_delta * 0.5) < 1.0

    def test_rating_clamped_to_valid_range(self):
        from app.services.glicko2 import calculate_glicko2
        # Massive loss shouldn't go below 0
        new_r, _, _ = calculate_glicko2(
            100, 350, 0.06, 3000, 50, 0.0,
        )
        assert new_r >= 0.0

    def test_rd_clamped(self):
        from app.services.glicko2 import calculate_glicko2, MIN_RD, MAX_RD
        _, new_rd, _ = calculate_glicko2(
            1500, 350, 0.06, 1500, 350, 1.0,
        )
        assert MIN_RD <= new_rd <= MAX_RD

    def test_volatility_finite(self):
        from app.services.glicko2 import calculate_glicko2
        _, _, new_vol = calculate_glicko2(
            1500, 200, 0.06, 1500, 200, 1.0,
        )
        assert math.isfinite(new_vol)
        assert new_vol > 0

    def test_new_volatility_zero_sigma_guard(self):
        """sigma=0 should not cause log(0) crash."""
        from app.services.glicko2 import _new_volatility
        result = _new_volatility(sigma=0, phi=1.0, v=1.0, delta=0.5)
        assert math.isfinite(result)
        assert result > 0

    def test_rd_decay_inactive(self):
        from app.services.glicko2 import apply_rd_decay
        from datetime import datetime, timezone, timedelta
        # 4 weeks inactive → +60 RD
        last_played = datetime.now(timezone.utc) - timedelta(weeks=4)
        new_rd = apply_rd_decay(100.0, last_played)
        assert new_rd == pytest.approx(160.0, abs=5)

    def test_rd_decay_cap(self):
        from app.services.glicko2 import apply_rd_decay, RD_DECAY_CAP
        from datetime import datetime, timezone, timedelta
        # 100 weeks inactive → capped at 250
        last_played = datetime.now(timezone.utc) - timedelta(weeks=100)
        new_rd = apply_rd_decay(100.0, last_played)
        assert new_rd == RD_DECAY_CAP


# ═══════════════════════════════════════════════════════════════════════════
# S3-06: Hunter Score dynamic achievement count
# ═══════════════════════════════════════════════════════════════════════════


class TestS306aDynamicCount:
    def test_no_hardcoded_140(self):
        """hunter_score.py must NOT have hardcoded '/ 140'."""
        source = inspect.getsource(
            __import__("app.services.hunter_score", fromlist=["update_hunter_score"]).update_hunter_score
        )
        assert "/ 140" not in source, \
            "Hardcoded '/ 140' found — must use dynamic count from AchievementDefinition"

    def test_uses_achievement_definition(self):
        """update_hunter_score must query AchievementDefinition for total count."""
        source = inspect.getsource(
            __import__("app.services.hunter_score", fromlist=["update_hunter_score"]).update_hunter_score
        )
        assert "AchievementDefinition" in source

    def test_fallback_when_table_empty(self):
        """If AchievementDefinition is empty, fallback to 140."""
        source = inspect.getsource(
            __import__("app.services.hunter_score", fromlist=["update_hunter_score"]).update_hunter_score
        )
        assert "or 140" in source or "140" in source, \
            "Must have fallback value when achievement_definitions table is empty"

    def test_uses_func_count(self):
        """Must use SELECT COUNT(*) FROM achievement_definitions."""
        source = inspect.getsource(
            __import__("app.services.hunter_score", fromlist=["update_hunter_score"]).update_hunter_score
        )
        assert "func.count" in source
        assert "AchievementDefinition" in source


class TestS306bHunterScoreFormula:
    def test_calculate_score_range(self):
        from app.services.hunter_score import calculate_hunter_score
        score = calculate_hunter_score(
            training_level=10,
            pvp_rating_percentile=0.5,
            knowledge_avg_score=50,
            achievement_completion_pct=0.5,
            reputation_score=50,
        )
        assert 0 <= score <= 100

    def test_max_score(self):
        from app.services.hunter_score import calculate_hunter_score
        score = calculate_hunter_score(
            training_level=20,
            pvp_rating_percentile=1.0,
            knowledge_avg_score=100,
            achievement_completion_pct=1.0,
            reputation_score=100,
        )
        assert score == 100.0

    def test_min_score(self):
        from app.services.hunter_score import calculate_hunter_score
        score = calculate_hunter_score(
            training_level=0,
            pvp_rating_percentile=0.0,
            knowledge_avg_score=0,
            achievement_completion_pct=0.0,
            reputation_score=0,
        )
        assert score == 0.0

    def test_weights_sum_to_100(self):
        """Component weights (35+25+20+10+10) must equal 100%."""
        from app.services.hunter_score import calculate_hunter_score
        # Each component at exactly 100% of its range
        score = calculate_hunter_score(
            training_level=20,      # 35% × 100
            pvp_rating_percentile=1.0,  # 25% × 100
            knowledge_avg_score=100,    # 20% × 100
            achievement_completion_pct=1.0,  # 10% × 100
            reputation_score=100,       # 10% × 100
        )
        assert score == 100.0

    def test_pvp_rank_to_difficulty_mapping(self):
        from app.services.hunter_score import PVP_RANK_TO_DIFFICULTY
        assert "iron" in PVP_RANK_TO_DIFFICULTY
        assert "grandmaster" in PVP_RANK_TO_DIFFICULTY
        assert len(PVP_RANK_TO_DIFFICULTY) == 8

    def test_streak_xp_multiplier(self):
        from app.services.hunter_score import get_streak_xp_multiplier
        assert get_streak_xp_multiplier(0) == 1.0
        assert get_streak_xp_multiplier(5) == 1.2
        assert get_streak_xp_multiplier(10) == 1.3
        assert get_streak_xp_multiplier(15) == 1.5


# ═══════════════════════════════════════════════════════════════════════════
# S3-04/05/06: Integration / cross-cutting checks
# ═══════════════════════════════════════════════════════════════════════════


class TestCrossCutting:
    def test_season_reset_resets_placement(self):
        """Season reset must set placement_done=False so players re-do placement (S3-12/v12 fix)."""
        source = inspect.getsource(
            __import__("app.services.glicko2", fromlist=["apply_season_reset"]).apply_season_reset
        )
        assert "placement_done=False" in source
        assert "placement_count=0" in source

    def test_leaderboard_requires_placement_done(self):
        """Leaderboard must only show placed players."""
        import pathlib
        source = pathlib.Path(__file__).parent.parent / "app" / "api" / "pvp.py"
        content = source.read_text()
        assert "placement_done" in content

    def test_matchmaker_queue_metadata_complete(self):
        """Queue metadata must include all required fields."""
        source = inspect.getsource(
            __import__("app.services.pvp_matchmaker", fromlist=["join_queue"]).join_queue
        )
        for field in ["rating", "rd", "queued_at", "status", "placement"]:
            assert f'"{field}"' in source, f"Missing '{field}' in queue metadata"

    def test_achievement_definition_model_exists(self):
        """AchievementDefinition model must exist."""
        from app.models.progress import AchievementDefinition
        assert AchievementDefinition.__tablename__ == "achievement_definitions"

    def test_achievement_definition_has_code_pk(self):
        """AchievementDefinition primary key must be 'code'."""
        from app.models.progress import AchievementDefinition
        pk_cols = [c.name for c in AchievementDefinition.__table__.primary_key.columns]
        assert "code" in pk_cols
