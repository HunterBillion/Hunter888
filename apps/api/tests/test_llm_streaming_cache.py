"""Smoke tests for the Plan-A LLM perf improvements.

Three things we want to lock down:
  1. ``_split_system_prompt_for_cache`` correctly partitions into
     stable_prefix + dynamic_suffix at the canonical "\\n\\n---\\n\\n"
     boundary used by ``_build_system_prompt``.
  2. ``_build_oai_messages_with_cache`` emits TWO system messages when
     the flag is on, ONE when off — preserving the prior contract.
  3. ``_is_private_local_url`` correctly distinguishes private Ollama
     hosts from public OpenAI-compat proxies (navy.api).

We don't unit-test the SSE streaming itself here — that's an integration
concern with the real network. We do verify the FUNCTION EXISTS and is
importable so a refactor regression is caught.
"""
from __future__ import annotations

import importlib

import pytest

from app.services import llm as llm_mod


# ── _split_system_prompt_for_cache ──────────────────────────────────────────


def test_split_returns_single_when_no_separator() -> None:
    assert llm_mod._split_system_prompt_for_cache("flat prompt") == ("flat prompt", None)


def test_split_returns_empty_for_empty() -> None:
    assert llm_mod._split_system_prompt_for_cache("") == ("", None)


def test_split_two_parts() -> None:
    raw = "CHARACTER\n\n---\n\nDYNAMIC"
    stable, dynamic = llm_mod._split_system_prompt_for_cache(raw)
    assert stable == "CHARACTER"
    assert dynamic == "DYNAMIC"


def test_split_three_parts_keeps_first_two_stable() -> None:
    raw = "CHAR\n\n---\n\nGUARDS\n\n---\n\nEMOTION"
    stable, dynamic = llm_mod._split_system_prompt_for_cache(raw)
    assert stable == "CHAR\n\n---\n\nGUARDS"
    assert dynamic == "EMOTION"


def test_split_five_parts_dynamic_concatenates_remainder() -> None:
    raw = "A\n\n---\n\nB\n\n---\n\nC\n\n---\n\nD\n\n---\n\nE"
    stable, dynamic = llm_mod._split_system_prompt_for_cache(raw)
    assert stable == "A\n\n---\n\nB"
    assert dynamic == "C\n\n---\n\nD\n\n---\n\nE"


# ── _build_oai_messages_with_cache (flag off vs on) ─────────────────────────


def test_messages_flag_off_single_system(monkeypatch) -> None:
    monkeypatch.setattr(llm_mod.settings, "local_llm_prompt_cache_enabled", False)
    out = llm_mod._build_oai_messages_with_cache(
        "CHAR\n\n---\n\nDYNAMIC",
        [{"role": "user", "content": "hi"}],
    )
    assert out[0]["role"] == "system"
    assert out[0]["content"] == "CHAR\n\n---\n\nDYNAMIC"
    assert out[1]["role"] == "user"
    assert len(out) == 2


def test_messages_flag_on_two_system(monkeypatch) -> None:
    monkeypatch.setattr(llm_mod.settings, "local_llm_prompt_cache_enabled", True)
    out = llm_mod._build_oai_messages_with_cache(
        "CHAR\n\n---\n\nDYNAMIC",
        [{"role": "user", "content": "hi"}],
    )
    assert out[0]["role"] == "system"
    assert out[0]["content"] == "CHAR"
    assert out[1]["role"] == "system"
    assert out[1]["content"] == "DYNAMIC"
    assert out[2]["role"] == "user"


def test_messages_flag_on_no_separator_single(monkeypatch) -> None:
    """Without the canonical separator, we still produce a valid message
    list (one system + history) — no cache benefit, but no regression."""
    monkeypatch.setattr(llm_mod.settings, "local_llm_prompt_cache_enabled", True)
    out = llm_mod._build_oai_messages_with_cache(
        "FLAT PROMPT",
        [{"role": "user", "content": "hi"}],
    )
    sys_msgs = [m for m in out if m["role"] == "system"]
    assert len(sys_msgs) == 1
    assert sys_msgs[0]["content"] == "FLAT PROMPT"


