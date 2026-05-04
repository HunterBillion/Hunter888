"""Regression tests for the BUG B3 v3 — β scoring additions.

This module pins the new aggregate-mistake penalties wired into
``scoring._score_anti_patterns`` from the real-time
``mistake_detector`` firings (persisted via ``mistake_aggregator``).

Why these tests matter
──────────────────────
The realtime toasts (``coaching.mistake`` WS events) were already
visible in-session before β. The hole this PR closes is that the L4
scoring layer never saw them: ``mistake_detector``'s Redis state is a
small rolling window, not a historical total. So a session where the
manager monologued for 20 turns straight or hogged 80% of talk-time
walked away with the same L4 score as a clean session.

We lock in:

* per-firing weights for monologue / talk_ratio_high / repeated_argument,
* the per-type caps (3 for monologue/repeat, 2 for talk_ratio),
* the deliberate omissions (``no_open_question`` is covered by the
  absence-based ``zero_open_questions`` branch from PR #217;
  ``early_pricing`` needs stage-aware logic, separate spike),
* that the PR #217 ``zero_open_questions`` branch is unbroken by the
  new code path.
"""
from __future__ import annotations

import pytest

from app.services import scoring


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _no_anti_patcher(monkeypatch) -> None:
    """Bypass the LLM anti-pattern detector. We test scoring math, not
    the embeddings call (covered in script_checker tests)."""
    async def _no_anti(text: str) -> list[dict]:
        return []
    monkeypatch.setattr(scoring, "detect_anti_patterns", _no_anti)


