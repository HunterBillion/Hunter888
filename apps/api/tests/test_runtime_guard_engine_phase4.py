"""TZ-2 §8 Phase 4 deferred guards.

Each test exercises the guard's pre-fix-fail / post-fix-pass pattern:
the guard MUST return a violation when the condition is broken and
MUST return None on the happy path. Wiring tests live alongside the
existing REST/WS handler suites — these are unit tests on the engine
layer.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.runtime_guard_engine import (
    GUARD_LEAD_CLIENT_ACCESS_DENIED,
    GUARD_PROJECTION_TARGET_MISSING,
    GUARD_RUNTIME_STATUS_NOT_FINALIZABLE,
    GUARD_SESSION_UNIQUENESS_VIOLATED,
    evaluate_lead_client_access_guard,
    evaluate_projection_safe_commit_guard,
    evaluate_runtime_status_guard,
    evaluate_session_uniqueness_guard,
)


# ── lead_client_access_guard ────────────────────────────────────────────────


def test_lead_client_access_passes_when_user_owns_real_client():
    user_id = uuid.uuid4()
    user = SimpleNamespace(id=user_id, role="manager")
    real_client = SimpleNamespace(id=uuid.uuid4(), manager_id=user_id)
    assert evaluate_lead_client_access_guard(user=user, real_client=real_client) is None


def test_lead_client_access_passes_for_admin_role():
    user = SimpleNamespace(id=uuid.uuid4(), role="admin")
    real_client = SimpleNamespace(id=uuid.uuid4(), manager_id=uuid.uuid4())  # different owner
    assert evaluate_lead_client_access_guard(user=user, real_client=real_client) is None


def test_lead_client_access_passes_when_no_real_client():
    """Simulation paths skip RBAC — there's no client to gate."""
    user = SimpleNamespace(id=uuid.uuid4(), role="manager")
    assert evaluate_lead_client_access_guard(user=user, real_client=None) is None


def test_lead_client_access_denies_when_user_does_not_own_real_client():
    user = SimpleNamespace(id=uuid.uuid4(), role="manager")
    real_client = SimpleNamespace(id=uuid.uuid4(), manager_id=uuid.uuid4())  # different owner
    v = evaluate_lead_client_access_guard(user=user, real_client=real_client)
    assert v is not None
    assert v.code == GUARD_LEAD_CLIENT_ACCESS_DENIED
    assert v.details and "real_client_id" in v.details


# ── session_uniqueness_guard ────────────────────────────────────────────────


def _db_with_existing_session(existing_session_id: uuid.UUID | None):
    """Build a mock async DB whose execute() returns the given id."""
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=existing_session_id)
    db.execute = AsyncMock(return_value=result)
    return db


@pytest.mark.asyncio
async def test_session_uniqueness_passes_when_no_active_session():
    db = _db_with_existing_session(None)
    v = await evaluate_session_uniqueness_guard(
        db, user_id=uuid.uuid4(), real_client_id=uuid.uuid4(),
    )
    assert v is None


@pytest.mark.asyncio
async def test_session_uniqueness_passes_for_simulation_paths():
    """No real_client_id → simulation runtime → multiple concurrent
    sessions are intentionally allowed."""
    db = _db_with_existing_session(uuid.uuid4())  # would block if checked
    v = await evaluate_session_uniqueness_guard(
        db, user_id=uuid.uuid4(), real_client_id=None,
    )
    assert v is None
    db.execute.assert_not_called()  # short-circuits before SELECT


@pytest.mark.asyncio
async def test_session_uniqueness_blocks_when_active_session_exists():
    existing_id = uuid.uuid4()
    db = _db_with_existing_session(existing_id)
    v = await evaluate_session_uniqueness_guard(
        db, user_id=uuid.uuid4(), real_client_id=uuid.uuid4(),
    )
    assert v is not None
    assert v.code == GUARD_SESSION_UNIQUENESS_VIOLATED
    assert v.details
    assert v.details["active_session_id"] == str(existing_id)


# ── runtime_status_guard ────────────────────────────────────────────────────


def test_runtime_status_passes_for_active_session():
    from app.models.training import SessionStatus

    session = SimpleNamespace(id=uuid.uuid4(), status=SessionStatus.active)
    assert evaluate_runtime_status_guard(session=session) is None


