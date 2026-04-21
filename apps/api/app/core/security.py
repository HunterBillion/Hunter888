"""JWT token creation/verification and password hashing.

Uses PyJWT (``jwt``) — the actively maintained JWT library.
Migrated from python-jose which is in maintenance mode since 2024.

S4-01: Role freshness — access token TTL reduced to 5 min,
role_version claim checked against Redis on every request.
"""

import logging
import uuid as _uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
import redis.asyncio as aioredis

from app.config import settings
from app.core.redis_pool import get_redis

_logger = logging.getLogger(__name__)

# Hardcoded algorithm whitelist — NEVER allow "none" or RS* from env vars
_JWT_ALLOWED_ALGORITHMS = frozenset({"HS256", "HS384", "HS512"})


def _safe_algorithm() -> str:
    """Return JWT algorithm only if it's in the whitelist."""
    alg = settings.jwt_algorithm
    if alg not in _JWT_ALLOWED_ALGORITHMS:
        raise ValueError(f"JWT algorithm '{alg}' not in whitelist {_JWT_ALLOWED_ALGORITHMS}")
    return alg


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


async def get_role_version(user_id: str) -> int:
    """Get current role_version for a user from Redis. Returns 0 if not set.

    T3 fix (2026-04-17): added SETNX warm-up for the missing-key case.
    Previously, a fresh register + burst of parallel requests would race on
    the missing Redis key, causing ~20% spurious 401s. The warm-up SETs the
    key to 0 atomically on first read, so subsequent reads see the cache
    populated.

    Fail-closed preserved: if Redis is unreachable (exception), we return a
    very high version number so that any token's rv claim is lower than it
    and access is denied. This matches the blacklist/JTI revocation design.
    """
    try:
        r = get_redis()
        val = await r.get(f"role_version:{user_id}")
        if val is not None:
            return int(val)
        # Warm-up on missing key: set to 0 so burst reads after token
        # issuance see the cache populated immediately, preventing the race.
        try:
            await r.set(
                f"role_version:{user_id}",
                0,
                nx=True,
                ex=settings.jwt_refresh_token_expire_days * 86400,
            )
        except aioredis.RedisError:
            pass  # warm-up is best-effort; fall through with rv=0
        return 0
    except (aioredis.RedisError, Exception):
        _logger.critical(
            "Redis unavailable during role_version check for user %s — "
            "failing closed (denying access)",
            user_id,
        )
        return 999999


async def bump_role_version(user_id: str) -> int:
    """Increment role_version when a user's role changes.

    S4-01: Any access token with an older role_version will be rejected
    by the middleware, forcing the client to refresh and get a new token
    with the updated role.
    """
    try:
        r = get_redis()
        new_ver = await r.incr(f"role_version:{user_id}")
        # Keep version key alive for the duration of refresh token lifetime
        await r.expire(f"role_version:{user_id}", settings.jwt_refresh_token_expire_days * 86400)
        _logger.info("role_version bumped for user %s → v%d", user_id, new_ver)
        return int(new_ver)
    except aioredis.RedisError as exc:
        _logger.error("Failed to bump role_version for %s: %s", user_id, exc)
        return 0


def create_access_token(data: dict, *, role_version: int = 0) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    to_encode.update({
        "exp": expire,
        "type": "access",
        "jti": _uuid.uuid4().hex,  # Unique token ID for per-token revocation
        "rv": role_version,  # S4-01: role version for freshness check
    })
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=_safe_algorithm())


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days)
    to_encode.update({
        "exp": expire,
        "type": "refresh",
        "jti": _uuid.uuid4().hex,  # Unique token ID for rotation/revocation
    })
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=_safe_algorithm())


def decode_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret,
            algorithms=list(_JWT_ALLOWED_ALGORITHMS),  # Whitelist only
        )
        return payload
    except (jwt.InvalidTokenError, jwt.ExpiredSignatureError, jwt.DecodeError):
        return None
