"""Regression for BUG#11 — structured wiki/RAG JSON truncated at 800 tokens.

Symptom (prod, 2026-05-29): wiki-ingest and daily/weekly synthesis logged

    Failed to parse LLM response as JSON: {\n "session_summary": "...
    Wiki ingest failed ... attempt1:parse_failed (len=3094) | attempt2:parse_failed

The root cause is *not* the output filter (BUG#1, already fixed). It is the
wire-level token cap: ``generate_response(task_type="structured")`` resolves
``_forwarded_max_tokens`` to ``None`` unless the caller passes ``max_tokens``
explicitly. With ``None`` the provider stack falls back to its hardcoded
800-token literal, which truncates long session-summary JSON mid-object so it
never parses — even after the stricter retry.

The computed ``_default_max_tokens`` (600 for structured) is logging-only and
never reaches the wire, so the *only* fix is an explicit ``max_tokens`` at the
call site. These tests pin that contract: the wiki structured-JSON callers must
forward a cap large enough to hold a multi-page summary (>= 2048 tokens).

Run on pre-fix code (no ``max_tokens`` kwarg) both tests fail; post-fix both pass.
"""
from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, patch

import pytest

# A cap below this would re-truncate the ~3 KB summaries seen in prod.
MIN_SAFE_TOKENS = 2048


def _fake_resp() -> object:
    """Minimal stand-in for an LLMResponse with parseable JSON."""
    class _R:
        content = '{"session_summary": "ok", "key_points": [], "objections": []}'
        input_tokens = 10
        output_tokens = 20

    return _R()


@pytest.mark.asyncio
async def test_wiki_ingest_forwards_large_max_tokens():
    """``_llm_structured_json`` must forward max_tokens >= MIN_SAFE_TOKENS."""
    from app.services import wiki_ingest_service

    captured: dict = {}

    async def _spy(*args, **kwargs):
        captured.update(kwargs)
        return _fake_resp()

    # generate_response is imported lazily *inside* the helper
    # (``from app.services.llm import generate_response``), so the live symbol
    # to patch lives on the llm module, not on wiki_ingest_service.
    with patch("app.services.llm.generate_response", new=AsyncMock(side_effect=_spy)):
        parsed, _tokens, err = await wiki_ingest_service._llm_structured_json(
            system_prompt="sys",
            user_prompt="usr",
            user_id="u1",
        )

    assert err is None and parsed is not None, f"helper failed: {err}"
    assert "max_tokens" in captured, (
        "generate_response called without max_tokens — wire will apply the "
        "hardcoded 800-token cap and truncate long JSON (BUG#11)."
    )
    assert captured["max_tokens"] >= MIN_SAFE_TOKENS, (
        f"max_tokens={captured['max_tokens']} too low; long session summaries "
        f"(~3 KB / >800 tokens) will truncate."
    )
    assert captured.get("task_type") == "structured"


def test_synthesis_call_sites_pass_max_tokens():
    """Static guard: synthesis generate_response calls carry an explicit cap.

    AST-level so it fails even if the LLM path is hard to exercise end-to-end:
    every ``generate_response(...)`` in wiki_synthesis_service must include a
    ``max_tokens=`` keyword, otherwise the 800-token wire default truncates the
    analysis JSON exactly like wiki-ingest did.
    """
    import ast

    from app.services import wiki_synthesis_service

    src = inspect.getsource(wiki_synthesis_service)
    tree = ast.parse(src)

    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "generate_response"
    ]
    assert calls, "no generate_response calls found — test is stale"

    offenders = [
        c.lineno
        for c in calls
        if "max_tokens" not in {kw.arg for kw in c.keywords}
    ]
    assert not offenders, (
        f"generate_response at line(s) {offenders} in wiki_synthesis_service "
        f"lack an explicit max_tokens — risks 800-token truncation (BUG#11)."
    )
