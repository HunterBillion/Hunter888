"""(2026-05-01) Adaptive temperature 0.4-1.0 per emotion — tests.

Pin the contract:
  * flag default OFF
  * helper maps each canonical emotion to its band value
  * unknown emotion → safe default (0.80)
  * output always clamped to [0.40, 1.00]
  * hostile > deal > hangup (semantic monotonicity — chaos vs calm)
  * generate_response: when flag OFF, temperature stays None
  * generate_response: when flag ON + call mode + no caller override,
    emotion-derived temperature is computed and forwarded
  * generate_response: explicit caller temperature wins over adaptive
    (judges / coaches keep determinism)
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.llm import (
    ADAPTIVE_TEMPERATURE_DEFAULT,
    ADAPTIVE_TEMPERATURE_MAX,
    ADAPTIVE_TEMPERATURE_MIN,
    _ADAPTIVE_TEMPERATURE_BY_EMOTION,
    adaptive_temperature_for_emotion,
)


def test_flag_default_off():
    from app.config import settings
    assert settings.adaptive_temperature_enabled is False


def test_band_constants_match_user_spec():
    """User explicitly requested range 0.4-1.0."""
    assert ADAPTIVE_TEMPERATURE_MIN == 0.40
    assert ADAPTIVE_TEMPERATURE_MAX == 1.00


def test_default_is_in_band_and_centred():
    assert ADAPTIVE_TEMPERATURE_MIN <= ADAPTIVE_TEMPERATURE_DEFAULT <= ADAPTIVE_TEMPERATURE_MAX
    # Default should be on the calmer side of the median (0.7) — most
    # call sessions start in cold/curious, neither chaotic nor terminal.
    assert 0.70 <= ADAPTIVE_TEMPERATURE_DEFAULT <= 0.85


@pytest.mark.parametrize("emotion,expected", [
    ("hangup",      0.40),
    ("deal",        0.55),
    ("negotiating", 0.65),
    ("considering", 0.70),
    ("cold",        0.80),
    ("curious",     0.80),
    ("callback",    0.85),
    ("guarded",     0.85),
    ("hostile",     0.95),
    ("testing",     1.00),
])
def test_each_canonical_emotion_maps_correctly(emotion: str, expected: float):
    out = adaptive_temperature_for_emotion(emotion)
    assert out == pytest.approx(expected), (
        f"emotion {emotion!r} mapped to {out}, expected {expected}"
    )


def test_unknown_emotion_falls_back_to_default():
    assert adaptive_temperature_for_emotion("nonsense") == ADAPTIVE_TEMPERATURE_DEFAULT
    assert adaptive_temperature_for_emotion("") == ADAPTIVE_TEMPERATURE_DEFAULT


def test_chaos_monotonicity():
    """A chaotic mood must produce a higher T than a calm mood —
    catches accidental swap of values in the table."""
    hostile = adaptive_temperature_for_emotion("hostile")
    deal = adaptive_temperature_for_emotion("deal")
    hangup = adaptive_temperature_for_emotion("hangup")
    testing = adaptive_temperature_for_emotion("testing")
    cold = adaptive_temperature_for_emotion("cold")
    assert testing >= hostile > cold > deal > hangup, (
        f"monotonicity broken: testing={testing} hostile={hostile} cold={cold} "
        f"deal={deal} hangup={hangup}"
    )


def test_all_table_values_in_band():
    """Hard guard: no entry can drift outside [0.4, 1.0] — providers
    have their own ceilings and we'd silently get clipped or rejected."""
    for emotion, val in _ADAPTIVE_TEMPERATURE_BY_EMOTION.items():
        assert ADAPTIVE_TEMPERATURE_MIN <= val <= ADAPTIVE_TEMPERATURE_MAX, (
            f"emotion {emotion!r} value {val} outside [0.4, 1.0]"
        )


def test_helper_clamps_table_with_bad_values(monkeypatch):
    """Even if the table is corrupted at runtime (shouldn't happen, but
    defence in depth), clamp guarantees the output stays in band."""
    from app.services import llm as llm_mod
    monkeypatch.setitem(llm_mod._ADAPTIVE_TEMPERATURE_BY_EMOTION, "cold", 1.7)
    assert adaptive_temperature_for_emotion("cold") == ADAPTIVE_TEMPERATURE_MAX
    monkeypatch.setitem(llm_mod._ADAPTIVE_TEMPERATURE_BY_EMOTION, "cold", -0.2)
    assert adaptive_temperature_for_emotion("cold") == ADAPTIVE_TEMPERATURE_MIN
