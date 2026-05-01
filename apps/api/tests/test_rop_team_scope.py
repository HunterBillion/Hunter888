"""Tests for ROP team-scope tightening on /rop session endpoints.

SEC-2026-05-02 (9-layer audit fix #9). Closes the data leak where a
ROP from team-A could read every team-B training session via
``GET /rop/sessions`` (paged listing) or ``GET /rop/sessions/{id}/details``.

The same helpers (``_filter_session_by_caller_team``,
``_scope_check_session``, ``_is_admin``) are exercised here so a
future regression on the browse listing or the details lookup is
caught at PR time.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException


# ── _is_admin ─────────────────────────────────────────────────────────────


def test_is_admin_recognises_admin_role():
    from app.api.rop import _is_admin

    admin = MagicMock()
    admin.role = MagicMock(value="admin")
    assert _is_admin(admin) is True


def test_is_admin_rejects_rop_role():
    from app.api.rop import _is_admin

    rop = MagicMock()
    rop.role = MagicMock(value="rop")
    assert _is_admin(rop) is False


def test_is_admin_rejects_manager_role():
    from app.api.rop import _is_admin

    mgr = MagicMock()
    mgr.role = MagicMock(value="manager")
    assert _is_admin(mgr) is False


def test_is_admin_handles_string_role():
    """Some test fixtures give role as a plain string instead of enum."""
    from app.api.rop import _is_admin

    admin = MagicMock()
    admin.role = "admin"
    assert _is_admin(admin) is True


# ── _filter_session_by_caller_team ─────────────────────────────────────────


def test_filter_passes_through_unchanged_for_admin():
    """Admin escape: the SELECT statement must NOT receive any extra
    where clause. We compare the raw whereclause of the returned stmt
    to the original to verify."""
    from app.api.rop import _filter_session_by_caller_team
    from app.models.training import TrainingSession
    from app.models.user import User
    from sqlalchemy import select

    admin = MagicMock()
    admin.role = MagicMock(value="admin")

    base = select(TrainingSession).join(User, User.id == TrainingSession.user_id)
    result = _filter_session_by_caller_team(base, admin)
    # Admin path returns the *same* statement object — no new WHERE.
    assert result is base


def test_filter_appends_team_anchored_where_for_rop():
    """ROP with a team_id: the returned stmt must have a WHERE referencing
    User.team_id and the caller's team value."""
    from app.api.rop import _filter_session_by_caller_team
    from app.models.training import TrainingSession
    from app.models.user import User
    from sqlalchemy import select

    rop = MagicMock()
    rop.role = MagicMock(value="rop")
    rop_team = uuid.uuid4()
    rop.team_id = rop_team

    base = select(TrainingSession).join(User, User.id == TrainingSession.user_id)
    result = _filter_session_by_caller_team(base, rop)

    # Result is a new stmt object (not base)
    assert result is not base
    # Verify caller's team_id appears in the compiled SQL params.
    compiled = result.compile()
    assert rop_team in compiled.params.values() or str(rop_team) in str(compiled.params.values()), (
        f"caller team_id {rop_team} should appear in compiled params; got {compiled.params}"
    )


def test_filter_returns_zero_results_for_team_less_rop():
    """ROP with no team_id: the returned stmt must have a WHERE that
    can never match (literal-false equivalent — User.team_id == zero
    UUID, which can't exist for real users)."""
    from app.api.rop import _filter_session_by_caller_team
    from app.models.training import TrainingSession
    from app.models.user import User
    from sqlalchemy import select

    rop = MagicMock()
    rop.role = MagicMock(value="rop")
    rop.team_id = None

    base = select(TrainingSession).join(User, User.id == TrainingSession.user_id)
    result = _filter_session_by_caller_team(base, rop)
    assert result is not base
    # Verify the zero-UUID sentinel made it into the params.
    compiled = result.compile()
    zero = uuid.UUID(int=0)
    assert zero in compiled.params.values() or str(zero) in str(compiled.params.values())


# ── _scope_check_session ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scope_check_session_admin_passes():
    """Admin bypasses the team gate."""
    from app.api.rop import _scope_check_session

    admin = MagicMock()
    admin.role = MagicMock(value="admin")
    fake_db = MagicMock()
    fake_db.execute = AsyncMock()  # not called because admin escape

    await _scope_check_session(fake_db, uuid.uuid4(), admin)
    fake_db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_scope_check_session_rop_same_team_passes():
    from app.api.rop import _scope_check_session

    team = uuid.uuid4()
    rop = MagicMock()
    rop.role = MagicMock(value="rop")
    rop.team_id = team

    fake_result = MagicMock()
    fake_result.scalar_one_or_none = MagicMock(return_value=team)
    fake_db = MagicMock()
    fake_db.execute = AsyncMock(return_value=fake_result)

    await _scope_check_session(fake_db, uuid.uuid4(), rop)


@pytest.mark.asyncio
async def test_scope_check_session_rop_other_team_403():
    from app.api.rop import _scope_check_session

    rop = MagicMock()
    rop.role = MagicMock(value="rop")
    rop.team_id = uuid.uuid4()

    other_team = uuid.uuid4()
    fake_result = MagicMock()
    fake_result.scalar_one_or_none = MagicMock(return_value=other_team)
    fake_db = MagicMock()
    fake_db.execute = AsyncMock(return_value=fake_result)

    with pytest.raises(HTTPException) as exc:
        await _scope_check_session(fake_db, uuid.uuid4(), rop)
    assert exc.value.status_code == 403
    assert "другой команд" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_scope_check_session_rop_no_team_403():
    """ROP without a team_id is denied with a clear message."""
    from app.api.rop import _scope_check_session

    rop = MagicMock()
    rop.role = MagicMock(value="rop")
    rop.team_id = None

    fake_db = MagicMock()
    fake_db.execute = AsyncMock()  # not called because team_id None short-circuits

    with pytest.raises(HTTPException) as exc:
        await _scope_check_session(fake_db, uuid.uuid4(), rop)
    assert exc.value.status_code == 403
    assert "команд" in exc.value.detail.lower()
    fake_db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_scope_check_session_session_owner_no_team_403():
    """Session owner with NULL team_id (legacy / data corruption) is
    treated as 'different team' — refuse to surface the data."""
    from app.api.rop import _scope_check_session

    rop = MagicMock()
    rop.role = MagicMock(value="rop")
    rop.team_id = uuid.uuid4()

    fake_result = MagicMock()
    fake_result.scalar_one_or_none = MagicMock(return_value=None)
    fake_db = MagicMock()
    fake_db.execute = AsyncMock(return_value=fake_result)

    with pytest.raises(HTTPException) as exc:
        await _scope_check_session(fake_db, uuid.uuid4(), rop)
    assert exc.value.status_code == 403
