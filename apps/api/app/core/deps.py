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

    # Check if user was logged out (token blacklisted)
    if await _is_user_blacklisted(user_id):
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
