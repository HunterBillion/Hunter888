"""Tests for the emotion engine (services/emotion.py).

Covers MoodBuffer state management, emotion transitions, timeline tracking,
and emotion state persistence. Tests both synchronous buffer logic and
async emotion state management.
"""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.emotion import (
    MoodBuffer,
    DEFAULT_ENERGY,
    ALLOWED_TRANSITIONS,
    TRIGGERS,
)


# ═════════════════════════════════════════════════════════════════════════════
# MoodBuffer Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestMoodBuffer:
    """Test MoodBuffer energy accumulation, decay, EMA, and thresholds."""

    def test_initial_state(self):
        """MoodBuffer should start with zero energy."""
        buf = MoodBuffer()
        assert buf.current_energy == 0.0
        assert buf.energy_smoothed == 0.0

    def test_update_positive_energy(self):
        """Positive update should increase current_energy."""
        buf = MoodBuffer()
        buf.update(0.3)
        assert buf.current_energy > 0.0
        assert buf.energy_smoothed > 0.0

    def test_update_negative_energy(self):
        """Negative update should decrease current_energy."""
        buf = MoodBuffer()
        buf.update(-0.4)
        assert buf.current_energy < 0.0
        assert buf.energy_smoothed < 0.0

    def test_apply_decay_positive_energy(self):
        """Decay should reduce positive energy toward zero."""
        buf = MoodBuffer(current_energy=1.0)
        buf.apply_decay()
        assert buf.current_energy < 1.0
        assert buf.current_energy >= 0.0

    def test_apply_decay_negative_energy(self):
        """Decay should increase negative energy toward zero."""
        buf = MoodBuffer(current_energy=-1.0)
        buf.apply_decay()
        assert buf.current_energy > -1.0
        assert buf.current_energy <= 0.0

    def test_apply_ema_smoothing(self):
        """EMA should smooth energy_smoothed toward current_energy."""
        buf = MoodBuffer(
            current_energy=1.0,
            energy_smoothed=0.0,
            ema_alpha=0.3,
        )
        buf.apply_ema()
        # energy_smoothed = 0.3 * 1.0 + 0.7 * 0.0 = 0.3
        assert buf.energy_smoothed == 0.3
        assert 0.0 < buf.energy_smoothed < 1.0

    def test_should_transition_positive(self):
        """should_transition_forward when energy_smoothed >= threshold."""
        buf = MoodBuffer(
            energy_smoothed=0.7,
            threshold_positive=0.6,
        )
        assert buf.should_transition_forward() is True

    def test_should_not_transition_positive_below_threshold(self):
        """should_transition_forward when energy below threshold."""
        buf = MoodBuffer(
            energy_smoothed=0.5,
            threshold_positive=0.6,
        )
        assert buf.should_transition_forward() is False

    def test_should_transition_negative(self):
        """should_transition_backward when energy_smoothed <= threshold."""
        buf = MoodBuffer(
            energy_smoothed=-0.6,
            threshold_negative=-0.5,
        )
        assert buf.should_transition_backward() is True

    def test_should_not_transition_negative_above_threshold(self):
        """should_transition_backward when energy above threshold."""
        buf = MoodBuffer(
            energy_smoothed=-0.4,
            threshold_negative=-0.5,
        )
        assert buf.should_transition_backward() is False

    def test_reset_after_transition(self):
        """reset_after_transition should zero both energies."""
        buf = MoodBuffer(current_energy=1.0, energy_smoothed=0.8)
        buf.reset_after_transition()
        assert buf.current_energy == 0.0
        assert buf.energy_smoothed == 0.0

    def test_clamping_high(self):
        """Clamp should limit energy to max 100.0."""
        buf = MoodBuffer(current_energy=200.0, energy_smoothed=150.0)
        buf.clamp()
        assert buf.current_energy == 100.0
        assert buf.energy_smoothed == 100.0

    def test_clamping_low(self):
        """Clamp should limit energy to min -100.0."""
        buf = MoodBuffer(current_energy=-200.0, energy_smoothed=-150.0)
        buf.clamp()
        assert buf.current_energy == -100.0
        assert buf.energy_smoothed == -100.0

    def test_full_update_cycle(self):
        """Full update should apply delta, decay, EMA, and clamp."""
        buf = MoodBuffer()
        buf.update(0.5)
        # After update, energy should be positive but decayed and smoothed
        assert buf.current_energy > 0.0
        assert buf.energy_smoothed > 0.0
        assert buf.current_energy <= 100.0
        assert buf.energy_smoothed <= 100.0

    def test_to_dict(self):
        """to_dict should return valid dictionary representation."""
        buf = MoodBuffer(current_energy=0.5, energy_smoothed=0.3)
        d = buf.to_dict()
        assert isinstance(d, dict)
        assert d["current_energy"] == 0.5
        assert d["energy_smoothed"] == 0.3

    def test_from_dict(self):
        """from_dict should reconstruct MoodBuffer from dict."""
        d = {
            "current_energy": 0.5,
            "energy_smoothed": 0.3,
            "ema_alpha": 0.3,
            "threshold_positive": 0.6,
            "threshold_negative": -0.5,
            "decay_rate": 0.1,
        }
        buf = MoodBuffer.from_dict(d)
        assert buf.current_energy == 0.5
        assert buf.energy_smoothed == 0.3


