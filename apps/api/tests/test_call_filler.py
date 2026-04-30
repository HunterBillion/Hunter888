"""IL-1 (2026-04-30) — call filler audio bank tests.

Pin the contract:
  • flag default OFF
  • pick_filler returns a phrase from the right per-emotion bank
  • SILENCE_RATE produces no-text outcome ~15% of the time (deterministic
    via seeded RNG)
  • unknown / "hangup" emotions never produce a filler
  • each filler is at least MIN_FILLER_LEN chars
  • returned phrases are short (≤ 30 chars — these are thinking sounds,
    not full sentences) — protects against accidental long entries
"""

from __future__ import annotations

import random

import pytest

from app.services.call_filler import (
    FILLERS_BY_EMOTION,
    MIN_FILLER_LEN,
    SILENCE_RATE,
    FillerChoice,
    pick_filler,
)


def test_flag_default_off():
    from app.config import settings
    assert settings.call_filler_v1 is False, (
        "call_filler_v1 must default to False until we ship + measure"
    )


@pytest.mark.parametrize("emotion", ["cold", "guarded", "curious", "considering",
                                      "negotiating", "deal", "testing",
                                      "callback", "hostile"])
def test_filler_for_known_emotion_returns_text(emotion: str):
    """Each non-hangup emotion has a non-empty bank and yields a filler
    when the RNG forbids the silence branch."""
    rng = random.Random(0)  # deterministic; happens to roll past the silence gate
    out = pick_filler(emotion, rng=rng)
    assert isinstance(out, FillerChoice)
    if out.text is not None:
        assert len(out.text) >= MIN_FILLER_LEN
        assert out.emotion == emotion


def test_filler_for_hangup_is_always_silent():
    """About-to-hang-up clients shouldn't make a thinking sound."""
    for seed in range(20):
        rng = random.Random(seed)
        out = pick_filler("hangup", rng=rng)
        assert out.text is None, "hangup emotion must never emit a filler"


def test_filler_for_unknown_emotion_is_silent():
    out = pick_filler("nonsense", rng=random.Random(0))
    assert out.text is None


def test_silence_rate_roughly_matches_constant():
    """Over many samples, the no-filler rate should approximate SILENCE_RATE.

    Allow ±5pp slack — this is a sanity guard against accidentally
    hardcoding 0% or 100% silence.
    """
    rng = random.Random(42)
    n = 1000
    silent = 0
    for _ in range(n):
        out = pick_filler("cold", rng=rng)
        if out.text is None:
            silent += 1
    observed = silent / n
    assert abs(observed - SILENCE_RATE) <= 0.05, (
        f"observed silence rate {observed:.3f} drifts from SILENCE_RATE={SILENCE_RATE}"
    )


def test_all_filler_phrases_are_short():
    """Fillers are thinking sounds, not full sentences. Keep < 30 chars."""
    for emotion, bank in FILLERS_BY_EMOTION.items():
        for phrase in bank:
            assert len(phrase) <= 30, (
                f"filler {phrase!r} for {emotion!r} is too long — "
                "thinking sounds should be ≤ 30 chars"
            )


def test_all_filler_phrases_meet_min_length():
    """A single Cyrillic char synth produces inaudible audio. Enforce floor."""
    for emotion, bank in FILLERS_BY_EMOTION.items():
        for phrase in bank:
            assert len(phrase) >= MIN_FILLER_LEN, (
                f"filler {phrase!r} for {emotion!r} is below MIN_FILLER_LEN"
            )


def test_filler_choice_carries_emotion():
    """Caller should be able to log which emotion drove the pick."""
    rng = random.Random(0)
    out = pick_filler("guarded", rng=rng)
    assert out.emotion == "guarded"


def test_pick_is_distributed_over_bank():
    """No single phrase should dominate (>80%) over many picks for one emotion."""
    bank = FILLERS_BY_EMOTION["cold"]
    rng = random.Random(7)
    counts: dict[str, int] = {p: 0 for p in bank}
    n_drawn = 0
    for _ in range(2000):
        out = pick_filler("cold", rng=rng)
        if out.text is not None:
            counts[out.text] = counts.get(out.text, 0) + 1
            n_drawn += 1
    if n_drawn:
        max_share = max(counts.values()) / n_drawn
        assert max_share <= 0.8, (
            f"phrase distribution skewed: {counts!r} (max share {max_share:.2f})"
        )
