"""Deepgram STT — DEPRECATED SHIM (2026-04-18).

Original 464-line Deepgram WebSocket + REST client was removed as dead code:
- settings.stt_provider default = "whisper" (Deepgram never dispatched via stt.py)
- settings.deepgram_api_key default = "" (no API key configured)
- Platform uses navy.api Whisper as primary STT (WHISPER_URL=https://api.navy)
- Required `websockets` library was not in pyproject.toml dependencies

This shim preserves public names (DeepgramStreamingSTT, StreamingTranscript,
transcribe_rest, transcribe_with_fallback) so existing imports in training.py
and stt.py do not break. All calls signal "unavailable" → callers fall through
to Whisper via transcribe_audio().

To re-enable Deepgram in the future: restore this file from git history of
commits prior to 2026-04-18 and add `websockets>=12` to pyproject.toml.
"""

import logging
from dataclasses import dataclass, field

from app.services.stt import STTResult, STTError

logger = logging.getLogger(__name__)


@dataclass
class StreamingTranscript:
    """Accumulated transcript from a streaming session. Kept for import compatibility."""
    text: str = ""
    confidence: float = 0.0
    is_final: bool = False
    language: str = "ru"
    duration_ms: int = 0
    words: list = field(default_factory=list)


class DeepgramStreamingSTT:
    """No-op shim. start_stream() always returns False → caller falls back to Whisper."""

    def __init__(self):
        self._connected = False

    def is_connected(self) -> bool:
        return False

    async def start_stream(
        self,
        language: str | None = None,
        model: str | None = None,
        sample_rate: int = 16000,
        encoding: str = "linear16",
        channels: int = 1,
    ) -> bool:
        # Signal "unavailable" — training.py checks return value and falls back to Whisper.
        return False

    async def send_audio(self, chunk: bytes) -> None:
        raise STTError("Deepgram streaming disabled (shim)")

    async def get_transcript(self) -> StreamingTranscript:
        return StreamingTranscript()

    async def get_final_result(self) -> STTResult:
        raise STTError("Deepgram disabled (shim)")

    async def close(self) -> None:
        return None

    def reset(self) -> None:
        return None


async def transcribe_rest(
    audio_bytes: bytes,
    *,
    language: str | None = None,
    model: str | None = None,
    mime_type: str = "audio/webm",
) -> STTResult:
    """Shim: always raises STTError → caller falls back to Whisper via stt.transcribe_audio."""
    raise STTError("Deepgram REST disabled (shim). Use app.services.stt.transcribe_audio.")


async def transcribe_with_fallback(
    audio_bytes: bytes,
    *,
    language: str | None = None,
    model: str | None = None,
) -> STTResult:
    """Shim that immediately falls back to Whisper via stt.transcribe_audio."""
    from app.services.stt import transcribe_audio
    logger.debug("Deepgram shim: dispatching to Whisper")
    return await transcribe_audio(audio_bytes, language=language, model=model)
