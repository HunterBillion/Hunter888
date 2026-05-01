import logging
import uuid

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core import errors as err
from app.core.security import decode_token, get_role_version
from app.core.redis_pool import get_redis
from app.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)


async def _is_user_blacklisted(user_id: str) -> bool:
    """Check if user's tokens were invalidated via logout.

    Uses the central Redis connection pool (app.core.redis_pool).
    SECURITY: Fails CLOSED — if Redis is down, deny access.
    This prevents logged-out users from using revoked tokens.
    """
    try:
        r = get_redis()
        result = await r.get(f"blacklist:user:{user_id}")
        return result is not None
    except aioredis.ConnectionError:
        logger.error("Redis unavailable for blacklist check — DENYING access (fail-closed)")
        return True
    except Exception:
        logger.error("Unexpected error in blacklist check — DENYING access", exc_info=True)
        return True


async def _is_token_revoked(jti: str | None) -> bool:
    """Check if a specific token (by JTI) has been revoked.

    Used for per-token revocation (refresh token rotation, forced logout of specific sessions).
    SECURITY: Fails CLOSED — if Redis is down, deny access.
    """
    if not jti:
        logger.warning("Token without JTI rejected — possible legacy or forged token")
        return True  # Reject tokens without JTI — all current token creation includes JTI
    try:
        r = get_redis()
        result = await r.get(f"token:revoked:{jti}")
        return result is not None
    except aioredis.ConnectionError:
        logger.error("Redis unavailable for JTI revocation check — DENYING access (fail-closed)")
        return True
    except Exception:
        logger.error("Unexpected error in JTI revocation check — DENYING access", exc_info=True)
        return True


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

    # Check if this specific token was revoked (per-token revocation via JTI)
    if await _is_token_revoked(payload.get("jti")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=err.TOKEN_REVOKED,
        )

    # Check if user was logged out (token blacklisted)
    if await _is_user_blacklisted(user_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=err.TOKEN_REVOKED,
        )

    # S4-01: Check role_version freshness — reject tokens with stale role
    token_rv = payload.get("rv", 0)
    current_rv = await get_role_version(user_id)
    if token_rv < current_rv:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=err.ROLE_VERSION_STALE,
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
    """Raise 403 if user is not admin/rop and not the wiki owner.

    NOTE: This is the legacy *read* gate — it does NOT enforce that a
    ROP belongs to the same team as the manager whose wiki they are
    accessing. For mutating operations (PUT, POST ingest, …) callers
    MUST additionally use :func:`check_wiki_team_access`, which loads
    the target manager's ``team_id`` from the DB and rejects cross-team
    writes by ROPs.
    """
    if user.role.value in ("admin", "rop"):
        return
    if str(user.id) == str(manager_id):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Cannot access other managers' wikis",
    )


async def check_wiki_team_access(user: User, manager_id, db) -> None:
    """Stricter ownership gate for mutating wiki ops (PR-X foundation #3).

    Closes the cross-team write hole in :func:`check_wiki_access`:
    that helper lets *any* ``rop`` edit *any* manager's wiki regardless
    of team membership, which is fine on a 15-tester pilot but a real
    multi-tenant bug as soon as we onboard a second company. This
    helper keeps admin-as-superuser semantics, requires the same team
    for ROPs, and lets a manager edit their own wiki only.

    Rules:
      * ``admin``         → always allowed (cross-team is the job).
      * ``rop``           → only when ``rop.team_id == manager.team_id``
                            (and both are non-NULL — a ROP without a
                            team has no scope and cannot write).
      * ``manager``       → only their own ``user_id == manager_id``.
      * other roles       → 403.

    Performs one extra ``SELECT users.team_id`` per mutating call.
    Cached lookups are not worth the staleness risk on an authz check.
    """
    role = user.role.value

    if role == "admin":
        return

    if role == "manager":
        if str(user.id) == str(manager_id):
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Managers can only edit their own wiki",
        )

    if role == "rop":
        # ROP without a team has no scope — refuse rather than fall
        # through to the legacy "any rop can edit anything" path.
        if user.team_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="ROP is not assigned to a team",
            )
        target_team = (
            await db.execute(select(User.team_id).where(User.id == manager_id))
        ).scalar_one_or_none()
        if target_team is None or str(target_team) != str(user.team_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot modify a wiki outside your team",
            )
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=err.INSUFFICIENT_PERMISSIONS,
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


def _plan_limit_payload(
    feature: str,
    *,
    plan: str,
    limit: int,
    used: int,
    friendly_ru: str,
) -> dict:
    """Uniform 429 body so the frontend PlanLimitModal can render a proper
    upsell dialog instead of a generic toast.

    Phase C (2026-04-20): owner feedback — юзер, упирающийся в лимит, не
    должен видеть «Daily limit reached», он должен видеть «Scout: 3/3.
    Обновись до Ranger — 10/день». Structured keys:

      feature     — `sessions | pvp | rag` (for analytics + icon choice)
      plan        — текущий plan (`scout | ranger | hunter | master`)
      limit       — численный порог текущего plan
      used        — сколько уже израсходовано
      message     — человек-фраза на ру (legacy `detail` alias)
    """
    return {
        "detail": f"{friendly_ru} (лимит {limit}, план {plan}).",
        "feature": feature,
        "plan": plan,
        "limit": limit,
        "used": used,
        "message": friendly_ru,
    }


async def check_session_limit(user: User, db) -> None:
    """Check if user hasn't exceeded daily session limit. Raises 429 if exceeded."""
    from app.services.entitlement import get_entitlement, check_session_limit as _check
    ent = await get_entitlement(user.id, db)
    if not _check(ent):
        raise HTTPException(
            status_code=429,
            detail=_plan_limit_payload(
                "sessions",
                plan=ent.plan.value,
                limit=ent.limits.sessions_per_day,
                used=ent.sessions_used_today,
                friendly_ru="Дневной лимит тренировок достигнут",
            ),
        )


async def check_pvp_limit(user: User, db) -> None:
    """Check PvP match limit by plan. Raises 429 if exceeded."""
    from app.services.entitlement import get_entitlement, check_pvp_limit as _check
    ent = await get_entitlement(user.id, db)
    if not _check(ent):
        raise HTTPException(
            status_code=429,
            detail=_plan_limit_payload(
                "pvp",
                plan=ent.plan.value,
                limit=ent.limits.pvp_matches_per_day,
                used=ent.pvp_used_today,
                friendly_ru="Дневной лимит PvP матчей достигнут",
            ),
        )


async def check_rag_limit(user: User, db) -> None:
    """Check RAG query limit by plan. Raises 429 if exceeded."""
    from app.services.entitlement import get_entitlement, check_rag_limit as _check
    ent = await get_entitlement(user.id, db)
    if not _check(ent):
        raise HTTPException(
            status_code=429,
            detail=_plan_limit_payload(
                "rag",
                plan=ent.plan.value,
                limit=ent.limits.rag_queries_per_day,
                used=ent.rag_used_today,
                friendly_ru="Дневной лимит RAG-запросов достигнут",
            ),
        )
