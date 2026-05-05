"""PR-C tests for call cognitive modifier (working memory, barge-in,
distraction, silence-as-pressure).

Pre-fix the AI client treated chat and call sessions identically modulo
phone register. Real phone calls differ on cognitive dimensions the AI
ignored. These tests verify each cue produces the right behavioural
hint in the system prompt.
"""
from __future__ import annotations

from app.services.llm import build_call_cognitive_modifier


def test_baseline_call_renders_working_memory_block():
    """Even with no special cues, the call modifier must inject the
    working-memory limit so the AI doesn't quote message 1 verbatim
    during minute 8 of a call."""
    out = build_call_cognitive_modifier()
    assert "ЗВОНОК — когнитивная модель" in out
    assert "ВОСПРИЯТИЕ_ЗВОНКА" in out
    assert "последние 4-5 реплик" in out


def test_barge_in_cue_with_chars():
    """Barge-in: manager interrupted mid-reply. AI must know it didn't
    finish so it doesn't reference cut content."""
    out = build_call_cognitive_modifier(
        interrupted_last_turn=True,
        interrupted_played_chars=42,
    )
    assert "ПЕРЕБИЛИ" in out
    assert "~42" in out
    assert "не ссылайся на оборванное" in out


def test_barge_in_zero_chars():
    """Manager started talking before any audio reached them — AI
    treats last turn as not having happened."""
    out = build_call_cognitive_modifier(
        interrupted_last_turn=True,
        interrupted_played_chars=0,
    )
    assert "ПЕРЕБИЛИ" in out
    assert "ничего ещё не сказал" in out


def test_silence_pressure_cue_at_threshold():
    """5+ seconds of manager silence on a phone is awkward — AI should
    proactively prompt («алло, вы тут?»)."""
    out = build_call_cognitive_modifier(user_silent_seconds=7.0)
    assert "МОЛЧАНИЕ" in out
    assert "7 секунд" in out
    assert "алло" in out.lower() or "поторопи" in out


def test_silence_pressure_below_threshold_silent():
    """A 2-second pause is normal speech tempo, not awkward. No cue."""
    out = build_call_cognitive_modifier(user_silent_seconds=2.0)
    assert "МОЛЧАНИЕ" not in out


def test_distraction_cue_passthrough():
    """Caller-supplied distraction hint must appear verbatim so the
    WS handler can A/B different wording without redeploying."""
    out = build_call_cognitive_modifier(
        distraction_hint="Где-то рядом плачет ребёнок — попроси повторить.",
    )
    assert "ОТВЛЁК" in out
    assert "плачет ребёнок" in out


def test_no_cues_still_returns_working_memory_only():
    """No barge-in, no silence, no distraction — but we still want the
    working-memory line (call mode is its baseline)."""
    out = build_call_cognitive_modifier()
    assert "ВОСПРИЯТИЕ_ЗВОНКА" in out
    # And nothing else.
    assert "ПЕРЕБИЛИ" not in out
    assert "МОЛЧАНИЕ" not in out
    assert "ОТВЛЁК" not in out


def test_all_cues_compose_in_one_block():
    """All four cues fired at once — modifier renders them all in one
    section header. This is the worst case for prompt size; validates
    we don't accidentally double the section header."""
    out = build_call_cognitive_modifier(
        interrupted_last_turn=True,
        interrupted_played_chars=15,
        user_silent_seconds=8.5,
        distraction_hint="отвлёкся на улицу",
    )
    # Single section header, four cue tags.
    assert out.count("## ЗВОНОК — когнитивная модель") == 1
    assert "ВОСПРИЯТИЕ_ЗВОНКА" in out
    assert "ПЕРЕБИЛИ" in out
    assert "МОЛЧАНИЕ" in out
    assert "ОТВЛЁК" in out
