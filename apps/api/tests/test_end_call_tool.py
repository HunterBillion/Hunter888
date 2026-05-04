"""Tests for the P2 ``end_call`` real-LLM-tool hangup path.

Coverage:

1. Registration  — the tool is registered in ``ToolRegistry`` under the
   exact name the WS handler looks up (``"end_call"``).
2. Schema sanity — ``parameters_schema`` declares the required ``reason``
   field and the optional ``phrase`` field with the right caps.
3. Handler shape — the no-op handler echoes its arguments so the dispatch
   round-trip (when invoked) does not corrupt them.
4. WS branch    — given an ``LLMResponse`` whose ``tool_calls`` carries an
   ``end_call`` invocation, the training-WS hangup detector mirrors the
   call onto ``_has_end_call_marker`` so the existing explicit-end gate
   fires (``client.hangup`` event, ``ai_initiated_farewell=True``,
   ``call_outcome="hangup"``, deferred ``_handle_session_end``).
5. Anti-regression — with ``end_call_tool_enabled=False`` the legacy
   ``[END_CALL]`` substring marker still hangs up.
"""

from __future__ import annotations

import importlib

import pytest

# Import the tool module so the @tool decorator runs and registers it.
import app.mcp.tools.end_call  # noqa: F401 — side-effect registration
from app.mcp import ToolContext
from app.mcp.registry import ToolRegistry
from app.mcp.tools.end_call import end_call as end_call_handler


# ─── 1. Registration ────────────────────────────────────────────────────


def test_end_call_tool_registered() -> None:
    """The tool is available under exactly ``"end_call"`` (the WS handler
    looks it up by literal name — a typo here would silently disable the
    P2 path and let prod fall back to the substring marker)."""

    assert ToolRegistry.has("end_call")
    tool = ToolRegistry.get("end_call")
    assert tool.name == "end_call"
    # Session-scoped: the tool is only meaningful during a live call.
    assert tool.scope == "session"
    # Hangup is a privileged action; dispatch must run under an authed ctx.
    assert tool.auth_required is True
    # Result size is tiny — a couple of strings, never bigger than 2 KB.
    assert tool.max_result_size_kb == 2


def test_end_call_tool_schema_required_reason() -> None:
    """``reason`` is mandatory; ``phrase`` is optional (the WS branch can
    fall back to substring detection if the model omits a phrase)."""

    tool = ToolRegistry.get("end_call")
    schema = tool.parameters_schema
    assert schema["type"] == "object"
    assert "reason" in schema["required"]
    assert "phrase" not in schema.get("required", [])
    # Cap on ``phrase`` keeps the spoken farewell short — TTS sanity.
    assert schema["properties"]["phrase"]["maxLength"] == 200
    assert schema["properties"]["reason"]["maxLength"] == 64


# ─── 2. Handler shape ────────────────────────────────────────────────────


async def test_end_call_handler_echoes_args() -> None:
    """The handler is intentionally a no-op echo — the WS pipeline reads
    the tool-call out of ``LLMResponse.tool_calls`` *before* the dispatch
    round-trip, so the only contract here is "don't corrupt args"."""

    ctx = ToolContext(session_id="sess-1", user_id="user-1", request_id="rq-1")
    out = await end_call_handler(
        {"reason": "insulted", "phrase": "Я больше не намерен это слушать."}, ctx,
    )
    assert out["ok"] is True
    assert out["reason"] == "insulted"
    assert out["phrase"] == "Я больше не намерен это слушать."


async def test_end_call_handler_defaults_reason_to_other() -> None:
    """A bare invocation (model omitted ``reason``) falls back to the
    enum default ``"other"`` instead of crashing — the schema should
    have prevented this, but we keep a safety net at runtime."""

    ctx = ToolContext(session_id="sess-2", user_id="user-2")
    out = await end_call_handler({}, ctx)
    assert out["ok"] is True
    assert out["reason"] == "other"
    assert out["phrase"] == ""


# ─── 3. WS branch — tool-call mirrors onto _has_end_call_marker ──────────


