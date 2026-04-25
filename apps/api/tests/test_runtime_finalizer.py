"""runtime_finalizer Phase 1 — apply_post_finalize_enrichment.

Phase 1 contract: REST path post-finalize must run the same XP +
AI-coach + RAG steps as WS, with SessionHistory.session_id UNIQUE
acting as the idempotency lock so a second arrival (REST after WS,
or vice versa) is a noop, never a double-XP.

These tests pin:
  * happy path — SessionHistory created, XP returned, no double-call
  * idempotency — second invocation returns existing row, skips XP
  * IntegrityError fallback path — caught, no exception bubbles up
  * missing scores → noop (don't crash on degraded session)
  * synthesized defaults work when state is None (REST entrypoint)
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.services.runtime_finalizer import apply_post_finalize_enrichment


def _make_session(*, feedback_text=None, scoring_details=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        feedback_text=feedback_text,
        emotion_timeline={},
        duration_seconds=120,
        score_total=80.0,
        scoring_details=scoring_details or {},
    )


def _make_scores():
    return SimpleNamespace(
        total=80.0,
        script_adherence=15.0,
        objection_handling=15.0,
        communication=15.0,
        anti_patterns=10.0,
        result=15.0,
        legal_accuracy=2.0,
        chain_traversal=5.0,
        trap_handling={"fell_count": 0, "dodged_count": 2},
    )


class _Savepoint:
    def __init__(self, on_exit_raise=None):
        self._on_exit_raise = on_exit_raise

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._on_exit_raise is not None:
            raise self._on_exit_raise


def _make_db(*, integrity_error=False, existing_row=None):
    db = SimpleNamespace()
    db.add = MagicMock()
    db.flush = AsyncMock()

    if integrity_error:
        db.begin_nested = MagicMock(
            return_value=_Savepoint(
                on_exit_raise=IntegrityError("INSERT", {}, Exception("UNIQUE"))
            )
        )
    else:
        db.begin_nested = MagicMock(return_value=_Savepoint())

    # db.execute returns a result whose scalar_one_or_none gives the existing
    # SessionHistory if we're testing the duplicate-write path.
    exec_result = MagicMock()
    exec_result.scalar_one_or_none = MagicMock(return_value=existing_row)
    db.execute = AsyncMock(return_value=exec_result)
    return db


@pytest.mark.asyncio
async def test_happy_path_awards_xp_and_marks_history_created():
    db = _make_db()
    session = _make_session()
    scores = _make_scores()

    fake_svc = MagicMock()
    fake_svc.update_after_session = AsyncMock(
        return_value={"xp_breakdown": {"grand_total": 42, "base": 20, "bonus": 22}}
    )

    with (
        patch(
            "app.services.manager_progress.ManagerProgressService",
            return_value=fake_svc,
        ),
        patch("app.services.scenario_engine.generate_session_report", new_callable=AsyncMock),
        patch("app.services.session_manager.get_message_history", new=AsyncMock(return_value=[])),
        patch("app.services.session_manager.get_message_history_db", new=AsyncMock(return_value=[])),
    ):
        result = await apply_post_finalize_enrichment(
            db, session=session, scores=scores, state={"call_outcome": "success"}
        )

    assert result["session_history_created"] is True
    assert result["xp_earned"] == 42
    fake_svc.update_after_session.assert_awaited_once()


@pytest.mark.asyncio
async def test_integrity_error_short_circuits_returning_existing_xp():
    """Second writer (e.g. REST after WS already finalized) must NOT
    award XP again. The UNIQUE on session_id raises IntegrityError;
    helper catches, re-SELECTs, returns existing row's xp_earned."""
    existing = SimpleNamespace(xp_earned=99)
    db = _make_db(integrity_error=True, existing_row=existing)

    session = _make_session()
    scores = _make_scores()

    fake_svc = MagicMock()
    fake_svc.update_after_session = AsyncMock()

    with patch(
        "app.services.manager_progress.ManagerProgressService",
        return_value=fake_svc,
    ):
        result = await apply_post_finalize_enrichment(
            db, session=session, scores=scores, state=None
        )

    assert result["session_history_created"] is False
    assert result["xp_earned"] == 99
    # Critically: XP service was NEVER called on the duplicate path.
    fake_svc.update_after_session.assert_not_called()


@pytest.mark.asyncio
async def test_missing_scores_returns_noop_result():
    db = _make_db()
    session = _make_session()
    result = await apply_post_finalize_enrichment(
        db, session=session, scores=None, state=None
    )
    assert result == {
        "session_history_created": False,
        "xp_earned": None,
        "coach_report_generated": False,
        "rag_feedback_count": 0,
    }


@pytest.mark.asyncio
async def test_state_none_uses_session_defaults():
    """REST callers pass state=None. The helper must synthesise sensible
    defaults from the session row (call_outcome from scoring_details,
    archetype 'unknown', etc.) without crashing."""
    db = _make_db()
    session = _make_session(scoring_details={"call_outcome": "needs_followup"})
    scores = _make_scores()

    fake_svc = MagicMock()
    fake_svc.update_after_session = AsyncMock(
        return_value={"xp_breakdown": {"grand_total": 10}}
    )

    with (
        patch(
            "app.services.manager_progress.ManagerProgressService",
            return_value=fake_svc,
        ),
        patch("app.services.scenario_engine.generate_session_report", new_callable=AsyncMock),
        patch("app.services.session_manager.get_message_history", new=AsyncMock(return_value=[])),
        patch("app.services.session_manager.get_message_history_db", new=AsyncMock(return_value=[])),
    ):
        result = await apply_post_finalize_enrichment(
            db, session=session, scores=scores, state=None
        )

    assert result["session_history_created"] is True
    # The synthesized SessionHistory.outcome came from scoring_details fallback.
    sh_added = db.add.call_args[0][0]
    assert sh_added.outcome == "needs_followup"


@pytest.mark.asyncio
async def test_skips_coach_report_when_feedback_text_already_set():
    """If the WS path's coach report ran first and populated feedback_text,
    REST must NOT regenerate it (don't waste an LLM call, don't risk
    overwriting richer text)."""
    db = _make_db()
    session = _make_session(feedback_text="WS already wrote this")
    scores = _make_scores()

    fake_svc = MagicMock()
    fake_svc.update_after_session = AsyncMock(
        return_value={"xp_breakdown": {"grand_total": 5}}
    )

    coach_mock = AsyncMock()
    with (
        patch(
            "app.services.manager_progress.ManagerProgressService",
            return_value=fake_svc,
        ),
        patch("app.services.scenario_engine.generate_session_report", coach_mock),
    ):
        result = await apply_post_finalize_enrichment(
            db, session=session, scores=scores, state=None
        )

    assert result["coach_report_generated"] is False
    coach_mock.assert_not_called()
    # feedback_text untouched
    assert session.feedback_text == "WS already wrote this"
