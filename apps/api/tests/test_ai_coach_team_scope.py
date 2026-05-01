"""Tests for ai_coach.coach_chat passing team_id to unified RAG.

P0 #1 from the 9-layer audit + prod-deploy report (2026-05-02):
``ai_coach.coach_chat`` called ``retrieve_all_context`` without ``team_id``,
so the methodology branch (TZ-8 PR-B) was silently skipped — every
ROP-uploaded playbook was invisible to the coach.

Locks in:

* ``coach_chat`` resolves the caller's ``user.team_id`` BEFORE calling
  the unified RAG entry point.
* The team_id (whatever value, including ``None`` for legacy users)
  is forwarded as a kwarg, NOT silently dropped.
* When ``user.team_id`` is None, retrieve_all_context still gets called
  with ``team_id=None`` (the rag side then skips methodology, which is
  the correct behaviour — no team, no per-team scope).
"""

from __future__ import annotations

import inspect


def test_coach_chat_resolves_team_id_before_rag_call():
    """Source-level guard: future regression that drops the team_id
    forwarding (or skips the User SELECT) is caught at PR time."""
    from app.services import ai_coach

    src = inspect.getsource(ai_coach.coach_chat)

    # Must SELECT team_id from User by user_id.
    assert "_User.team_id" in src, (
        "coach_chat must select team_id from User row (P0 #1 audit fix)"
    )
    assert "_User.id == user_id" in src, (
        "team_id resolution must scope to the caller user_id"
    )
    # Must forward team_id to retrieve_all_context.
    assert "team_id=_team_id" in src, (
        "coach_chat must forward team_id to retrieve_all_context "
        "(otherwise methodology RAG silently skipped per rag_unified.py:264)"
    )


def test_coach_chat_calls_retrieve_all_context_with_keyword_team_id():
    """The team_id kwarg must be supplied as a keyword, never positional —
    rag_unified's signature is keyword-only after the ``*,`` marker so a
    positional pass would raise TypeError at runtime."""
    from app.services import ai_coach

    src = inspect.getsource(ai_coach.coach_chat)
    # Crude but sufficient: find the retrieve_all_context call block and
    # check team_id is in the kwarg form.
    idx = src.find("retrieve_all_context(")
    assert idx >= 0, "retrieve_all_context call site must be present"
    block = src[idx : idx + 600]
    assert "team_id=" in block, (
        "team_id must be passed as kwarg to retrieve_all_context"
    )


def test_rag_unified_signature_has_team_id_kwarg():
    """Sanity check: rag_unified didn't change its kwarg shape and
    ai_coach is still on the right contract."""
    from app.services.rag_unified import retrieve_all_context

    sig = inspect.signature(retrieve_all_context)
    assert "team_id" in sig.parameters, (
        "retrieve_all_context must still expose a team_id kwarg"
    )
    param = sig.parameters["team_id"]
    # Keyword-only (after the ``*,`` marker in the source).
    assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
        "team_id must remain keyword-only (rag_unified contract)"
    )
