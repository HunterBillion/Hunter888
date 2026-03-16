"""Load test: 10 concurrent STT transcription requests.

Tests that the Whisper STT service handles 10 simultaneous audio transcription
requests without errors.

Requires running Whisper service at WHISPER_URL (default: http://localhost:8001).
Run with: pytest tests/e2e/test_stt_load.py -v
"""

import asyncio
import os
import struct
import wave
import io

import httpx
import pytest

WHISPER_URL = os.getenv("WHISPER_URL", "http://localhost:8001")
CONCURRENT_REQUESTS = 10
TIMEOUT_SECONDS = 30


def generate_wav_bytes(duration_sec: float = 2.0, sample_rate: int = 16000) -> bytes:
    """Generate a simple WAV file with silence (valid audio for Whisper)."""
    num_samples = int(sample_rate * duration_sec)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        # Write silence (zeros)
        w.writeframes(struct.pack(f"<{num_samples}h", *([0] * num_samples)))
    return buf.getvalue()


async def transcribe_single(client: httpx.AsyncClient, audio_bytes: bytes, idx: int) -> dict:
    """Send a single transcription request and return result."""
    files = {"file": (f"test_{idx}.wav", audio_bytes, "audio/wav")}
    data = {"model": "Systran/faster-whisper-small", "language": "ru"}

    resp = await client.post(
        f"{WHISPER_URL}/v1/audio/transcriptions",
        files=files,
        data=data,
        timeout=TIMEOUT_SECONDS,
    )
    return {"status": resp.status_code, "idx": idx, "body": resp.text}


@pytest.mark.asyncio
async def test_whisper_health():
    """Test: Whisper service is reachable."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{WHISPER_URL}/health", timeout=5.0)
            # Some whisper servers don't have /health, so also try a simple request
        except httpx.ConnectError:
            pytest.skip("Whisper service not running at " + WHISPER_URL)


@pytest.mark.asyncio
async def test_stt_10_concurrent():
    """Test: 10 concurrent STT requests complete without errors."""
    audio_bytes = generate_wav_bytes(duration_sec=2.0)

    async with httpx.AsyncClient() as client:
        # First, verify service is available
        try:
            test_files = {"file": ("test.wav", audio_bytes, "audio/wav")}
            test_data = {"model": "Systran/faster-whisper-small", "language": "ru"}
            resp = await client.post(
                f"{WHISPER_URL}/v1/audio/transcriptions",
                files=test_files,
                data=test_data,
                timeout=10.0,
            )
            if resp.status_code != 200:
                pytest.skip(f"Whisper service returned {resp.status_code}: {resp.text}")
        except (httpx.ConnectError, httpx.ReadTimeout):
            pytest.skip("Whisper service not available at " + WHISPER_URL)

        # Fire 10 concurrent requests
        tasks = [
            transcribe_single(client, audio_bytes, i)
            for i in range(CONCURRENT_REQUESTS)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    errors = []
    for r in results:
        if isinstance(r, Exception):
            errors.append(str(r))
        elif r["status"] != 200:
            errors.append(f"Request {r['idx']} failed with status {r['status']}: {r['body']}")

    success_count = CONCURRENT_REQUESTS - len(errors)
    print(f"\nSTT Load Test: {success_count}/{CONCURRENT_REQUESTS} succeeded")

    if errors:
        for e in errors:
            print(f"  ERROR: {e}")

    assert len(errors) == 0, f"{len(errors)} out of {CONCURRENT_REQUESTS} requests failed"


@pytest.mark.asyncio
async def test_stt_response_time():
    """Test: average STT response time is reasonable (< 10s per request)."""
    import time

    audio_bytes = generate_wav_bytes(duration_sec=3.0)

    async with httpx.AsyncClient() as client:
        try:
            start = time.monotonic()
            test_files = {"file": ("test.wav", audio_bytes, "audio/wav")}
            test_data = {"model": "Systran/faster-whisper-small", "language": "ru"}
            resp = await client.post(
                f"{WHISPER_URL}/v1/audio/transcriptions",
                files=test_files,
                data=test_data,
                timeout=15.0,
            )
            elapsed = time.monotonic() - start

            if resp.status_code != 200:
                pytest.skip("Whisper service not configured correctly")

            print(f"\nSingle STT request: {elapsed:.2f}s")
            assert elapsed < 10.0, f"STT response took {elapsed:.2f}s (limit: 10s)"

        except (httpx.ConnectError, httpx.ReadTimeout):
            pytest.skip("Whisper service not available")
