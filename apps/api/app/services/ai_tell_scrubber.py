"""Sentence-level AI-tell scrubber for the call humanisation pipeline.

Sprint 0 (2026-04-29) — narrow phrase scanner that runs *before* a
sentence is dispatched to ElevenLabs. The pre-existing post-stream
filter (in services/llm.py) only logs violations *after* delivery
("filter_ai_output triggered AFTER delivery" — see WARN log there); by
then the audio has already played in the user's ear.

This module is intentionally tiny:
  * One source of phrases: ``app.services.ai_lexicon.KNOWN_RUSSIAN_AI_PHRASES``.
  * One matching strategy: case-fold + substring.
  * Three behaviours: warn / strip / drop. Default: warn.

Why not the full ``nlp_cheat_detector.detect_ai_text_markers``?
  The cheat detector mixes a dozen heuristics — formal vocabulary
  density, sentence-length variance, hesitation absence, etc. Those are
  great for *post-hoc* AI-text detection, but they fire on perfectly
  legitimate short call replies (``"да, понимаю."`` — zero hesitations,
  uniform length, formal-ish, "ai_probability"≈0.4). Running them on a
  stream chunk would produce a flood of false positives. The phrase
  list is the narrowest, most predictable signal.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.services.ai_lexicon import KNOWN_RUSSIAN_AI_PHRASES

logger = logging.getLogger(__name__)


SCRUB_MODE_WARN = "warn"
SCRUB_MODE_STRIP = "strip"
SCRUB_MODE_DROP = "drop"
_VALID_MODES = frozenset({SCRUB_MODE_WARN, SCRUB_MODE_STRIP, SCRUB_MODE_DROP})

# When mode=strip, only consider an AI-tell strippable if it appears within
# this many characters of the start. Beyond that the tell is "embedded" in
# the sentence and a clean strip is unsafe (would butcher grammar).
_STRIP_PREFIX_BUDGET = 30

# After stripping, the residue must be at least this many characters to be
# worth speaking — otherwise we treat the strip as a drop.
_MIN_RESIDUE_CHARS = 6


@dataclass(frozen=True)
class ScrubResult:
    """Outcome of scanning one sentence.

    Attributes
    ----------
    text:
        The sentence to actually pass to TTS. Same as the input in ``warn``
        mode and when no AI-tell was matched. May be a stripped substring
        in ``strip`` mode, or empty if ``drop`` (or strip-with-empty-residue).
    matches:
        List of phrases (lower-cased) that matched. Empty if clean. Always
        populated regardless of mode — callers can log it for observability
        even in warn mode.
    action:
        One of "pass" (audio plays unchanged), "stripped" (audio plays
        a shorter version), "dropped" (audio is suppressed).
    """

    text: str
    matches: tuple[str, ...]
    action: str  # pass | stripped | dropped


def scan_sentence(sentence: str) -> tuple[str, ...]:
    """Return the AI-tell phrases (lowercased) that occur in the sentence.

    Pure substring match against ``KNOWN_RUSSIAN_AI_PHRASES`` — no regex,
    no fuzzy. The set is the contract; if a phrase needs to be caught it
    must be added there (or to the auto-mining output).
    """
    if not sentence:
        return ()
    normalized = sentence.lower()
    hits = tuple(p for p in KNOWN_RUSSIAN_AI_PHRASES if p in normalized)
    return hits


def scrub(sentence: str, mode: str = SCRUB_MODE_WARN) -> ScrubResult:
    """Scan ``sentence`` and apply the requested ``mode``.

    Modes
    -----
    warn (default):
        Audio plays unchanged. Matches are returned for the caller to log
        and emit observability events. Use this until the FP rate is
        validated against real call traffic.
    strip:
        If a match starts within the first ``_STRIP_PREFIX_BUDGET`` chars,
        cut the sentence to the substring AFTER the match and trim leading
        punctuation/whitespace. If the residue is shorter than
        ``_MIN_RESIDUE_CHARS``, treat as drop.
    drop:
        If any match is found, suppress the audio entirely (caller skips
        the TTS task).

    Unknown modes silently fall back to warn — settings.py validates the
    string but a stale .env should not break the audio path.
    """
    if mode not in _VALID_MODES:
        # We do not raise: a bad config string must not blackhole audio.
        logger.warning(
            "ai_tell_scrubber: unknown mode %r — falling back to warn", mode,
        )
        mode = SCRUB_MODE_WARN

    matches = scan_sentence(sentence)
    if not matches:
        return ScrubResult(text=sentence, matches=(), action="pass")

    if mode == SCRUB_MODE_WARN:
        return ScrubResult(text=sentence, matches=matches, action="pass")

    if mode == SCRUB_MODE_DROP:
        return ScrubResult(text="", matches=matches, action="dropped")

    # strip mode: try to cut a leading AI-tell off cleanly.
    normalized = sentence.lower()
    # Pick the *earliest* match — that's the one we can strip without
    # damaging the rest of the sentence. Multiple matches: warn-only
    # outcome unless the first is a leading prefix.
    earliest_idx = min(normalized.find(m) for m in matches)
    if earliest_idx > _STRIP_PREFIX_BUDGET:
        # AI-tell is embedded mid-sentence; safe behaviour is to keep
        # the text and let the warn signal go to logs.
        return ScrubResult(text=sentence, matches=matches, action="pass")

    earliest_match = next(
        m for m in matches if normalized.find(m) == earliest_idx
    )
    # Cut to the position right after the matched phrase, then trim
    # leading separators (", ", ". ", " — ", quotes, etc).
    cut_at = earliest_idx + len(earliest_match)
    residue = sentence[cut_at:].lstrip(' ,.;:—–-…!?"\'»«')
    # Re-capitalise the residue's first letter so the speaker doesn't
    # sound like they started mid-word.
    if residue:
        residue = residue[0].upper() + residue[1:]
    if len(residue) < _MIN_RESIDUE_CHARS:
        return ScrubResult(text="", matches=matches, action="dropped")
    return ScrubResult(text=residue, matches=matches, action="stripped")
