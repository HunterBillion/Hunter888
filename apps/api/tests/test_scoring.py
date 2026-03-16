from app.models.character import EmotionState
from app.services.emotion import get_next_emotion
from app.services.scoring import (
    _has_pattern,
    _score_communication,
    _score_emotional_intelligence,
    _score_objection_handling,
    _score_result,
)


def test_emotion_cold_to_warming():
    result = get_next_emotion(EmotionState.cold, "good_response")
    assert result == EmotionState.warming


def test_emotion_cold_stays_cold():
    result = get_next_emotion(EmotionState.cold, "bad_response")
    assert result == EmotionState.cold


def test_emotion_warming_to_open():
    result = get_next_emotion(EmotionState.warming, "good_response")
    assert result == EmotionState.open


def test_emotion_warming_back_to_cold():
    result = get_next_emotion(EmotionState.warming, "bad_response")
    assert result == EmotionState.cold


def test_emotion_open_stays_open():
    result = get_next_emotion(EmotionState.open, "good_response")
    assert result == EmotionState.open


def test_emotion_open_back_to_warming():
    result = get_next_emotion(EmotionState.open, "bad_response")
    assert result == EmotionState.warming


# ── Scoring engine unit tests ──


def test_objection_handling_no_objections():
    """When no objections raised, score should be 100."""
    score, details = _score_objection_handling(
        user_messages=["Здравствуйте, предлагаю вам кредит"],
        assistant_messages=["Расскажите подробнее"],
        pairs=[],
    )
    assert score == 100.0
    assert details["objections_found"] == 0


def test_objection_handling_with_acknowledgement():
    """When objection raised and manager acknowledges, partial score."""
    score, details = _score_objection_handling(
        user_messages=["Я вас понимаю, давайте разберёмся"],
        assistant_messages=["У меня уже есть кредит в другом банке, зачем мне это?"],
        pairs=[],
    )
    assert score >= 40  # heard + acknowledged at minimum
    assert details["heard"] is True
    assert details["acknowledged"] is True


def test_communication_polite():
    """Polite messages should score higher."""
    score, details = _score_communication([
        "Здравствуйте, меня зовут Иван",
        "Спасибо за ваше время",
        "Пожалуйста, обратите внимание на условия",
    ])
    assert score >= 60
    assert details["polite_markers"] >= 2


def test_communication_empty():
    """Empty messages should score 0."""
    score, _ = _score_communication([])
    assert score == 0.0


def test_emotional_intelligence_positive_dynamics():
    """Positive emotion dynamics should score higher."""
    timeline = [
        {"state": "cold", "timestamp": 1.0},
        {"state": "warming", "timestamp": 2.0},
        {"state": "open", "timestamp": 3.0},
    ]
    score, details = _score_emotional_intelligence(
        timeline,
        ["Я вас понимаю, это важно для вас"],
    )
    assert score >= 50
    assert details["emotion_start"] == "cold"
    assert details["emotion_end"] == "open"


def test_emotional_intelligence_negative_dynamics():
    """When emotions go from warming back to cold, score should be lower."""
    timeline = [
        {"state": "warming", "timestamp": 1.0},
        {"state": "cold", "timestamp": 2.0},
    ]
    score, details = _score_emotional_intelligence(
        timeline,
        ["Это не моя проблема, сами виноваты"],
    )
    assert score < 50  # escalation + negative dynamics


def test_result_full_conversation():
    """A full conversation with positive indicators should score well."""
    assistant_msgs = [
        "У меня строительная компания, мы работаем уже 10 лет",
        "А какие условия по кредитной линии?",
        "Ладно, присылайте предложение",
    ]
    score, details = _score_result(assistant_msgs, [], None)
    assert score >= 60
    assert details["completed_conversation"] is True
    assert details["client_revealed_situation"] is True


def test_result_empty():
    """No messages should score 0."""
    score, _ = _score_result([], [], None)
    assert score == 0.0
