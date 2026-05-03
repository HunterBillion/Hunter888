"""Snapshot tests for tts_sanitizer — guard against regressions in the
stage-direction stripping pipeline.

Each case represents a real failure mode observed in prod (2026-05-03)
where ElevenLabs spoke the literal marker text instead of performing
the sound.
"""
from __future__ import annotations

import pytest

from app.services.tts_sanitizer import sanitize_for_tts


@pytest.mark.parametrize(
    "raw, expected",
    [
        # Russian markers injected by inject_hesitations / inject_breathing.
        ("*вздох* да, понимаю", "[sighs] да, понимаю"),
        ("*тяжёлый вздох* что вы хотите", "[sighs] что вы хотите"),
        ("*нервный вздох* ладно", "[sighs] ладно"),
        ("*вдох* итак", "[inhales] итак"),
        ("*выдох* хорошо", "[exhales] хорошо"),
        # Parens form.
        ("(вздох) понятно", "[sighs] понятно"),
        ("(нервный вздох) что вы хотите", "[sighs] что вы хотите"),
        # Angle-bracket form (LLM may emit <sigh> on its own).
        ("<sigh> okay", "[sighs] okay"),
        ("<whisper> hello", "[whispers] hello"),
        # Unknown markers — must be stripped, never spoken.
        ("так... *пауза* и точка", "так... и точка"),
        ("привет *unknown_action* как дела", "привет как дела"),
        # Multiple in one utterance.
        ("*вздох* да *смеётся* конечно", "[sighs] да [laughs] конечно"),
        # Real SSML break tag must survive.
        ('пауза <break time="500ms"/> ок', 'пауза <break time="500ms"/> ок'),
        # Empty / no-marker passthrough.
        ("просто текст без маркеров", "просто текст без маркеров"),
        ("", ""),
        # English variants seen in mixed-language LLM output.
        ("(sigh) I understand", "[sighs] I understand"),
        ("*laughs* yeah", "[laughs] yeah"),
        # Edge: marker with trailing punctuation inside.
        ("*вздох.* да", "[sighs] да"),
    ],
)
def test_sanitize_for_tts(raw: str, expected: str) -> None:
    assert sanitize_for_tts(raw) == expected


def test_sanitize_does_not_crash_on_none_or_weird_input() -> None:
    assert sanitize_for_tts("") == ""
    assert sanitize_for_tts("***") == ""  # degenerate, but must not raise
    # Long marker — exceeds 40-char inner limit; should be passed through
    # unchanged (the regex won't match), preserving "no surprise" rule.
    long_inner = "x" * 60
    out = sanitize_for_tts(f"*{long_inner}* tail")
    assert "tail" in out
