"""IL-3 (2026-05-01) — STT keyword priming tests.

Pin the contract:
  * flag default OFF
  * flag OFF → no ``prompt`` field in the multipart payload
  * flag ON  → ``prompt`` populated with default RU bankruptcy lexicon
  * flag ON  + custom override text → that text is used verbatim
  * default lexicon mentions the highest-value domain terms (ФССП, 127-ФЗ,
    Сбер) so the test catches accidental erasure of the priming corpus
"""

from __future__ import annotations

from unittest.mock import patch, AsyncMock, MagicMock

import pytest


def test_flag_default_off():
    from app.config import settings
    assert settings.stt_keyword_prompt_enabled is False, (
        "stt_keyword_prompt_enabled must default OFF — opt in per env"
    )
    assert settings.stt_keyword_prompt_text == "", (
        "stt_keyword_prompt_text default override must be empty"
    )


def test_default_lexicon_mentions_high_value_domain_terms():
    """The built-in RU prompt must include the most likely-mis-recognised
    bankruptcy / call domain terms. If a future cleanup deletes them by
    accident, this guard fires."""
    from app.services.stt import _DEFAULT_STT_KEYWORD_PROMPT_RU

    must_have = [
        "127-ФЗ",         # the law
        "ФССП",           # bailiff service
        "арбитражный",    # procedure
        "Сбер",           # creditor
        "Тинькофф",       # creditor
        "Госуслуги",      # gov ID system
        "процедуры",      # bankruptcy proper noun
    ]
    for term in must_have:
        assert term in _DEFAULT_STT_KEYWORD_PROMPT_RU, (
            f"default keyword prompt missing high-value term {term!r}"
        )


@pytest.mark.asyncio
async def test_prompt_field_omitted_when_flag_off(monkeypatch):
    """flag OFF: the multipart ``data`` dict sent to Whisper has no ``prompt``."""
    from app.services import stt as stt_mod

    captured = {}
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json = MagicMock(return_value={
        "text": "тест",
        "language": "ru",
        "duration": 1.0,
        "segments": [{
            "text": "тест", "avg_logprob": -0.1, "no_speech_prob": 0.05,
        }],
    })

    class _FakeClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None
        async def post(self, url, files=None, data=None, headers=None):
            captured["data"] = data
            return fake_response

    monkeypatch.setattr(stt_mod.httpx, "AsyncClient", _FakeClient)

    with patch.object(stt_mod, "settings") as s:
        s.whisper_url = "http://w"
        s.whisper_language = "ru"
        s.whisper_model = "small"
        s.whisper_timeout_seconds = 10
        s.whisper_api_key = ""
        s.stt_keyword_prompt_enabled = False
        s.stt_keyword_prompt_text = ""
        # Minimum viable audio: webm magic + non-trivial body
        audio = b"\x1a\x45\xdf\xa3" + b"\x00" * 4096
        await stt_mod._transcribe_whisper(audio, language="ru")

    assert "prompt" not in captured["data"], (
        f"flag OFF must not include prompt field; got data={captured['data']!r}"
    )


@pytest.mark.asyncio
async def test_default_prompt_used_when_flag_on(monkeypatch):
    from app.services import stt as stt_mod

    captured = {}
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json = MagicMock(return_value={
        "text": "тест",
        "language": "ru",
        "duration": 1.0,
        "segments": [{
            "text": "тест", "avg_logprob": -0.1, "no_speech_prob": 0.05,
        }],
    })

    class _FakeClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None
        async def post(self, url, files=None, data=None, headers=None):
            captured["data"] = data
            return fake_response

    monkeypatch.setattr(stt_mod.httpx, "AsyncClient", _FakeClient)

    with patch.object(stt_mod, "settings") as s:
        s.whisper_url = "http://w"
        s.whisper_language = "ru"
        s.whisper_model = "small"
        s.whisper_timeout_seconds = 10
        s.whisper_api_key = ""
        s.stt_keyword_prompt_enabled = True
        s.stt_keyword_prompt_text = ""
        audio = b"\x1a\x45\xdf\xa3" + b"\x00" * 4096
        await stt_mod._transcribe_whisper(audio, language="ru")

    assert "prompt" in captured["data"]
    p = captured["data"]["prompt"]
    assert "127-ФЗ" in p
    assert "ФССП" in p


@pytest.mark.asyncio
async def test_custom_override_used_when_provided(monkeypatch):
    from app.services import stt as stt_mod

    custom = "Своя кастомная подсказка."
    captured = {}
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json = MagicMock(return_value={
        "text": "тест",
        "language": "ru",
        "duration": 1.0,
        "segments": [{
            "text": "тест", "avg_logprob": -0.1, "no_speech_prob": 0.05,
        }],
    })

    class _FakeClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None
        async def post(self, url, files=None, data=None, headers=None):
            captured["data"] = data
            return fake_response

    monkeypatch.setattr(stt_mod.httpx, "AsyncClient", _FakeClient)

    with patch.object(stt_mod, "settings") as s:
        s.whisper_url = "http://w"
        s.whisper_language = "ru"
        s.whisper_model = "small"
        s.whisper_timeout_seconds = 10
        s.whisper_api_key = ""
        s.stt_keyword_prompt_enabled = True
        s.stt_keyword_prompt_text = custom
        audio = b"\x1a\x45\xdf\xa3" + b"\x00" * 4096
        await stt_mod._transcribe_whisper(audio, language="ru")

    assert captured["data"].get("prompt") == custom
