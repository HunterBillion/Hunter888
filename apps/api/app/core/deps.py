import logging
import uuid

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core import errors as err
from app.core.security import decode_token
from app.core.redis_pool import get_redis
from app.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)


async def _check_revocation(user_id: str, jti: str | None) -> tuple[bool, bool]:
    """Single-roundtrip check of both blacklist and JTI revocation keys.

    2026-04-20: previously the two checks were two separate Redis GETs back-to-
    back. Under parallel load (~25 concurrent /auth/me calls) the connection
    pool saturated frequently enough that one of the two GETs would raise a
    transient `ConnectionError` and the fail-closed branch would deny a fully
    valid request — observed as roughly 1 in 25 requests returning 401.
    Batching the two keys into a single MGET halves Redis load per auth
    check, removes the inter-call race window, and lets one transient error
    fail both checks consistently (still closed). A single short retry on
    ConnectionError is added so that routine pool churn doesn't surface as
    user-visible 401 spikes.

    Returns (blacklisted, revoked). Both default to True on persistent
    Redis failure (fail-closed).
    """
    keys = [f"blacklist:user:{user_id}"]
    if jti:
        keys.append(f"token:revoked:{jti}")

    for attempt in (1, 2):
        try:
            r = get_redis()
            values = await r.mget(*keys)
            blacklisted = values[0] is not None
            revoked = bool(jti and len(values) > 1 and values[1] is not None)
            return blacklisted, revoked
        except aioredis.ConnectionError:
            if attempt == 1:
                # One-shot retry — most saturation events clear in <50ms
                continue
            logger.error(
                "Redis unavailable for revocation check (after retry) — DENYING access (fail-closed)"
            )
            return True, True
        except Exception:
            logger.error(
                "Unexpected error in revocation check — DENYING access (fail-closed)",
                exc_info=True,
            )
            return True, True
    # Unreachable — loop either returns or breaks explicitly; kept for mypy.
    return True, True


async def _is_user_blacklisted(user_id: str) -> bool:
    """Back-compat shim. Prefer `_check_revocation` for new call sites."""
    blacklisted, _ = await _check_revocation(user_id, None)
    return blacklisted


async def _is_token_revoked(jti: str | None) -> bool:
    """Back-compat shim. Prefer `_check_revocation` for new call sites."""
    if not jti:
        return False
    _, revoked = await _check_revocation("", jti)
    return revoked


from fastapi import Cookie, Request


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
    access_token: str | None = Cookie(default=None),
) -> User:
    # Try Bearer header first, then httpOnly cookie
    token = None
    if credentials:
        token = credentials.credentials
    elif access_token:
        token = access_token

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=err.NOT_AUTHENTICATED,
        )

    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=err.INVALID_OR_EXPIRED_TOKEN,
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=err.INVALID_TOKEN)

    # 2026-04-20: batched atomic check — was two sequential Redis GETs, now
    # one MGET. Fixes the 1-in-25 401-under-load race (see _check_revocation).
    blacklisted, revoked = await _check_revocation(user_id, payload.get("jti"))
    if revoked or blacklisted:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=err.TOKEN_REVOKED,
        )

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=err.USER_NOT_FOUND)

    return user


def require_role(*roles: str):
    """FastAPI dependency factory: returns a dependency that checks user role.

    Usage: Depends(require_role("admin", "rop"))
    """

    async def checker(user: User = Depends(get_current_user)) -> User:
        if user.role.value not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=err.INSUFFICIENT_PERMISSIONS,
            )
        return user

    return checker


def check_wiki_access(user: User, manager_id) -> None:
    """Raise 403 if user is not admin/rop and not the wiki owner."""
    if user.role.value in ("admin", "rop"):
        return
    if str(user.id) == str(manager_id):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Cannot access other managers' wikis",
    )


async def check_entitlement(feature: str, user: User, db) -> None:
    """Check if user's subscription plan allows a feature. Raises 403 if not."""
    from app.services.entitlement import get_entitlement, check_feature
    ent = await get_entitlement(user.id, db)
    if not check_feature(ent, feature):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Feature '{feature}' requires a higher plan. Current: {ent.plan.value}",
        )


async def check_session_limit(user: User, db) -> None:
    """Check if user hasn't exceeded daily session limit. Raises 429 if exceeded."""
    from app.services.entitlement import get_entitlement, check_session_limit as _check
    ent = await get_entitlement(user.id, db)
    if not _check(ent):
        raise HTTPException(
            status_code=429,
            detail=f"Daily session limit reached ({ent.limits.sessions_per_day}). Upgrade your plan.",
        )
