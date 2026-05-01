"""Per-manager KPI targets — Команда v2 follow-up.

The Команда panel (PR #122) shows three KPIs per manager: sessions
last 30 days, avg score, days since last session. PR #122 lands the
read side. This module adds the *targets* side — a ROP can set per-
manager goals so the FE renders progress-vs-target indicators.

TODO(post-#122-merge): consolidate this module into ``app/api/team.py``
======================================================================

Status as of 2026-05-01: PR #122 is now merged. This module was kept
separate originally so #151 could land before/after #122 without
merge conflicts. Now that both are on main, the next sweep over
the team panel surface should fold these endpoints into ``team.py``
(roughly: import the four route handlers, drop this file, remove
the ``team_kpi_router`` registration in ``app/api/router.py``).
Not done inline because it's a non-trivial code move that deserves
its own PR with focused review. Tracking: this comment.

Endpoints
---------

* ``GET    /team/users/{user_id}/kpi``   — read targets for one manager
* ``GET    /team/kpi``                    — bulk read for the caller's team
* ``PATCH  /team/users/{user_id}/kpi``   — set/update targets (rop+admin)
* ``DELETE /team/users/{user_id}/kpi``   — clear targets (rop+admin)

Auth + scope: ROP can only touch managers in their own team; admin sees
and edits across all teams. Same rule as `/team/assignments/bulk` in
PR #122.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role
from app.core.rate_limit import limiter
from app.database import get_db
from app.models.user import ManagerKpiTarget, User, UserRole

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Request / response shapes ──────────────────────────────────────────


class KpiTargetUpdateRequest(BaseModel):
    """All three fields optional and explicitly nullable.

    PATCH semantics: if a key is OMITTED → keep existing value. If a key
    is set to ``null`` → clear that target (means "no target", FE hides
    the progress bar).

    Pydantic doesn't distinguish "absent" from "null=None" directly, so
    we use a sentinel default (`Field(default=...)` skipped via
    `model_dump(exclude_unset=True)`) on the server side — see
    ``update_kpi_target`` for the mechanics.
    """

    target_sessions_per_month: int | None = Field(default=None, ge=0)
    target_avg_score: float | None = Field(default=None, ge=0.0, le=100.0)
    target_max_days_without_session: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "KpiTargetUpdateRequest":
        # We can't tell "absent" from "null" at the dataclass level, so
        # the API endpoint re-checks via `model_dump(exclude_unset=True)`
        # and rejects an empty PATCH there. Keeping this hook so future
        # validation can hang off it.
        return self


class KpiTargetResponse(BaseModel):
    user_id: uuid.UUID
    target_sessions_per_month: int | None
    target_avg_score: float | None
    target_max_days_without_session: int | None
    updated_by: uuid.UUID | None
    created_at: str | None
    updated_at: str | None


class KpiTargetBulkResponse(BaseModel):
    targets: list[KpiTargetResponse]


# ── Helpers ────────────────────────────────────────────────────────────


def _row_to_response(row: ManagerKpiTarget) -> KpiTargetResponse:
    return KpiTargetResponse(
        user_id=row.user_id,
        target_sessions_per_month=row.target_sessions_per_month,
        target_avg_score=row.target_avg_score,
        target_max_days_without_session=row.target_max_days_without_session,
        updated_by=row.updated_by,
        created_at=row.created_at.isoformat() if row.created_at else None,
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
    )


async def _scope_check_manager(
    db: AsyncSession, user_id: uuid.UUID, caller: User
) -> User:
    """Ensure target user exists, is a manager, and the caller is allowed
    to touch them (admin always; ROP only for own team)."""
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    target_role = getattr(target.role, "value", str(target.role))
    if target_role != "manager":
        raise HTTPException(
            status_code=409,
            detail=f"KPI targets are only set on managers, got role={target_role!r}",
        )
    is_admin = getattr(caller.role, "value", str(caller.role)) == "admin"
    if not is_admin and target.team_id != caller.team_id:
        raise HTTPException(
            status_code=403,
            detail="ROPs can only manage KPIs for managers in their own team",
        )
    return target


# ── Endpoints ──────────────────────────────────────────────────────────


@router.get("/users/{user_id}/kpi", response_model=KpiTargetResponse)
async def get_kpi_target(
    user_id: uuid.UUID,
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Read one manager's KPI targets. Returns null fields if no row
    exists yet (no implicit creation — ROP explicitly PATCHes to set)."""
    await _scope_check_manager(db, user_id, user)

    row = (
        await db.execute(
            select(ManagerKpiTarget).where(ManagerKpiTarget.user_id == user_id)
        )
    ).scalar_one_or_none()
    if row is None:
        # Synthesize an empty response so the FE can render a "set
        # target" CTA without a 404 round-trip.
        return KpiTargetResponse(
            user_id=user_id,
            target_sessions_per_month=None,
            target_avg_score=None,
            target_max_days_without_session=None,
            updated_by=None,
            created_at=None,
            updated_at=None,
        )
    return _row_to_response(row)


