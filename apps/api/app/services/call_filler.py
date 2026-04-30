"""IL-1 (2026-04-30) — filler audio bank.

Goal: kill the 1.7-4.7s of dead air between "manager finishes speaking" and
"AI starts replying" by playing a short in-character thinking sound (≤500ms
of audio, e.g. "Ну...", "Ммм...", "Так-так...") IMMEDIATELY when the user
turn ends, while the LLM is still generating the real reply.

Why this works
──────────────
Every voice product that "feels human" does this (Vapi audio caching,
ElevenLabs Conversational AI, Sierra) — pre-cached short fillers played
during LLM gen reduce perceived latency by ~50% even though wall-clock
is unchanged.

The architecture
────────────────
Reserve sentence_index=0 in the streaming TTS pipeline for the filler.
Real LLM-generated sentences then start at sentence_index=1, etc. The
existing client-side queue (useTTS.ts playNextChunk) plays in order:
    [0] filler → [1] first real sentence → [2] second real sentence ...

The filler text is picked by emotion (cold/guarded/curious/...) so it
matches the persona's mood — a hostile client says "Что?" not "Ммм...".
15% of the time we skip the filler entirely (real humans sometimes
respond instantly without a thinking sound).

The filler audio itself goes through the regular ElevenLabs synth path,
so the **first** session pays a ~400-800ms TTS round-trip. Subsequent
sessions hit the existing ``tts.py`` LRU cache (keyed on text + voice +
emotion + factors) and play instantly. A future enhancement: pre-warm
the cache at server startup.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ── Filler banks per emotion ────────────────────────────────────────────────
#
# Each list has 4-7 short Russian fillers. Keys mirror the 10 canonical
# emotion states from llm.py (_EMOTION_BEHAVIORS). "hangup" is intentionally
# empty — the call is ending, no thinking sound needed.

FILLERS_BY_EMOTION: dict[str, tuple[str, ...]] = {
    "cold": (
        "Так...",
        "Ну?",
        "Кто это?",
        "Что?",
        "Слушаю...",
    ),
    "guarded": (
        "Минутку...",
        "Подождите...",
        "Хм...",
        "Так-так...",
        "Эээ...",
    ),
    "curious": (
        "Ммм...",
        "Так-так...",
        "А-а...",
        "Понятно...",
        "Ну-ка...",
    ),
    "considering": (
        "Ммм...",
        "Так...",
        "Подождите-ка...",
        "Дайте подумать...",
        "Так-так...",
    ),
    "negotiating": (
        "Так...",
        "Хм...",
        "Ну-у...",
        "Давайте посмотрим...",
    ),
    "deal": (
        "Хорошо...",
        "Так...",
        "Понятно...",
    ),
    "testing": (
        "Ну-ка...",
        "Хм...",
        "Интересно...",
        "Так-так...",
    ),
    "callback": (
        "Подождите...",
        "Минутку...",
        "Эээ...",
    ),
    "hostile": (
        "Что?",
        "Ну?",
        "Опять?",
        "Чего?",
    ),
    "hangup": (),
}

# 15% of turns get NO filler — sometimes a real person responds instantly.
SILENCE_RATE = 0.15

# A filler must be at least this many chars to be worth a TTS round-trip.
# "А?" is 2 chars; we want at minimum 3 so synth produces audible audio.
MIN_FILLER_LEN = 3


@dataclass(frozen=True)
class FillerChoice:
    """One filler decision for one turn."""

    text: str | None  # None means "no filler this turn"
    emotion: str
    rng_seed: int | None = None  # for tests


def pick_filler(
    emotion: str,
    *,
    rng: random.Random | None = None,
) -> FillerChoice:
    """Pick a filler for ``emotion``, or None if we're skipping this turn.

    The returned choice is a stable record:
      * ``text`` — the Russian filler phrase to TTS, or None to skip.
      * ``emotion`` — the input emotion (for logging / observability).

    Caller is responsible for piping ``text`` into the streaming TTS
    pipeline at sentence_index=0 (see ``_handle_text_message`` /
    ``_generate_character_reply`` integration).
    """
    rng = rng if rng is not None else random.Random()

    if rng.random() < SILENCE_RATE:
        return FillerChoice(text=None, emotion=emotion)

    options = FILLERS_BY_EMOTION.get(emotion)
    if not options:
        # Unknown emotion or "hangup" — don't fire a filler.
        return FillerChoice(text=None, emotion=emotion)

    pick = rng.choice(options)
    if len(pick) < MIN_FILLER_LEN:
        return FillerChoice(text=None, emotion=emotion)

    return FillerChoice(text=pick, emotion=emotion)


__all__ = [
    "FillerChoice",
    "FILLERS_BY_EMOTION",
    "MIN_FILLER_LEN",
    "SILENCE_RATE",
    "pick_filler",
]
