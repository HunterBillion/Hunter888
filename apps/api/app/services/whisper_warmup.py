"""Whisper cold-start warmup.

Phase I (2026-05-08).

The remote faster-whisper service (e.g. Navy proxy) loads its model
lazily. The FIRST transcription request after an idle period (or
immediately after container restart) takes 6–10 seconds while the
model loads into memory. Subsequent requests are fast (~200-500ms).

The WS handler at training.py has a `_check_stt_available()` that
hits `GET /v1/models` (cheap, 10s timeout) — but `/v1/models` does
NOT trigger model load. The cold-start race only manifests when the
first user's audio chunk lands and gets a slow response, sometimes
exceeding our internal STT timeout.

This module sends a TINY silent WAV through the actual transcription
endpoint at startup, forcing the remote model to load BEFORE any
real user request arrives. Best-effort; failure logs a warning but
never blocks app startup.

Idempotent — safe to call multiple times. Each call is a fresh HTTP
request so repeated warmup also keeps the model hot if it tends to
unload between sessions.
"""

from __future__ import annotations

import asyncio
import io
import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


# Minimal valid WAV: 16-bit PCM mono 16000Hz, 100ms of silence.
# RIFF header + fmt chunk + data chunk + 3200 bytes of silence (200 samples).
def _build_silent_wav() -> bytes:
    """Build a tiny valid WAV file containing 100ms of silence at 16kHz."""
    sample_rate = 16000
    num_samples = sample_rate // 10  # 100ms
    # 16-bit PCM mono → 2 bytes per sample.
    data_size = num_samples * 2
    riff_size = 36 + data_size  # full size minus first 8 bytes
    out = io.BytesIO()
    out.write(b"RIFF")
    out.write(riff_size.to_bytes(4, "little"))
    out.write(b"WAVE")
    out.write(b"fmt ")
    out.write((16).to_bytes(4, "little"))            # fmt chunk size
    out.write((1).to_bytes(2, "little"))             # PCM
    out.write((1).to_bytes(2, "little"))             # mono
    out.write(sample_rate.to_bytes(4, "little"))     # sample rate
    out.write((sample_rate * 2).to_bytes(4, "little"))  # byte rate
    out.write((2).to_bytes(2, "little"))             # block align
    out.write((16).to_bytes(2, "little"))            # bits per sample
    out.write(b"data")
    out.write(data_size.to_bytes(4, "little"))
    out.write(b"\x00" * data_size)                   # silent samples
    return out.getvalue()


async def warmup_whisper(timeout_seconds: float = 30.0) -> bool:
    """Send a tiny silent WAV through the Whisper transcription endpoint.

    Forces the remote model to load if it wasn't already. Returns True
    on a 2xx response (any text or empty), False on any failure.
    Best-effort — never raises.

    Skips when:
      - Deepgram is the configured STT provider (no Whisper to warm)
      - WHISPER_URL is empty (Whisper not configured)
    """
    if settings.stt_provider == "deepgram" and settings.deepgram_api_key:
        logger.debug("whisper_warmup: skipped — Deepgram is primary STT")
        return False
    if not settings.whisper_url:
        logger.debug("whisper_warmup: skipped — WHISPER_URL not configured")
        return False

    # Same URL normalization as in services/stt.py.
    base = settings.whisper_url.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    url = f"{base}/v1/audio/transcriptions"

    silent_wav = _build_silent_wav()
    files = {"file": ("warmup.wav", io.BytesIO(silent_wav), "audio/wav")}
    data = {
        "model": settings.whisper_model,
        "language": settings.whisper_language,
        "response_format": "verbose_json",
    }
    headers: dict[str, str] = {}
    if settings.whisper_api_key:
        headers["Authorization"] = f"Bearer {settings.whisper_api_key}"

    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(url, files=files, data=data, headers=headers)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        if response.status_code == 200:
            logger.info(
                "whisper_warmup: success | latency=%dms | model=%s | lang=%s",
                elapsed_ms, settings.whisper_model, settings.whisper_language,
            )
            return True
        logger.warning(
            "whisper_warmup: HTTP %d after %dms | body=%r",
            response.status_code, elapsed_ms, response.text[:200],
        )
        return False
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        logger.warning(
            "whisper_warmup: failed after %dms | %s: %s",
            elapsed_ms, type(exc).__name__, exc,
        )
        return False


async def warmup_whisper_background() -> None:
    """Fire-and-forget warmup task for FastAPI lifespan.

    Wraps warmup_whisper() with a small delay so it doesn't compete
    with other startup tasks for HTTP connections. Logs once and
    exits — does NOT loop. The model stays warm long enough that
    real user traffic keeps it hot after the first session.
    """
    # Delay so we don't fight with other lifespan startup HTTP work
    # (LLM health probe, BlitzPool warmup, etc).
    await asyncio.sleep(3.0)
    await warmup_whisper(timeout_seconds=30.0)
