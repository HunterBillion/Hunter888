"""Phase 1 — ConversationCompletionPolicy tests (Roadmap §6.5).

Covers the pure-function surface (enums, validate, outcome_from_raw)
and finalize() idempotency + column stamping using a SQLAlchemy in-
memory instance as the ``session`` object (no DB round-trip needed for
the logic under test — the DB layer is already exercised by the shape
verification in test_phase0_hotfixes.py via AST checks on call sites).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.completion_policy import (
    CompletedVia,
    InvalidTerminalOutcome,
    TerminalOutcome,
    TerminalReason,
    finalize_pvp_duel,
    finalize_training_session,
    outcome_from_raw,
    validate,
)


# ── Enum hygiene ─────────────────────────────────────────────────────────


def test_terminal_outcome_covers_training_and_pvp():
    training = {
        "success", "hard_reject", "needs_followup", "need_documents",
        "callback_requested", "no_answer", "hangup", "timeout",
        "technical_failed", "operator_aborted",
    }
    pvp = {"pvp_win", "pvp_loss", "pvp_draw", "pvp_abandoned"}
    values = {o.value for o in TerminalOutcome}
    assert training | pvp == values


def test_terminal_reason_catalog_matches_roadmap():
    expected = {
        "user_ended", "user_farewell_detected", "client_farewell_detected",
        "silence_timeout", "ws_disconnect", "route_navigation",
        "matchmaking_timeout", "judge_failed", "judge_completed", "admin_aborted",
    }
    assert {r.value for r in TerminalReason} == expected


# ── validate() ───────────────────────────────────────────────────────────


def test_validate_accepts_training_outcomes():
    for outcome in TerminalOutcome:
        if outcome.value.startswith("pvp_"):
            continue
        validate("chat", outcome, is_pvp=False)  # no raise


def test_validate_rejects_pvp_outcome_for_training():
    with pytest.raises(InvalidTerminalOutcome):
        validate("chat", TerminalOutcome.pvp_win, is_pvp=False)


def test_validate_rejects_training_outcome_for_pvp():
    with pytest.raises(InvalidTerminalOutcome):
        validate("pvp", TerminalOutcome.success, is_pvp=True)


def test_validate_blocks_hangup_for_center_mode():
    # Центр — это физическая консультация, "положить трубку" не бывает.
    with pytest.raises(InvalidTerminalOutcome):
        validate("center", TerminalOutcome.hangup, is_pvp=False)


def test_validate_allows_timeout_for_center_mode():
    # Тайм-аут WS при центре — это legit (пользователь закрыл вкладку).
    validate("center", TerminalOutcome.timeout, is_pvp=False)


# ── outcome_from_raw ─────────────────────────────────────────────────────


def test_outcome_from_raw_common_aliases():
    cases = {
        None: TerminalOutcome.operator_aborted,
        "": TerminalOutcome.operator_aborted,
        "   ": TerminalOutcome.operator_aborted,
        "deal": TerminalOutcome.success,
        "Deal_Agreed": TerminalOutcome.success,
        "rejected": TerminalOutcome.hard_reject,
        "LOST": TerminalOutcome.hard_reject,
        "callback": TerminalOutcome.callback_requested,
        "hangup": TerminalOutcome.hangup,
        "silence_timeout": TerminalOutcome.timeout,
        "garbage-value": TerminalOutcome.operator_aborted,
    }
    for raw, expected in cases.items():
        assert outcome_from_raw(raw) == expected, f"{raw!r}"


# ── finalize_training_session ────────────────────────────────────────────


def _fake_session(**overrides):
    base = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        scenario_id=uuid.uuid4(),
        status=SimpleNamespace(value="active", name="active"),
        started_at=None,
        ended_at=None,
        duration_seconds=None,
        score_total=87.5,
        score_human_factor=None,
        score_narrative=None,
        score_legal=None,
        scoring_details=None,
        custom_params=None,
        real_client_id=None,
        source="training",
        terminal_outcome=None,
        terminal_reason=None,
        completed_via=None,
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


@pytest.mark.asyncio
async def test_finalize_stamps_terminal_columns(monkeypatch):
    import app.services.completion_policy as cp

    monkeypatch.setattr(cp.settings, "completion_policy_strict", False, raising=False)
    monkeypatch.setattr(cp.settings, "completion_policy_emit_event", False, raising=False)

    # Make status enum behave like the SessionStatus we expect
    from app.models.training import SessionStatus

    session = _fake_session(status=SessionStatus.active)
    db = AsyncMock()

    result = await finalize_training_session(
        db,
        session=session,
        outcome=TerminalOutcome.success,
        reason=TerminalReason.user_ended,
        completed_via=CompletedVia.rest,
        manager_id=uuid.uuid4(),
    )

    assert not result.already_completed
    assert session.terminal_outcome == "success"
    assert session.terminal_reason == "user_ended"
    assert session.completed_via == "rest"
    assert session.status == SessionStatus.completed
    assert session.ended_at is not None
    # Scoring details mirror kept in sync
    assert session.scoring_details["terminal_outcome"] == "success"


@pytest.mark.asyncio
async def test_finalize_is_idempotent_on_already_stamped(monkeypatch):
    import app.services.completion_policy as cp

    monkeypatch.setattr(cp.settings, "completion_policy_strict", False, raising=False)
    monkeypatch.setattr(cp.settings, "completion_policy_emit_event", False, raising=False)

    from app.models.training import SessionStatus

    session = _fake_session(
        status=SessionStatus.completed,
        terminal_outcome="success",
        terminal_reason="user_ended",
        completed_via="rest",
    )
    db = AsyncMock()

    result = await finalize_training_session(
        db,
        session=session,
        # Caller attempts a DIFFERENT outcome on a second invocation;
        # policy ignores it and returns the cached decision.
        outcome=TerminalOutcome.hangup,
        reason=TerminalReason.client_farewell_detected,
        completed_via=CompletedVia.ws,
        manager_id=uuid.uuid4(),
    )

    assert result.already_completed
    assert result.outcome == TerminalOutcome.success
    assert session.terminal_outcome == "success"  # unchanged


@pytest.mark.asyncio
async def test_finalize_strict_mode_calls_tail_helpers(monkeypatch):
    import app.services.completion_policy as cp

    monkeypatch.setattr(cp.settings, "completion_policy_strict", True, raising=False)
    monkeypatch.setattr(cp.settings, "completion_policy_emit_event", False, raising=False)

    from app.models.training import SessionStatus

    session = _fake_session(status=SessionStatus.active, real_client_id=uuid.uuid4())
    db = AsyncMock()

    followup = AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4()))
    log_crm = AsyncMock(return_value=(SimpleNamespace(id=uuid.uuid4()), SimpleNamespace(id=uuid.uuid4())))
    emit_bus = AsyncMock()

    with patch("app.services.crm_followup.ensure_followup_for_session", followup), \
         patch("app.services.client_domain.log_training_real_case_summary", log_crm), \
         patch("app.services.event_bus.event_bus.emit", emit_bus):
        result = await finalize_training_session(
            db,
            session=session,
            outcome=TerminalOutcome.callback_requested,
            reason=TerminalReason.user_ended,
            completed_via=CompletedVia.rest,
            manager_id=uuid.uuid4(),
        )

    followup.assert_awaited_once()
    log_crm.assert_awaited_once()
    emit_bus.assert_awaited_once()
    assert set(result.events_emitted) >= {
        "crm.reminder_created",
        "training.real_case_logged",
        "training_completed",
    }


# ── finalize_pvp_duel ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_finalize_pvp_stamps_and_is_idempotent():
    from app.models.pvp import DuelStatus

    duel = SimpleNamespace(
        id=uuid.uuid4(),
        status=DuelStatus.completed,
        terminal_outcome=None,
        terminal_reason=None,
    )
    db = AsyncMock()

    first = await finalize_pvp_duel(
        db,
        duel=duel,
        outcome=TerminalOutcome.pvp_win,
        reason=TerminalReason.judge_completed,
    )
    assert first.outcome == TerminalOutcome.pvp_win
    assert duel.terminal_outcome == "pvp_win"

    # Second attempt with a different outcome is a no-op.
    second = await finalize_pvp_duel(
        db,
        duel=duel,
        outcome=TerminalOutcome.pvp_draw,
        reason=TerminalReason.judge_completed,
    )
    assert second.already_completed
    assert duel.terminal_outcome == "pvp_win"


@pytest.mark.asyncio
async def test_finalize_pvp_rejects_training_outcome():
    from app.models.pvp import DuelStatus

    duel = SimpleNamespace(
        id=uuid.uuid4(),
        status=DuelStatus.completed,
        terminal_outcome=None,
        terminal_reason=None,
    )
    db = AsyncMock()

    with pytest.raises(InvalidTerminalOutcome):
        await finalize_pvp_duel(
            db,
            duel=duel,
            outcome=TerminalOutcome.success,  # training-only outcome
            reason=TerminalReason.judge_completed,
        )
