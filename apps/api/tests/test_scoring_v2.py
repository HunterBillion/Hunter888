"""Tests for 5-layer scoring engine with TZ weights."""

from app.services.scoring import (
    _has_pattern,
    _score_anti_patterns,
    _score_communication,
    _score_objection_handling,
    _score_result,
    ANTI_PATTERNS,
)


class TestAntiPatterns:
    def test_false_promises_detected(self):
        msgs = ["Я вам гарантирую 100% списание всех долгов!"]
        penalty, details = _score_anti_patterns(msgs)
        assert penalty > 0
        assert "false_promises" in details.get("detected", []) or details.get("penalty", 0) > 0

    def test_intimidation_detected(self):
        msgs = ["Если вы не согласитесь, вас посадят в тюрьму"]
        penalty, details = _score_anti_patterns(msgs)
        assert penalty > 0

    def test_rudeness_detected(self):
        msgs = ["Вы сами виноваты в своих проблемах, дурак"]
        penalty, details = _score_anti_patterns(msgs)
        assert penalty > 0

    def test_incorrect_info_detected(self):
        msgs = ["Банкротство абсолютно бесплатно, ничего платить не нужно"]
        penalty, details = _score_anti_patterns(msgs)
        assert penalty > 0

    def test_clean_text_no_penalty(self):
        msgs = ["Здравствуйте, давайте разберём вашу ситуацию подробнее"]
        penalty, details = _score_anti_patterns(msgs)
        assert penalty == 0

    def test_penalty_capped_at_15(self):
        msgs = [
            "Гарантирую 100% списание",
            "Вас посадят если откажетесь",
            "Дурак, сами виноваты",
            "Банкротство бесплатно",
        ]
        penalty, _ = _score_anti_patterns(msgs)
        assert penalty <= 15


class TestCommunication:
    def test_polite_scores_high(self):
        msgs = [
            "Здравствуйте, меня зовут Иван",
            "Спасибо за ваше время",
            "Пожалуйста, расскажите подробнее",
        ]
        score, details = _score_communication(msgs)
        assert score >= 50
        assert details["polite_markers"] >= 2

    def test_empty_scores_zero(self):
        score, _ = _score_communication([])
        assert score == 0.0


class TestObjectionHandling:
    def test_no_objections_full_score(self):
        score, details = _score_objection_handling(
            user_messages=["Здравствуйте"],
            assistant_messages=["Добрый день"],
            pairs=[],
        )
        assert score == 100.0
        assert details["objections_found"] == 0

    def test_acknowledged_objection(self):
        score, details = _score_objection_handling(
            user_messages=["Я вас понимаю, давайте разберёмся"],
            assistant_messages=["Зачем мне это, у меня уже есть кредит"],
            pairs=[],
        )
        assert score >= 30
        assert details["heard"] is True


class TestResult:
    def test_completed_conversation(self):
        assistant_msgs = [
            "У меня строительная компания",
            "Какие условия?",
            "Ладно, присылайте предложение",
        ]
        score, details = _score_result(assistant_msgs, [], None)
        assert score >= 40
        assert details["completed_conversation"] is True

    def test_empty_scores_zero(self):
        score, _ = _score_result([], [], None)
        assert score == 0.0


class TestHasPattern:
    def test_finds_pattern(self):
        assert _has_pattern("не уверен в этом", [r"не\s*уверен"]) is True

    def test_no_match(self):
        assert _has_pattern("всё хорошо", [r"не\s*уверен"]) is False
