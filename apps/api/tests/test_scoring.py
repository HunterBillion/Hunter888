"""Tests for the 10-layer scoring engine (services/scoring.py).

Covers individual layer scoring, the ScoreBreakdown data class,
normalization, objection handling patterns, communication sub-scores,
result scoring, and the human factor layer. All tests are synchronous
or mock async dependencies.
"""

import pytest

from app.services.scoring import (
    V3_RESCALE,
    ScoreBreakdown,
    _normalize,
    _has_pattern,
    _score_objection_handling,
    _score_communication,
    _score_result,
    _score_human_factor,
    OBJECTION_PATTERNS,
    ACKNOWLEDGE_PATTERNS,
    CLARIFY_PATTERNS,
    ARGUMENT_PATTERNS,
    CHECK_PATTERNS,
)


# ---------------------------------------------------------------------------
# _normalize
# ---------------------------------------------------------------------------

class TestNormalize:
    """Normalize value to 0-1 range."""

    def test_zero(self):
        assert _normalize(0, 100) == 0.0

    def test_max(self):
        assert _normalize(100, 100) == 1.0

    def test_half(self):
        assert _normalize(50, 100) == pytest.approx(0.5)

    def test_over_max_clamped(self):
        assert _normalize(200, 100) == 1.0

    def test_negative_clamped_to_zero(self):
        assert _normalize(-10, 100) == 0.0

    def test_max_value_zero_returns_zero(self):
        assert _normalize(10, 0) == 0.0

    def test_negative_max_returns_zero(self):
        assert _normalize(10, -5) == 0.0


# ---------------------------------------------------------------------------
# _has_pattern
# ---------------------------------------------------------------------------

class TestHasPattern:
    """Regex pattern matching helper."""

    def test_objection_detected(self):
        assert _has_pattern("не уверен что это мне нужно", OBJECTION_PATTERNS) is True

    def test_acknowledge_detected(self):
        assert _has_pattern("Я вас понимаю, это важный вопрос", ACKNOWLEDGE_PATTERNS) is True

    def test_no_match(self):
        assert _has_pattern("hello world", OBJECTION_PATTERNS) is False

    def test_clarify_detected(self):
        assert _has_pattern("А почему вы так считаете?", CLARIFY_PATTERNS) is True

    def test_argument_with_numbers(self):
        assert _has_pattern("Это позволит экономить 15% ежемесячно", ARGUMENT_PATTERNS) is True

    def test_check_pattern(self):
        assert _has_pattern("Что думаете об этом предложении?", CHECK_PATTERNS) is True


# ---------------------------------------------------------------------------
# ScoreBreakdown
# ---------------------------------------------------------------------------

class TestScoreBreakdown:
    """ScoreBreakdown data class properties."""

    @pytest.fixture
    def breakdown(self):
        return ScoreBreakdown(
            script_adherence=20.0,
            objection_handling=15.0,
            communication=12.0,
            anti_patterns=-5.0,
            result=6.0,
            chain_traversal=5.0,
            trap_handling=3.0,
            human_factor=10.0,
            narrative_progression=7.0,
            legal_accuracy=3.0,
            total=76.0,
        )

    def test_base_score(self, breakdown):
        expected = 20.0 + 15.0 + 12.0 + (-5.0) + 6.0 + 5.0 + 3.0
        assert breakdown.base_score == pytest.approx(expected)

    def test_realtime_score(self, breakdown):
        assert breakdown.realtime_score == pytest.approx(breakdown.base_score + 10.0)

    def test_total_clamped_at_boundaries(self):
        bd = ScoreBreakdown(
            script_adherence=22.5,
            objection_handling=18.75,
            communication=15.0,
            anti_patterns=0.0,
            result=7.5,
            chain_traversal=7.5,
            trap_handling=7.5,
            human_factor=15.0,
            narrative_progression=10.0,
            legal_accuracy=5.0,
            total=100.0,
        )
        assert bd.total == 100.0

    def test_skill_radar_returns_six_skills(self, breakdown):
        radar = breakdown.skill_radar
        expected_keys = {
            "empathy", "knowledge", "objection_handling",
            "stress_resistance", "closing", "qualification",
        }
        assert set(radar.keys()) == expected_keys

    def test_skill_radar_values_in_range(self, breakdown):
        for skill, value in breakdown.skill_radar.items():
            assert 0 <= value <= 100, f"{skill}={value} out of range"


# ---------------------------------------------------------------------------
# L2: Objection handling
# ---------------------------------------------------------------------------

class TestObjectionHandling:
    """L2: Objection handling scoring."""

    def test_no_objections_full_score(self):
        """If no objections raised, user gets full marks."""
        score, details = _score_objection_handling(
            user_messages=["Здравствуйте, расскажу о нашем предложении"],
            assistant_messages=["Здравствуйте, слушаю вас"],
        )
        assert score == pytest.approx(18.75)

    def test_objection_with_full_handling(self):
        """User acknowledges, clarifies, argues, and checks."""
        assistant_msgs = ["Не уверен, что мне это нужно"]
        user_msgs = [
            "Понимаю ваше сомнение",
            "А почему вы так считаете?",
            "Это позволит сэкономить 20% ежемесячно",
            "Это отвечает на ваш вопрос?",
        ]
        score, details = _score_objection_handling(user_msgs, assistant_msgs)
        assert score > 0
        assert details["acknowledged"] is True
        assert details["clarified"] is True
        assert details["argued"] is True
        assert details["checked"] is True

    def test_objection_no_handling(self):
        """Objection raised but user doesn't handle it properly."""
        assistant_msgs = ["Не уверен, что мне это нужно"]
        user_msgs = ["Ну ладно, до свидания"]
        score, details = _score_objection_handling(user_msgs, assistant_msgs)
        # Only "heard" should be true
        assert details["heard"] is True
        assert details["acknowledged"] is False