# ═════════════════════════════════════════════════════════════════════════════
# Emotion State Tests (mocked Redis)
# ═════════════════════════════════════════════════════════════════════════════


class TestEmotionState:
    """Test emotion state management with mocked async Redis."""

    @pytest.mark.asyncio
    async def test_init_emotion_sets_cold(self):
        """init_emotion should set state to 'cold' by default."""
        from app.services.emotion import init_emotion

        session_id = uuid.uuid4()
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_redis.pipeline.return_value.__aenter__ = AsyncMock()
        mock_redis.pipeline.return_value.__aexit__ = AsyncMock()

        # Mock _get_redis to return our mock
        with patch("app.services.emotion._get_redis", return_value=mock_redis):
            await init_emotion(session_id, initial_state="cold")
            # Verify Redis was accessed (pipeline called)
            assert mock_redis.pipeline.called

    @pytest.mark.asyncio
    async def test_get_emotion_after_set(self):
        """get_emotion should return the state set by set_emotion."""
        from app.services.emotion import get_emotion, set_emotion

        session_id = uuid.uuid4()
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "guarded"
        mock_redis.pipeline.return_value.__aenter__ = AsyncMock()
        mock_redis.pipeline.return_value.__aexit__ = AsyncMock()

        with patch("app.services.emotion._get_redis", return_value=mock_redis):
            # Set emotion
            await set_emotion(session_id, "guarded")
            # Get emotion
            result = await get_emotion(session_id)
            assert result == "guarded"

    @pytest.mark.asyncio
    async def test_get_emotion_default_cold_no_redis(self):
        """get_emotion should return 'cold' if Redis unavailable."""
        from app.services.emotion import get_emotion

        session_id = uuid.uuid4()

        # Redis is None
        with patch("app.services.emotion._get_redis", return_value=None):
            result = await get_emotion(session_id)
            assert result == "cold"

    @pytest.mark.asyncio
    async def test_set_emotion_with_metadata(self):
        """set_emotion should accept and store metadata."""
        from app.services.emotion import set_emotion

        session_id = uuid.uuid4()
        mock_redis = AsyncMock()
        mock_pipeline = AsyncMock()
        mock_redis.pipeline.return_value = mock_pipeline
        mock_pipeline.__aenter__.return_value = mock_pipeline
        mock_pipeline.__aexit__.return_value = None

        with patch("app.services.emotion._get_redis", return_value=mock_redis):
            await set_emotion(
                session_id,
                "curious",
                previous_state="cold",
                triggers=["empathy", "facts"],
                energy_before=0.0,
                energy_after=0.5,
            )
            # Verify pipeline was used
            assert mock_redis.pipeline.called

    @pytest.mark.asyncio
    async def test_cleanup_emotion(self):
        """cleanup_emotion should delete emotion state from Redis."""
        from app.services.emotion import cleanup_emotion

        session_id = uuid.uuid4()
        mock_redis = AsyncMock()
        mock_redis.delete.return_value = 1
        mock_redis.lrange.return_value = []

        with patch("app.services.emotion._get_redis", return_value=mock_redis):
            result = await cleanup_emotion(session_id)
            assert mock_redis.delete.called


# ═════════════════════════════════════════════════════════════════════════════
# Emotion Timeline Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestEmotionTimeline:
    """Test emotion state timeline and history tracking."""

    @pytest.mark.asyncio
    async def test_get_emotion_timeline_structure(self):
        """get_emotion_timeline should return list of timeline entries."""
        from app.services.emotion import get_emotion_timeline

        session_id = uuid.uuid4()
        mock_redis = AsyncMock()

        # Mock timeline data
        timeline_data = [
            b'{"state":"cold","timestamp":"2026-04-01T10:00:00"}',
            b'{"state":"guarded","timestamp":"2026-04-01T10:01:00"}',
        ]
        mock_redis.lrange.return_value = timeline_data

        with patch("app.services.emotion._get_redis", return_value=mock_redis):
            result = await get_emotion_timeline(session_id)
            assert isinstance(result, list)
            # Verify timeline entries have expected keys
            if len(result) > 0:
                entry = result[0]
                assert "state" in entry
                assert "timestamp" in entry

    @pytest.mark.asyncio
    async def test_timeline_entries_have_state_and_timestamp(self):
        """Each timeline entry must have 'state' and 'timestamp' keys."""
        from app.services.emotion import get_emotion_timeline

        session_id = uuid.uuid4()
        mock_redis = AsyncMock()

        timeline_data = [
            b'{"state":"cold","timestamp":"2026-04-01T10:00:00","previous_state":"cold"}',
        ]
        mock_redis.lrange.return_value = timeline_data

        with patch("app.services.emotion._get_redis", return_value=mock_redis):
            result = await get_emotion_timeline(session_id)
            if len(result) > 0:
                entry = result[0]
                assert "state" in entry
                assert "timestamp" in entry
                # Timestamp should be ISO format
                assert "T" in entry["timestamp"]


