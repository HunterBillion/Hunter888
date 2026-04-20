"""Case-intro TTS — personality-voice mapping + audio synthesis.

Generates audio for the narrative case briefing so the user HEARS the
detective / professor read the case file. Best-effort: any failure returns
None, frontend falls back to silent text display.

Voice selection per user decision (2026-04-18):
  - detective → navy voice "onyx"   (deep, noir)
  - professor → navy voice "echo"   (calm, academic)

Backend prefers navy.api (OpenAI-compatible /v1/audio/speech) because it's
already configured as primary TTS (ElevenLabs has gender-split voice-IDs
meant for AI-client personas, not quiz narrators).
"""

from __future__ import annotations

import base64
import logging
from typing import Literal

logger = logging.getLogger(__name__)

Personality = Literal["professor", "detective", "blitz"]

_VOICE_MAP: dict[Personality, str] = {
    "detective": "onyx",    # deep, male, investigative
    "professor": "echo",    # calm, lecturing
    "blitz":     "shimmer", # peppy; unused (blitz skips case)
}

_SPEED_MAP: dict[Personality, float] = {
    "detective": 0.92,  # slightly slow, noir feel
    "professor": 1.0,
    "blitz":     1.1,
}


async def synth_case_intro_audio(
    intro_text: str,
    personality: Personality,
) -> str | None:
    """Synthesize case-intro narrative; return data-URL string or None.

    Format: "data:audio/mpeg;base64,<b64>" — ready for <audio src=...>.

    Keeps text under 2.5k chars (navy OpenAI-compat limit ~4k, safety margin).
    Returns None on any configuration/network error — caller proceeds silent.
    """
    from app.config import settings
    if not (settings.navy_tts_enabled and settings.local_llm_url and settings.local_llm_api_key):
        logger.debug("quiz_v2.voice: navy TTS disabled, skipping intro audio")
        return None

    text = (intro_text or "").strip()
    if not text:
        return None
    if len(text) > 2500:
        text = text[:2500]

    voice = _VOICE_MAP.get(personality, "echo")
    speed = _SPEED_MAP.get(personality, 1.0)

    try:
        from app.services.tts import _synthesize_navy  # private but stable path
        audio_bytes = await _synthesize_navy(text, voice=voice, speed=speed)
        if not audio_bytes or len(audio_bytes) < 200:
            return None
        b64 = base64.b64encode(audio_bytes).decode("ascii")
        logger.info(
            "quiz_v2.voice: synthesized intro audio personality=%s voice=%s bytes=%d",
            personality, voice, len(audio_bytes),
        )
        return f"data:audio/mpeg;base64,{b64}"
    except Exception as exc:
        logger.warning("quiz_v2.voice: synth failed (%s) — intro will be silent", exc)
        return None
