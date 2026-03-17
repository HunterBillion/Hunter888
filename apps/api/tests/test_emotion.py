"""Tests for the emotion engine state transitions."""

from app.models.character import EmotionState
from app.services.emotion import TRANSITIONS, get_next_emotion


class TestColdState:
    def test_empathy_warms(self):
        assert get_next_emotion(EmotionState.cold, "empathy") == EmotionState.warming

    def test_facts_warms(self):
        assert get_next_emotion(EmotionState.cold, "facts") == EmotionState.warming

    def test_good_response_warms(self):
        assert get_next_emotion(EmotionState.cold, "good_response") == EmotionState.warming

    def test_pressure_stays_cold(self):
        assert get_next_emotion(EmotionState.cold, "pressure") == EmotionState.cold

    def test_bad_response_stays_cold(self):
        assert get_next_emotion(EmotionState.cold, "bad_response") == EmotionState.cold


class TestWarmingState:
    def test_empathy_opens(self):
        assert get_next_emotion(EmotionState.warming, "empathy") == EmotionState.open

    def test_facts_opens(self):
        assert get_next_emotion(EmotionState.warming, "facts") == EmotionState.open

    def test_good_response_opens(self):
        assert get_next_emotion(EmotionState.warming, "good_response") == EmotionState.open

    def test_pressure_cools(self):
        assert get_next_emotion(EmotionState.warming, "pressure") == EmotionState.cold

    def test_bad_response_cools(self):
        assert get_next_emotion(EmotionState.warming, "bad_response") == EmotionState.cold


class TestOpenState:
    def test_empathy_stays_open(self):
        assert get_next_emotion(EmotionState.open, "empathy") == EmotionState.open

    def test_facts_stays_open(self):
        assert get_next_emotion(EmotionState.open, "facts") == EmotionState.open

    def test_good_response_stays_open(self):
        assert get_next_emotion(EmotionState.open, "good_response") == EmotionState.open

    def test_pressure_cools_to_warming(self):
        assert get_next_emotion(EmotionState.open, "pressure") == EmotionState.warming

    def test_bad_response_cools_to_warming(self):
        assert get_next_emotion(EmotionState.open, "bad_response") == EmotionState.warming


class TestEdgeCases:
    def test_unknown_trigger_returns_same_state(self):
        assert get_next_emotion(EmotionState.cold, "unknown_trigger") == EmotionState.cold
        assert get_next_emotion(EmotionState.warming, "xyz") == EmotionState.warming
        assert get_next_emotion(EmotionState.open, "foobar") == EmotionState.open

    def test_all_states_in_transitions(self):
        for state in EmotionState:
            assert state in TRANSITIONS

    def test_transitions_cover_all_triggers(self):
        expected = {"empathy", "facts", "good_response", "pressure", "bad_response"}
        for state in EmotionState:
            assert set(TRANSITIONS[state].keys()) == expected