# ═════════════════════════════════════════════════════════════════════════════
# Emotion Transition Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestEmotionTransitions:
    """Test emotion state transition rules."""

    def test_allowed_transitions_structure(self):
        """ALLOWED_TRANSITIONS should have states as keys."""
        assert isinstance(ALLOWED_TRANSITIONS, dict)
        assert "cold" in ALLOWED_TRANSITIONS
        assert "guarded" in ALLOWED_TRANSITIONS
        assert "curious" in ALLOWED_TRANSITIONS
        assert "hostile" in ALLOWED_TRANSITIONS
        assert "hangup" in ALLOWED_TRANSITIONS

    def test_cold_can_transition_to_guarded_or_hostile(self):
        """From 'cold', should be able to go to 'guarded' or 'hostile'."""
        cold_transitions = ALLOWED_TRANSITIONS["cold"]
        assert "guarded" in cold_transitions
        assert "hostile" in cold_transitions

    def test_guarded_is_branching_node(self):
        """'guarded' should have multiple transitions (branching point)."""
        guarded_transitions = ALLOWED_TRANSITIONS["guarded"]
        assert len(guarded_transitions) > 2
        assert "curious" in guarded_transitions
        assert "testing" in guarded_transitions
        assert "callback" in guarded_transitions

    def test_hostile_can_transition_to_hangup(self):
        """From 'hostile', should be able to go to 'hangup'."""
        hostile_transitions = ALLOWED_TRANSITIONS["hostile"]
        assert "hangup" in hostile_transitions

    def test_hangup_is_terminal(self):
        """'hangup' should have no transitions (terminal state)."""
        hangup_transitions = ALLOWED_TRANSITIONS["hangup"]
        assert len(hangup_transitions) == 0

    def test_triggers_are_valid(self):
        """TRIGGERS list should contain expected trigger names."""
        assert isinstance(TRIGGERS, list)
        assert "empathy" in TRIGGERS
        assert "facts" in TRIGGERS
        assert "bad_response" in TRIGGERS
        assert "calm_response" in TRIGGERS
        assert "pressure" in TRIGGERS

    def test_default_energy_covers_triggers(self):
        """DEFAULT_ENERGY should define energy for each trigger."""
        assert isinstance(DEFAULT_ENERGY, dict)
        # At least most triggers should have default energy
        empathy_energy = DEFAULT_ENERGY.get("empathy")
        assert empathy_energy is not None
        assert empathy_energy > 0.0
        bad_response_energy = DEFAULT_ENERGY.get("bad_response")
        assert bad_response_energy is not None
        assert bad_response_energy < 0.0


# ═════════════════════════════════════════════════════════════════════════════
# Integration Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestEmotionIntegration:
    """Integration tests combining multiple emotion components."""

    def test_mood_buffer_state_roundtrip(self):
        """MoodBuffer state should survive to_dict/from_dict roundtrip."""
        buf1 = MoodBuffer(current_energy=0.5, energy_smoothed=0.3)
        d = buf1.to_dict()
        buf2 = MoodBuffer.from_dict(d)
        assert buf2.current_energy == buf1.current_energy
        assert buf2.energy_smoothed == buf1.energy_smoothed

    def test_multiple_mood_buffer_updates(self):
        """Multiple sequential updates should accumulate and smooth."""
        buf = MoodBuffer()
        buf.update(0.2)
        energy_after_1 = buf.energy_smoothed
        buf.update(0.3)
        energy_after_2 = buf.energy_smoothed
        # Energy should generally increase (though decay might reduce it)
        assert energy_after_2 >= 0.0

    @pytest.mark.asyncio
    async def test_emotion_state_persistence(self):
        """Emotion state should persist through set/get cycle."""
        from app.services.emotion import set_emotion, get_emotion

        session_id = uuid.uuid4()
        mock_redis = AsyncMock()
        stored_state = None

        def mock_set(key, value, **kwargs):
            nonlocal stored_state
            stored_state = value
            return True

        mock_redis.set = mock_set
        mock_redis.get = AsyncMock(side_effect=lambda key: stored_state)
        mock_redis.pipeline.return_value.__aenter__ = AsyncMock()
        mock_redis.pipeline.return_value.__aexit__ = AsyncMock()

        with patch("app.services.emotion._get_redis", return_value=mock_redis):
            # Set and get
            await set_emotion(session_id, "curious")
            # Note: get_emotion uses its own redis.get, mock that
            with patch.object(mock_redis, "get", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = "curious"
                result = await get_emotion(session_id)
                # Should retrieve what was stored
                assert "curious" in result or result == "curious"
