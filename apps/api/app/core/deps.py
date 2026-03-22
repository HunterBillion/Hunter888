import logging
import uuid

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import decode_token
from app.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)
security = HTTPBearer()


_blacklist_pool: aioredis.ConnectionPool | None = None


def _get_blacklist_redis() -> aioredis.Redis:
    """Get a Redis client using a shared connection pool for blacklist checks.

    FIX: Previously created a new connection per request, causing connection leaks
    under load (~1000 users/day = thousands of leaked connections).
    """
    global _blacklist_pool
    if _blacklist_pool is None:
        _blacklist_pool = aioredis.ConnectionPool.from_url(
            settings.redis_url, decode_responses=True, max_connections=10
        )
    return aioredis.Redis(connection_pool=_blacklist_pool)


async def _is_user_blacklisted(user_id: str) -> bool:
    """Check if user's tokens were invalidated via logout.

    SECURITY: Fails CLOSED — if Redis is down, deny access.
    This prevents logged-out users from using revoked tokens.
    """
    try:
        redis = _get_blacklist_redis()
        result = await redis.get(f"blacklist:user:{user_id}")
        return result is not None
    except aioredis.ConnectionError:
        logger.error("Redis unavailable for blacklist check — DENYING access (fail-closed)")
        return True
    except Exception:
        logger.error("Unexpected error in blacklist check — DENYING access")
        return True


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_token(credentials.credentials)
    if payload is None or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # Check if user was logged out (token blacklisted)
    if await _is_user_blacklisted(user_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return user


def require_role(*roles: str):
    """FastAPI dependency factory: returns a dependency that checks user role.

    Usage: Depends(require_role("admin", "rop"))
    """

    async def checker(user: User = Depends(get_current_user)) -> User:
        if user.role.value not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return checker
