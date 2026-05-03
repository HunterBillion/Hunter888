"""Snapshot tests for end_call_marker — guard the explicit hangup signal.

Each case represents a real LLM-output shape that must round-trip
correctly: the marker must be detected when present, must NOT be
detected when absent, and must always be stripped from the user-visible
text without leaving artefacts.
"""
from __future__ import annotations

import pytest

from app.services.end_call_marker import (
    detect_and_strip,
    detect_end_call,
    strip_end_call,
)


@pytest.mark.parametrize(
    "raw, expected_detect, expected_stripped",
    [
        # Canonical usage — marker at very end after farewell.
        ("Всё, до свидания. [END_CALL]", True, "Всё, до свидания."),
        # Lower-case marker (LLM might forget the case).
        ("Спасибо, я подумаю. [end_call]", True, "Спасибо, я подумаю."),
        # Mixed case.
        ("Удачи. [End_Call]", True, "Удачи."),
        # Marker without trailing punctuation/space.
        ("Прощайте[END_CALL]", True, "Прощайте"),
        # No marker — must be untouched.
        ("Слушайте, я подумаю и сам перезвоню.", False, "Слушайте, я подумаю и сам перезвоню."),
        # Empty.
        ("", False, ""),
        # Marker mid-text (LLM placed badly) — still detected and stripped.
        ("Ну ладно [END_CALL] до свидания", True, "Ну ладно до свидания"),
        # Multiple markers (LLM emitted twice) — both stripped.
        ("[END_CALL] всё [END_CALL]", True, "всё"),
        # Substring-only farewell WITHOUT marker — must NOT be detected
        # (this is what the legacy substring gate handles separately).
        ("До свидания, всего доброго", False, "До свидания, всего доброго"),
    ],
)
def test_marker_round_trip(raw: str, expected_detect: bool, expected_stripped: str) -> None:
    assert detect_end_call(raw) is expected_detect
    assert strip_end_call(raw) == expected_stripped
    has, stripped = detect_and_strip(raw)
    assert has is expected_detect
    assert stripped == expected_stripped


def test_strip_idempotent() -> None:
    """Stripping twice must produce the same result."""
    raw = "Всё, до свидания. [END_CALL]"
    once = strip_end_call(raw)
    twice = strip_end_call(once)
    assert once == twice == "Всё, до свидания."


def test_no_brackets_short_circuits() -> None:
    """Inputs without '[' shortcut to no-detect (microbenchmark sanity)."""
    assert detect_end_call("обычный ответ без маркеров") is False
