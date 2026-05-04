"""Admin user-management endpoints.

Houses two actions:

1. **POST /admin/users/{id}/unblacklist** — manual override for the
   refresh-replay protection in :mod:`app.api.auth`.
2. **PATCH /admin/users/{id}** — edit role / team_id / is_active /
   full_name without dropping into SQL on a prod host. Replaces the
   workflow that previously required the admin to SSH cqax + ``docker
   compose exec api psql`` on every team rebalance or hire/fire.

Both actions are admin-only, rate-limited, and write to ``audit_log``
with full old/new-value diffs. Role changes also trigger
:func:`bump_role_version` so any cached JWT carrying the old role gets
invalidated on the next /auth/me hit (otherwise an ex-admin would keep
admin privileges until the access token expired, up to 60 minutes).
"""
from __future__ import annotations

import logging
import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role
from app.core.rate_limit import limiter
from app.core.redis_pool import get_redis
from app.core.security import bump_role_version
from app.database import get_db
from app.models.user import Team, User, UserRole
from app.services.audit import write_audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/users", tags=["admin", "users"])

_require_admin = require_role("admin")


class UnblacklistRequest(BaseModel):
    # Required, non-empty. Forces the operator to record *why* — this is
    # the difference between "audit trail" and "audit trail with signal".
    # Min 8 chars rejects placeholder values like "fix" / "ok" / "1".
    reason: str = Field(..., min_length=8, max_length=500)


class UnblacklistResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    was_blacklisted: bool
    cleared_keys: list[str]


