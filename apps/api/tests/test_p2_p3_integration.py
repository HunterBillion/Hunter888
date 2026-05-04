"""Smoke tests for P2 (end_call tool) + P3 (cross-session memory).

These cover the *interfaces* — the tool spec is registered, the system
prompt picks up `client_history`, the cross-session helper produces a
sensible Russian summary. End-to-end LLM behaviour is validated on prod
after deploy (per CLAUDE.md §4.4 — "deploy verified" requires the
user-facing scenario, not just unit tests).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


# ── P2: end_call tool registration ──────────────────────────────────────────


def test_end_call_tool_registered() -> None:
    """Importing app.mcp.tools triggers @tool decorators; ToolRegistry
    must have an `end_call` entry by name."""
    from app.mcp import ToolRegistry
    import app.mcp.tools  # noqa: F401 — side-effect

    assert ToolRegistry.has("end_call")
    spec = ToolRegistry.get("end_call")
    assert spec.name == "end_call"
    assert "reason" in spec.parameters_schema.get("properties", {})
    assert "phrase" in spec.parameters_schema.get("properties", {})
    # Description must be in Russian (the model is Russian-trained).
    assert any(c >= "А" for c in spec.description)


def test_end_call_tool_handler_echoes() -> None:
    """Handler is intentionally a no-op echo. Returned dict must
    contain `ok=True` plus the args."""
    import asyncio

    from app.mcp import ToolContext
    from app.mcp.tools.end_call import end_call

    ctx = ToolContext(session_id="test-sid", user_id="u1", request_id="r1")
    result = asyncio.get_event_loop().run_until_complete(
        end_call({"reason": "insulted", "phrase": "Всё, до свидания."}, ctx)
    )
    assert result == {"ok": True, "reason": "insulted", "phrase": "Всё, до свидания."}


# ── P3: cross-session summary rendering ─────────────────────────────────────


def test_extract_closing_emotion_list_shape() -> None:
    from app.services.cross_session_memory import extract_closing_emotion

    timeline = [
        {"state": "cold", "ts": 1.0},
        {"state": "guarded", "ts": 2.0},
        {"state": "hostile", "ts": 3.0},
    ]
    assert extract_closing_emotion(timeline) == "hostile"


def test_extract_closing_emotion_dict_shape() -> None:
    from app.services.cross_session_memory import extract_closing_emotion

    timeline = {"events": [{"state": "callback", "ts": 1.0}]}
    assert extract_closing_emotion(timeline) == "callback"


def test_extract_closing_emotion_empty_returns_none() -> None:
    from app.services.cross_session_memory import extract_closing_emotion

    assert extract_closing_emotion(None) is None
    assert extract_closing_emotion([]) is None
    assert extract_closing_emotion({}) is None


def test_render_summary_is_russian_and_under_300_chars() -> None:
    from app.services.cross_session_memory import render_summary

    text = render_summary(
        completed_at=datetime.now(timezone.utc) - timedelta(days=1),
        closing_emotion="hostile",
        score_total=42.0,
        terminal_outcome="client_hangup",
        judge_rationale="Менеджер был груб, не выявил потребность.",
    )
    assert "вчера" in text.lower()
    assert "HOSTILE" in text
    assert "42/100" in text
    assert "бросил трубку" in text
    assert "Судья" in text
    assert len(text) <= 300


def test_render_summary_no_judge_no_score() -> None:
    """All optional fields can be missing; output still readable."""
    from app.services.cross_session_memory import render_summary

    text = render_summary(
        completed_at=None,
        closing_emotion=None,
        score_total=None,
        terminal_outcome=None,
        judge_rationale=None,
    )
    # Should still produce SOMETHING — at minimum a sentence about what
    # ended last time.
    assert len(text) > 0
    assert "разговор оборвался" in text


# ── P2 + P3: system prompt block injection ──────────────────────────────────


def test_build_system_prompt_includes_client_history_block() -> None:
    from app.services.llm import _build_system_prompt

    prompt = _build_system_prompt(
        character_prompt="CHAR",
        guardrails="GUARDS",
        emotion_state="cold",
        client_history="В прошлый звонок клиент завершил на эмоции HOSTILE.",
    )
    assert "ЧТО БЫЛО В ПРОШЛЫЙ РАЗ" in prompt
    assert "HOSTILE" in prompt


def test_build_system_prompt_omits_history_block_when_empty() -> None:
    from app.services.llm import _build_system_prompt

    prompt = _build_system_prompt(
        character_prompt="CHAR",
        guardrails="GUARDS",
        emotion_state="cold",
        client_history=None,
    )
    assert "ЧТО БЫЛО В ПРОШЛЫЙ РАЗ" not in prompt
    # back-compat: empty string also skips the block
    prompt2 = _build_system_prompt(
        character_prompt="CHAR",
        guardrails="GUARDS",
        emotion_state="cold",
        client_history="   ",
    )
    assert "ЧТО БЫЛО В ПРОШЛЫЙ РАЗ" not in prompt2


def test_build_system_prompt_rule_9_mentions_end_call_tool() -> None:
    """System prompt rule 9 must instruct the model to use the tool —
    if the wording regresses, the model stops calling end_call."""
    from app.services.llm import _build_system_prompt

    prompt = _build_system_prompt(
        character_prompt="", guardrails="", emotion_state="cold",
    )
    assert "end_call" in prompt
    # The fallback marker must still be documented for the model.
    assert "[END_CALL]" in prompt
