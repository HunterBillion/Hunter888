"""Calibration tests for the weighted hangup decision (BUG 1 follow-up).

Each case mirrors a specific real or hypothetical session pattern. If any
of these flips, hangup behaviour visibly changes for users — so the
weights are pinned by these expectations rather than by their numerical
values directly.
"""
from __future__ import annotations

import pytest

from app.services.hangup_decision import (
    THRESHOLD,
    HangupSignals,
    decide_hangup,
)


# ── Hard NOs (must NOT trigger) ─────────────────────────────────────────────


def test_no_substring_means_no_hangup_no_matter_what() -> None:
    """Without a farewell phrase in the reply, the scorer never fires."""
    s = HangupSignals(
        substring_hit=False,
        is_question=False,
        msg_count=20,
        emotion="hostile",
        rudeness_detected=True,
        ai_said_farewell_before=True,
    )
    d = decide_hangup(s)
    assert d.should_end is False
    assert d.score == 0.0


def test_theatrical_exit_on_turn_2_does_not_trigger() -> None:
    """LLM improvising 'всё, до свидания, разговор окончен!' early on a
    cold emotion must NOT end the call — that's the regression v3 was
    written to prevent."""
    s = HangupSignals(
        substring_hit=True,
        is_question=False,
        msg_count=2,
        emotion="cold",
    )
    d = decide_hangup(s)
    assert d.should_end is False, f"score={d.score}, breakdown={d.breakdown}"
    # Sanity: substring + not_question = 0.60, just under threshold.
    assert 0.55 <= d.score < THRESHOLD


def test_short_call_with_question_does_not_trigger() -> None:
    """'Ну, до свидания?' — question form invites continuation."""
    s = HangupSignals(
        substring_hit=True,
        is_question=True,
        msg_count=3,
        emotion="cold",
    )
    d = decide_hangup(s)
    assert d.should_end is False


# ── Hard YESs (must trigger) ────────────────────────────────────────────────


def test_prod_case_dead_son_prank_triggers_at_msg10() -> None:
    """The motivating prod session: user pranks AI about a dead son,
    AI is hostile, says 'до свидания, кладу трубку'. With the v3 hard
    gates this STILL didn't end (FSM emotion was 'callback', not
    'hostile' literal at that moment). The weighted scorer must catch
    it via rudeness_detected + msg_count + not_question."""
    s = HangupSignals(
        substring_hit=True,
        is_question=False,
        msg_count=10,
        emotion="callback",
        rudeness_detected=True,
    )
    d = decide_hangup(s)
    assert d.should_end is True
    assert d.score >= THRESHOLD
    assert "rudeness_detected" in d.breakdown


def test_polite_cold_goodbye_after_four_useless_turns_triggers() -> None:
    """Manager spent 4 turns off-topic; AI politely says 'всего доброго'
    on a cold emotion. The v3 gate REQUIRED 'hostile' AND msg>=8 — both
    fail here. Weighted: substring + not_question + cold_with_context +
    msg_medium = 0.40 + 0.20 + 0.15 + 0.10 = 0.85 ⇒ trigger."""
    s = HangupSignals(
        substring_hit=True,
        is_question=False,
        msg_count=5,
        emotion="cold",
    )
    d = decide_hangup(s)
    assert d.should_end is True
    assert d.score >= THRESHOLD


def test_repeated_ai_farewells_eventually_trigger() -> None:
    """Edge: AI said 'до свидания' once already; says it again. The
    'ai_said_farewell_before' bonus pushes a borderline case over."""
    s = HangupSignals(
        substring_hit=True,
        is_question=False,
        msg_count=3,                         # below msg_medium threshold
        emotion="cold",
        ai_said_farewell_before=True,
    )
    # 0.40 + 0.20 + 0.20 = 0.80 ⇒ trigger
    d = decide_hangup(s)
    assert d.should_end is True


# ── Borderline / audit traceability ─────────────────────────────────────────


def test_breakdown_is_populated_when_triggered() -> None:
    s = HangupSignals(
        substring_hit=True,
        is_question=False,
        msg_count=10,
        emotion="hostile",
        rudeness_detected=True,
    )
    d = decide_hangup(s)
    assert d.should_end is True
    assert set(d.breakdown).issuperset({
        "substring_hit",
        "emotion_hostile_like",
        "not_question",
        "msg_count_long",
        "rudeness_detected",
    })
    # Score should match summed components exactly (weights pinned).
    assert d.score == pytest.approx(sum(d.breakdown.values()), rel=1e-3)


def test_threshold_is_065() -> None:
    """If you are about to relax this, write a new test case for the
    user-visible behaviour you intend to enable, then change the
    threshold and re-run the suite. Don't tune in the dark."""
    assert THRESHOLD == 0.65
