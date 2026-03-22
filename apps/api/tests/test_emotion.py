"""Tests for the 5-state emotion engine transitions."""

from app.models.character import EmotionState
from app.services.emotion import TRANSITIONS, get_next_emotion


class TestColdState:
    def test_empathy_to_skeptical(self):
        assert get_next_emotion(EmotionState.cold, "empathy") == EmotionState.skeptical

    def test_facts_to_skeptical(self):
        assert get_next_emotion(EmotionState.cold, "facts") == EmotionState.skeptical

    def test_good_response_to_skeptical(self):
        assert get_next_emotion(EmotionState.cold, "good_response") == EmotionState.skeptical

    def test_pressure_stays_cold(self):
        assert get_next_emotion(EmotionState.cold, "pressure") == EmotionState.cold

    def test_bad_response_stays_cold(self):
        assert get_next_emotion(EmotionState.cold, "bad_response") == EmotionState.cold


class TestSkepticalState:
    def test_empathy_to_warming(self):
        assert get_next_emotion(EmotionState.skeptical, "empathy") == EmotionState.warming

    def test_facts_to_warming(self):
        assert get_next_emotion(EmotionState.skeptical, "facts") == EmotionState.warming

    def test_good_response_to_warming(self):
        assert get_next_emotion(EmotionState.skeptical, "good_response") == EmotionState.warming

    def test_pressure_to_cold(self):
        assert get_next_emotion(EmotionState.skeptical, "pressure") == EmotionState.cold

    def test_bad_response_to_cold(self):
        assert get_next_emotion(EmotionState.skeptical, "bad_response") == EmotionState.cold


class TestWarmingState:
    def test_empathy_to_open(self):
        assert get_next_emotion(EmotionState.warming, "empathy") == EmotionState.open

    def test_facts_to_open(self):
        assert get_next_emotion(EmotionState.warming, "facts") == EmotionState.open

    def test_good_response_to_open(self):
        assert get_next_emotion(EmotionState.warming, "good_response") == EmotionState.open

    def test_pressure_to_skeptical(self):
        assert get_next_emotion(EmotionState.warming, "pressure") == EmotionState.skeptical

    def test_bad_response_to_skeptical(self):
        assert get_next_emotion(EmotionState.warming, "bad_response") == EmotionState.skeptical


class TestOpenState:
    def test_empathy_to_deal(self):
        assert get_next_emotion(EmotionState.open, "empathy") == EmotionState.deal

    def test_facts_to_deal(self):
        assert get_next_emotion(EmotionState.open, "facts") == EmotionState.deal

    def test_good_response_to_deal(self):
        assert get_next_emotion(EmotionState.open, "good_response") == EmotionState.deal

    def test_pressure_to_warming(self):
        assert get_next_emotion(EmotionState.open, "pressure") == EmotionState.warming

    def test_bad_response_to_warming(self):
        assert get_next_emotion(EmotionState.open, "bad_response") == EmotionState.warming


class TestDealState:
    def test_empathy_stays_deal(self):
        assert get_next_emotion(EmotionState.deal, "empathy") == EmotionState.deal

    def test_facts_stays_deal(self):
        assert get_next_emotion(EmotionState.deal, "facts") == EmotionState.deal

    def test_good_response_stays_deal(self):
        assert get_next_emotion(EmotionState.deal, "good_response") == EmotionState.deal

    def test_pressure_to_open(self):
        assert get_next_emotion(EmotionState.deal, "pressure") == EmotionState.open

    def test_bad_response_to_open(self):
        assert get_next_emotion(EmotionState.deal, "bad_response") == EmotionState.open


class TestEdgeCases:
    def test_unknown_trigger_returns_same_state(self):
        for state in EmotionState:
            assert get_next_emotion(state, "unknown_trigger") == state

    def test_all_5_states_in_transitions(self):
        assert len(TRANSITIONS) == 5
        for state in EmotionState:
            assert state in TRANSITIONS

    def test_transitions_cover_all_triggers(self):
        expected = {"empathy", "facts", "good_response", "pressure", "bad_response"}
        for state in EmotionState:
            assert set(TRANSITIONS[state].keys()) == expected
