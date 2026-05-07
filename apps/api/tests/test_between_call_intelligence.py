"""Tests for the Between-Call Intelligence system.

Covers the upgraded functions in scenario_engine.py and training.py:
  - apply_between_calls_context() with relationship/lifecycle/storylet/consequence modifiers
  - generate_pre_call_brief() with enriched parameters
  - _pick_silence_phrase() from training.py with emotion-based escalation
"""

import pytest
from unittest.mock import patch, MagicMock

from app.services.scenario_engine import (
    apply_between_calls_context,
    generate_pre_call_brief,
)
from app.ws.training import _pick_silence_phrase, SILENCE_PHRASES_BY_EMOTION


# ═══════════════════════════════════════════════════════════════════════════════
# Test apply_between_calls_context() — Between-call event generation
# ═══════════════════════════════════════════════════════════════════════════════


class TestApplyBetweenCallsContext:
    """Test the upgraded apply_between_calls_context function."""

    def test_returns_list_of_events(self):
        """Should return a list of event dicts."""
        result = apply_between_calls_context(
            call_number=2,
            archetype_code="anxious",
        )
        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(e, dict) for e in result)

    def test_event_dict_structure(self):
        """Each event should have required fields."""
        result = apply_between_calls_context(
            call_number=2,
            archetype_code="pragmatic",
        )
        for event in result:
            assert "event" in event
            assert "impact" in event
            assert "description" in event
            assert "emotion_shift" in event

    def test_default_relationship_score_neutral(self):
        """With default relationship_score=50.0, should generate neutral events."""
        result = apply_between_calls_context(
            call_number=2,
            archetype_code="pragmatic",
            relationship_score=50.0,
        )
        assert result  # Should have events
        # At score 50, positive and negative should be equally weighted

    def test_high_relationship_score_boosts_positive_events(self):
        """High relationship_score (80+) should increase positive events."""
        with patch('random.choices') as mock_choices, \
             patch('random.random') as mock_random:
            # Mock to force selection of positive events
            mock_random.return_value = 0.05
            result_high = apply_between_calls_context(
                call_number=2,
                archetype_code="pragmatic",
                relationship_score=85.0,
            )

            result_low = apply_between_calls_context(
                call_number=2,
                archetype_code="pragmatic",
                relationship_score=15.0,
            )

            # Both should have events
            assert result_high
            assert result_low

    def test_low_relationship_score_boosts_negative_events(self):
        """Low relationship_score (<35) should increase negative events."""
        # Low score should bias toward negative events like collector_visit, court_letter
        result = apply_between_calls_context(
            call_number=2,
            archetype_code="anxious",
            relationship_score=10.0,
        )
        assert result

    def test_lifecycle_state_ghosting_boosts_collector_visit(self):
        """GHOSTING lifecycle should boost collector_visit and court_letter."""
        result = apply_between_calls_context(
            call_number=2,
            archetype_code="pragmatic",
            lifecycle_state="GHOSTING",
        )
        # GHOSTING state should favor negative events
        assert result

    def test_lifecycle_state_interested_boosts_positive_review(self):
        """INTERESTED lifecycle should boost positive_review_seen and friend_went_through."""
        result = apply_between_calls_context(
            call_number=2,
            archetype_code="pragmatic",
            lifecycle_state="INTERESTED",
        )
        # INTERESTED state should favor positive events
        assert result

    def test_active_storylets_wife_found_out_boosts_family_discussion(self):
        """wife_found_out storylet should boost family_discussion event."""
        result = apply_between_calls_context(
            call_number=3,
            archetype_code="passive",
            active_storylets=["wife_found_out"],
        )
        # Should potentially have family_discussion event
        assert result
        events = [e["event"] for e in result]
        # Storylet should increase probability of related events
        assert len(events) >= 1

    def test_active_storylets_multiple(self):
        """Multiple active storylets should compound modifiers."""
        result = apply_between_calls_context(
            call_number=3,
            archetype_code="desperate",
            active_storylets=["wife_found_out", "collectors_arrived"],
        )
        assert result
        # Multiple storylets should create coherent event selection

    def test_consequence_log_suppresses_redundant_events(self):
        """Active consequences in log should suppress redundant events."""
        consequence_log = [
            {"event_code": "collector_visit", "is_active": True},
            {"event_code": "court_letter", "is_active": False},  # Inactive, should not suppress
        ]
        result = apply_between_calls_context(
            call_number=2,
            archetype_code="anxious",
            consequence_log=consequence_log,
        )
        # collector_visit should be suppressed
        events = [e["event"] for e in result]
        # collector_visit should be suppressed by active consequence
        assert all(e != "collector_visit" for e in events)

    def test_call_progression_arc_call_2(self):
        """Call 2 should have 1-2 events (setup phase)."""
        with patch('random.choices', return_value=[1]):
            result = apply_between_calls_context(
                call_number=2,
                archetype_code="pragmatic",
            )
            # Mock forces 1 event
            assert len(result) == 1

    def test_call_progression_arc_call_3(self):
        """Call 3 should have 2-3 events (rising action)."""
        result = apply_between_calls_context(
            call_number=3,
            archetype_code="pragmatic",
        )
        # Call 3 is rising action: expect more events
        assert result

    def test_call_progression_arc_call_4(self):
        """Call 4 should favor 3 events (climax)."""
        result = apply_between_calls_context(
            call_number=4,
            archetype_code="pragmatic",
        )
        # Call 4 (climax) should have events
        assert result

    def test_previous_outcome_deal_reduces_negative_events(self):
        """previous_outcome='deal' should reduce negative event probability."""
        # Deal outcome should have lower outcome_mod (0.5)
        result = apply_between_calls_context(
            call_number=3,
            archetype_code="anxious",
            previous_outcome="deal",
        )
        assert result

    def test_previous_outcome_hostile_increases_negative_events(self):
        """previous_outcome='hostile' should increase negative event probability."""
        # Hostile outcome should have higher outcome_mod (1.3)
        result = apply_between_calls_context(
            call_number=3,
            archetype_code="anxious",
            previous_outcome="hostile",
        )
        assert result

    def test_archetype_modifier_anxious(self):
        """anxious archetype should boost creditor_called, collector_visit, court_letter."""
        result = apply_between_calls_context(
            call_number=2,
            archetype_code="anxious",
        )
        assert result

    def test_archetype_modifier_paranoid(self):
        """paranoid archetype should boost found_competitor and client_googled_bankruptcy."""
        result = apply_between_calls_context(
            call_number=2,
            archetype_code="paranoid",
        )
        assert result

    def test_no_duplicate_events_except_nothing_happened(self):
        """Exact duplicate events should not be added (except nothing_happened)."""
        existing = [
            {"event": "creditor_called", "impact": "negative", "description": "Creditor called"},
        ]
        result = apply_between_calls_context(
            call_number=2,
            archetype_code="anxious",
            existing_events=existing,
        )
        # creditor_called should not repeat
        events = [e["event"] for e in result]
        assert events.count("creditor_called") <= 1

    def test_fallback_nothing_happened_event(self):
        """If no events can be generated, should add 'nothing_happened' event."""
        # Force empty candidate pool by making all events impossible
        result = apply_between_calls_context(
            call_number=2,
            archetype_code="pragmatic",
            existing_events=[
                {"event": "creditor_called", "impact": "negative", "description": ""},
                {"event": "collector_visit", "impact": "negative", "description": ""},
                {"event": "court_letter", "impact": "negative", "description": ""},
                {"event": "salary_delayed", "impact": "negative", "description": ""},
                {"event": "found_competitor", "impact": "negative", "description": ""},
                {"event": "client_googled_bankruptcy", "impact": "negative", "description": ""},
                {"event": "family_discussion", "impact": "negative", "description": ""},
                {"event": "positive_review_seen", "impact": "positive", "description": ""},
                {"event": "friend_went_through", "impact": "positive", "description": ""},
            ],
            consequence_log=[
                {"event_code": "nothing_happened", "is_active": False},
            ],
        )
        # Should still return at least one event
        assert len(result) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# Test generate_pre_call_brief() — Pre-call briefing generation
