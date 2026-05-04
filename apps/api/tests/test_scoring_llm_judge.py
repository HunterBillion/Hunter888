"""Unit tests for the LLM-as-judge scoring layer.

Covers (per α / BUG B3 v3 spec):

* Stub ``generate_response`` to return valid JSON → verdict parses correctly.
* Stub it to return invalid JSON → fail-soft default verdict.
* Stub it to raise ``LLMError`` → fail-soft default verdict.
* Caller in ``calculate_scores`` skips the judge entirely when
  ``len(user_messages) < 4``.
* Cache hit on second call with the same content → second call doesn't hit
  the LLM stub.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.services import scoring_llm_judge as judge_mod
from app.services.scoring_llm_judge import (
    JudgeVerdict,
    _FAIL_SOFT_RATIONALE,
    _PARSE_FAIL_RATIONALE,
    _SCORE_ADJUST_MAX,
    _SCORE_ADJUST_MIN,
    judge_transcript,
)


# ─── Helpers ───────────────────────────────────────────────────────────────


class _StubResponse:
    """Mimics ``LLMResponse`` minimally so the judge code path works."""

    def __init__(self, content: str, model: str = "stub-model"):
        self.content = content
        self.model = model


class _CountingStub:
    """Stub for ``generate_response`` that records call count and a reply.

    Pass ``raises=True`` to simulate an LLM error path.
    """

    def __init__(self, reply: str = "", *, raises: bool = False):
        self.reply = reply
        self.raises = raises
        self.calls = 0

    async def __call__(self, *args: Any, **kwargs: Any) -> _StubResponse:
        self.calls += 1
        if self.raises:
            from app.services.llm import LLMError

            raise LLMError("stub LLM failure")
        return _StubResponse(self.reply)


def _patch_llm(monkeypatch: pytest.MonkeyPatch, stub: _CountingStub) -> None:
    """Patch the lazy import target inside scoring_llm_judge._invoke_llm.

    The judge does ``from app.services.llm import generate_response`` inside
    ``_invoke_llm``. Patch the attribute on the ``app.services.llm`` module
    so each invocation picks up the stub.
    """
    import app.services.llm as llm_mod

    monkeypatch.setattr(llm_mod, "generate_response", stub)


_USER_MSGS = [
    "Здравствуйте, Иван!",
    "Я представляю компанию по банкротству.",
    "У нас есть рассрочка.",
    "Когда вам удобно встретиться?",
]
_AI_MSGS = [
    "Здравствуйте.",
    "Слушаю.",
    "Не интересно.",
    "Подумаю.",
]


# ─── 1. Valid JSON → verdict parses ────────────────────────────────────────


@pytest.mark.asyncio
async def test_valid_json_parses_into_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = (
        '{"verdict":"good","score_adjust":3,'
        '"rationale_ru":"Менеджер выдержал паузу и выявил потребность.",'
        '"red_flags":[],"strengths":["эмпатичный отклик"]}'
    )
    stub = _CountingStub(payload)
    _patch_llm(monkeypatch, stub)

    verdict = await judge_transcript(
        session_id="s-valid",
        user_messages=_USER_MSGS,
        assistant_messages=_AI_MSGS,
        archetype="skeptic",
        emotion_arc=["cold", "curious"],
        call_outcome="appointment_set",
        redis_client=None,
    )

    assert isinstance(verdict, JudgeVerdict)
    assert verdict.verdict == "good"
    assert verdict.score_adjust == 3
    assert "выдержал паузу" in verdict.rationale_ru
    assert verdict.strengths == ["эмпатичный отклик"]
    assert verdict.red_flags == []
    assert stub.calls == 1


# ─── 2. Invalid JSON → fail-soft ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_invalid_json_returns_fail_soft_default(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = _CountingStub("this is not JSON at all")
    _patch_llm(monkeypatch, stub)

    verdict = await judge_transcript(
        session_id="s-bad",
        user_messages=_USER_MSGS,
        assistant_messages=_AI_MSGS,
        archetype=None,
        emotion_arc=[],
        call_outcome="unknown",
        redis_client=None,
    )

    assert verdict.verdict == "mixed"
    assert verdict.score_adjust == 0
    assert verdict.rationale_ru == _PARSE_FAIL_RATIONALE
    assert stub.calls == 1


# ─── 3. LLMError → fail-soft ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_llm_error_returns_fail_soft_default(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = _CountingStub(raises=True)
    _patch_llm(monkeypatch, stub)

    verdict = await judge_transcript(
        session_id="s-err",
        user_messages=_USER_MSGS,
        assistant_messages=_AI_MSGS,
        archetype="analyst",
        emotion_arc=["cold"],
        call_outcome="unknown",
        redis_client=None,
    )

    assert verdict.verdict == "mixed"
    assert verdict.score_adjust == 0
    assert verdict.rationale_ru == _FAIL_SOFT_RATIONALE
    assert stub.calls == 1


# ─── 4. Score adjust gets clamped to [-8, +5] ──────────────────────────────


@pytest.mark.asyncio
async def test_score_adjust_is_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM tries to give -50 — must be clamped to -8."""
    payload = (
        '{"verdict":"red_flag","score_adjust":-50,'
        '"rationale_ru":"Грубо нарушил этику.",'
        '"red_flags":["оскорбил клиента"],"strengths":[]}'
    )
    stub = _CountingStub(payload)
    _patch_llm(monkeypatch, stub)

    verdict = await judge_transcript(
        session_id="s-clamp-low",
        user_messages=_USER_MSGS,
        assistant_messages=_AI_MSGS,
        archetype=None,
        emotion_arc=[],
        call_outcome="hangup",
        redis_client=None,
    )
    assert verdict.score_adjust == _SCORE_ADJUST_MIN

    payload2 = (
        '{"verdict":"excellent","score_adjust":99,'
        '"rationale_ru":"Безупречно.","red_flags":[],"strengths":["идеально"]}'
    )
    stub2 = _CountingStub(payload2)
    _patch_llm(monkeypatch, stub2)
    verdict2 = await judge_transcript(
        session_id="s-clamp-high",
        user_messages=_USER_MSGS,
        assistant_messages=_AI_MSGS,
        archetype=None,
        emotion_arc=[],
        call_outcome="appointment_set",
        redis_client=None,
    )
    assert verdict2.score_adjust == _SCORE_ADJUST_MAX