@router.get("/kpi", response_model=KpiTargetBulkResponse)
async def list_team_kpi_targets(
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Bulk read of every KPI row for managers in the caller's team
    (admin → all teams). Used by the FE widget to render the analytics
    table in one round-trip; missing rows are treated as "no target"
    on the FE side."""
    is_admin = getattr(user.role, "value", str(user.role)) == "admin"

    manager_q = select(User.id).where(User.role == UserRole.manager)
    if not is_admin:
        if user.team_id is None:
            return KpiTargetBulkResponse(targets=[])
        manager_q = manager_q.where(User.team_id == user.team_id)
    manager_ids = [r for (r,) in (await db.execute(manager_q)).all()]
    if not manager_ids:
        return KpiTargetBulkResponse(targets=[])

    rows = (
        await db.execute(
            select(ManagerKpiTarget).where(ManagerKpiTarget.user_id.in_(manager_ids))
        )
    ).scalars().all()
    return KpiTargetBulkResponse(
        targets=[_row_to_response(r) for r in rows]
    )


@router.patch("/users/{user_id}/kpi", response_model=KpiTargetResponse)
@limiter.limit("30/minute")
async def update_kpi_target(
    request,  # noqa: ARG001 — required by limiter
    user_id: uuid.UUID,
    body: KpiTargetUpdateRequest,
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Set/update KPI targets for one manager (PATCH semantics).

    Behaviour:
      * Missing keys in the request body are LEFT untouched on the row.
      * Keys explicitly set to null clear that target (FE hides bar).
      * Empty body → 400 "no fields to update".
      * Inserts a row if none exists; updates in place otherwise.
    """
    await _scope_check_manager(db, user_id, user)

    patch = body.model_dump(exclude_unset=True)
    if not patch:
        raise HTTPException(
            status_code=400, detail="No KPI fields supplied",
        )

    # Audit fix (BLOCKER): the original SELECT-then-INSERT-or-UPDATE
    # pattern races on first-time creation: two parallel PATCHes both
    # see `None` from SELECT, both try to INSERT, second one hits the
    # PK conflict (user_id is PK). Result: HTTP 500. Mirror the
    # `_insert_with_dedup` race resolution from attachment_pipeline —
    # wrap the INSERT branch in a savepoint and retry as UPDATE if the
    # row already exists by the time we get there.
    row = (
        await db.execute(
            select(ManagerKpiTarget).where(ManagerKpiTarget.user_id == user_id)
        )
    ).scalar_one_or_none()

    if row is None:
        # First-time creation path — race-safe INSERT + fallback to UPDATE.
        try:
            async with db.begin_nested():
                row = ManagerKpiTarget(user_id=user_id, updated_by=user.id)
                for k, v in patch.items():
                    setattr(row, k, v)
                db.add(row)
                await db.flush()
        except IntegrityError:
            # Lost the race — another writer just created the row. Fall
            # through to the UPDATE path with a fresh SELECT.
            row = (
                await db.execute(
                    select(ManagerKpiTarget).where(ManagerKpiTarget.user_id == user_id)
                )
            ).scalar_one()
            for k, v in patch.items():
                setattr(row, k, v)
            row.updated_by = user.id
            await db.flush()
    else:
        for k, v in patch.items():
            setattr(row, k, v)
        row.updated_by = user.id
        await db.flush()

    await db.commit()
    return _row_to_response(row)


@router.delete("/users/{user_id}/kpi", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
async def delete_kpi_target(
    request,  # noqa: ARG001 — required by limiter
    user_id: uuid.UUID,
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Clear KPI targets for one manager (deletes the row entirely —
    next read returns the synthesized "no target" response)."""
    await _scope_check_manager(db, user_id, user)

    row = (
        await db.execute(
            select(ManagerKpiTarget).where(ManagerKpiTarget.user_id == user_id)
        )
    ).scalar_one_or_none()
    if row is not None:
        await db.delete(row)
        await db.commit()
    return None