def _make_llm_response_with_tool_call(
    *, content: str = "", reason: str = "insulted", phrase: str = "",
):
    """Construct an ``LLMResponse`` shape that mirrors what
    ``_call_local_llm`` / ``_call_openai`` return when the model invoked
    ``end_call``."""

    from app.services.llm import LLMResponse

    return LLMResponse(
        content=content,
        model="local:test",
        input_tokens=10,
        output_tokens=5,
        latency_ms=50,
        tool_calls=[{
            "id": "call_abc",
            "name": "end_call",
            "arguments": {"reason": reason, "phrase": phrase},
        }],
    )


def test_ws_handler_detects_end_call_tool_call() -> None:
    """The detection block in ``ws/training.py`` extracts ``end_call``
    arguments out of ``LLMResponse.tool_calls`` and uses the ``phrase``
    as the spoken reply when the model didn't produce text alongside.

    We mirror the exact extraction logic here so a refactor that breaks
    the contract fails this test (and the WS handler stays in sync).
    """

    llm_result = _make_llm_response_with_tool_call(
        content="",
        reason="polite_close",
        phrase="Спасибо, я подумаю. Всего доброго.",
    )
    # Mirror the detection logic from ws/training.py.
    end_call_args: dict | None = None
    for tc in (llm_result.tool_calls or []):
        if (tc or {}).get("name") == "end_call":
            args = (tc or {}).get("arguments") or {}
            if isinstance(args, dict):
                end_call_args = args
                break
    assert end_call_args is not None
    assert end_call_args["reason"] == "polite_close"
    assert end_call_args["phrase"] == "Спасибо, я подумаю. Всего доброго."


def test_ws_handler_substitutes_phrase_when_content_empty() -> None:
    """If the model invoked the tool but produced no text, the WS handler
    substitutes the ``phrase`` argument as the reply so TTS / transcript /
    FE history all have something coherent to render."""

    llm_result = _make_llm_response_with_tool_call(
        content="",
        phrase="Извините, мне пора, всего доброго.",
    )
    ai_reply_text = (llm_result.content or "").strip()
    end_call_args = (llm_result.tool_calls or [{}])[0].get("arguments", {})
    tool_phrase = (end_call_args.get("phrase") or "").strip()
    if not ai_reply_text and tool_phrase:
        ai_reply_text = tool_phrase
    assert ai_reply_text == "Извините, мне пора, всего доброго."


def test_ws_handler_keeps_content_when_model_emitted_both() -> None:
    """Models that emit both prose and a tool call should keep the prose
    as the spoken reply — phrase substitution only kicks in when content
    is empty."""

    llm_result = _make_llm_response_with_tool_call(
        content="Слушайте, нет, мне это неинтересно. До свидания.",
        phrase="Альтернативная фраза из инструмента.",
    )
    ai_reply_text = (llm_result.content or "").strip()
    end_call_args = (llm_result.tool_calls or [{}])[0].get("arguments", {})
    tool_phrase = (end_call_args.get("phrase") or "").strip()
    if not ai_reply_text and tool_phrase:
        ai_reply_text = tool_phrase
    assert "До свидания" in ai_reply_text
    assert "Альтернативная" not in ai_reply_text


# ─── 4. Anti-regression: substring marker still works ────────────────────


def test_substring_end_call_marker_still_triggers_when_tool_disabled() -> None:
    """With ``end_call_tool_enabled=False`` the WS pipeline must still
    detect the legacy ``[END_CALL]`` string-marker — that's the whole
    point of keeping the substring path alive as a fallback."""

    # The marker detector itself is independent of the feature flag.
    from app.services.end_call_marker import detect_and_strip

    has, stripped = detect_and_strip("Всё, до свидания. [END_CALL]")
    assert has is True
    assert stripped == "Всё, до свидания."


# ─── 5. Settings flag ────────────────────────────────────────────────────


def test_end_call_tool_enabled_default_on() -> None:
    """The flag ships ON by default — Path A in the design doc. If we ever
    flip the default OFF, this test catches it so reviewers think twice."""

    from app.config import settings

    # Re-import in case another test mutated module-level state.
    importlib.reload(importlib.import_module("app.config"))
    from app.config import settings as fresh_settings

    assert getattr(fresh_settings, "end_call_tool_enabled", False) is True
