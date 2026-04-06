"""Tests for the V3 emotion state machine (10-state nonlinear graph).

Covers MoodBuffer EMA calculations, state transitions, archetype configs,
and fake transitions — all without database or Redis.
"""

import pytest

from app.services.emotion import (
    ALLOWED_TRANSITIONS,
    TRANSITIONS,
    DEFAULT_ENERGY,
    MoodBuffer,
    InteractionMemory,
    FakeTransition,
    ArchetypeConfig,
    ARCHETYPE_CONFIGS,
)


# ---------------------------------------------------------------------------
# MoodBuffer — initialization and basic properties
# ---------------------------------------------------------------------------

class TestMoodBufferInit:
    """MoodBuffer default values and construction."""

    def test_default_values(self):
        buf = MoodBuffer()
        assert buf.current_energy == 0.0
        assert buf.energy_smoothed == 0.0
        assert buf.ema_alpha == 0.3
        assert buf.threshold_positive == 0.6
        assert buf.threshold_negative == -0.5
        assert buf.decay_rate == 0.1

    def test_custom_values(self):
        buf = MoodBuffer(
            current_energy=0.5,
            energy_smoothed=0.3,
            ema_alpha=0.5,
            threshold_positive=0.8,
            threshold_negative=-0.3,
            decay_rate=0.2,
        )
        assert buf.current_energy == 0.5
        assert buf.ema_alpha == 0.5

    def test_serialization_roundtrip(self):
        buf = MoodBuffer(current_energy=0.42, ema_alpha=0.7)
        restored = MoodBuffer.from_dict(buf.to_dict())
        assert restored.current_energy == pytest.approx(0.42)
        assert restored.ema_alpha == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# MoodBuffer — EMA calculation
# ---------------------------------------------------------------------------

class TestMoodBufferEMA:
    """Exponential moving average smoothing."""

    def test_ema_single_update(self):
        buf = MoodBuffer(ema_alpha=0.3)
        buf.current_energy = 1.0
        buf.apply_ema()
        # EMA = 0.3 * 1.0 + 0.7 * 0.0 = 0.3
        assert buf.energy_smoothed == pytest.approx(0.3)

    def test_ema_converges_toward_current(self):
        buf = MoodBuffer(ema_alpha=0.5)
        buf.current_energy = 1.0
        for _ in range(20):
            buf.apply_ema()
        assert buf.energy_smoothed == pytest.approx(1.0, abs=0.01)

    def test_ema_negative_energy(self):
        buf = MoodBuffer(ema_alpha=0.3)
        buf.current_energy = -1.0
        buf.apply_ema()
        assert buf.energy_smoothed == pytest.approx(-0.3)


# ---------------------------------------------------------------------------
# MoodBuffer — decay
# ---------------------------------------------------------------------------

class TestMoodBufferDecay:
    """Energy decay toward zero."""

    def test_positive_energy_decays(self):
        buf = MoodBuffer(current_energy=1.0, decay_rate=0.1)
        buf.apply_decay()
        assert buf.current_energy == pytest.approx(0.9)

    def test_negative_energy_decays(self):
        buf = MoodBuffer(current_energy=-1.0, decay_rate=0.1)
        buf.apply_decay()
        assert buf.current_energy == pytest.approx(-0.9)

    def test_zero_energy_no_change(self):
        buf = MoodBuffer(current_energy=0.0, decay_rate=0.5)
        buf.apply_decay()
        assert buf.current_energy == 0.0


# ---------------------------------------------------------------------------
# MoodBuffer — full update cycle
# ---------------------------------------------------------------------------

class TestMoodBufferUpdate:
    """Full update: delta + decay + EMA + clamp."""

    def test_update_adds_delta_then_processes(self):
        buf = MoodBuffer(ema_alpha=0.3, decay_rate=0.1)
        buf.update(0.5)
        # After add: 0.5, after decay: 0.5 * 0.9 = 0.45
        assert buf.current_energy == pytest.approx(0.45)
        # EMA: 0.3 * 0.45 + 0.7 * 0 = 0.135
        assert buf.energy_smoothed == pytest.approx(0.135)

    def test_clamp_upper_bound(self):
        buf = MoodBuffer()
        buf.update(200.0)
        assert buf.current_energy <= 100.0
        assert buf.energy_smoothed <= 100.0

    def test_clamp_lower_bound(self):
        buf = MoodBuffer()
        buf.update(-200.0)
        assert buf.current_energy >= -100.0
        assert buf.energy_smoothed >= -100.0


# ---------------------------------------------------------------------------
# MoodBuffer — threshold transitions
# ---------------------------------------------------------------------------

class TestMoodBufferThresholds:
    """Threshold crossing for state transitions."""

    def test_forward_transition_at_threshold(self):
        buf = MoodBuffer(threshold_positive=0.6)
        buf.energy_smoothed = 0.6
        assert buf.should_transition_forward() is True

    def test_forward_transition_below_threshold(self):
        buf = MoodBuffer(threshold_positive=0.6)
        buf.energy_smoothed = 0.59
        assert buf.should_transition_forward() is False

    def test_backward_transition_at_threshold(self):
        buf = MoodBuffer(threshold_negative=-0.5)
        buf.energy_smoothed = -0.5
        assert buf.should_transition_backward() is True

    def test_backward_transition_above_threshold(self):
        buf = MoodBuffer(threshold_negative=-0.5)
        buf.energy_smoothed = -0.49
        assert buf.should_transition_backward() is False

    def test_reset_after_transition(self):
        buf = MoodBuffer(current_energy=0.8, energy_smoothed=0.7)
        buf.reset_after_transition()
        assert buf.current_energy == 0.0
        assert buf.energy_smoothed == 0.0

    def test_zero_energy_no_transition(self):
        buf = MoodBuffer()
        assert buf.should_transition_forward() is False
        assert buf.should_transition_backward() is False


