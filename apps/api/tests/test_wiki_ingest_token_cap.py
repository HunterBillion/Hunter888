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


# ═══════════════════════════════════════════════════════════════════════════
# Residual class: abandoned "Алло, да?" calls — skip before the LLM call.
#
# After the token-cap fix the only remaining wiki parse_failed in prod were
# tiny greeting echoes (len=9..13) from near-empty sessions. ingest_session now
# short-circuits those before creating a wiki or calling the LLM, so they no
# longer produce noisy WARNING logs.
# ═══════════════════════════════════════════════════════════════════════════


class _FakeMsg:
    def __init__(self, content: str):
        self.content = content


class _FakeScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class _FakeResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return _FakeScalars(self._items)


class _FakeSession:
    user_id = "u-abandoned"
    custom_params = {}
    score_total = None
    duration_seconds = 3


def _make_db(messages):
    """AsyncMock db whose .get returns a session and .execute returns messages."""
    from unittest.mock import AsyncMock, MagicMock

    db = MagicMock()
    db.get = AsyncMock(return_value=_FakeSession())
    db.execute = AsyncMock(return_value=_FakeResult(messages))
    return db


@pytest.mark.asyncio
async def test_abandoned_call_skipped_without_llm():
    """A near-empty transcript is skipped before any LLM call."""
    import uuid

    from app.services import wiki_ingest_service

    db = _make_db([_FakeMsg("Алло, да?"), _FakeMsg("Слушаю вас.")])

    # If the guard fails, _get_or_create_wiki / generate_response would run and
    # blow up against the MagicMock db — patch them so a regression is a clean
    # assertion failure, not a noisy traceback.
    with patch.object(
        wiki_ingest_service, "_get_or_create_wiki", new=AsyncMock()
    ) as woc, patch(
        "app.services.llm.generate_response", new=AsyncMock()
    ) as gr:
        result = await wiki_ingest_service.ingest_session(uuid.uuid4(), db)

    assert result == {"status": "skipped", "reason": "insufficient_content"}, result
    woc.assert_not_called()  # no wiki created for an empty session
    gr.assert_not_called()  # no LLM spent on a greeting-only call


@pytest.mark.asyncio
async def test_substantive_session_passes_guard():
    """A real exchange clears the threshold and proceeds past the guard."""
    import uuid

    from app.services import wiki_ingest_service

    long_turn = (
        "Здравствуйте, меня зовут Дмитрий, я звоню по поводу процедуры "
        "банкротства физических лиц, у вас есть пара минут обсудить вашу "
        "ситуацию с задолженностью?"
    )
    db = _make_db([_FakeMsg(long_turn), _FakeMsg("Да, конечно, слушаю.")])

    # Stop execution right after the guard: _get_or_create_wiki raises a marker
    # so we prove the guard let us through without standing up the whole path.
    class _Pass(Exception):
        pass

    with patch.object(
        wiki_ingest_service, "_get_or_create_wiki", new=AsyncMock(side_effect=_Pass)
    ):
        with pytest.raises(_Pass):
            await wiki_ingest_service.ingest_session(uuid.uuid4(), db)