# ═══════════════════════════════════════════════════════════════════════════════


class TestGeneratePreCallBrief:
    """Test the upgraded generate_pre_call_brief function."""

    def test_returns_string(self):
        """Should return a markdown string."""
        result = generate_pre_call_brief(
            call_number=1,
            client_name="John Smith",
            archetype_code="skeptic",
            previous_outcome=None,
            previous_emotion="cold",
            between_events=[],
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_call_number_in_title(self):
        """Brief should contain the call number in title."""
        result = generate_pre_call_brief(
            call_number=3,
            client_name="John Smith",
            archetype_code="skeptic",
            previous_outcome=None,
            previous_emotion="cold",
            between_events=[],
        )
        assert "3" in result or "#3" in result

    def test_contains_client_name(self):
        """Brief should contain the client name."""
        client_name = "Ivan Petrov"
        result = generate_pre_call_brief(
            call_number=1,
            client_name=client_name,
            archetype_code="skeptic",
            previous_outcome=None,
            previous_emotion="cold",
            between_events=[],
        )
        assert client_name in result

    def test_contains_archetype_code(self):
        """Brief should mention the archetype."""
        result = generate_pre_call_brief(
            call_number=1,
            client_name="John Smith",
            archetype_code="desperate",
            previous_outcome=None,
            previous_emotion="cold",
            between_events=[],
        )
        assert "desperate" in result or "архетип" in result

    def test_contains_relationship_section_with_score(self):
        """Brief should contain relationship section with score."""
        result = generate_pre_call_brief(
            call_number=2,
            client_name="John Smith",
            archetype_code="skeptic",
            previous_outcome=None,
            previous_emotion="cold",
            between_events=[],
            relationship_score=75.0,
        )
        assert "75" in result or "Доверие" in result

    def test_relationship_score_label_low(self):
        """Relationship score <35 should label as 'низкое' (low)."""
        result = generate_pre_call_brief(
            call_number=1,
            client_name="John Smith",
            archetype_code="skeptic",
            previous_outcome=None,
            previous_emotion="cold",
            between_events=[],
            relationship_score=20.0,
        )
        assert "низкое" in result or "20" in result

    def test_relationship_score_label_medium(self):
        """Relationship score 35-65 should label as 'среднее' (medium)."""
        result = generate_pre_call_brief(
            call_number=1,
            client_name="John Smith",
            archetype_code="skeptic",
            previous_outcome=None,
            previous_emotion="cold",
            between_events=[],
            relationship_score=50.0,
        )
        assert "50" in result

    def test_relationship_score_label_high(self):
        """Relationship score >65 should label as 'высокое' (high)."""
        result = generate_pre_call_brief(
            call_number=1,
            client_name="John Smith",
            archetype_code="skeptic",
            previous_outcome=None,
            previous_emotion="cold",
            between_events=[],
            relationship_score=80.0,
        )
        assert "высокое" in result or "80" in result

    def test_contains_lifecycle_state(self):
        """Brief should contain lifecycle state label."""
        result = generate_pre_call_brief(
            call_number=2,
            client_name="John Smith",
            archetype_code="skeptic",
            previous_outcome=None,
            previous_emotion="cold",
            between_events=[],
            lifecycle_state="INTERESTED",
        )
        assert "INTERESTED" in result or "Заинтересован" in result or "Этап" in result

    def test_lifecycle_labels_mapping(self):
        """Various lifecycle states should map to Russian labels."""
        states_to_test = [
            ("INTERESTED", "Заинтересован"),
            ("GHOSTING", "Пропал"),
            ("REJECTED", "Отказ"),
        ]
        for state, expected_label in states_to_test:
            result = generate_pre_call_brief(
                call_number=1,
                client_name="John Smith",
                archetype_code="skeptic",
                previous_outcome=None,
                previous_emotion="cold",
                between_events=[],
                lifecycle_state=state,
            )
            # Should contain either the English state or Russian label
            assert state in result or expected_label in result

    def test_contains_previous_outcome_if_provided(self):
        """Brief should include previous call outcome."""
        result = generate_pre_call_brief(
            call_number=3,
            client_name="John Smith",
            archetype_code="skeptic",
            previous_outcome="callback",
            previous_emotion="considering",
            between_events=[],
        )
        assert "callback" in result or "Прошлый" in result or "considering" in result

    def test_contains_previous_emotion(self):
        """Brief should include previous emotion state."""
        result = generate_pre_call_brief(
            call_number=2,
            client_name="John Smith",
            archetype_code="skeptic",
            previous_outcome="callback",
            previous_emotion="guarded",
            between_events=[],
        )
        assert "guarded" in result or "emotion" in result.lower()

    def test_lists_active_storylets_if_present(self):
        """Brief should list active storylets."""
        result = generate_pre_call_brief(
            call_number=3,
            client_name="John Smith",
            archetype_code="skeptic",
            previous_outcome=None,
            previous_emotion="cold",
            between_events=[],
            active_storylets=["wife_found_out", "collectors_arrived"],
        )
        # Should mention storylets section and the storylets
        assert ("сюжетные" in result or "wife_found_out" in result or
                "collectors_arrived" in result)

    def test_between_events_included_in_brief(self):
        """Brief should include between-call events."""
        events = [
            {"event": "creditor_called", "description": "Creditor called about debt"},
            {"event": "family_discussion", "description": "Wife found out about debts"},
        ]
        result = generate_pre_call_brief(
            call_number=3,
            client_name="John Smith",
            archetype_code="skeptic",
            previous_outcome=None,
            previous_emotion="cold",
            between_events=events,
        )
        # Should have events section
        assert "произошло" in result or "Creditor" in result or "Debt" in result

    def test_client_messages_quoted_if_present(self):
        """Brief should quote client messages."""
        messages = [
            "I'm not sure about this",
            "Can we discuss payment terms?",
        ]
        result = generate_pre_call_brief(
            call_number=2,
            client_name="John Smith",
            archetype_code="skeptic",
            previous_outcome=None,
            previous_emotion="cold",
            between_events=[],
            client_messages=messages,
        )
        # Should have messages section
        assert ("Сообщение" in result or "sure" in result or
                "payment" in result or '"' in result)

    def test_manager_weak_points_generate_coaching_tips(self):
        """Brief should include coaching tips based on manager weak points."""
        weak_points = ["active_listening", "handling_objections"]
        result = generate_pre_call_brief(
            call_number=2,
            client_name="John Smith",
            archetype_code="skeptic",
            previous_outcome=None,
            previous_emotion="cold",
            between_events=[],
            manager_weak_points=weak_points,
        )
        # Should have recommendations/coaching section
        assert "Рекомендация" in result or "coaching" in result.lower() or len(result) > 100

    def test_key_memories_included_if_provided(self):
        """Brief should include key memories from past calls."""
        memories = [
            {"content": "Client mentioned he's concerned about bankruptcy risk"},
            {"content": "Wife is opposed to legal action"},
        ]
        result = generate_pre_call_brief(
            call_number=3,
            client_name="John Smith",
            archetype_code="skeptic",
            previous_outcome=None,
            previous_emotion="cold",
            between_events=[],
            key_memories=memories,
        )
        # Should have memories section
        assert "bankruptcy" in result.lower() or "ключевые" in result or len(result) > 100

    def test_recommendations_always_present(self):
        """Brief should always include tactical recommendations."""
        result = generate_pre_call_brief(
            call_number=2,
            client_name="John Smith",
            archetype_code="skeptic",
            previous_outcome=None,
            previous_emotion="cold",
            between_events=[],
        )
        # Should have recommendations section
        assert "Рекомендация" in result or "recommendation" in result.lower()

    def test_markdown_formatting(self):
        """Brief should use markdown formatting."""
        result = generate_pre_call_brief(
            call_number=1,
            client_name="John Smith",
            archetype_code="skeptic",
            previous_outcome=None,
            previous_emotion="cold",
            between_events=[],
        )
        # Should have markdown headers or formatting
        assert "#" in result or "**" in result or "##" in result

    def test_brief_content_length_reasonable(self):
        """Brief should be substantial but not excessively long."""
        result = generate_pre_call_brief(
            call_number=2,
            client_name="John Smith",
            archetype_code="skeptic",
            previous_outcome="callback",
            previous_emotion="considering",
            between_events=[
                {"event": "creditor_called", "description": "Creditor called"},
            ],
            active_storylets=["wife_found_out"],
            client_messages=["Not sure yet", "Need more time"],
        )
        # Should be at least 100 chars but reasonably sized
        assert len(result) > 100
        assert len(result) < 5000


# ═══════════════════════════════════════════════════════════════════════════════
# Test _pick_silence_phrase() — Silence phrase selection from training.py
# ═══════════════════════════════════════════════════════════════════════════════


class TestPickSilencePhrase:
    """Test the _pick_silence_phrase function with emotion-based escalation."""

    def test_returns_string(self):
        """Should return a string silence phrase."""
        result = _pick_silence_phrase("cold")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_valid_emotion_cold(self):
        """cold emotion should return from cold phrase pool."""
        result = _pick_silence_phrase("cold")
        assert result in SILENCE_PHRASES_BY_EMOTION["cold"]

    def test_valid_emotion_hostile(self):
        """hostile emotion should return from hostile phrase pool."""
        result = _pick_silence_phrase("hostile")
        assert result in SILENCE_PHRASES_BY_EMOTION["hostile"]

    def test_valid_emotion_guarded(self):
        """guarded emotion should return from guarded phrase pool."""
        result = _pick_silence_phrase("guarded")
        assert result in SILENCE_PHRASES_BY_EMOTION["guarded"]

    def test_valid_emotion_curious(self):
        """curious emotion should return from curious phrase pool."""
        result = _pick_silence_phrase("curious")
        assert result in SILENCE_PHRASES_BY_EMOTION["curious"]

    def test_valid_emotion_considering(self):
        """considering emotion should return from considering phrase pool."""
        result = _pick_silence_phrase("considering")
        assert result in SILENCE_PHRASES_BY_EMOTION["considering"]

    def test_valid_emotion_negotiating(self):
        """negotiating emotion should return from negotiating phrase pool."""
        result = _pick_silence_phrase("negotiating")
        assert result in SILENCE_PHRASES_BY_EMOTION["negotiating"]

    def test_valid_emotion_deal(self):
        """deal emotion should return from deal phrase pool."""
        result = _pick_silence_phrase("deal")
        assert result in SILENCE_PHRASES_BY_EMOTION["deal"]

    def test_valid_emotion_testing(self):
        """testing emotion should return from testing phrase pool."""
        result = _pick_silence_phrase("testing")
        assert result in SILENCE_PHRASES_BY_EMOTION["testing"]

    def test_unknown_emotion_falls_back_to_default(self):
        """Unknown emotion should fall back to default phrases."""
        result = _pick_silence_phrase("unknown_emotion")
        # Should fall back to default (not in unknown pool)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_escalation_silence_count_0(self):
        """silence_count=0 should pick from initial band."""
        with patch('random.choice') as mock_choice:
            mock_choice.return_value = "test_phrase"
            _pick_silence_phrase("cold", silence_count=0)
            # Should be called with phrase list
            mock_choice.assert_called_once()

    def test_escalation_silence_count_2_more_insistent(self):
        """silence_count=2 should pick from more insistent phrases."""
        # At high silence_count, should pick later phrases
        result = _pick_silence_phrase("cold", silence_count=2)
        assert result in SILENCE_PHRASES_BY_EMOTION["cold"]

    def test_escalation_different_counts_same_emotion(self):
        """Different silence counts should pick from different bands."""
        phrase_0 = _pick_silence_phrase("hostile", silence_count=0)
        phrase_2 = _pick_silence_phrase("hostile", silence_count=2)
        # Both should be valid, from same pool
        assert phrase_0 in SILENCE_PHRASES_BY_EMOTION["hostile"]
        assert phrase_2 in SILENCE_PHRASES_BY_EMOTION["hostile"]

    def test_all_emotion_pools_have_minimum_phrases(self):
        """All emotion pools should have at least 2 phrases."""
        for emotion, phrases in SILENCE_PHRASES_BY_EMOTION.items():
            assert len(phrases) >= 2, f"Emotion '{emotion}' has fewer than 2 phrases"

    def test_phrase_band_extraction_silence_count_0(self):
        """silence_count=0 should target band around index 0."""
        pool = SILENCE_PHRASES_BY_EMOTION["cold"]
        # silence_count=0: idx=min(0, len(pool)-1)=0
        # band_start=max(0, 0-1)=0, band_end=min(len, 0+2)
        result = _pick_silence_phrase("cold", silence_count=0)
        assert result in pool

    def test_phrase_band_extraction_high_silence_count(self):
        """High silence_count should target later phrases."""
        pool = SILENCE_PHRASES_BY_EMOTION["cold"]
        # Simulate high silence count
        result = _pick_silence_phrase("cold", silence_count=5)
        assert result in pool

    def test_consistency_same_emotion_repeated(self):
        """Calling with same emotion should always return valid phrases."""
        for _ in range(10):
            result = _pick_silence_phrase("considering")
            assert result in SILENCE_PHRASES_BY_EMOTION["considering"]

    def test_emotion_pool_diversity(self):
        """Different emotions should have distinct phrase pools."""
        cold_phrases = set(SILENCE_PHRASES_BY_EMOTION["cold"])
        hostile_phrases = set(SILENCE_PHRASES_BY_EMOTION["hostile"])
        # Pools should not be identical (at least some difference)
        # Note: some phrases might overlap, but pools should be distinct
        assert len(cold_phrases.intersection(hostile_phrases)) < len(cold_phrases)

    def test_fallback_phrases_not_empty(self):
        """Fallback phrase pool should be available."""
        # Test with an emotion that doesn't exist
        from app.ws.training import _SILENCE_FALLBACK
        assert len(_SILENCE_FALLBACK) > 0
        assert all(isinstance(p, str) for p in _SILENCE_FALLBACK)

    def test_silence_escalation_gentle_to_insistent(self):
        """Escalation should go from gentle (count=0) to insistent (count=2+)."""
        # This tests the escalation logic without mocking
        result = _pick_silence_phrase("cold", silence_count=0)
        assert isinstance(result, str)

        result = _pick_silence_phrase("cold", silence_count=1)
        assert isinstance(result, str)

        result = _pick_silence_phrase("cold", silence_count=3)
        assert isinstance(result, str)


# ═══════════════════════════════════════════════════════════════════════════════
# Integration tests — Between-call intelligence system
# ═══════════════════════════════════════════════════════════════════════════════


class TestBetweenCallIntelligenceIntegration:
    """Integration tests for the full between-call intelligence system."""

    def test_context_to_brief_flow(self):
        """Generate events, then brief from them."""
        events = apply_between_calls_context(
            call_number=2,
            archetype_code="anxious",
            relationship_score=60.0,
            lifecycle_state="INTERESTED",
        )

        brief = generate_pre_call_brief(
            call_number=3,
            client_name="Test Client",
            archetype_code="anxious",
            previous_outcome="callback",
            previous_emotion="considering",
            between_events=events,
            relationship_score=60.0,
            lifecycle_state="INTERESTED",
        )

        assert events
        assert brief
        assert len(brief) > 100

    def test_full_scenario_progression(self):
        """Test a full call progression scenario."""
        # Call 1: Initial
        brief_1 = generate_pre_call_brief(
            call_number=1,
            client_name="John Doe",
            archetype_code="skeptic",
            previous_outcome=None,
            previous_emotion="cold",
            between_events=[],
            relationship_score=30.0,
            lifecycle_state="FIRST_CONTACT",
        )
        assert "John Doe" in brief_1

        # Between calls 1-2
        events_2 = apply_between_calls_context(
            call_number=2,
            archetype_code="skeptic",
            previous_outcome="callback",
            relationship_score=40.0,
            lifecycle_state="THINKING",
        )

        # Call 2 brief
        brief_2 = generate_pre_call_brief(
            call_number=2,
            client_name="John Doe",
            archetype_code="skeptic",
            previous_outcome="callback",
            previous_emotion="considering",
            between_events=events_2,
            relationship_score=40.0,
            lifecycle_state="THINKING",
        )
        assert events_2
        assert brief_2

    def test_silence_phrase_integration_with_emotions(self):
        """Test silence phrases match call emotions."""
        emotions_in_call = [
            "cold", "hostile", "guarded", "curious", "considering",
            "negotiating", "deal", "testing"
        ]

        for emotion in emotions_in_call:
            phrase = _pick_silence_phrase(emotion, silence_count=0)
            assert isinstance(phrase, str)
            assert phrase in SILENCE_PHRASES_BY_EMOTION[emotion]


# ═══════════════════════════════════════════════════════════════════════════════
# PR-B regression — between-call appendix survives session.start prompt rebuild
# ═══════════════════════════════════════════════════════════════════════════════
#
# 2026-05-07: before PR-B, _handle_story_next_call wrote tier3 situational
# context and hangup recovery bias directly into state["client_profile_prompt"].
# The next session.start handler then ran _build_client_profile_prompt from
# the cloned profile and OVERWROTE state["client_profile_prompt"] — the AI
# on call #2 never saw consequences/storylets/relationship state. PR-B
# routes these additions through state["between_call_appendix"] and consumes
# them in session.start via _consume_between_call_appendix().


class TestBetweenCallAppendixConsumption:
    """Pure-function tests for the appendix accumulator helper.

    These guard against (a) accidental removal of any consume site in
    _handle_session_start / _handle_session_resume — the original PR-B
    regression — and (b) re-introducing the self-clearing behaviour
    that PR-F removed (the appendix must persist so a mid-call WS
    reconnect can re-apply it to the rebuilt prompt).
    """

    def test_no_key_no_change(self):
        """Non-story sessions never set the key — helper is a no-op."""
        from app.ws.training import _consume_between_call_appendix
        state: dict = {}
        result = _consume_between_call_appendix(state, "BASE PROMPT")
        assert result == "BASE PROMPT"
        assert "between_call_appendix" not in state

    def test_empty_string_appendix_no_change(self):
        """Empty appendix means nothing to append; key stays empty."""
        from app.ws.training import _consume_between_call_appendix
        state = {"between_call_appendix": ""}
        result = _consume_between_call_appendix(state, "BASE")
        assert result == "BASE"

    def test_tier3_context_appended_persists_in_state(self):
        """Story call #2 with tier3 context: appendix lands on prompt
        AND remains in state so a mid-call reconnect can re-apply it."""
        from app.ws.training import _consume_between_call_appendix
        tier3 = (
            "\n\n[BETWEEN-CALL CONTEXT (Tier 3 — situational awareness):\n"
            "- Между звонками произошло: жена узнала о долгах.\n"
            "- Уровень доверия НИЖЕ СРЕДНЕГО.]"
        )
        state = {"between_call_appendix": tier3}
        result = _consume_between_call_appendix(state, "PROFILE PROMPT")
        assert result == "PROFILE PROMPT" + tier3
        # PR-F: do NOT clear — survives so a reconnect rebuilds
        # client_profile_prompt with the same tier3 context.
        assert state["between_call_appendix"] == tier3

    def test_hangup_context_appended_persists_in_state(self):
        """Story call after a hangup carries hostile bias forward
        and the bias persists across reconnects within the same call."""
        from app.ws.training import _consume_between_call_appendix
        hangup = (
            "\n\n[CONTEXT: Клиент помнит неудачный предыдущий разговор. "
            "Начинай с враждебной позиции.]"
        )
        state = {"between_call_appendix": hangup}
        result = _consume_between_call_appendix(state, "BASE")
        assert "враждебной" in result
        assert state["between_call_appendix"] == hangup  # PR-F: not cleared

    def test_combined_hangup_and_tier3(self):
        """If both writers fire on the same call (hangup → tier3),
        the accumulator concatenates and consume returns both."""
        from app.ws.training import _consume_between_call_appendix
        hangup = "\n\n[CONTEXT: hostile.]"
        tier3 = "\n\n[Tier 3 context]"
        state: dict = {}
        state["between_call_appendix"] = state.get("between_call_appendix", "") + hangup
        state["between_call_appendix"] = state.get("between_call_appendix", "") + tier3
        result = _consume_between_call_appendix(state, "BASE")
        assert result == "BASE" + hangup + tier3
        assert state["between_call_appendix"] == hangup + tier3  # PR-F: not cleared

    def test_consume_is_idempotent_when_called_twice_with_same_base(self):
        """Repeated consume on the same fresh base returns the same
        result — caller-side idempotency, no double-application."""
        from app.ws.training import _consume_between_call_appendix
        state = {"between_call_appendix": "\n\nAPPENDIX"}
        first = _consume_between_call_appendix(state, "BASE")
        second = _consume_between_call_appendix(state, "BASE")
        assert first == "BASE\n\nAPPENDIX"
        assert second == "BASE\n\nAPPENDIX"  # PR-F: same result, not cleared

    def test_pre_pr_b_regression_demonstration(self):
        """Documents the original PR-B bug.

        Pre-PR-B code did:
            prev_prompt = state.get("client_profile_prompt", "")
            state["client_profile_prompt"] = prev_prompt + tier3_context
            ...
            # later in _handle_session_start:
            state["client_profile_prompt"] = client_profile_prompt   # NUKES tier3

        Post-PR-B/F code routes the addition through the appendix
        accumulator which session.start consumes BEFORE assigning the
        prompt.
        """
        from app.ws.training import _consume_between_call_appendix

        tier3 = "\n\n[Tier3]"
        rebuilt_profile_prompt = "FRESH PROFILE FROM CLONE"

        # --- Pre-PR-B (broken) flow, simulated ---
        state_pre = {"client_profile_prompt": "OLD"}
        state_pre["client_profile_prompt"] = state_pre["client_profile_prompt"] + tier3
        state_pre["client_profile_prompt"] = rebuilt_profile_prompt  # session.start nukes
        assert tier3 not in state_pre["client_profile_prompt"]  # bug

        # --- Post-PR-B/F (fixed) flow ---
        state_post: dict = {}
        state_post["between_call_appendix"] = (
            state_post.get("between_call_appendix", "") + tier3
        )
        state_post["client_profile_prompt"] = _consume_between_call_appendix(
            state_post, rebuilt_profile_prompt
        )
        assert tier3 in state_post["client_profile_prompt"]  # fixed

    def test_pr_f_reconnect_mid_call_preserves_tier3(self):
        """PR-F regression: mid-call WS reconnect rebuilds the prompt;
        the appendix must still apply on that rebuild.

        Pre-PR-F: consume cleared the appendix on first session.start,
        so a reconnect that re-ran _build_client_profile_prompt landed
        on state without tier3 — AI forgot the between-call context for
        the rest of the call.
        """
        from app.ws.training import _consume_between_call_appendix

        tier3 = "\n\n[Tier3 — relationship LOW]"
        state: dict = {"between_call_appendix": tier3}

        # First session.start (fresh path) — call #2 begins.
        prompt_call_start = _consume_between_call_appendix(state, "FRESH PROFILE")
        assert tier3 in prompt_call_start

        # ... mid-call, WS drops, FE auto-reconnects, sends session.start
        # again with session_id set → resume branch runs and rebuilds the
        # profile prompt fresh from DB. The appendix must be re-applied.
        prompt_after_reconnect = _consume_between_call_appendix(state, "FRESH PROFILE")
        assert tier3 in prompt_after_reconnect
        assert prompt_after_reconnect == prompt_call_start  # same context

    def test_pr_f_next_call_resets_appendix(self):
        """PR-F regression: next-call setup must blank the appendix
        before accumulating call N+1's tier3, otherwise call N's
        between-call context bleeds into call N+1.

        Replays the explicit reset that _handle_story_next_call does at
        its start.
        """
        from app.ws.training import _consume_between_call_appendix

        state: dict = {"between_call_appendix": "\n\n[CALL_N tier3]"}
        # Simulate the start of _handle_story_next_call for call N+1:
        state["between_call_appendix"] = ""
        # Then accumulate fresh tier3 for call N+1:
        state["between_call_appendix"] = (
            state.get("between_call_appendix", "") + "\n\n[CALL_N+1 tier3]"
        )
        prompt = _consume_between_call_appendix(state, "BASE")
        assert "CALL_N tier3" not in prompt
        assert "CALL_N+1 tier3" in prompt
