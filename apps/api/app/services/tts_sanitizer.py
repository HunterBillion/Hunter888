"""TTS text sanitizer — strip / convert stage-direction markers before synthesis.

Background (2026-05-03 prod incident)
-------------------------------------
Operators were hearing the literal word "звёздочка вздох звёздочка" in TTS
output. Root cause: ``inject_hesitations`` / ``inject_pauses`` in
``tts.py`` injects markers like ``*вздох*`` into the text fed to
ElevenLabs, but ElevenLabs reads them character-for-character unless they
are real audio-tag syntax.

Industry precedent
------------------
* **ElevenLabs v3 audio tags** — ``[sigh]``, ``[laughs]``, ``[whispers]``,
  etc. are pronounced as the sound, not the word. Reference:
  https://elevenlabs.io/docs/best-practices/prompting/controls
* **Pipecat** — ``BaseTextFilter`` chain in
  ``pipecat/processors/text_filters/`` strips/normalises stage directions
  before TTS frames go out.
* **LiveKit Agents** — ``before_tts_cb`` hook in
  ``livekit-agents/livekit/agents/tts/stream_adapter.py`` does the same.

Behaviour
---------
* ``*…*`` / ``(…)`` / ``<…>`` (max 40 chars inside) are detected.
* Inner word looked up in ``RU_TO_AUDIO_TAG`` / ``EN_TO_AUDIO_TAG``.
  - Hit → replaced with ``[<tag>]`` (canonical ElevenLabs v3 audio tag).
  - Miss → stripped entirely (nothing left to mispronounce).
* Real SSML ``<break time="..."/>`` is preserved verbatim.
* The function is pure / side-effect-free, so unit-testing is trivial.
"""
from __future__ import annotations

import re
from typing import Final

# Mapping of cosmetic markers (inserted by ``inject_hesitations`` /
# ``inject_pauses`` in tts.py, or potentially leaking from the LLM) to
# canonical ElevenLabs v3 audio tags. Keys are lowercased and stripped of
# punctuation/whitespace before lookup.
RU_TO_AUDIO_TAG: Final[dict[str, str]] = {
    "вздох": "sighs",
    "тяжёлый вздох": "sighs",
    "тяжелый вздох": "sighs",
    "нервный вздох": "sighs",
    "глубокий вздох": "sighs",
    "вдох": "inhales",
    "выдох": "exhales",
    "смеётся": "laughs",
    "смеется": "laughs",
    "смех": "laughs",
    "усмехается": "laughs",
    "хмыкает": "laughs",
    "шёпотом": "whispers",
    "шепотом": "whispers",
    "шепчет": "whispers",
}

EN_TO_AUDIO_TAG: Final[dict[str, str]] = {
    "sigh": "sighs",
    "sighs": "sighs",
    "heavy sigh": "sighs",
    "deep sigh": "sighs",
    "inhale": "inhales",
    "exhale": "exhales",
    "laugh": "laughs",
    "laughs": "laughs",
    "laughing": "laughs",
    "whisper": "whispers",
    "whispers": "whispers",
    "whispering": "whispers",
}

# *…*  or  (…)  or  <…>  with up to 40 chars inside.
# We exclude '<break' to keep real SSML break tags intact (handled
# separately below).
_STAGE_DIR_RE: Final[re.Pattern[str]] = re.compile(
    r"\*([^*\n]{1,40})\*"          # *вздох*
    r"|\(([^)\n]{1,40})\)"          # (вздох)
    r"|<(?!break\b|/break\b)([^>\n]{1,40})>",  # <sigh> but not <break ../>
    flags=re.IGNORECASE,
)

# Collapse runs of whitespace introduced by stripped markers.
_WS_RE: Final[re.Pattern[str]] = re.compile(r"[ \t]{2,}")


def _normalise_inner(token: str) -> str:
    """Lowercase + strip punctuation/whitespace for lookup."""
    return token.strip().strip(".,!?;:").lower()


def sanitize_for_tts(text: str) -> str:
    """Strip / convert stage-direction markers in ``text`` for ElevenLabs v3.

    Pure function — safe to call on every synthesis request.

    Examples
    --------
    >>> sanitize_for_tts("*вздох* да, понимаю")
    '[sighs] да, понимаю'
    >>> sanitize_for_tts("(нервный вздох) что вы хотите")
    '[sighs] что вы хотите'
    >>> sanitize_for_tts("так... *неизвестное* и точка")
    'так...  и точка'
    >>> sanitize_for_tts('пауза <break time="500ms"/> ок')
    'пауза <break time="500ms"/> ок'
    """
    if not text or ("*" not in text and "(" not in text and "<" not in text):
        return text

    def _repl(m: re.Match[str]) -> str:
        inner_raw = m.group(1) or m.group(2) or m.group(3) or ""
        key = _normalise_inner(inner_raw)
        if not key:
            return ""
        # Russian first (more common in this codebase)
        tag = RU_TO_AUDIO_TAG.get(key) or EN_TO_AUDIO_TAG.get(key)
        if tag:
            return f"[{tag}]"
        # Unknown marker (e.g. "*пауза*") → drop. Better silence than
        # the model speaking the literal word.
        return ""

    out = _STAGE_DIR_RE.sub(_repl, text)
    out = _WS_RE.sub(" ", out)
    return out.strip()


__all__ = ["sanitize_for_tts", "RU_TO_AUDIO_TAG", "EN_TO_AUDIO_TAG"]
