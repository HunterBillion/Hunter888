"""Tests for the game director engine (services/game_director.py).

Covers consequence events, storylet activation, between-call events,
context injection, session results, and relationship modifiers.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.game_director import (
    ConsequenceEvent,
    StoryletActivation,
    BetweenCallEvent,
    ContextInjection,
    SessionResult,
    LIFECYCLE_STATES,
    LIFECYCLE_TRANSITIONS,
    CONSEQUENCE_COSMETIC,
    CONSEQUENCE_LOCAL,
    CONSEQUENCE_GLOBAL,
    REL_PROMISE_KEPT,
    REL_EMPATHY_DETECTED,
    REL_PROMISE_BROKEN,
    REL_RUDENESS,
    REL_FORGOT_CLIENT,
    REL_PERFECT_CALL,
)


# ═══════════════════════════════════════════════════════════════════════════════
# TestConsequenceEvent — Consequence creation and levels
# ═══════════════════════════════════════════════════════════════════════════════


class TestConsequenceEvent:
    """Test ConsequenceEvent dataclass."""

    def test_consequence_event_create_with_defaults(self):
        """Create ConsequenceEvent with defaults."""
        event = ConsequenceEvent()
        assert event.id is not None
        assert event.level == CONSEQUENCE_LOCAL
        assert event.trigger_action == ""
        assert event.effect_description == ""
        assert event.is_active is True

    def test_consequence_event_create_with_local_level(self):
        """Create ConsequenceEvent with level=local."""
        event = ConsequenceEvent(
            level=CONSEQUENCE_LOCAL,
            trigger_action="promised_discount",
            effect_description="Client remembers the promise",
            source_agent="agent_1",
        )
        assert event.level == CONSEQUENCE_LOCAL
        assert event.trigger_action == "promised_discount"
        assert event.effect_description == "Client remembers the promise"
        assert event.source_agent == "agent_1"

    def test_consequence_event_cosmetic_level(self):
        """ConsequenceEvent can have cosmetic level."""
        event = ConsequenceEvent(level=CONSEQUENCE_COSMETIC)
        assert event.level == CONSEQUENCE_COSMETIC

    def test_consequence_event_global_level(self):
        """ConsequenceEvent can have global level."""
        event = ConsequenceEvent(level=CONSEQUENCE_GLOBAL)
        assert event.level == CONSEQUENCE_GLOBAL

    def test_consequence_event_applied_at_defaults_to_now(self):
        """applied_at should default to current datetime."""
        before = datetime.utcnow()
        event = ConsequenceEvent()
        after = datetime.utcnow()
        assert before <= event.applied_at <= after

    def test_consequence_event_with_expiry(self):
        """ConsequenceEvent can have expiry date."""
        now = datetime.utcnow()
        expires = now + type(now)(days=7)
        event = ConsequenceEvent(expires_at=expires)
        assert event.expires_at == expires

    def test_consequence_event_unique_ids(self):
        """Each ConsequenceEvent should have unique ID."""
        event1 = ConsequenceEvent()
        event2 = ConsequenceEvent()
        assert event1.id != event2.id


# ═══════════════════════════════════════════════════════════════════════════════
# TestStoryletActivation — Storylet creation and effects
# ═══════════════════════════════════════════════════════════════════════════════


class TestStoryletActivation:
    """Test StoryletActivation dataclass."""

    def test_storylet_activation_create_with_defaults(self):
        """Create StoryletActivation with defaults."""
        storylet = StoryletActivation()
        assert storylet.storylet_code == ""
        assert storylet.narrative_text == ""
        assert storylet.effects == {}
        assert storylet.priority == 5

    def test_storylet_activation_with_code_and_narrative(self):
        """Create StoryletActivation with code and narrative."""
        storylet = StoryletActivation(
            storylet_code="deal_advanced",
            narrative_text="The manager demonstrates advanced closing techniques.",
            priority=8,
        )
        assert storylet.storylet_code == "deal_advanced"
        assert storylet.narrative_text == "The manager demonstrates advanced closing techniques."
        assert storylet.priority == 8

    def test_storylet_activation_with_effects(self):
        """StoryletActivation can have effects dict."""
        effects = {
            "emotion_shift": {"from": "cold", "to": "warm"},
            "xp_bonus": 50,
        }
        storylet = StoryletActivation(
            storylet_code="empathy_moment",
            effects=effects,
        )
        assert storylet.effects == effects

    def test_storylet_activation_priority_levels(self):
        """StoryletActivation priority should be adjustable."""
        low = StoryletActivation(priority=1)
        medium = StoryletActivation(priority=5)
        high = StoryletActivation(priority=10)
        assert low.priority < medium.priority < high.priority

    def test_storylet_activation_timestamp(self):
        """StoryletActivation should track activation time."""
        before = datetime.utcnow()
        storylet = StoryletActivation(storylet_code="test")
        after = datetime.utcnow()
        assert before <= storylet.activated_at <= after


# ═══════════════════════════════════════════════════════════════════════════════
# TestBetweenCallEvent — Frontend panel events
# ═══════════════════════════════════════════════════════════════════════════════


class TestBetweenCallEvent:
    """Test BetweenCallEvent dataclass."""

    def test_between_call_event_create_with_defaults(self):
        """Create BetweenCallEvent with defaults."""
        event = BetweenCallEvent()
        assert event.event_type == "message"
        assert event.title == ""
        assert event.content == ""
        assert event.payload == {}

    def test_between_call_event_message_type(self):
        """BetweenCallEvent with message event_type."""
        event = BetweenCallEvent(
            event_type="message",
            title="New Opportunity",
            content="The client seemed interested in the premium package.",
        )
        assert event.event_type == "message"
        assert event.title == "New Opportunity"

    def test_between_call_event_status_change_type(self):
        """BetweenCallEvent with status_change event_type."""
        event = BetweenCallEvent(
            event_type="status_change",
            title="Status Updated",
            content="From INTERESTED to MEETING_SET",
            payload={"from_state": "INTERESTED", "to_state": "MEETING_SET"},
        )
        assert event.event_type == "status_change"
        assert event.payload["from_state"] == "INTERESTED"

    def test_between_call_event_consequence_type(self):
        """BetweenCallEvent with consequence event_type."""
        event = BetweenCallEvent(
            event_type="consequence",
            title="Consequence Triggered",
            content="Promise broken: forgot to send documents",
            payload={"consequence_id": "prom_broken_1", "impact": -10},
        )
        assert event.event_type == "consequence"

    def test_between_call_event_storylet_type(self):
        """BetweenCallEvent with storylet event_type."""
        event = BetweenCallEvent(
            event_type="storylet",
            title="Story Development",
            content="A new subplot has been activated.",
            payload={"storylet_code": "subplot_1"},
        )
        assert event.event_type == "storylet"

    def test_between_call_event_callback_type(self):
        """BetweenCallEvent with callback event_type."""
        event = BetweenCallEvent(
            event_type="callback",
            title="Callback Scheduled",
            content="Follow-up call scheduled for tomorrow at 10 AM.",
            payload={"callback_time": "2026-04-02T10:00:00"},
        )
        assert event.event_type == "callback"

    def test_between_call_event_timestamp(self):
        """BetweenCallEvent should have game_timestamp."""
        before = datetime.utcnow()
        event = BetweenCallEvent(event_type="message")
        after = datetime.utcnow()
        assert before <= event.game_timestamp <= after


# ═══════════════════════════════════════════════════════════════════════════════
# TestContextInjection — Three-tier context assembly
# ═══════════════════════════════════════════════════════════════════════════════


class TestContextInjection:
    """Test ContextInjection three-tier context."""

    def test_context_injection_create_with_defaults(self):
        """Create ContextInjection with defaults."""
        context = ContextInjection()
        assert context.tier1_identity == ""
        assert context.tier2_memory == ""
        assert context.tier3_situational == ""
        assert context.total_tokens == 0
        assert context.active_factors == []
        assert context.active_storylets == []
        assert context.active_consequences == []

    def test_context_injection_tier1_identity_not_empty(self):
        """Tier1 identity should contain archetype, emotion, personality."""
        context = ContextInjection(
            tier1_identity="Archetype: Skeptical CFO, Emotion: Guarded, Personality: Detail-oriented",
        )
        assert context.tier1_identity != ""
        assert len(context.tier1_identity) > 0

    def test_context_injection_tier2_memory_not_empty(self):
        """Tier2 memory should contain past calls, consequences, promises."""
        context = ContextInjection(
            tier2_memory="Past call: discussed pricing, promised discount 20%. Consequence: promised but didn't send contract.",
        )
        assert context.tier2_memory != ""
        assert len(context.tier2_memory) > 0

    def test_context_injection_tier3_situational_not_empty(self):
        """Tier3 situational should contain storylets, events, reputation."""
        context = ContextInjection(
            tier3_situational="Storylets: deal_advanced, empathy_moment. Reputation: high. Current event: third call.",
        )
        assert context.tier3_situational != ""
        assert len(context.tier3_situational) > 0

    def test_context_injection_active_factors_is_list(self):
        """active_factors should be a list."""
        factors = ["negotiating", "budget_aware", "time_sensitive"]
        context = ContextInjection(active_factors=factors)
        assert isinstance(context.active_factors, list)
        assert context.active_factors == factors

    def test_context_injection_active_storylets_is_list(self):
        """active_storylets should be a list."""
        storylets = ["deal_advanced", "empathy_moment"]
        context = ContextInjection(active_storylets=storylets)
        assert isinstance(context.active_storylets, list)
        assert context.active_storylets == storylets

    def test_context_injection_active_consequences_is_list(self):
        """active_consequences should be a list."""
        consequences = [
            {"id": "cons_1", "effect": "trust_reduced"},
            {"id": "cons_2", "effect": "objection_increased"},
        ]
        context = ContextInjection(active_consequences=consequences)
        assert isinstance(context.active_consequences, list)


# ═══════════════════════════════════════════════════════════════════════════════
# TestSessionResult — Training session result data
# ═══════════════════════════════════════════════════════════════════════════════


class TestSessionResult:
    """Test SessionResult dataclass."""

    def test_session_result_create_with_defaults(self):
        """Create SessionResult with defaults."""
        result = SessionResult()
        assert result.session_id == ""
        assert result.client_story_id == ""
        assert result.final_emotion_state == "cold"
        assert result.score_total == 0.0
        assert result.duration_seconds == 0
        assert result.empathy_detected is False
        assert result.rudeness_detected is False

    def test_session_result_create_with_values(self):
        """Create SessionResult with specific values."""
        result = SessionResult(
            session_id="sess_1",
            client_story_id="story_1",
            final_emotion_state="deal",
            score_total=85.5,
            duration_seconds=480,
            empathy_detected=True,
            rudeness_detected=False,
        )
        assert result.session_id == "sess_1"
        assert result.client_story_id == "story_1"
        assert result.final_emotion_state == "deal"
        assert result.score_total == 85.5
        assert result.duration_seconds == 480

    def test_session_result_score_breakdown(self):
        """SessionResult can have score breakdown dict."""
        breakdown = {
            "communication": 85,
            "objection_handling": 75,
            "closing": 90,
            "empathy": 80,
        }
        result = SessionResult(
            score_total=85.0,
            score_breakdown=breakdown,
        )
        assert result.score_breakdown == breakdown

    def test_session_result_traps_fell_list(self):
        """SessionResult tracks traps the manager fell into."""
        traps = ["price_objection", "timing_objection"]
        result = SessionResult(traps_fell=traps)
        assert result.traps_fell == traps

    def test_session_result_traps_dodged_list(self):
        """SessionResult tracks traps the manager avoided."""
        traps = ["false_objection"]
        result = SessionResult(traps_dodged=traps)
        assert result.traps_dodged == traps

    def test_session_result_promises_made(self):
        """SessionResult tracks promises made by manager."""
        promises = [
            "Send contract by Friday",
            "Call back Monday",
        ]
        result = SessionResult(promises_made=promises)
        assert result.promises_made == promises

    def test_session_result_promises_broken(self):
        """SessionResult tracks promises broken by manager."""
        promises = ["Send contract by Friday"]
        result = SessionResult(promises_broken=promises)
        assert result.promises_broken == promises

    def test_session_result_key_moments(self):
        """SessionResult tracks key moments in conversation."""
        moments = [
            "Client expressed budget constraint",
            "Manager demonstrated deep product knowledge",
            "Agreement reached on meeting",
        ]
        result = SessionResult(key_moments=moments)
        assert result.key_moments == moments

    def test_session_result_empathy_detected_boolean(self):
        """empathy_detected should be boolean."""
        result1 = SessionResult(empathy_detected=True)
        result2 = SessionResult(empathy_detected=False)
        assert result1.empathy_detected is True
        assert result2.empathy_detected is False

    def test_session_result_rudeness_detected_boolean(self):
        """rudeness_detected should be boolean."""
        result1 = SessionResult(rudeness_detected=True)
        result2 = SessionResult(rudeness_detected=False)
        assert result1.rudeness_detected is True
        assert result2.rudeness_detected is False

    def test_session_result_legal_errors(self):
        """SessionResult can track legal errors."""
        errors = [
            "Mentioned price guarantee without terms",
            "Promised deadline without confirmation",
        ]
        result = SessionResult(legal_errors=errors)
        assert result.legal_errors == errors


# ═══════════════════════════════════════════════════════════════════════════════
# TestLifecycleStates — Lifecycle state constants
# ═══════════════════════════════════════════════════════════════════════════════


class TestLifecycleStates:
    """Test lifecycle state definitions."""

    def test_lifecycle_states_exist(self):
        """LIFECYCLE_STATES should be defined."""
        assert LIFECYCLE_STATES is not None
        assert isinstance(LIFECYCLE_STATES, list)

    def test_lifecycle_states_contains_key_states(self):
        """LIFECYCLE_STATES should contain key sales states."""
        required_states = [
            "NEW_LEAD",
            "FIRST_CONTACT",
            "INTERESTED",
            "DEAL_CLOSED",
            "REJECTED",
            "GHOSTING",
        ]
        for state in required_states:
            assert state in LIFECYCLE_STATES

    def test_lifecycle_transitions_defined(self):
        """LIFECYCLE_TRANSITIONS should map allowed transitions."""
        assert LIFECYCLE_TRANSITIONS is not None
        assert isinstance(LIFECYCLE_TRANSITIONS, dict)

    def test_lifecycle_transitions_all_states_have_entry(self):
        """All states should have entry in transitions dict."""
        for state in LIFECYCLE_STATES:
            assert state in LIFECYCLE_TRANSITIONS

    def test_lifecycle_transitions_are_lists(self):
        """Transition values should be lists of states."""
        for from_state, to_states in LIFECYCLE_TRANSITIONS.items():
            assert isinstance(to_states, list)
            for to_state in to_states:
                assert to_state in LIFECYCLE_STATES

    def test_lifecycle_transitions_deal_closed_terminal(self):
        """DEAL_CLOSED should be terminal (no outgoing transitions)."""
        assert LIFECYCLE_TRANSITIONS["DEAL_CLOSED"] == []


# ═══════════════════════════════════════════════════════════════════════════════
# TestRelationshipModifiers — Relationship score modifiers
# ═══════════════════════════════════════════════════════════════════════════════


class TestRelationshipModifiers:
    """Test relationship score modifier constants."""

    def test_rel_promise_kept_positive(self):
        """REL_PROMISE_KEPT should be positive."""
        assert REL_PROMISE_KEPT > 0
        assert REL_PROMISE_KEPT == 5

    def test_rel_empathy_detected_positive(self):
        """REL_EMPATHY_DETECTED should be positive."""
        assert REL_EMPATHY_DETECTED > 0
        assert REL_EMPATHY_DETECTED == 3

    def test_rel_perfect_call_positive(self):
        """REL_PERFECT_CALL should be positive."""
        assert REL_PERFECT_CALL > 0
        assert REL_PERFECT_CALL == 10

    def test_rel_promise_broken_negative(self):
        """REL_PROMISE_BROKEN should be negative."""
        assert REL_PROMISE_BROKEN < 0
        assert REL_PROMISE_BROKEN == -10

    def test_rel_rudeness_negative(self):
        """REL_RUDENESS should be negative."""
        assert REL_RUDENESS < 0
        assert REL_RUDENESS == -15

    def test_rel_forgot_client_negative(self):
        """REL_FORGOT_CLIENT should be negative."""
        assert REL_FORGOT_CLIENT < 0
        assert REL_FORGOT_CLIENT == -5

    def test_modifiers_magnitude_relationship(self):
        """Modifiers should have sensible magnitude relationships."""
        # Breaking promise worse than forgetting
        assert abs(REL_PROMISE_BROKEN) > abs(REL_FORGOT_CLIENT)
        # Rudeness worst negative
        assert abs(REL_RUDENESS) > abs(REL_PROMISE_BROKEN)
        # Perfect call best positive
        assert REL_PERFECT_CALL > REL_PROMISE_KEPT
        assert REL_PERFECT_CALL > REL_EMPATHY_DETECTED