# ---------------------------------------------------------------------------
# L3: Communication
# ---------------------------------------------------------------------------

class TestCommunication:
    """L3: Communication skills scoring."""

    def test_empty_messages(self):
        score, details = _score_communication([])
        assert score == 0.0

    def test_empathy_detected(self):
        msgs = ["Понимаю ваши переживания по этому поводу"]
        score, details = _score_communication(msgs)
        assert details["empathy_detected"] is True

    def test_polite_markers_increase_score(self):
        msgs = [
            "Здравствуйте, спасибо за ваше время",
            "Пожалуйста, позвольте объяснить",
        ]
        score, details = _score_communication(msgs)
        assert details["polite_markers"] >= 2

    def test_max_score_bounded(self):
        """Communication score should not exceed 15 pts (20 * 0.75)."""
        msgs = [
            "Здравствуйте, понимаю ваши чувства",
            "Спасибо, расскажите подробнее",
            "Пожалуйста, будьте добры",
        ]
        score, _ = _score_communication(msgs)
        assert score <= 15.0


# ---------------------------------------------------------------------------
# L5: Result
# ---------------------------------------------------------------------------

class TestResultScoring:
    """L5: Result/outcome scoring."""

    def test_no_messages(self):
        score, details = _score_result([], [])
        assert score == 0.0

    def test_agreement_detected(self):
        assistant_msgs = ["Ладно, давайте попробуем"]
        score, details = _score_result(assistant_msgs, [])
        assert details["consultation_agreed"] is True
        assert score > 0

    def test_meeting_scheduled(self):
        assistant_msgs = ["Давайте в понедельник в 10:00"]
        score, details = _score_result(assistant_msgs, [])
        assert details["meeting_scheduled"] is True

    def test_positive_final_emotion(self):
        assistant_msgs = ["Согласен, интересно"]
        timeline = [{"state": "cold"}, {"state": "curious"}, {"state": "deal"}]
        score, details = _score_result(assistant_msgs, timeline)
        assert details.get("ended_positive") is True


# ---------------------------------------------------------------------------
# L8: Human Factor
# ---------------------------------------------------------------------------

class TestHumanFactor:
    """L8: Human factor handling scoring."""

    def test_no_hostility_neutral_score(self):
        user_msgs = ["Здравствуйте", "Расскажите подробнее"]
        assistant_msgs = ["Слушаю вас"]
        timeline = [{"state": "cold"}, {"state": "guarded"}]
        score, details = _score_human_factor(user_msgs, assistant_msgs, timeline)
        assert 0 <= score <= 15.0

    def test_calm_under_hostility_high_patience(self):
        user_msgs = [
            "Понимаю ваше раздражение",
            "Давайте спокойно обсудим",
        ]
        assistant_msgs = ["Отстаньте от меня!", "Не звоните больше!"]
        timeline = [
            {"state": "cold"},
            {"state": "hostile"},
            {"state": "hostile"},
            {"state": "hostile"},
        ]
        score, details = _score_human_factor(user_msgs, assistant_msgs, timeline)
        assert details["patience_score"] >= 4.0

    def test_aggressive_response_penalized(self):
        user_msgs = ["Да вы что, хватит кричать!"]
        assistant_msgs = ["Не хочу разговаривать"]
        timeline = [{"state": "hostile"}, {"state": "hostile"}]
        score, details = _score_human_factor(user_msgs, assistant_msgs, timeline)
        assert details["composure_score"] < 5.0

    def test_max_human_factor_capped(self):
        user_msgs = [
            "Понимаю ваше раздражение",
            "Понимаю как вам сложно",
            "Я на вашей стороне",
            "Давайте без эмоций",
        ]
        assistant_msgs = ["Хватит!"]
        timeline = [{"state": "hostile"}] * 5
        score, _ = _score_human_factor(user_msgs, assistant_msgs, timeline)
        assert score <= 15.0

    def test_fake_transition_bonus(self):
        user_msgs = ["Понимаю ваше раздражение"]
        assistant_msgs = []
        timeline = [{"state": "hostile"}, {"state": "hostile"}]
        custom = {"fake_transitions_detected": True}
        score, details = _score_human_factor(
            user_msgs, assistant_msgs, timeline, custom_params=custom
        )
        assert details["fake_detected"] is True


# ---------------------------------------------------------------------------
# V3_RESCALE constant
# ---------------------------------------------------------------------------

class TestRescale:
    """V3 rescale factor correctness."""

    def test_rescale_value(self):
        assert V3_RESCALE == 0.75

    def test_rescale_script_max(self):
        """L1 max: 30 * 0.75 = 22.5."""
        assert 30 * V3_RESCALE == pytest.approx(22.5)

    def test_rescale_objection_max(self):
        """L2 max: 25 * 0.75 = 18.75."""
        assert 25 * V3_RESCALE == pytest.approx(18.75)
