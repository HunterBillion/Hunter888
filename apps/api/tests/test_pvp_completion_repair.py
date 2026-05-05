"""PR-1 (2026-05-05): regression tests for the §3.3 invariant gap.

Production audit found 7/11 cancelled duels with terminal_outcome=NULL
because:
  1. ``_cancel_duel_after_disconnect`` bypassed the completion policy.
  2. The ``_finalize_duel`` judge_error path forgot to stamp.
  3. No reaper closed duels stuck in non-terminal state when a worker
     died with the in-memory ``_disconnect_tasks`` dict.

These tests pin the fix:
  * the new ``opponent_disconnected`` and ``reaper_stuck_state``
    TerminalReasons round-trip through ``finalize_pvp_duel``;
  * ``PvPDuelReaper._run_one`` flips a stuck row to cancelled AND
    stamps ``terminal_outcome``/``terminal_reason``;
  * the reaper ignores fresh rows (created_at within stuck-age) and
    rows already in a terminal state.

Run on the in-memory SQLite ``db_session`` fixture from conftest.py so
the assertions exercise the real ORM path (status enum, server defaults,
column types) instead of an AsyncMock.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.completion_policy import (
    TerminalOutcome,
    TerminalReason,
    finalize_pvp_duel,
)


# ── 1. New TerminalReason enum values are accepted by finalize_pvp_duel ──


@pytest.mark.asyncio
async def test_finalize_pvp_accepts_opponent_disconnected_reason():
    from app.models.pvp import DuelStatus

    duel = SimpleNamespace(
        id=uuid.uuid4(),
        status=DuelStatus.cancelled,
        terminal_outcome=None,
        terminal_reason=None,
    )
    db = AsyncMock()

    result = await finalize_pvp_duel(
        db,
        duel=duel,
        outcome=TerminalOutcome.pvp_abandoned,
        reason=TerminalReason.opponent_disconnected,
    )
    assert result.outcome == TerminalOutcome.pvp_abandoned
    assert result.reason == TerminalReason.opponent_disconnected
    assert duel.terminal_outcome == "pvp_abandoned"
    assert duel.terminal_reason == "opponent_disconnected"


@pytest.mark.asyncio
async def test_finalize_pvp_accepts_reaper_stuck_state_reason():
    from app.models.pvp import DuelStatus

    duel = SimpleNamespace(
        id=uuid.uuid4(),
        status=DuelStatus.cancelled,
        terminal_outcome=None,
        terminal_reason=None,
    )
    db = AsyncMock()

    result = await finalize_pvp_duel(
        db,
        duel=duel,
        outcome=TerminalOutcome.pvp_abandoned,
        reason=TerminalReason.reaper_stuck_state,
    )
    assert result.reason == TerminalReason.reaper_stuck_state
    assert duel.terminal_reason == "reaper_stuck_state"


@pytest.mark.asyncio
async def test_finalize_pvp_accepts_judge_failed_reason():
    """The judge_error path in _finalize_duel uses TerminalReason.judge_failed
    (already in the enum, but never previously paired with pvp_abandoned)."""
    from app.models.pvp import DuelStatus

    duel = SimpleNamespace(
        id=uuid.uuid4(),
        status=DuelStatus.completed,
        terminal_outcome=None,
        terminal_reason=None,
    )
    db = AsyncMock()

    result = await finalize_pvp_duel(
        db,
        duel=duel,
        outcome=TerminalOutcome.pvp_abandoned,
        reason=TerminalReason.judge_failed,
    )
    assert duel.terminal_outcome == "pvp_abandoned"
    assert duel.terminal_reason == "judge_failed"


# ── 2. Reaper sweep — real DB roundtrip ──────────────────────────────────


async def _make_stuck_duel(db_session, status_enum, *, age_minutes: int):
    """Insert a PvPDuel row at the given status with created_at in the past.

    Uses two distinct user UUIDs so the unique constraints stay satisfied;
    the rows are PvE (is_pve=True) to avoid needing real users.
    """
    from app.models.pvp import PvPDuel

    duel = PvPDuel(
        id=uuid.uuid4(),
        player1_id=uuid.uuid4(),
        player2_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        scenario_id=None,
        archetype_code="skeptic",
        status=status_enum,
        difficulty="easy",
        round_number=1,
        is_pve=True,
        created_at=datetime.now(timezone.utc) - timedelta(minutes=age_minutes),
    )
    db_session.add(duel)
    await db_session.commit()
    await db_session.refresh(duel)
    return duel


@pytest.mark.asyncio
async def test_reaper_closes_old_round_1_duel_and_stamps_terminal(db_session, monkeypatch):
    """A duel stuck in round_1 for >30min must be flipped to cancelled with
    terminal_outcome=pvp_abandoned and terminal_reason=reaper_stuck_state."""
    from app.models.pvp import DuelStatus, PvPDuel
    from app.services.pvp_duel_reaper import PvPDuelReaper

    duel = await _make_stuck_duel(db_session, DuelStatus.round_1, age_minutes=45)

    # Reaper imports `from app.database import async_session` inside _run_one,
    # so patching the module attribute before the call rebinds the symbol.
    from sqlalchemy.ext.asyncio import async_sessionmaker
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    monkeypatch.setattr("app.database.async_session", lambda: factory(), raising=True)

    reaper = PvPDuelReaper(stuck_age_seconds=30 * 60)
    n = await reaper._run_one()

    assert n == 1
    # Re-fetch in the test's own session — the reaper opened a separate one.
    await db_session.refresh(duel)
    assert duel.status == DuelStatus.cancelled
    assert duel.terminal_outcome == "pvp_abandoned"
    assert duel.terminal_reason == "reaper_stuck_state"
    assert duel.completed_at is not None
    assert duel.duration_seconds is not None and duel.duration_seconds >= 0


@pytest.mark.asyncio
async def test_reaper_skips_recent_round_1_duel(db_session, monkeypatch):
    """A duel stuck in round_1 for only 5min must NOT be reaped."""
    from app.models.pvp import DuelStatus
    from app.services.pvp_duel_reaper import PvPDuelReaper

    duel = await _make_stuck_duel(db_session, DuelStatus.round_1, age_minutes=5)

    from sqlalchemy.ext.asyncio import async_sessionmaker
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    monkeypatch.setattr("app.database.async_session", lambda: factory(), raising=True)

    reaper = PvPDuelReaper(stuck_age_seconds=30 * 60)
    n = await reaper._run_one()

    assert n == 0
    await db_session.refresh(duel)
    assert duel.status == DuelStatus.round_1
    assert duel.terminal_outcome is None


@pytest.mark.asyncio
async def test_reaper_skips_already_terminal_duel(db_session, monkeypatch):
    """A completed duel must never be re-touched even if its created_at is old."""
    from app.models.pvp import DuelStatus
    from app.services.pvp_duel_reaper import PvPDuelReaper

    duel = await _make_stuck_duel(db_session, DuelStatus.completed, age_minutes=120)

    from sqlalchemy.ext.asyncio import async_sessionmaker
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    monkeypatch.setattr("app.database.async_session", lambda: factory(), raising=True)

    reaper = PvPDuelReaper(stuck_age_seconds=30 * 60)
    n = await reaper._run_one()

    assert n == 0
    await db_session.refresh(duel)
    assert duel.status == DuelStatus.completed
    assert duel.terminal_outcome is None  # we did NOT stamp it post-hoc


# ── 3. Disconnect-cancel SQL path — the main path this PR exists for ────


@pytest.mark.asyncio
async def test_cancel_duel_in_db_stamps_terminal_columns(db_session):
    """Direct exercise of the disconnect-cancel SQL half. Pre-fix this path
    wrote status=cancelled but left terminal_* NULL — exactly the 7/11 prod
    bug. After fix the row should have outcome=pvp_abandoned and
    reason=opponent_disconnected."""
    from app.models.pvp import DuelStatus
    from app.ws.pvp import _cancel_duel_in_db

    duel = await _make_stuck_duel(db_session, DuelStatus.round_1, age_minutes=2)

    flipped = await _cancel_duel_in_db(db_session, duel.id)
    await db_session.commit()
    await db_session.refresh(duel)

    assert flipped is True
    assert duel.status == DuelStatus.cancelled
    assert duel.terminal_outcome == "pvp_abandoned"
    assert duel.terminal_reason == "opponent_disconnected"
    assert duel.completed_at is not None
    assert duel.duration_seconds is not None and duel.duration_seconds >= 0


@pytest.mark.asyncio
async def test_cancel_duel_in_db_skips_already_completed(db_session):
    """A completed duel must not be re-touched — this guards the rare
    case where _finalize_duel finished while the disconnect-grace task
    was sleeping its 60s."""
    from app.models.pvp import DuelStatus
    from app.ws.pvp import _cancel_duel_in_db

    duel = await _make_stuck_duel(db_session, DuelStatus.completed, age_minutes=1)

    flipped = await _cancel_duel_in_db(db_session, duel.id)
    await db_session.commit()
    await db_session.refresh(duel)

    assert flipped is False
    assert duel.status == DuelStatus.completed
    assert duel.terminal_outcome is None  # never re-stamped


@pytest.mark.asyncio
async def test_cancel_duel_in_db_skips_judging(db_session):
    """Review fix #1: do NOT cancel a duel mid-judging. Pre-fix this path
    would race the judge and overwrite a completed/win row."""
    from app.models.pvp import DuelStatus
    from app.ws.pvp import _cancel_duel_in_db

    duel = await _make_stuck_duel(db_session, DuelStatus.judging, age_minutes=1)

    flipped = await _cancel_duel_in_db(db_session, duel.id)
    await db_session.commit()
    await db_session.refresh(duel)

    assert flipped is False
    assert duel.status == DuelStatus.judging
    assert duel.terminal_outcome is None


@pytest.mark.asyncio
async def test_cancel_duel_in_db_idempotent_on_repeat(db_session):
    """Two sequential cancel calls must produce the same row state and
    not corrupt terminal_outcome on the second pass."""
    from app.models.pvp import DuelStatus
    from app.ws.pvp import _cancel_duel_in_db

    duel = await _make_stuck_duel(db_session, DuelStatus.round_1, age_minutes=2)

    flipped_1 = await _cancel_duel_in_db(db_session, duel.id)
    await db_session.commit()
    flipped_2 = await _cancel_duel_in_db(db_session, duel.id)
    await db_session.commit()
    await db_session.refresh(duel)

    assert flipped_1 is True
    assert flipped_2 is False  # already terminal — short-circuit
    assert duel.status == DuelStatus.cancelled
    assert duel.terminal_outcome == "pvp_abandoned"
    assert duel.terminal_reason == "opponent_disconnected"


@pytest.mark.asyncio
async def test_cancel_duel_in_db_concurrent_with_gather(db_session):
    """Concurrent gather of two cancel calls must converge on a single
    cancelled row. SQLite serialises writes per connection, so this
    test verifies functional convergence rather than true row-level
    contention (Postgres provides that via with_for_update)."""
    import asyncio
    from app.models.pvp import DuelStatus
    from app.ws.pvp import _cancel_duel_in_db

    duel = await _make_stuck_duel(db_session, DuelStatus.round_1, age_minutes=2)

    # Two concurrent cancel calls on the same row + a single commit.
    a, b = await asyncio.gather(
        _cancel_duel_in_db(db_session, duel.id),
        _cancel_duel_in_db(db_session, duel.id),
    )
    await db_session.commit()
    await db_session.refresh(duel)

    # Exactly one call should have observed the non-terminal state and
    # flipped it; the other call should have hit the terminal-status
    # short-circuit. Convergent state: cancelled + pvp_abandoned.
    assert {a, b} == {True, False}
    assert duel.status == DuelStatus.cancelled
    assert duel.terminal_outcome == "pvp_abandoned"
    assert duel.terminal_reason == "opponent_disconnected"


@pytest.mark.asyncio
async def test_reaper_handles_all_non_terminal_states(db_session, monkeypatch):
    """Reaper must catch every non-terminal status: pending/round_1/swap/round_2/judging."""
    from app.models.pvp import DuelStatus
    from app.services.pvp_duel_reaper import PvPDuelReaper

    states = [
        DuelStatus.pending,
        DuelStatus.round_1,
        DuelStatus.swap,
        DuelStatus.round_2,
        DuelStatus.judging,
    ]
    duels = []
    for st in states:
        duels.append(await _make_stuck_duel(db_session, st, age_minutes=45))

    from sqlalchemy.ext.asyncio import async_sessionmaker
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    monkeypatch.setattr("app.database.async_session", lambda: factory(), raising=True)

    reaper = PvPDuelReaper(stuck_age_seconds=30 * 60)
    n = await reaper._run_one()

    assert n == len(states)
    for d in duels:
        await db_session.refresh(d)
        assert d.status == DuelStatus.cancelled, f"state={d.status} not flipped"
        assert d.terminal_outcome == "pvp_abandoned"
        assert d.terminal_reason == "reaper_stuck_state"