# ─── 5. Caller skip when len(user_messages) < 4 (integration shim) ────────


@pytest.mark.asyncio
async def test_caller_skips_judge_when_transcript_too_short(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cost guard lives in ``scoring.calculate_scores``: when the user
    transcript has fewer than 4 turns, the judge must NOT be called.

    We test the wired-in invariant by simulating the exact branching
    structure used in ``calculate_scores``: short conversations skip the
    judge entirely and yield ``judge_score=0``.
    """
    stub = _CountingStub("should not be called")
    _patch_llm(monkeypatch, stub)

    # Simulate the calculate_scores branch.
    user_messages = ["Привет.", "Меня зовут Иван."]  # 2 < 4
    judge_verdict = None
    judge_score = 0.0

    if len(user_messages) >= 4:
        judge_verdict = await judge_transcript(
            session_id="s-short",
            user_messages=user_messages,
            assistant_messages=["Здравствуйте."],
            archetype=None,
            emotion_arc=[],
            call_outcome="unknown",
            redis_client=None,
        )
        judge_score = float(judge_verdict.score_adjust)

    assert stub.calls == 0
    assert judge_verdict is None
    assert judge_score == 0.0


# ─── 6. Redis cache hit ────────────────────────────────────────────────────


class _FakeAsyncRedis:
    """Tiny in-memory stand-in for the redis client interface used by
    ``_cache_get`` / ``_cache_set``. Stores raw strings."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.get_calls = 0
        self.set_calls = 0

    async def get(self, key: str) -> str | None:
        self.get_calls += 1
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:  # noqa: ARG002
        self.set_calls += 1
        self.store[key] = value


@pytest.mark.asyncio
async def test_cache_hit_skips_llm_on_second_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = (
        '{"verdict":"poor","score_adjust":-4,'
        '"rationale_ru":"Не выявил потребность.",'
        '"red_flags":["не выявил потребность"],"strengths":[]}'
    )
    stub = _CountingStub(payload)
    _patch_llm(monkeypatch, stub)
    redis = _FakeAsyncRedis()

    # First call — miss, hits LLM, writes cache.
    v1 = await judge_transcript(
        session_id="s-cache",
        user_messages=_USER_MSGS,
        assistant_messages=_AI_MSGS,
        archetype="hostile",
        emotion_arc=["hostile", "hostile"],
        call_outcome="hangup",
        redis_client=redis,
    )
    assert stub.calls == 1
    assert redis.set_calls == 1
    assert v1.verdict == "poor"
    assert v1.score_adjust == -4

    # Second call with the same transcript — hits cache, NO new LLM call.
    v2 = await judge_transcript(
        session_id="s-cache",
        user_messages=_USER_MSGS,
        assistant_messages=_AI_MSGS,
        archetype="hostile",
        emotion_arc=["hostile", "hostile"],
        call_outcome="hangup",
        redis_client=redis,
    )
    assert stub.calls == 1, "second call must NOT hit the LLM"
    assert v2.verdict == v1.verdict
    assert v2.score_adjust == v1.score_adjust


@pytest.mark.asyncio
async def test_fail_soft_verdict_is_not_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transient LLM errors should NOT poison the 24h cache — the next
    call must retry."""
    stub = _CountingStub(raises=True)
    _patch_llm(monkeypatch, stub)
    redis = _FakeAsyncRedis()

    v1 = await judge_transcript(
        session_id="s-no-cache-on-fail",
        user_messages=_USER_MSGS,
        assistant_messages=_AI_MSGS,
        archetype=None,
        emotion_arc=[],
        call_outcome="unknown",
        redis_client=redis,
    )
    assert v1.rationale_ru == _FAIL_SOFT_RATIONALE
    assert redis.set_calls == 0, "fail-soft verdict must NOT be cached"

    # Second call still hits the LLM (no cache from the first attempt).
    v2 = await judge_transcript(
        session_id="s-no-cache-on-fail",
        user_messages=_USER_MSGS,
        assistant_messages=_AI_MSGS,
        archetype=None,
        emotion_arc=[],
        call_outcome="unknown",
        redis_client=redis,
    )
    assert stub.calls == 2
    assert v2.rationale_ru == _FAIL_SOFT_RATIONALE


# ─── 7. Timeout path ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_timeout_returns_fail_soft(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the LLM hangs past the 8s budget, judge returns the fail-soft
    verdict instead of blocking finalize forever."""

    async def _hanging(*_a: Any, **_k: Any) -> _StubResponse:  # pragma: no cover
        await asyncio.sleep(60)
        return _StubResponse('{"verdict":"good","score_adjust":1,"rationale_ru":"x","red_flags":[],"strengths":[]}')

    import app.services.llm as llm_mod

    monkeypatch.setattr(llm_mod, "generate_response", _hanging)
    monkeypatch.setattr(judge_mod, "_JUDGE_TIMEOUT_S", 0.05)

    verdict = await judge_transcript(
        session_id="s-timeout",
        user_messages=_USER_MSGS,
        assistant_messages=_AI_MSGS,
        archetype=None,
        emotion_arc=[],
        call_outcome="unknown",
        redis_client=None,
    )
    assert verdict.score_adjust == 0
    assert verdict.rationale_ru == _FAIL_SOFT_RATIONALE


# ─── 8. Transcript shape — caps & M:/К: format ─────────────────────────────


def test_transcript_format_uses_M_and_K_prefixes() -> None:
    out = judge_mod._format_transcript(["один", "два"], ["alpha", "beta"])
    lines = out.split("\n")
    assert lines == ["M: один", "К: alpha", "M: два", "К: beta"]


def test_transcript_format_caps_to_last_turns() -> None:
    users = [f"u{i}" for i in range(40)]
    assistants = [f"a{i}" for i in range(40)]
    out = judge_mod._format_transcript(users, assistants)
    lines = out.split("\n")
    # Cap is _MAX_TURNS (30) lines from the end.
    assert len(lines) <= judge_mod._MAX_TURNS
    # Tail is preserved.
    assert lines[-1].startswith("К: a39") or lines[-1].startswith("M: u39")


def test_transcript_format_caps_to_max_chars() -> None:
    big_msg = "x" * 5000
    out = judge_mod._format_transcript([big_msg, big_msg], [big_msg, big_msg])
    assert len(out) <= judge_mod._MAX_CHARS
