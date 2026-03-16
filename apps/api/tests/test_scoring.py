from app.models.character import EmotionState
from app.services.emotion import get_next_emotion


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
