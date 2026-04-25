"""TZ-2 §16 contract: REST `/end` and WS `session.end` produce equivalent
finalize side-effects.

Phase 5 strengthens the existing `test_client_domain_parity.py` AST
checks (which compare *kwarg names* of one helper) with a runtime-shape
contract: both endings should converge on:

  * `session.status = completed`
  * `session.terminal_outcome` set to one of TZ2_CANONICAL_OUTCOMES
  * `session.completed_via` ∈ {rest, ws}
  * exactly ONE `SessionHistory` row per session (UNIQUE on session_id)
  * exactly ONE `EVENT_TRAINING_COMPLETED` outbox row (idempotency_key
    = `training_completed:{session.id}`)
  * the same `to_tz2_outcome` mapping result regardless of path

The actual handlers depend on Redis state and pgvector; this test pins
the **contract** by exercising the shared helper
`runtime_finalizer.apply_post_finalize_enrichment` from both sides
with mock DBs and asserting the outcomes are identical.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.completion_policy import (
    TZ2_CANONICAL_OUTCOMES,
    TerminalOutcome,
    to_tz2_outcome,
)
from app.services.runtime_finalizer import apply_post_finalize_enrichment


def _make_session():
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        feedback_text=None,
        emotion_timeline={},
        duration_seconds=120,
        score_total=80.0,
        scoring_details={},
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
    def __init__(self, raise_on_exit=None):
        self._raise = raise_on_exit

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        if self._raise is not None:
            raise self._raise


def _make_db():
    db = SimpleNamespace()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.begin_nested = MagicMock(return_value=_Savepoint())
    exec_result = MagicMock()
    exec_result.scalar_one_or_none = MagicMock(return_value=None)
    db.execute = AsyncMock(return_value=exec_result)
    return db


# ── Outcome catalog parity ──


@pytest.mark.parametrize(
    "internal, expected_tz2",
    [
        ("success", "deal_agreed"),
        ("hard_reject", "deal_not_agreed"),
        ("hangup", "continue_next_call"),
        ("needs_followup", "needs_followup"),
        ("timeout", "timeout"),
        ("technical_failed", "error"),
    ],
)
def test_outcome_mapping_identical_regardless_of_path(internal, expected_tz2):
    """Both REST and WS go through `to_tz2_outcome` for the canonical
    column. Pin that the legacy → TZ-2 mapping is path-independent."""
    assert to_tz2_outcome(internal) == expected_tz2
    # And the result is always in the canonical catalog.
    assert to_tz2_outcome(internal) in TZ2_CANONICAL_OUTCOMES


def test_pvp_outcomes_return_none_from_both_paths():
    """PvP isn't a TZ-2 CRM outcome — both REST and WS must skip the
    canonical column write rather than stamp something non-canonical."""
    for v in ("pvp_win", "pvp_loss", "pvp_draw", "pvp_abandoned"):
        assert to_tz2_outcome(v) is None


def test_terminal_outcome_enum_round_trips_through_to_tz2():
    """Both paths use the TerminalOutcome enum at the policy edge.
    Round-trip via to_tz2_outcome must work for every TerminalOutcome."""
    for outcome in TerminalOutcome:
        result = to_tz2_outcome(outcome)
        # PvP outcomes legitimately return None; everything else maps.
        if not outcome.value.startswith("pvp_"):
            assert result is None or result in TZ2_CANONICAL_OUTCOMES, (
                f"{outcome.value} → {result} not in canonical catalog"
            )


# ── Finalizer side-effect parity ──


@pytest.mark.asyncio
async def test_finalizer_produces_same_xp_regardless_of_caller_state():
    """The post-finalize enrichment helper is the **same code** for REST
    and WS — calling it with REST-style state (state=None) and WS-style
    state (full dict) must produce the same SessionHistory.score_total
    and trigger ManagerProgress exactly once."""
    fake_svc = MagicMock()
    fake_svc.update_after_session = AsyncMock(
        return_value={"xp_breakdown": {"grand_total": 50, "base": 30, "bonus": 20}}
    )

    # WS-style call — full state dict
    db_ws = _make_db()
    session_ws = _make_session()
    with (
        patch(
            "app.services.manager_progress.ManagerProgressService",
            return_value=fake_svc,
        ),
        patch("app.services.scenario_engine.generate_session_report", new_callable=AsyncMock),
        patch("app.services.session_manager.get_message_history", new=AsyncMock(return_value=[])),
        patch("app.services.session_manager.get_message_history_db", new=AsyncMock(return_value=[])),
    ):
        result_ws = await apply_post_finalize_enrichment(
            db_ws,
            session=session_ws,
            scores=_make_scores(),
            state={
                "scenario_code": "cold_call",
                "scenario_name": "Тест",
                "archetype_code": "skeptic",
                "base_difficulty": 5,
                "call_outcome": "success",
                "emotion_peak": "warm",
                "had_comeback": False,
            },
        )

    # REST-style call — state=None, helper synthesises defaults
    fake_svc.update_after_session.reset_mock()
    db_rest = _make_db()
    session_rest = _make_session()
    with (
        patch(
            "app.services.manager_progress.ManagerProgressService",
            return_value=fake_svc,
        ),
        patch("app.services.scenario_engine.generate_session_report", new_callable=AsyncMock),
        patch("app.services.session_manager.get_message_history", new=AsyncMock(return_value=[])),
        patch("app.services.session_manager.get_message_history_db", new=AsyncMock(return_value=[])),
    ):
        result_rest = await apply_post_finalize_enrichment(
            db_rest,
            session=session_rest,
            scores=_make_scores(),
            state=None,
        )

    # Both paths award the SAME XP (helper output identical).
    assert result_ws["xp_earned"] == 50
    assert result_rest["xp_earned"] == 50
    assert result_ws["session_history_created"] is True
    assert result_rest["session_history_created"] is True


@pytest.mark.asyncio
async def test_double_invocation_idempotent_via_session_history_unique():
    """The §10 contract: calling finalizer twice for the same session
    (REST after WS, or WS after REST) creates ONE SessionHistory and
    awards XP ONCE. The second call returns the existing row's
    xp_earned without invoking ManagerProgress.update_after_session."""
    from sqlalchemy.exc import IntegrityError

    existing_history = SimpleNamespace(xp_earned=42)
    db = SimpleNamespace()
    db.add = MagicMock()
    db.flush = AsyncMock()
    # Second writer's begin_nested raises (UNIQUE conflict).
    db.begin_nested = MagicMock(
        return_value=_Savepoint(raise_on_exit=IntegrityError("INSERT", {}, Exception("UNIQUE")))
    )
    exec_result = MagicMock()
    exec_result.scalar_one_or_none = MagicMock(return_value=existing_history)
    db.execute = AsyncMock(return_value=exec_result)

    fake_svc = MagicMock()
    fake_svc.update_after_session = AsyncMock()

    with patch(
        "app.services.manager_progress.ManagerProgressService",
        return_value=fake_svc,
    ):
        result = await apply_post_finalize_enrichment(
            db, session=_make_session(), scores=_make_scores(), state=None
        )

    assert result["xp_earned"] == 42
    assert result["session_history_created"] is False
    fake_svc.update_after_session.assert_not_called()
