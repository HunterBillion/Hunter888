"""STT adapter for self-hosted faster-whisper (OpenAI-compatible API).

Sends audio to WHISPER_URL/v1/audio/transcriptions and returns transcription
with confidence. Gracefully handles Whisper unavailability.
"""

import io
import logging
import time
from dataclasses import dataclass

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class STTResult:
    text: str
    confidence: float
    language: str
    duration_ms: int


class STTError(Exception):
    """Raised when the STT service is unavailable or returns an error."""


async def transcribe_audio(
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

    # Build multipart form data (OpenAI-compatible)
    files = {
        "file": ("audio.webm", io.BytesIO(audio_bytes), "audio/webm"),
    }
    data = {
        "model": mdl,
        "language": lang,
        "response_format": "verbose_json",
    }

    start_ts = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
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

    return STTResult(
        text=text,
        confidence=round(confidence, 3),
        language=detected_language,
        duration_ms=int(audio_duration_sec * 1000) or elapsed_ms,
    )
