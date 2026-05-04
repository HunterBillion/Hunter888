"""Regression tests for the LLM-reasoning-leak strip in filter_ai_output.

Real production sample (2026-05-04 user session example 1) shipped this
text to the chat:

  "Понятно. Тогда кто это?## Test Output Reasoning
   We need answer as client persona. User says ... Already crafted."

The strip must:
  * cut at the first marker
  * preserve the user-facing prefix
  * record the violation so we can dashboard the rate
  * NOT mangle clean replies

Markers we cover are documented in the implementation comment.
"""
from __future__ import annotations

import pytest

from app.services.content_filter import filter_ai_output


@pytest.mark.parametrize(
    "raw, expected_clean, expect_violation",
    [
        # The actual prod sample, lightly trimmed.
        (
            "Понятно. Тогда кто это?## Test Output Reasoning "
            "We need answer as client persona. Short max 4 sentences. "
            "Already crafted.",
            "Понятно. Тогда кто это?",
            True,
        ),
        # Anthropic-style <think>...</think> blocks.
        (
            "Согласен. <think>The manager is asking for a meeting…</think>",
            "Согласен.",
            True,
        ),
        # Closing tag form.
        (
            "Хорошо, давайте.</think>",
            "Хорошо, давайте.",
            True,
        ),
        # Bracketed internal label.
        (
            "Я подумаю.[ASSISTANT_REASONING] Need to be cold.",
            "Я подумаю.",
            True,
        ),
        # Code-fence leak.
        (
            "Хм, возможно. ```json\n{\"verdict\":\"poor\"}\n```",
            "Хм, возможно.",
            True,
        ),
        # ## Reasoning header variant.
        (
            "Спасибо за информацию.## Reasoning The user asked X.",
            "Спасибо за информацию.",
            True,
        ),
        # Clean reply must pass through untouched.
        (
            "Здравствуйте. Слушаю.",
            "Здравствуйте. Слушаю.",
            False,
        ),
        # Clean reply containing a literal '#' that ISN'T a marker.
        (
            "У меня долг #1 — банк.",
            "У меня долг #1 — банк.",
            False,
        ),
        # Edge: marker right at the end without trailing text.
        (
            "Понятно.## Test Output",
            "Понятно.",
            True,
        ),
    ],
)
def test_strip_reasoning_leak(raw: str, expected_clean: str, expect_violation: bool) -> None:
    cleaned, violations = filter_ai_output(raw)
    assert cleaned == expected_clean
    if expect_violation:
        assert "reasoning_leak" in violations
    else:
        assert "reasoning_leak" not in violations


def test_marker_only_does_not_produce_blank_with_period() -> None:
    """A reply that is JUST a marker (degenerate LLM output) — we strip
    everything and return an empty string rather than a stray period."""
    cleaned, violations = filter_ai_output("## Test Output Reasoning blah")
    assert cleaned == ""
    assert "reasoning_leak" in violations
