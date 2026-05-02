"""Admin user-management endpoints.

Currently houses the **unblacklist** action — a manual override for the
refresh-replay protection in :mod:`app.api.auth`. When a user's refresh
token is reused (or password changed, or they explicitly logged out)
the auth layer writes ``blacklist:user:{id}`` to Redis with TTL =
``jwt_refresh_token_expire_days * 86400`` (default 7 days). During that
window every request from that user is 401'd as TOKEN_REVOKED.

For pilot users who tripped the protection accidentally (e.g. multi-tab
race, mobile network glitch causing the FE to retry a refresh that
already succeeded), the only recovery was to ask the operator to
``redis-cli DEL blacklist:user:{id}`` — which (a) requires Redis CLI
access on a prod host, (b) leaves no audit trail of who unlocked whom
and why. This endpoint replaces that workflow with an admin-only,
audit-logged, rate-limited HTTP call.

Scope: ``admin`` only (not ``rop``). Per-token JTI revocation is **not**
touched — those entries expire on their own and the user just logs in
fresh anyway.
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
from app.database import get_db
from app.models.user import User
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