def test_runtime_status_passes_for_string_status_active():
    """ORM emits SessionStatus enum, but JSON payloads sometimes carry
    the raw string. Coerce both."""
    session = SimpleNamespace(id=uuid.uuid4(), status="active")
    assert evaluate_runtime_status_guard(session=session) is None


def test_runtime_status_blocks_for_completed_session():
    from app.models.training import SessionStatus

    session = SimpleNamespace(id=uuid.uuid4(), status=SessionStatus.completed)
    v = evaluate_runtime_status_guard(session=session)
    assert v is not None
    assert v.code == GUARD_RUNTIME_STATUS_NOT_FINALIZABLE
    assert v.details and v.details["current_status"] == "completed"


def test_runtime_status_blocks_for_abandoned_session():
    from app.models.training import SessionStatus

    session = SimpleNamespace(id=uuid.uuid4(), status=SessionStatus.abandoned)
    v = evaluate_runtime_status_guard(session=session)
    assert v is not None
    assert v.code == GUARD_RUNTIME_STATUS_NOT_FINALIZABLE


def test_runtime_status_passes_for_ending_state():
    """TZ-2 §6.4 reserves an `ending` state for two-phase teardown.
    The current ORM enum doesn't include it yet; the guard must accept
    the future value so a follow-up migration doesn't bring this guard
    down by surprise."""
    session = SimpleNamespace(id=uuid.uuid4(), status="ending")
    assert evaluate_runtime_status_guard(session=session) is None


# ── projection_safe_commit_guard ────────────────────────────────────────────


def _db_with_lead(lead):
    db = MagicMock()
    db.get = AsyncMock(return_value=lead)
    return db


@pytest.mark.asyncio
async def test_projection_safe_commit_passes_for_simulation_session():
    """No real_client_id → no projection target needed."""
    db = MagicMock()
    db.get = AsyncMock()
    session = SimpleNamespace(id=uuid.uuid4(), real_client_id=None)
    v = await evaluate_projection_safe_commit_guard(db, session=session)
    assert v is None
    db.get.assert_not_called()


@pytest.mark.asyncio
async def test_projection_safe_commit_passes_when_lead_active():
    real_id = uuid.uuid4()
    lead = SimpleNamespace(id=real_id, work_state="active")
    db = _db_with_lead(lead)
    session = SimpleNamespace(id=uuid.uuid4(), real_client_id=real_id)
    v = await evaluate_projection_safe_commit_guard(db, session=session)
    assert v is None


@pytest.mark.asyncio
async def test_projection_safe_commit_blocks_when_lead_missing():
    real_id = uuid.uuid4()
    db = _db_with_lead(None)
    session = SimpleNamespace(id=uuid.uuid4(), real_client_id=real_id)
    v = await evaluate_projection_safe_commit_guard(db, session=session)
    assert v is not None
    assert v.code == GUARD_PROJECTION_TARGET_MISSING
    assert v.details and v.details["reason"] == "lead_client_not_found"


@pytest.mark.asyncio
async def test_projection_safe_commit_blocks_when_lead_archived():
    real_id = uuid.uuid4()
    lead = SimpleNamespace(id=real_id, work_state="archived")
    db = _db_with_lead(lead)
    session = SimpleNamespace(id=uuid.uuid4(), real_client_id=real_id)
    v = await evaluate_projection_safe_commit_guard(db, session=session)
    assert v is not None
    assert v.code == GUARD_PROJECTION_TARGET_MISSING
    assert v.details and v.details["reason"] == "lead_client_archived"


# ── flag-default sanity ─────────────────────────────────────────────────────


def test_all_phase4_flags_default_off():
    """Every Phase 4 flag must default to False so a deploy never
    silently enables a new guard. SRE flips them per-environment after
    24h observation. If this test fails, you're about to ship a
    behavioural change without an explicit owner sign-off."""
    from app.config import settings

    assert settings.tz2_guard_lead_client_access_enabled is False
    assert settings.tz2_guard_session_uniqueness_enabled is False
    assert settings.tz2_guard_runtime_status_enabled is False
    assert settings.tz2_guard_projection_safe_commit_enabled is False
