"""Sprint 0 §5 — AI-tell sentence scrubber.

Pins the scan + scrub contract used by the call streaming pipeline.
Three modes (warn / strip / drop) are tested for both clean sentences
(no-op) and AI-tell sentences.
"""

import pytest

from app.services.ai_tell_scrubber import (
    SCRUB_MODE_DROP,
    SCRUB_MODE_STRIP,
    SCRUB_MODE_WARN,
    ScrubResult,
    scan_sentence,
    scrub,
)


# ─── scan_sentence ───────────────────────────────────────────────────────────


def test_scan_clean_sentence_returns_empty():
    assert scan_sentence("Слушаю, говорите.") == ()


def test_scan_picks_up_seed_phrase():
    hits = scan_sentence("Конечно, давайте разберёмся с этим.")
    assert "конечно" in hits
    assert "давайте разберёмся" in hits


def test_scan_is_case_insensitive():
    assert "конечно" in scan_sentence("КОНЕЧНО, отвечу.")


def test_scan_empty_string_safe():
    assert scan_sentence("") == ()
    assert scan_sentence("   ") == ()


# ─── scrub: warn mode ────────────────────────────────────────────────────────


def test_warn_mode_passes_clean_unchanged():
    result = scrub("Слушаю, говорите.", mode=SCRUB_MODE_WARN)
    assert result.text == "Слушаю, говорите."
    assert result.matches == ()
    assert result.action == "pass"


def test_warn_mode_passes_dirty_unchanged_but_reports_matches():
    result = scrub("Конечно, я подумаю.", mode=SCRUB_MODE_WARN)
    assert result.text == "Конечно, я подумаю."
    assert "конечно" in result.matches
    assert result.action == "pass"


# ─── scrub: drop mode ────────────────────────────────────────────────────────


def test_drop_mode_passes_clean_unchanged():
    result = scrub("Слушаю.", mode=SCRUB_MODE_DROP)
    assert result.text == "Слушаю."
    assert result.action == "pass"


def test_drop_mode_drops_dirty():
    result = scrub("Конечно, я подумаю.", mode=SCRUB_MODE_DROP)
    assert result.text == ""
    assert "конечно" in result.matches
    assert result.action == "dropped"


# ─── scrub: strip mode ───────────────────────────────────────────────────────


def test_strip_mode_strips_leading_phrase():
    """The classic case: 'Конечно, давайте обсудим' → 'Давайте обсудим'."""
    result = scrub("Конечно, давайте обсудим цену.", mode=SCRUB_MODE_STRIP)
    assert result.action == "stripped"
    assert result.text.startswith("Давайте")
    assert "конечно" not in result.text.lower()


def test_strip_mode_drops_when_residue_too_short():
    """'Конечно' alone strips to empty → drop."""
    result = scrub("Конечно.", mode=SCRUB_MODE_STRIP)
    assert result.action == "dropped"
    assert result.text == ""


def test_strip_mode_passes_when_match_is_embedded_not_prefix():
    """If the AI-tell sits mid-sentence, stripping would butcher grammar.
    Safe behaviour is warn-equivalent: pass the text, surface the match.
    """
    sentence = (
        "Слушайте, я ведь не маленький, чтобы вы мне говорили хороший вопрос."
    )
    result = scrub(sentence, mode=SCRUB_MODE_STRIP)
    assert result.action == "pass"
    assert "хороший вопрос" in result.matches
    assert result.text == sentence


def test_strip_mode_recapitalises_residue():
    """The residue's first letter is upper-cased so the speaker doesn't
    sound like they started mid-word."""
    result = scrub("Безусловно, цена меня не устраивает.", mode=SCRUB_MODE_STRIP)
    assert result.action == "stripped"
    assert result.text[0].isupper()


# ─── safety / fallback ───────────────────────────────────────────────────────


def test_unknown_mode_falls_back_to_warn():
    """A bad config string must NOT blackhole audio. Unknown mode → warn."""
    result = scrub("Конечно, понятно.", mode="nonsense_mode")
    assert result.action == "pass"
    assert result.text == "Конечно, понятно."
    assert "конечно" in result.matches


def test_scrub_result_is_frozen_dataclass():
    """ScrubResult is immutable so callers can pass it around without
    fearing accidental mutation in async tasks."""
    result = scrub("Hello", mode=SCRUB_MODE_WARN)
    with pytest.raises((AttributeError, Exception)):  # frozen → FrozenInstanceError
        result.text = "modified"  # type: ignore


def test_clean_short_sentence_skips_all_logic():
    """Single-word reply that has no AI-tell hits a fast path."""
    result = scrub("Да.", mode=SCRUB_MODE_DROP)
    assert result.action == "pass"
    assert result.text == "Да."
