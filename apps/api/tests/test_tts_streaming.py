"""IL-2 (2026-04-30) — ElevenLabs streaming endpoint tests.

Pin the contract:
  * flag ``elevenlabs_streaming_enabled`` defaults OFF.
  * when OFF: synthesize_speech hits /v1/text-to-speech/{voice_id}
    via client.post (legacy path, byte-identical to before).
  * when ON: hits /v1/text-to-speech/{voice_id}/stream via
    client.stream() with optimize_streaming_latency=3 query param.
  * accumulator returns the full mp3 bytes, same TTSResult shape.
  * non-200 from /stream is surfaced as TTSError or TTSQuotaExhausted
    same as the legacy path.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class _FakeStream:
    """Async-context-manager replacement for ``httpx.AsyncClient.stream(...)``.

    Yields a fake response with the given status + body. ``aiter_bytes`` chunks
    the body in 64-byte slices to exercise the accumulator path.
    """

    def __init__(self, status_code: int, body: bytes):
        self._resp = MagicMock()
        self._resp.status_code = status_code
        self._body = body

        async def _aiter():
            for i in range(0, len(body), 64):
                yield body[i:i + 64]
        self._resp.aiter_bytes = _aiter

        async def _aread():
            return body
        self._resp.aread = _aread

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, *a):
        return None


def _make_fake_client(stream_response: _FakeStream | None = None,
                     post_response: MagicMock | None = None):
    """Patch the shared httpx client. Either stream() or post() will be hit."""
    client = MagicMock()
    client.stream = MagicMock(return_value=stream_response)
    client.post = AsyncMock(return_value=post_response)
    return client


@pytest.mark.asyncio
async def test_streaming_off_uses_post_endpoint(monkeypatch):
    """Default flag OFF: legacy /text-to-speech/{voice_id} via client.post."""
    from app.services import tts as tts_mod

    fake_post_resp = MagicMock(
        status_code=200,
        content=b"\x00" * 256,
        text="",
    )
    client = _make_fake_client(post_response=fake_post_resp)
    monkeypatch.setattr(tts_mod, "_get_shared_client", lambda: client)

    with patch.object(tts_mod, "settings") as s:
        s.elevenlabs_api_key = "xx"
        s.elevenlabs_streaming_enabled = False
        s.elevenlabs_base_url = ""
        s.elevenlabs_model = "eleven_v3"
        s.navy_tts_enabled = False

        result = await tts_mod.synthesize_speech("привет", "voice-1", use_cache=False)

    assert result.audio_bytes == b"\x00" * 256
    assert client.post.await_count == 1
    # The URL hit must NOT have /stream when flag is off.
    called_url = client.post.await_args.args[0]
    assert called_url.endswith("/voice-1"), called_url
    assert "/stream" not in called_url
    # No streaming params in the post call.
    called_params = client.post.await_args.kwargs.get("params", {})
    assert "optimize_streaming_latency" not in called_params


@pytest.mark.asyncio
async def test_streaming_on_uses_stream_endpoint(monkeypatch):
    """Flag ON: /text-to-speech/{voice_id}/stream + optimize_streaming_latency=3."""
    from app.services import tts as tts_mod

    body = b"\xff" * 512
    stream = _FakeStream(200, body)
    client = _make_fake_client(stream_response=stream)
    monkeypatch.setattr(tts_mod, "_get_shared_client", lambda: client)

    with patch.object(tts_mod, "settings") as s:
        s.elevenlabs_api_key = "xx"
        s.elevenlabs_streaming_enabled = True
        s.elevenlabs_base_url = ""
        s.elevenlabs_model = "eleven_v3"
        s.navy_tts_enabled = False

        result = await tts_mod.synthesize_speech("привет", "voice-1", use_cache=False)

    assert result.audio_bytes == body
    # Should NOT have used post.
    assert client.post.await_count == 0
    # Should have used stream once.
    assert client.stream.call_count == 1
    args, kwargs = client.stream.call_args
    assert args[0] == "POST"
    called_url = args[1]
    assert called_url.endswith("/voice-1/stream"), called_url
    params = kwargs.get("params") or {}
    assert params.get("optimize_streaming_latency") == "3"


@pytest.mark.asyncio
async def test_streaming_on_status_402_raises_quota_exhausted(monkeypatch):
    from app.services import tts as tts_mod

    stream = _FakeStream(402, b"quota exceeded")
    client = _make_fake_client(stream_response=stream)
    monkeypatch.setattr(tts_mod, "_get_shared_client", lambda: client)

    with patch.object(tts_mod, "settings") as s:
        s.elevenlabs_api_key = "xx"
        s.elevenlabs_streaming_enabled = True
        s.elevenlabs_base_url = ""
        s.elevenlabs_model = "eleven_v3"
        s.navy_tts_enabled = False

        with pytest.raises(tts_mod.TTSQuotaExhausted):
            await tts_mod.synthesize_speech("привет", "voice-1", use_cache=False)


@pytest.mark.asyncio
async def test_streaming_on_status_500_falls_back_or_raises(monkeypatch):
    """Non-200 non-quota: when navy is disabled, raise TTSError."""
    from app.services import tts as tts_mod

    stream = _FakeStream(500, b"boom")
    client = _make_fake_client(stream_response=stream)
    monkeypatch.setattr(tts_mod, "_get_shared_client", lambda: client)

    with patch.object(tts_mod, "settings") as s:
        s.elevenlabs_api_key = "xx"
        s.elevenlabs_streaming_enabled = True
        s.elevenlabs_base_url = ""
        s.elevenlabs_model = "eleven_v3"
        s.navy_tts_enabled = False

        with pytest.raises(tts_mod.TTSError):
            await tts_mod.synthesize_speech("привет", "voice-1", use_cache=False)


def test_flag_default_off():
    from app.config import settings
    assert settings.elevenlabs_streaming_enabled is False, (
        "elevenlabs_streaming_enabled must default OFF until the pilot validates"
    )