# ---------------------------------------------------------------------------
# State graph — ALLOWED_TRANSITIONS
# ---------------------------------------------------------------------------

class TestStateGraph:
    """Verify the structure of the nonlinear state graph."""

    def test_cold_can_reach_guarded(self):
        assert "guarded" in ALLOWED_TRANSITIONS["cold"]

    def test_cold_can_reach_hostile(self):
        assert "hostile" in ALLOWED_TRANSITIONS["cold"]

    def test_hangup_is_terminal(self):
        assert ALLOWED_TRANSITIONS["hangup"] == set()

    def test_guarded_is_key_branching_node(self):
        exits = ALLOWED_TRANSITIONS["guarded"]
        assert len(exits) >= 4
        assert "curious" in exits
        assert "testing" in exits
        assert "hostile" in exits

    def test_hostile_limited_exits(self):
        exits = ALLOWED_TRANSITIONS["hostile"]
        assert exits == {"guarded", "hangup"}


# ---------------------------------------------------------------------------
# V1 backward-compat TRANSITIONS
# ---------------------------------------------------------------------------

class TestV1Transitions:
    """V1 direct transitions by response quality."""

    def test_cold_high_goes_to_guarded(self):
        assert TRANSITIONS["cold"]["high"] == "guarded"

    def test_cold_low_goes_to_hostile(self):
        assert TRANSITIONS["cold"]["low"] == "hostile"

    def test_deal_is_absorbing(self):
        assert TRANSITIONS["deal"]["high"] == "deal"
        assert TRANSITIONS["deal"]["medium"] == "deal"

    def test_hangup_is_absorbing(self):
        for quality in ("high", "medium", "low"):
            assert TRANSITIONS["hangup"][quality] == "hangup"


# ---------------------------------------------------------------------------
# FakeTransition
# ---------------------------------------------------------------------------

class TestFakeTransition:
    """Fake (deceptive) transitions for archetypes."""

    def test_creation_and_serialization(self):
        ft = FakeTransition(
            apparent_state="curious",
            real_state="testing",
            trigger_reveal="pressure",
            duration=3,
            turns_remaining=3,
        )
        d = ft.to_dict()
        assert d["apparent_state"] == "curious"
        assert d["real_state"] == "testing"
        restored = FakeTransition.from_dict(d)
        assert restored.trigger_reveal == "pressure"
        assert restored.turns_remaining == 3


# ---------------------------------------------------------------------------
# ArchetypeConfig
# ---------------------------------------------------------------------------

class TestArchetypeConfig:
    """Per-archetype behavior customization."""

    def test_skeptic_config_exists(self):
        assert "skeptic" in ARCHETYPE_CONFIGS

    def test_skeptic_facts_modifier(self):
        cfg = ARCHETYPE_CONFIGS["skeptic"]
        assert cfg.energy_modifiers.get("facts") == 1.5

    def test_skeptic_has_counter_gate(self):
        cfg = ARCHETYPE_CONFIGS["skeptic"]
        assert cfg.counter_gates.get("facts") == 2

    def test_anxious_higher_sensitivity(self):
        cfg = ARCHETYPE_CONFIGS["anxious"]
        assert cfg.threshold_negative == -0.3
        assert cfg.energy_modifiers.get("pressure") == 2.0

    def test_all_archetypes_have_valid_initial_state(self):
        valid_states = set(ALLOWED_TRANSITIONS.keys())
        for name, cfg in ARCHETYPE_CONFIGS.items():
            assert cfg.initial_state in valid_states, (
                f"Archetype {name} has invalid initial_state"
            )


# ---------------------------------------------------------------------------
# DEFAULT_ENERGY triggers
# ---------------------------------------------------------------------------

class TestDefaultEnergy:
    """Default energy values for triggers."""

    def test_positive_triggers_are_positive(self):
        positive = ["empathy", "facts", "hook", "resolve_fear"]
        for t in positive:
            assert DEFAULT_ENERGY[t] > 0, f"Trigger {t} should be positive"

    def test_negative_triggers_are_negative(self):
        negative = [
            "pressure", "bad_response", "insult",
            "wrong_answer", "counter_aggression",
        ]
        for t in negative:
            assert DEFAULT_ENERGY[t] < 0, f"Trigger {t} should be negative"

    def test_insult_is_strongest_negative(self):
        assert DEFAULT_ENERGY["insult"] == -1.0

    def test_hook_is_high_positive(self):
        assert DEFAULT_ENERGY["hook"] == 0.5


# ---------------------------------------------------------------------------
# InteractionMemory
# ---------------------------------------------------------------------------

class TestInteractionMemory:
    """Interaction history tracking."""

    def test_default_memory(self):
        mem = InteractionMemory()
        assert mem.last_5_triggers == []
        assert mem.rollback_count == 0
        assert mem.peak_state == "cold"

    def test_serialization_roundtrip(self):
        mem = InteractionMemory(
            last_5_triggers=["empathy", "facts"],
            rollback_count=2,
            peak_state="curious",
        )
        restored = InteractionMemory.from_dict(mem.to_dict())
        assert restored.last_5_triggers == ["empathy", "facts"]
        assert restored.peak_state == "curious"
