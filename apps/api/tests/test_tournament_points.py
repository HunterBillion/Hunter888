"""Unit tests for tournament_points converters — covering all boundary cases."""

from app.services.tournament_points import (
    knowledge_to_tp,
    pvp_to_tp,
    story_to_tp,
    training_to_tp,
)


class TestTrainingToTp:
    def test_zero_score_still_gives_floor_tp(self):
        assert training_to_tp(0, 5) == 10  # difficulty * 2

    def test_clamps_score_above_100(self):
        # 100 * 0.8 + 10 * 2 = 100
        assert training_to_tp(200, 10) == 100

    def test_typical_mid_session(self):
        # 50 * 0.8 + 5 * 2 = 40 + 10 = 50
        assert training_to_tp(50, 5) == 50

    def test_strong_session(self):
        # 80 * 0.8 + 5 * 2 = 64 + 10 = 74
        assert training_to_tp(80, 5) == 74

    def test_minimum_difficulty(self):
        assert training_to_tp(50, 1) == 42  # 40 + 2

    def test_maximum_difficulty(self):
        assert training_to_tp(50, 10) == 60  # 40 + 20

    def test_handles_none_gracefully(self):
        assert training_to_tp(None, None) >= 1

    def test_never_returns_zero(self):
        # 0 score, min difficulty → still 2 TP (1 * 2), clamped to 1
        assert training_to_tp(0, 1) >= 1


class TestPvpToTp:
    def test_win_no_elo_bonus(self):
        assert pvp_to_tp(True, 0, False) == 50

    def test_win_with_elo_bonus_capped(self):
        # bonus capped at 20
        assert pvp_to_tp(True, 100, False) == 70
        assert pvp_to_tp(True, 15, False) == 65

    def test_loss_base(self):
        assert pvp_to_tp(False, 0, False) == 15

    def test_loss_ignores_elo_delta(self):
        # elo_delta irrelevant on loss (we already lost some)
        assert pvp_to_tp(False, 100, False) == 15

    def test_pve_multiplier_halves_win(self):
        assert pvp_to_tp(True, 0, True) == 25  # 50 * 0.5

    def test_pve_loss(self):
        # 15 * 0.5 = 7.5 → round to 8
        assert pvp_to_tp(False, 0, True) == 8

    def test_negative_elo_clamped_to_zero(self):
        # Negative delta doesn't subtract from base
        assert pvp_to_tp(True, -50, False) == 50


class TestKnowledgeToTp:
    def test_empty_quiz_returns_zero(self):
        assert knowledge_to_tp(0, 0, False) == 0

    def test_perfect_accuracy_no_arena(self):
        # 100% / 2 = 50 TP
        assert knowledge_to_tp(10, 10, False) == 50

    def test_perfect_with_arena_win(self):
        # 50 + 25 = 75 TP
        assert knowledge_to_tp(10, 10, True) == 75

    def test_zero_correct_still_floors_at_1(self):
        # 0% + 0 bonus → 0 → floors to 1
        assert knowledge_to_tp(0, 10, False) == 1

    def test_fifty_percent(self):
        # 50% / 2 = 25 TP
        assert knowledge_to_tp(5, 10, False) == 25

    def test_arena_win_none_treated_as_false(self):
        assert knowledge_to_tp(10, 10, None) == 50


class TestStoryToTp:
    def test_empty_story_returns_zero(self):
        assert story_to_tp(50, 0, False) == 0

    def test_single_call(self):
        # 70 * 1 + 0 = 70
        assert story_to_tp(70, 1, False) == 70

    def test_full_completion_bonus(self):
        # 70 * 5 + 30 = 380
        assert story_to_tp(70, 5, True) == 380

    def test_partial_completion_no_bonus(self):
        # 70 * 3 = 210
        assert story_to_tp(70, 3, False) == 210

    def test_clamps_avg_score(self):
        assert story_to_tp(200, 1, False) == 100