def _short_clean_session() -> list[str]:
    """Short transcript that doesn't trigger the zero_open_questions
    fallback (so we can isolate the new mistake_counts penalties)."""
    return ["Здравствуйте.", "Готовы?"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_counts_no_new_entries(monkeypatch) -> None:
    """``mistake_counts={}`` → no ``mistake_*`` entries at all.

    Guards against a future regression where someone iterates the
    aggregate dict even when empty.
    """
    _no_anti_patcher(monkeypatch)
    penalty, details = await scoring._score_anti_patterns(
        _short_clean_session(), mistake_counts={},
    )
    cats = [d.get("category") for d in details.get("detected", [])]
    assert not any(c.startswith("mistake_") for c in cats), cats
    assert penalty == 0.0


@pytest.mark.asyncio
async def test_none_counts_no_new_entries(monkeypatch) -> None:
    """``mistake_counts=None`` (default) → no ``mistake_*`` entries.

    Validates the kwarg defaults so callers that haven't been migrated
    yet keep their pre-β behaviour.
    """
    _no_anti_patcher(monkeypatch)
    penalty, details = await scoring._score_anti_patterns(_short_clean_session())
    cats = [d.get("category") for d in details.get("detected", [])]
    assert not any(c.startswith("mistake_") for c in cats), cats
    assert penalty == 0.0


@pytest.mark.asyncio
async def test_single_monologue_firing_applies_minus_one_point_five(monkeypatch) -> None:
    """1 monologue firing → -1.5 raw applied (then × V3_RESCALE in payload)."""
    _no_anti_patcher(monkeypatch)
    penalty, details = await scoring._score_anti_patterns(
        _short_clean_session(), mistake_counts={"monologue": 1},
    )
    entries = [d for d in details["detected"] if d["category"] == "mistake_monologue"]
    assert len(entries) == 1, entries
    # Stored penalty in the breakdown is rescaled
    assert entries[0]["penalty"] == pytest.approx(-1.5 * scoring.V3_RESCALE)
    assert entries[0]["score"] == 1.0
    # Total raw penalty before the final clamp+rescale: -1.5
    # After clamp+rescale: -1.5 * V3_RESCALE
    assert penalty == pytest.approx(-1.5 * scoring.V3_RESCALE)


@pytest.mark.asyncio
async def test_monologue_cap_at_three_firings(monkeypatch) -> None:
    """5 firings → cap at min(5, 3) = 3 → -1.5 × 3 = -4.5 raw applied.

    Pins the per-type cap. Without it a runaway detector loop could
    blow past the L4 floor on its own.
    """
    _no_anti_patcher(monkeypatch)
    penalty, details = await scoring._score_anti_patterns(
        _short_clean_session(), mistake_counts={"monologue": 5},
    )
    entries = [d for d in details["detected"] if d["category"] == "mistake_monologue"]
    assert len(entries) == 1
    assert entries[0]["penalty"] == pytest.approx(-4.5 * scoring.V3_RESCALE)
    assert entries[0]["score"] == 5.0  # raw firing count surfaced for UX
    assert penalty == pytest.approx(-4.5 * scoring.V3_RESCALE)


@pytest.mark.asyncio
async def test_talk_ratio_cap_at_two_firings(monkeypatch) -> None:
    """3 talk_ratio_high firings → cap at min(3, 2) = 2 → -2.0 × 2 = -4.0 raw."""
    _no_anti_patcher(monkeypatch)
    penalty, details = await scoring._score_anti_patterns(
        _short_clean_session(), mistake_counts={"talk_ratio_high": 3},
    )
    entries = [d for d in details["detected"] if d["category"] == "mistake_talk_ratio_high"]
    assert len(entries) == 1
    assert entries[0]["penalty"] == pytest.approx(-4.0 * scoring.V3_RESCALE)
    assert penalty == pytest.approx(-4.0 * scoring.V3_RESCALE)


@pytest.mark.asyncio
async def test_repeated_argument_per_firing_and_cap(monkeypatch) -> None:
    """2 firings → -1.0 × 2 = -2.0; 10 firings → cap at 3 → -3.0."""
    _no_anti_patcher(monkeypatch)

    penalty2, details2 = await scoring._score_anti_patterns(
        _short_clean_session(), mistake_counts={"repeated_argument": 2},
    )
    e2 = [d for d in details2["detected"] if d["category"] == "mistake_repeated_argument"]
    assert e2[0]["penalty"] == pytest.approx(-2.0 * scoring.V3_RESCALE)
    assert penalty2 == pytest.approx(-2.0 * scoring.V3_RESCALE)

    penalty10, details10 = await scoring._score_anti_patterns(
        _short_clean_session(), mistake_counts={"repeated_argument": 10},
    )
    e10 = [d for d in details10["detected"] if d["category"] == "mistake_repeated_argument"]
    assert e10[0]["penalty"] == pytest.approx(-3.0 * scoring.V3_RESCALE)
    assert penalty10 == pytest.approx(-3.0 * scoring.V3_RESCALE)


@pytest.mark.asyncio
async def test_no_open_question_intentionally_omitted(monkeypatch) -> None:
    """The aggregate dict deliberately skips no_open_question because the
    absence-based zero_open_questions branch (PR #217) already handles
    it. Double-counting would make a single missed open-Q feel
    catastrophic. Lock the omission so future edits don't silently
    re-introduce it."""
    _no_anti_patcher(monkeypatch)
    penalty, details = await scoring._score_anti_patterns(
        _short_clean_session(), mistake_counts={"no_open_question": 99},
    )
    cats = [d.get("category") for d in details.get("detected", [])]
    assert not any(c.startswith("mistake_no_open_question") for c in cats), cats
    # And nothing else was added either
    assert not any(c.startswith("mistake_") for c in cats), cats
    assert penalty == 0.0


@pytest.mark.asyncio
async def test_early_pricing_intentionally_omitted(monkeypatch) -> None:
    """early_pricing requires stage-aware logic (penalty only relevant
    BEFORE stage 4); a flat per-firing weight here would punish
    legitimate pricing discussions in stage 4+. Pin the omission."""
    _no_anti_patcher(monkeypatch)
    penalty, details = await scoring._score_anti_patterns(
        _short_clean_session(), mistake_counts={"early_pricing": 5},
    )
    cats = [d.get("category") for d in details.get("detected", [])]
    assert not any(c.startswith("mistake_") for c in cats), cats
    assert penalty == 0.0


@pytest.mark.asyncio
async def test_zero_open_questions_branch_still_fires(monkeypatch) -> None:
    """PR #217's zero_open_questions branch must remain reachable in the
    presence of the new mistake_counts kwarg. Reuses the same 5-msg
    no-open-Q transcript from test_scoring_red_flags.
    """
    _no_anti_patcher(monkeypatch)
    user_msgs = [
        "Здравствуйте, это Иван из БФЛ.",
        "У нас есть услуга списания долгов.",
        "Многим клиентам помогли.",
        "Заходите к нам.",
        "Согласны?",
    ]
    penalty, details = await scoring._score_anti_patterns(
        user_msgs, mistake_counts=None,
    )
    cats = [d.get("category") for d in details.get("detected", [])]
    assert "zero_open_questions" in cats, cats
    assert penalty < 0


@pytest.mark.asyncio
async def test_combined_floor_clamps_aggregate(monkeypatch) -> None:
    """Even hitting all caps simultaneously, the existing -15.0 floor
    bounds the L4 penalty. -4.5 (mono) + -4.0 (talk) + -3.0 (repeat)
    + -4.0 (zero-OQ from PR #217) = -15.5 → clamped to -15.0 raw,
    rescaled to -11.25.
    """
    _no_anti_patcher(monkeypatch)
    user_msgs = [
        "Здравствуйте, это Иван из БФЛ.",
        "У нас есть услуга списания долгов.",
        "Многим клиентам помогли.",
        "Заходите к нам.",
    ]
    penalty, _ = await scoring._score_anti_patterns(
        user_msgs,
        mistake_counts={"monologue": 9, "talk_ratio_high": 9, "repeated_argument": 9},
    )
    # Floor: max(-15.0, -15.5) * 0.75 = -11.25
    assert penalty == pytest.approx(-15.0 * scoring.V3_RESCALE)