# ── _is_private_local_url ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url, expected",
    [
        ("http://localhost:11434/v1", True),
        ("http://127.0.0.1:11434/v1", True),
        ("http://192.168.1.50:11434/v1", True),
        ("http://10.0.0.5:11434/v1", True),
        ("http://172.20.0.5:11434/v1", True),
        ("https://api.navy/v1", False),
        ("https://api.openai.com/v1", False),
        ("https://navy.somewhere.com/v1", False),
        ("", False),
    ],
)
def test_is_private_local_url(monkeypatch, url, expected) -> None:
    monkeypatch.setattr(llm_mod.settings, "local_llm_url", url)
    assert llm_mod._is_private_local_url() is expected


# ── Function existence ──────────────────────────────────────────────────────


def test_stream_openai_compat_exists() -> None:
    assert hasattr(llm_mod, "_stream_openai_compat")
    assert callable(llm_mod._stream_openai_compat)


def test_build_keepalive_http_client_constructible() -> None:
    """Constructible with the expected http2 + keepalive limits.
    `httpx[http2]` is mandatory in pyproject so h2 is always present.
    """
    client = llm_mod._build_keepalive_http_client()
    assert client is not None
    # cleanup
    import asyncio
    asyncio.get_event_loop().run_until_complete(client.aclose())


# ── Streaming smoke (stubbed — critic-fix #10) ───────────────────────────────


class _StubChoice:
    def __init__(self, content: str | None) -> None:
        self.delta = type("D", (), {"content": content})()


class _StubChunk:
    def __init__(self, content: str | None) -> None:
        self.choices = [_StubChoice(content)]


class _StubAsyncIterator:
    def __init__(self, chunks: list[_StubChunk]) -> None:
        self._chunks = chunks
        self._i = 0

    def __aiter__(self) -> "_StubAsyncIterator":
        return self

    async def __anext__(self) -> _StubChunk:
        if self._i >= len(self._chunks):
            raise StopAsyncIteration
        c = self._chunks[self._i]
        self._i += 1
        return c


class _StubChatCompletions:
    def __init__(self, chunks: list[_StubChunk]) -> None:
        self._chunks = chunks
        self.calls: list[dict] = []

    async def create(self, **kwargs):  # noqa: ANN001
        self.calls.append(kwargs)
        return _StubAsyncIterator(self._chunks)


class _StubChat:
    def __init__(self, chunks: list[_StubChunk]) -> None:
        self.completions = _StubChatCompletions(chunks)


class _StubClient:
    def __init__(self, chunks: list[_StubChunk]) -> None:
        self.chat = _StubChat(chunks)


@pytest.mark.asyncio
async def test_stream_openai_compat_yields_tokens(monkeypatch) -> None:
    """End-to-end: monkeypatch _get_local_client to return a stub whose
    chat.completions.create returns an async iterator of fake chunks.
    Verify _stream_openai_compat yields the concatenated tokens.

    A regression that breaks the `async for chunk in stream` body or the
    `delta.content` access path will fail this test.
    """
    chunks = [
        _StubChunk("Здра"),
        _StubChunk("вствуй"),
        _StubChunk(", "),
        _StubChunk(None),         # null delta — must be skipped, not crash
        _StubChunk("слушаю"),
        _StubChunk(""),           # empty delta — must be skipped silently
        _StubChunk("."),
    ]
    stub = _StubClient(chunks)
    monkeypatch.setattr(llm_mod, "_get_local_client", lambda: stub)
    monkeypatch.setattr(llm_mod.settings, "local_llm_url", "https://api.navy/v1")
    monkeypatch.setattr(llm_mod.settings, "local_llm_enabled", True)
    monkeypatch.setattr(llm_mod.settings, "local_llm_model", "gpt-5.4")

    tokens = []
    async for tok in llm_mod._stream_openai_compat(
        system_prompt="SYS",
        messages=[{"role": "user", "content": "привет"}],
        timeout=10.0,
    ):
        tokens.append(tok)

    assert "".join(tokens) == "Здравствуй, слушаю."
    # Verify the stub got the streaming kwarg.
    assert stub.chat.completions.calls[-1]["stream"] is True
    assert stub.chat.completions.calls[-1]["model"] == "gpt-5.4"
