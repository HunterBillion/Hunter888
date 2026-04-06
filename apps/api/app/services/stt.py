"""STT adapter for self-hosted faster-whisper (OpenAI-compatible API).

Sends audio to WHISPER_URL/v1/audio/transcriptions and returns transcription
with confidence. Gracefully handles Whisper unavailability.
"""

import io
import logging
import re
import time
from dataclasses import dataclass

import httpx

from app.config import settings

_MIN_AUDIO_SIZE = 500  # Increased: 100 bytes is too small for any valid audio


def _detect_mime_type(audio_bytes: bytes) -> tuple[str, str]:
    """Detect audio MIME type and file extension from magic bytes.

    Returns:
        (mime_type, extension) e.g. ("audio/webm", "webm")
    """
    if len(audio_bytes) < 4:
        return "audio/webm", "webm"

    # WAV: starts with RIFF....WAVE
    if audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
        return "audio/wav", "wav"

    # OGG (includes Opus): starts with OggS
    if audio_bytes[:4] == b"OggS":
        return "audio/ogg", "ogg"

    # WebM/Matroska: starts with 0x1A45DFA3
    if audio_bytes[:4] == b"\x1a\x45\xdf\xa3":
        return "audio/webm", "webm"

    # MP3: starts with ID3 or 0xFF 0xFB/0xFF 0xF3/0xFF 0xF2
    if audio_bytes[:3] == b"ID3" or (audio_bytes[0] == 0xFF and audio_bytes[1] in (0xFB, 0xF3, 0xF2, 0xE3)):
        return "audio/mpeg", "mp3"

    # FLAC: starts with fLaC
    if audio_bytes[:4] == b"fLaC":
        return "audio/flac", "flac"

    # Default: assume webm (most common from browser MediaRecorder)
    return "audio/webm", "webm"

_BFL_CORRECTIONS = {
    r"\bбэ\s*фэ\s*эл\b": "БФЛ",
    r"\bбанкрот\s+физ\s*лиц\b": "банкротство физических лиц",
    r"\bарбитражн\w*\s+управля\w*\b": "арбитражный управляющий",
    r"\bфин\s*управля\w*\b": "финансовый управляющий",
    r"\bреструктуриз\w*\b": "реструктуризация",
    r"\bсубсиди[ая]рн\w*\b": "субсидиарная ответственность",
}

logger = logging.getLogger(__name__)


@dataclass
class STTResult:
    text: str
    confidence: float
    language: str
    duration_ms: int


class STTError(Exception):
    """Raised when the STT service is unavailable or returns an error."""


def _validate_audio(audio_bytes: bytes) -> None:
    if len(audio_bytes) < _MIN_AUDIO_SIZE:
        raise STTError(f"Audio too short ({len(audio_bytes)} bytes)")


def _postprocess_bfl_terms(text: str) -> str:
    for pattern, replacement in _BFL_CORRECTIONS.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


async def transcribe_audio(
    audio_bytes: bytes,
    *,
    language: str | None = None,
    model: str | None = None,
) -> STTResult:
    """Transcribe audio bytes using the configured STT provider.

    Routes to Deepgram (with Whisper fallback) or Whisper based on
    settings.stt_provider. Deepgram falls back to Whisper automatically
    on failure.

    Args:
        audio_bytes: Raw audio data (WAV, WebM, OGG, etc.)
        language: Override language (default from settings)
        model: Override model name (default from settings)

    Returns:
        STTResult with transcription text, confidence, language, and duration.

    Raises:
        STTError: If all STT services are unreachable.
    """
    if settings.stt_provider == "deepgram" and settings.deepgram_api_key:
        try:
            from app.services.stt_deepgram import transcribe_with_fallback
            return await transcribe_with_fallback(
                audio_bytes, language=language, model=model,
            )
        except Exception as e:
            logger.warning("Deepgram dispatch failed, using Whisper: %s", e)
            # Fall through to Whisper

    return await _transcribe_whisper(audio_bytes, language=language, model=model)


async def _transcribe_whisper(
    audio_bytes: bytes,
    *,
    language: str | None = None,
    model: str | None = None,
) -> STTResult:
    """Transcribe audio bytes using the self-hosted faster-whisper API.

    The API is OpenAI-compatible at WHISPER_URL/v1/audio/transcriptions.

    Args:
        audio_bytes: Raw audio data (WAV, WebM, OGG, etc.)
        language: Override language (default from settings: "ru")
        model: Override model name (default from settings)

    Returns:
        STTResult with transcription text, confidence, language, and duration.

    Raises:
        STTError: If Whisper is unreachable or returns an error.
    """
    url = f"{settings.whisper_url.rstrip('/')}/v1/audio/transcriptions"
    lang = language or settings.whisper_language
    mdl = model or settings.whisper_model

    # Detect MIME type from magic bytes instead of hardcoding
    mime_type, ext = _detect_mime_type(audio_bytes)
    files = {
        "file": (f"audio.{ext}", io.BytesIO(audio_bytes), mime_type),
    }
    data = {
        "model": mdl,
        "language": lang,
        "response_format": "verbose_json",
    }

    _validate_audio(audio_bytes)

    start_ts = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=float(settings.whisper_timeout_seconds)) as client:
            response = await client.post(url, files=files, data=data)
    except httpx.ConnectError:
        logger.error("STT service unavailable at %s", url)
        raise STTError(f"Whisper service unavailable at {settings.whisper_url}")
    except httpx.TimeoutException:
        logger.error("STT request timed out for %s", url)
        raise STTError("Whisper service request timed out")
    except httpx.HTTPError as exc:
        logger.error("STT HTTP error: %s", exc)
        raise STTError(f"Whisper HTTP error: {exc}")

    elapsed_ms = int((time.monotonic() - start_ts) * 1000)

    if response.status_code != 200:
        detail = response.text[:500]
        logger.error("STT error %d: %s", response.status_code, detail)
        raise STTError(f"Whisper returned {response.status_code}: {detail}")

    body = response.json()

    # Extract fields from verbose_json response
    text = body.get("text", "").strip()
    # Duration comes from Whisper's analysis of the audio
    audio_duration_sec = body.get("duration", 0.0)
    # Segments may carry per-segment confidence; average them
    segments = body.get("segments", [])
    if segments:
        avg_confidence = sum(
            seg.get("avg_logprob", -1.0) for seg in segments
        ) / len(segments)
        # Convert log-prob to a 0..1 confidence estimate (heuristic)
        # avg_logprob is typically between -1 (bad) and 0 (perfect)
        confidence = max(0.0, min(1.0, 1.0 + avg_confidence))
    else:
        confidence = 0.0 if not text else 0.5

    detected_language = body.get("language", lang)

    text = _postprocess_bfl_terms(text)

    return STTResult(
        text=text,
        confidence=round(confidence, 3),
        language=detected_language,
        duration_ms=int(audio_duration_sec * 1000) or elapsed_ms,
    )
