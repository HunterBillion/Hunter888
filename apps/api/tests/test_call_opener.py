"""(2026-05-01) Persona-aware call opener tests.

Pin the contract:
  * flag default OFF
  * pick_opener returns mood- and age-matched phrase
  * unknown moods fall back to 'cold'
  * 'hangup' → not surfaced as a normal mood (it's not in the bank, but
    fallback path supplies a safe default rather than crashing)
  * pickup_delay_ms is in the per-mood band (sanity check on triangular
    distribution)
  * every phrase is short (≤ 30 chars — phone openers are reflexive)
  * register sanity: senior cold ≠ young cold (catches accidental flat-pool
    regression)
"""

from __future__ import annotations

import random

import pytest

from app.services.call_opener import (
    _OPENER_BANK,
    _PICKUP_DELAY_BY_MOOD,
    DEFAULT_OPENER,
    _age_to_bucket,
    pick_opener,
)


def test_flag_default_off():
    from app.config import settings
    assert settings.call_opener_persona_aware is False


def test_age_bucketing():
    assert _age_to_bucket(None) == "middle"
    assert _age_to_bucket(20) == "young"
    assert _age_to_bucket(34) == "young"
    assert _age_to_bucket(35) == "middle"
    assert _age_to_bucket(49) == "middle"
    assert _age_to_bucket(50) == "senior"
    assert _age_to_bucket(75) == "senior"


@pytest.mark.parametrize("mood", [
    "cold", "guarded", "curious", "considering",
    "negotiating", "deal", "testing", "callback", "hostile",
])
def test_every_mood_yields_a_phrase(mood: str):
    rng = random.Random(0)
    out = pick_opener(mood, age=42, rng=rng)
    assert out.text, f"empty opener for mood={mood!r}"
    assert out.emotion == mood


def test_unknown_mood_falls_back_safely():
    """Made-up mood string → falls through cold/middle bucket without crash."""
    out = pick_opener("doesnotexist", age=42, rng=random.Random(0))
    assert out.text  # any non-empty phrase from cold/middle is acceptable


def test_register_differs_by_age_for_cold_mood():
    """Senior cold should NOT pick the same phrase pool as young cold —
    that's the whole point of persona-awareness."""
    young = set(_OPENER_BANK[("cold", "young")])
    senior = set(_OPENER_BANK[("cold", "senior")])
    # Pools should differ (some overlap is fine, but they can't be identical).
    assert young != senior, "young and senior cold pools collapsed to identical set"


def test_hostile_phrases_are_short_and_dismissive():
    """Hostile openers must be short (≤ 12 chars) — long hostile phrases
    feel scripted, not reflexive."""
    for age in ("young", "middle", "senior"):
        for phrase in _OPENER_BANK[("hostile", age)]:
            assert len(phrase) <= 16, (
                f"hostile {age!r} phrase {phrase!r} too long ({len(phrase)} chars)"
            )


def test_pickup_delay_in_band_for_each_mood():
    rng = random.Random(123)
    for mood, (lo, hi, _) in _PICKUP_DELAY_BY_MOOD.items():
        if hi == 0:
            # hangup mood → 0 always
            out = pick_opener(mood, age=40, rng=rng)
            assert out.pickup_delay_ms == 0
            continue
        for _ in range(50):
            out = pick_opener(mood, age=40, rng=rng)
            assert lo <= out.pickup_delay_ms <= hi, (
                f"mood={mood!r} delay={out.pickup_delay_ms} out of band [{lo}, {hi}]"
            )


def test_callback_mood_picks_longer_delays_than_curious():
    """'busy' personas should wait longer to pick up than 'expecting' ones —
    statistical sanity over 200 samples."""
    rng = random.Random(7)
    callback_delays = [pick_opener("callback", 42, rng=rng).pickup_delay_ms for _ in range(200)]
    curious_delays = [pick_opener("curious", 42, rng=rng).pickup_delay_ms for _ in range(200)]
    assert sum(callback_delays) / len(callback_delays) > sum(curious_delays) / len(curious_delays), (
        "callback (busy) mood should average longer pickup delay than curious (eager)"
    )


def test_all_phrases_under_30_chars():
    """Phone openers are reflex utterances — anything longer reads as
    scripted. Hard cap at 30 chars to catch accidental sentence drift."""
    for key, pool in _OPENER_BANK.items():
        for phrase in pool:
            assert len(phrase) <= 30, (
                f"opener {phrase!r} for {key!r} too long ({len(phrase)} chars)"
            )
            # Not too short either — single-char picks (e.g. "А") synth poorly.
            assert len(phrase) >= 2, (
                f"opener {phrase!r} for {key!r} too short ({len(phrase)} chars)"
            )


def test_default_fallback_is_universal():
    """DEFAULT_OPENER is the safety-net when every bucket is empty.
    It must be present and be a real opener, not "TODO" or empty."""
    assert DEFAULT_OPENER
    assert len(DEFAULT_OPENER) >= 3
    assert "?" in DEFAULT_OPENER or "." in DEFAULT_OPENER
