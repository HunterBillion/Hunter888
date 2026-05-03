"""End-of-call marker detection — explicit hangup signal from the LLM.

Background (2026-05-03 prod incident, BUG 1)
--------------------------------------------
The previous AI-farewell auto-end relied on a substring match of the LAST
sentence of the LLM reply (``"до свидания"``, ``"всего доброго"``, …) gated
by ``current_emotion == "hostile"`` AND ``message_count >= 8``. The gates
were tightened deliberately because the LLM frequently improvises
dramatic farewells (``"всё, до свидания, разговор окончен!"``) when it
doesn't actually mean it. The cost: real, polite, deserved hangups never
fire because the emotion stays ``cold`` / ``curious``.

Industry pattern (Vapi ``endCallPhrases`` / custom stop-tokens / OpenAI
function-calling):

* Give the LLM an explicit signal it must emit when it decides to hang up.
* Trust that signal more than substring heuristics.
* Strip the signal before TTS / FE display so the user never sees it.

The system prompt rule 9 in :func:`app.services.llm._build_system_prompt`
instructs the persona: when ending the call, append ``[END_CALL]`` to the
reply. This module detects + strips the marker.

The marker path bypasses the ``hostile`` / ``msg_count >= 8`` gates and
keeps only a minimal ``msg_count >= 4`` sanity floor (handled in the
caller) so a buggy first reply can't trigger an immediate hangup.
"""
from __future__ import annotations

import re
from typing import Final

# Match the marker with surrounding whitespace, case-insensitive. The
# marker MUST appear as a standalone bracketed token — embedded use like
# ``"... and don't [end_call] me"`` still matches but that's acceptable:
# the LLM is instructed to use it only at end-of-reply, and even an
# accidental match strips harmlessly.
_END_CALL_RE: Final[re.Pattern[str]] = re.compile(
    r"\s*\[END_CALL\]\s*",
    flags=re.IGNORECASE,
)


def detect_end_call(text: str) -> bool:
    """Return True iff ``text`` contains the ``[END_CALL]`` marker."""
    if not text or "[" not in text:
        return False
    return bool(_END_CALL_RE.search(text))


def strip_end_call(text: str) -> str:
    """Return ``text`` with all ``[END_CALL]`` markers removed.

    Multi-marker / lowercase / extra-whitespace forms are normalised to a
    single space and the result is trimmed.
    """
    if not text:
        return text
    out = _END_CALL_RE.sub(" ", text)
    # Collapse double spaces introduced by the strip.
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out.strip()


def detect_and_strip(text: str) -> tuple[bool, str]:
    """One-shot: ``(has_marker, text_without_marker)``."""
    has = detect_end_call(text)
    return has, strip_end_call(text) if has else text


__all__ = ["detect_end_call", "strip_end_call", "detect_and_strip"]
