"""Deepgram streaming STT client for Hunter888.

Provides real-time speech-to-text using Deepgram Nova-2 API.
Supports two modes:
1. WebSocket streaming (preferred) — real-time interim + final results
2. REST API fallback — batch transcription via /v1/listen

Falls back to Whisper if Deepgram is unavailable.

Requires: DEEPGRAM_API_KEY in .env
"""

import asyncio
import io
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

from app.config import settings
from app.services.stt import STTResult, STTError, _postprocess_bfl_terms

logger = logging.getLogger(__name__)

# Deepgram API endpoints
_DG_WS_URL = "wss://api.deepgram.com/v1/listen"
_DG_REST_URL = "https://api.deepgram.com/v1/listen"

# Try to import websockets; fall back to REST-only if unavailable
try:
    import websockets
    import websockets.exceptions
    _HAS_WEBSOCKETS = True
except ImportError:
    _HAS_WEBSOCKETS = False
    logger.info("websockets library not available — Deepgram will use REST API only")


@dataclass
class StreamingTranscript:
    """Accumulated transcript from a streaming session."""
    text: str = ""
    confidence: float = 0.0
    is_final: bool = False
    language: str = "ru"
    duration_ms: int = 0
    words: list = field(default_factory=list)


class DeepgramStreamingSTT:
    """Deepgram streaming STT client using WebSocket or REST fallback.

    Usage (WebSocket streaming):
        dg = DeepgramStreamingSTT()
        await dg.start_stream(language="ru")
        await dg.send_audio(chunk1)
        await dg.send_audio(chunk2)
        transcript = await dg.get_transcript()
        await dg.close()

    Usage (REST fallback — automatic if WS unavailable):
        dg = DeepgramStreamingSTT()
        result = await dg.transcribe_rest(audio_bytes)
    """

    def __init__(self):
        self._ws = None
        self._connected = False
        self._closing = False
        self._transcript = StreamingTranscript()
        self._final_transcripts: list[str] = []
        self._interim_text: str = ""
        self._listener_task: Optional[asyncio.Task] = None
        self._total_confidence: float = 0.0
        self._confidence_count: int = 0
        self._total_duration_ms: int = 0
        self._reconnect_attempts: int = 0
        self._max_reconnect_attempts: int = 3

    @property
    def is_connected(self) -> bool:
        return self._connected and self._ws is not None

    async def start_stream(
        self,
        language: str | None = None,
        model: str | None = None,
        sample_rate: int = 16000,
        encoding: str = "linear16",
        channels: int = 1,
    ) -> bool:
        """Open a WebSocket connection to Deepgram for streaming STT.

        Args:
            language: Language code (default from settings)
            model: Deepgram model (default from settings)
            sample_rate: Audio sample rate in Hz
            encoding: Audio encoding format
            channels: Number of audio channels

        Returns:
            True if connection established, False if falling back to REST.
        """
        if not settings.deepgram_api_key:
            logger.warning("Deepgram API key not configured — cannot start stream")
            return False

        if not _HAS_WEBSOCKETS:
            logger.info("websockets not available — will use REST API for Deepgram")
            return False

        lang = language or settings.deepgram_language
        mdl = model or settings.deepgram_model

        # Build WebSocket URL with query params
        params = {
            "model": mdl,
            "language": lang,
            "punctuate": "true",
            "interim_results": "true",
            "endpointing": "300",  # 300ms silence = end of utterance
            "vad_events": "true",
            "smart_format": "true",
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        ws_url = f"{_DG_WS_URL}?{query}"

        headers = {
            "Authorization": f"Token {settings.deepgram_api_key}",
        }

        try:
            self._ws = await websockets.connect(
                ws_url,
                additional_headers=headers,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5,
            )
            self._connected = True
            self._closing = False
            self._reconnect_attempts = 0

            # Start background listener for transcription results
            self._listener_task = asyncio.create_task(self._listen_responses())

            logger.info(
                "Deepgram WS connected | model=%s lang=%s",
                mdl, lang,
            )
            return True

        except Exception as e:
            logger.error("Failed to connect to Deepgram WS: %s", e)
            self._connected = False
            self._ws = None
            return False

    async def _listen_responses(self) -> None:
        """Background task: listen for Deepgram transcription responses."""
        if not self._ws:
            return

        try:
            async for message in self._ws:
                if self._closing:
                    break

                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    logger.warning("Deepgram sent non-JSON message: %s", message[:100])
                    continue

                msg_type = data.get("type", "")

                if msg_type == "Results":
                    await self._process_result(data)
                elif msg_type == "Metadata":
                    # Connection metadata — log for debugging
                    request_id = data.get("request_id", "")
                    logger.debug("Deepgram metadata: request_id=%s", request_id)
                elif msg_type == "SpeechStarted":
                    logger.debug("Deepgram: speech started")
                elif msg_type == "UtteranceEnd":
                    logger.debug("Deepgram: utterance end")
                elif msg_type == "Error":
                    err_msg = data.get("message", "Unknown Deepgram error")
                    logger.error("Deepgram error: %s", err_msg)

        except websockets.exceptions.ConnectionClosed as e:
            logger.warning("Deepgram WS closed: code=%s reason=%s", e.code, e.reason)
            self._connected = False
        except Exception as e:
            if not self._closing:
                logger.error("Deepgram listener error: %s", e)
            self._connected = False

    async def _process_result(self, data: dict) -> None:
        """Process a Deepgram transcription result."""
        channel = data.get("channel", {})
        alternatives = channel.get("alternatives", [])
        if not alternatives:
            return

        best = alternatives[0]
        transcript_text = best.get("transcript", "").strip()
        confidence = best.get("confidence", 0.0)
        words = best.get("words", [])

        is_final = data.get("is_final", False)
        speech_final = data.get("speech_final", False)

        # Track duration from word timestamps
        if words:
            last_word = words[-1]
            duration_sec = last_word.get("end", 0.0)
            self._total_duration_ms = int(duration_sec * 1000)

        if is_final and transcript_text:
            # Final result for this utterance segment
            self._final_transcripts.append(transcript_text)
            self._total_confidence += confidence
            self._confidence_count += 1
            self._interim_text = ""
            logger.debug(
                "Deepgram final: '%s' (conf=%.3f)",
                transcript_text[:80], confidence,
            )
        elif transcript_text:
            # Interim result — update current partial
            self._interim_text = transcript_text

        # Update combined transcript
        final_text = " ".join(self._final_transcripts)
        if self._interim_text:
            combined = f"{final_text} {self._interim_text}".strip()
        else:
            combined = final_text

        avg_conf = (
            self._total_confidence / self._confidence_count
            if self._confidence_count > 0
            else confidence
        )

        self._transcript = StreamingTranscript(
            text=combined,
            confidence=avg_conf,
            is_final=speech_final,
            language=settings.deepgram_language,
            duration_ms=self._total_duration_ms,
            words=words,
        )

    async def send_audio(self, chunk: bytes) -> None:
        """Send an audio chunk to Deepgram WebSocket.

        Args:
            chunk: Raw audio bytes (PCM, WAV, WebM, etc.)
        """
        if not self._connected or not self._ws:
            raise STTError("Deepgram WS not connected")

        try:
            await self._ws.send(chunk)
        except websockets.exceptions.ConnectionClosed:
            self._connected = False
            raise STTError("Deepgram WS connection lost")
        except Exception as e:
            logger.error("Error sending audio to Deepgram: %s", e)
            raise STTError(f"Deepgram send error: {e}")

    async def get_transcript(self) -> StreamingTranscript:
        """Get the latest accumulated transcript.

        Returns:
            StreamingTranscript with combined interim + final text.
        """
        return self._transcript

    async def get_final_result(self) -> STTResult:
        """Finalize the stream and return an STTResult compatible with the existing pipeline.

        Sends a close-stream message, waits briefly for final results,
        then returns the accumulated transcript as an STTResult.
        """
        if self._connected and self._ws:
            try:
                # Send close-stream message to signal end of audio
                await self._ws.send(json.dumps({"type": "CloseStream"}))
                # Wait a moment for final results to arrive
                await asyncio.sleep(0.5)
            except Exception:
                pass

        transcript = self._transcript
        text = _postprocess_bfl_terms(transcript.text.strip())

        return STTResult(
            text=text,
            confidence=round(transcript.confidence, 3),
            language=transcript.language,
            duration_ms=transcript.duration_ms,
        )

    async def close(self) -> None:
        """Close the WebSocket connection and clean up."""
        self._closing = True
        self._connected = False

        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        logger.debug("Deepgram streaming STT closed")

    def reset(self) -> None:
        """Reset transcript accumulators for a new utterance."""
        self._transcript = StreamingTranscript()
        self._final_transcripts = []
        self._interim_text = ""
        self._total_confidence = 0.0
        self._confidence_count = 0
        self._total_duration_ms = 0


async def transcribe_rest(
    audio_bytes: bytes,
    *,
    language: str | None = None,
    model: str | None = None,
    mime_type: str = "audio/webm",
) -> STTResult:
    """Transcribe audio using Deepgram REST API (non-streaming fallback).

    This is used when:
    - websockets library is not available
    - WebSocket connection failed
    - Single audio blob (push-to-talk) mode

    Args:
        audio_bytes: Complete audio file bytes
        language: Language code (default from settings)
        model: Deepgram model (default from settings)
        mime_type: Audio MIME type

    Returns:
        STTResult compatible with existing pipeline.

    Raises:
        STTError if Deepgram REST API fails.
    """
    if not settings.deepgram_api_key:
        raise STTError("Deepgram API key not configured")

    lang = language or settings.deepgram_language
    mdl = model or settings.deepgram_model

    params = {
        "model": mdl,
        "language": lang,
        "punctuate": "true",
        "smart_format": "true",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{_DG_REST_URL}?{query}"

    headers = {
        "Authorization": f"Token {settings.deepgram_api_key}",
        "Content-Type": mime_type,
    }

    start_ts = time.monotonic()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, content=audio_bytes, headers=headers)
    except httpx.ConnectError:
        logger.error("Deepgram REST API unreachable")
        raise STTError("Deepgram REST API unreachable")
    except httpx.TimeoutException:
        logger.error("Deepgram REST API timed out")
        raise STTError("Deepgram REST API timed out")
    except httpx.HTTPError as exc:
        logger.error("Deepgram REST HTTP error: %s", exc)
        raise STTError(f"Deepgram REST HTTP error: {exc}")

    elapsed_ms = int((time.monotonic() - start_ts) * 1000)

    if response.status_code != 200:
        detail = response.text[:500]
        logger.error("Deepgram REST error %d: %s", response.status_code, detail)
        raise STTError(f"Deepgram returned {response.status_code}: {detail}")

    body = response.json()

    # Parse Deepgram REST response
    results = body.get("results", {})
    channels = results.get("channels", [])
    if not channels:
        raise STTError("Deepgram returned empty channel results")

    alternatives = channels[0].get("alternatives", [])
    if not alternatives:
        raise STTError("Deepgram returned no alternatives")

    best = alternatives[0]
    text = best.get("transcript", "").strip()
    confidence = best.get("confidence", 0.0)

    # Duration from metadata
    metadata = body.get("metadata", {})
    duration_sec = metadata.get("duration", 0.0)

    text = _postprocess_bfl_terms(text)

    return STTResult(
        text=text,
        confidence=round(confidence, 3),
        language=lang,
        duration_ms=int(duration_sec * 1000) or elapsed_ms,
    )


async def transcribe_with_fallback(
    audio_bytes: bytes,
    *,
    language: str | None = None,
    model: str | None = None,
) -> STTResult:
    """Transcribe audio via Deepgram REST, falling back to Whisper on failure.

    This is the recommended entry point for batch (non-streaming) transcription
    when stt_provider is set to "deepgram".
    """
    from app.services.stt import _detect_mime_type

    mime_type, _ = _detect_mime_type(audio_bytes)

    try:
        return await transcribe_rest(
            audio_bytes,
            language=language,
            model=model,
            mime_type=mime_type,
        )
    except STTError as e:
        logger.warning("Deepgram failed, falling back to Whisper: %s", e)
        from app.services.stt import transcribe_audio as whisper_transcribe
        return await whisper_transcribe(audio_bytes, language=language)