@router.post(
    "/{user_id}/unblacklist",
    response_model=UnblacklistResponse,
    status_code=status.HTTP_200_OK,
)
# Rate limit: a misbehaving admin script could otherwise mass-unblacklist
# everyone — that would defeat the refresh-replay protection. 10/min is
# above any legitimate manual workflow but below "automated abuse".
@limiter.limit("10/minute")
async def unblacklist_user(
    request: Request,
    user_id: uuid.UUID,
    body: UnblacklistRequest,
    actor: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> UnblacklistResponse:
    """Clear the per-user blacklist sentinel for ``user_id`` in Redis.

    Writes an :class:`AuditLog` row (action = ``admin_unblacklist_user``)
    with the actor, target, reason, and request IP/user-agent. The audit
    row is written even if the target wasn't actually blacklisted — that
    way operators see "tried but no-op" attempts in the trail too.
    """
    target_lookup = await db.execute(select(User).where(User.id == user_id))
    target = target_lookup.scalar_one_or_none()
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user_not_found",
        )

    cleared: list[str] = []
    was_blacklisted = False

    try:
        r = get_redis()
        key = f"blacklist:user:{target.id}"
        # DEL returns the number of keys actually removed. 1 = was
        # blacklisted; 0 = no-op. We surface this so the admin UI can
        # show "user wasn't blacklisted, action no-op".
        removed = await r.delete(key)
        was_blacklisted = bool(removed)
        if was_blacklisted:
            cleared.append(key)
    except aioredis.RedisError as exc:
        # Redis unreachable — log + 503. Do NOT fall through silently:
        # an admin who hits this endpoint expects a definitive answer
        # ("user is now unlocked") not "maybe".
        logger.error(
            "Redis error during admin unblacklist",
            extra={
                "actor_id": str(actor.id),
                "target_id": str(target.id),
                "error": str(exc),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="redis_unavailable",
        ) from exc

    await write_audit_log(
        db,
        actor=actor,
        action="admin_unblacklist_user",
        entity_type="users",
        entity_id=target.id,
        new_values={
            "reason": body.reason,
            "was_blacklisted": was_blacklisted,
            "target_email": target.email,
        },
        request=request,
    )
    await db.commit()

    return UnblacklistResponse(
        user_id=target.id,
        email=target.email,
        was_blacklisted=was_blacklisted,
        cleared_keys=cleared,
    )


# ── PATCH /admin/users/{id} ─────────────────────────────────────────────


# Sentinel so the FE can clear team_id (set to NULL) by passing
# ``team_id: null``. Pydantic 2 distinguishes "field missing" from
# "field present with value null" when ``model_dump(exclude_unset=True)``
# is used — that's what powers the partial PATCH semantics here.
class UserPatchRequest(BaseModel):
    """Partial update — only fields actually present in the payload are
    applied. ``team_id: null`` explicitly clears the assignment.

    All four fields are optional; an empty body is a no-op (returns the
    user unchanged with no audit row). At least one field must change
    for the audit row to be written.
    """
    role: UserRole | None = None
    team_id: uuid.UUID | None = None
    is_active: bool | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    reason: str = Field(..., min_length=8, max_length=500)

    model_config = {"extra": "forbid"}


class UserPatchResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    role: str
    team_id: uuid.UUID | None
    team_name: str | None
    is_active: bool
    full_name: str
    changed_fields: list[str]
    role_version_bumped: bool
    tokens_revoked: bool


_AUDITED_FIELDS = ("role", "team_id", "is_active", "full_name")


@router.patch(
    "/{user_id}",
    response_model=UserPatchResponse,
    status_code=status.HTTP_200_OK,
)
# Same rationale as unblacklist: a misbehaving admin script could mass-
# downgrade users; 30/min is well above any real workflow but caps blast
# radius. Per-row failure is an HTTP 4xx, not a DB rollback of the batch
# (no batching at this endpoint by design — one user per call).
@limiter.limit("30/minute")
async def patch_user(
    request: Request,
    user_id: uuid.UUID,
    body: UserPatchRequest,
    actor: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> UserPatchResponse:
    """Edit role / team / is_active / full_name on a target user.

    Side-effects in order:
      1. Validate the new values (404 on bad team_id, 400 on self-demote,
         400 on body without any field changing).
      2. Snapshot old values and apply the patch.
      3. If ``role`` changed → :func:`bump_role_version` so any cached
         JWT with the old role becomes stale on the next request.
      4. If ``is_active`` flipped to ``False`` → write
         ``blacklist:user:{id}`` to Redis (TTL 7 days) so the target's
         existing access token can't keep working until natural expiry.
      5. Write an :class:`AuditLog` row with full diff + reason.
      6. Single ``db.commit()`` so steps 2 and 5 land atomically.

    Scope-rules (v1, admin-only — ROP-scoped edits will land in a
    follow-up):
      * Only admins can call this. ROPs use /team/* endpoints for their
        scoped subset (KPI, bulk-assign).
      * Admin **cannot** demote themself out of the admin role. That
        would deadlock the panel ("no admin left → no way to promote
        anyone back"). Use a different admin to demote you.
      * Admin **cannot** set ``is_active=False`` on themself for the
        same reason — they'd lock themself out.
    """
    target_lookup = await db.execute(select(User).where(User.id == user_id))
    target = target_lookup.scalar_one_or_none()
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found",
        )

    # ── Self-edit guards ────────────────────────────────────────────
    if target.id == actor.id:
        if body.role is not None and body.role != UserRole.admin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="admin_self_demote_forbidden",
            )
        if body.is_active is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="admin_self_deactivate_forbidden",
            )

    patch_data = body.model_dump(exclude_unset=True, exclude={"reason"})
    if not patch_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="no_fields_to_update",
        )

    # ── Validate team_id exists when set (skip when explicit null) ──
    if "team_id" in patch_data and patch_data["team_id"] is not None:
        team_check = await db.execute(
            select(Team.id).where(Team.id == patch_data["team_id"])
        )
        if team_check.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="team_not_found",
            )

    # ── Snapshot old values for audit ───────────────────────────────
    old_values = {
        "role": target.role.value,
        "team_id": str(target.team_id) if target.team_id else None,
        "is_active": target.is_active,
        "full_name": target.full_name,
    }

    # ── Apply patch + track which fields actually changed ───────────
    changed: list[str] = []
    for field in _AUDITED_FIELDS:
        if field in patch_data:
            new_val = patch_data[field]
            cur_val = getattr(target, field)
            # Compare by string for enum/UUID safety
            cur_str = cur_val.value if hasattr(cur_val, "value") else (
                str(cur_val) if isinstance(cur_val, uuid.UUID) else cur_val
            )
            new_str = new_val.value if hasattr(new_val, "value") else (
                str(new_val) if isinstance(new_val, uuid.UUID) else new_val
            )
            if cur_str != new_str:
                setattr(target, field, new_val)
                changed.append(field)

    if not changed:
        # Idempotent no-op — same values resubmitted. No audit row,
        # no role-bump, no token revoke. Return current state.
        team_name = None
        if target.team_id:
            t = await db.execute(select(Team.name).where(Team.id == target.team_id))
            team_name = t.scalar_one_or_none()
        return UserPatchResponse(
            user_id=target.id,
            email=target.email,
            role=target.role.value,
            team_id=target.team_id,
            team_name=team_name,
            is_active=target.is_active,
            full_name=target.full_name,
            changed_fields=[],
            role_version_bumped=False,
            tokens_revoked=False,
        )

    # ── Side-effects ────────────────────────────────────────────────
    role_bumped = False
    if "role" in changed:
        # Bumps Redis counter so any JWT issued before now carrying the
        # old role.value will be 403'd on next /auth/me hit. The user
        # must log in again to get a token with the new role.
        await bump_role_version(str(target.id))
        role_bumped = True

    tokens_revoked = False
    if "is_active" in changed and target.is_active is False:
        # Same blacklist sentinel the auth layer uses for token-replay.
        # TTL = 7 days = jwt_refresh_token_expire_days. Effectively
        # "until refresh expiry" so a deactivated user can't keep
        # working with a still-valid access token.
        try:
            r = get_redis()
            await r.setex(
                f"blacklist:user:{target.id}",
                7 * 24 * 3600,
                f"deactivated_by_admin:{actor.id}",
            )
            tokens_revoked = True
        except aioredis.RedisError as exc:
            # Don't fail the patch over a Redis blip — the user is now
            # is_active=False, /auth/me will refuse the next refresh.
            # But operator deserves to know it didn't fully revoke.
            logger.error(
                "Redis error while revoking tokens during admin patch",
                extra={
                    "actor_id": str(actor.id),
                    "target_id": str(target.id),
                    "error": str(exc),
                },
            )

    new_values = {field: old_values[field] for field in old_values}  # baseline
    for field in changed:
        cur = getattr(target, field)
        if hasattr(cur, "value"):
            new_values[field] = cur.value
        elif isinstance(cur, uuid.UUID):
            new_values[field] = str(cur)
        else:
            new_values[field] = cur
    new_values["reason"] = body.reason

    await write_audit_log(
        db,
        actor=actor,
        action="admin_patch_user",
        entity_type="users",
        entity_id=target.id,
        old_values={field: old_values[field] for field in changed},
        new_values={
            **{field: new_values[field] for field in changed},
            "reason": body.reason,
            "role_version_bumped": role_bumped,
            "tokens_revoked": tokens_revoked,
        },
        request=request,
    )

    await db.commit()
    await db.refresh(target)

    team_name = None
    if target.team_id:
        t = await db.execute(select(Team.name).where(Team.id == target.team_id))
        team_name = t.scalar_one_or_none()

    return UserPatchResponse(
        user_id=target.id,
        email=target.email,
        role=target.role.value,
        team_id=target.team_id,
        team_name=team_name,
        is_active=target.is_active,
        full_name=target.full_name,
        changed_fields=changed,
        role_version_bumped=role_bumped,
        tokens_revoked=tokens_revoked,
    )
