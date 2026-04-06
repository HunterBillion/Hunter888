"""JWT token creation/verification and password hashing.

Uses PyJWT (``jwt``) — the actively maintained JWT library.
Migrated from python-jose which is in maintenance mode since 2024.
"""

import uuid as _uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings

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


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    to_encode.update({
        "exp": expire,
        "type": "access",
        "jti": _uuid.uuid4().hex,  # Unique token ID for per-token revocation
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
