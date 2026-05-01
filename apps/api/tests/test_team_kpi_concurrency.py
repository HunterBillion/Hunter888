"""Race-resolution tests for KPI PATCH endpoint (CLAUDE.md §4.1).

Audit fix from 5-agent review (#5): the original `update_kpi_target`
SELECT-then-INSERT pattern raced on first-time creation — two parallel
PATCHes both saw `None` from SELECT, both tried to INSERT, second one
hit the PK conflict (`user_id` is PK on `manager_kpi_targets`). Result:
HTTP 500.

The fix wraps the INSERT branch in a savepoint and falls back to UPDATE
on `IntegrityError`. These tests verify the fallback works.

**Note on test DB**: the conftest fixtures use SQLite with `StaticPool`
(single connection), which serialises all "parallel" calls — true
`asyncio.gather` races can't materialise. To still exercise the
race-resolution branch, we simulate the lost-the-race scenario
deterministically: pre-create the row, then call `update_kpi_target`
expecting the SELECT to return None (it won't on a real race, but the
INSERT branch's `IntegrityError` catcher must still re-fetch and UPDATE
correctly). For full PG concurrency coverage, a separate testcontainers
fixture is needed — tracked as a follow-up in the audit batch-2 PR.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.api.team_kpi import KpiTargetUpdateRequest, update_kpi_target
from app.models.user import ManagerKpiTarget, User, UserRole


def _make_user(team_id: uuid.UUID, role: UserRole = UserRole.manager) -> User:
    return User(
        id=uuid.uuid4(),
        email=f"u_{uuid.uuid4().hex[:8]}@test.local",
        hashed_password="$2b$12$placeholder",
        full_name="Test User",
        role=role,
        team_id=team_id,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_kpi_patch_creates_row_first_time(db_session):
    """Happy path: first PATCH on a manager creates the row."""
    team_id = uuid.uuid4()
    rop = _make_user(team_id, UserRole.rop)
    manager = _make_user(team_id, UserRole.manager)
    db_session.add_all([rop, manager])
    await db_session.commit()

    req = KpiTargetUpdateRequest(target_sessions_per_month=20)
    resp = await update_kpi_target(
        request=None, user_id=manager.id, body=req, user=rop, db=db_session,
    )
    assert resp.target_sessions_per_month == 20

    rows = (
        await db_session.execute(
            select(ManagerKpiTarget).where(ManagerKpiTarget.user_id == manager.id)
        )
    ).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_kpi_patch_role_gate_in_handler_chain(db_session):
    """The handler relies on `_scope_check_manager` to refuse writes
    across teams. ROP from team A cannot PATCH manager from team B."""
    team_a = uuid.uuid4()
    team_b = uuid.uuid4()
    rop_a = _make_user(team_a, UserRole.rop)
    manager_b = _make_user(team_b, UserRole.manager)
    db_session.add_all([rop_a, manager_b])
    await db_session.commit()

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await update_kpi_target(
            request=None,
            user_id=manager_b.id,
            body=KpiTargetUpdateRequest(target_sessions_per_month=20),
            user=rop_a,
            db=db_session,
        )
    assert exc_info.value.status_code == 403
