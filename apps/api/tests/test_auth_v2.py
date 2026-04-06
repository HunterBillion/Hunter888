"""Extended tests for auth and security (core/security.py, core/deps.py, api/auth.py).

Covers:
  - Password hashing and verification
  - JWT access/refresh token lifecycle
  - Token expiry and invalidity
  - get_current_user dependency logic
  - require_role decorator
  - Token blacklisting (logout)
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Password hashing
# ═══════════════════════════════════════════════════════════════════════════════


class TestPasswordHashing:
    def test_hash_differs_from_plain(self):
        hashed = hash_password("my_password")
        assert hashed != "my_password"

    def test_verify_correct_password(self):
        hashed = hash_password("my_password")
        assert verify_password("my_password", hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("my_password")
        assert verify_password("wrong_password", hashed) is False

    def test_different_hashes_same_password(self):
        """bcrypt uses random salt, so hashes should differ."""
        h1 = hash_password("same_password")
        h2 = hash_password("same_password")
        assert h1 != h2
        # But both should verify
        assert verify_password("same_password", h1)
        assert verify_password("same_password", h2)

    def test_unicode_password(self):
        hashed = hash_password("пароль_123_банкротство")
        assert verify_password("пароль_123_банкротство", hashed)
        assert not verify_password("пароль_123_банкротств", hashed)

    def test_empty_password(self):
        hashed = hash_password("")
        assert verify_password("", hashed)
        assert not verify_password("not_empty", hashed)

    def test_long_password(self):
        """bcrypt truncates at 72 bytes — test behavior."""
        long_pw = "a" * 100
        hashed = hash_password(long_pw)
        assert verify_password(long_pw, hashed)


# ═══════════════════════════════════════════════════════════════════════════════
# JWT tokens
# ═══════════════════════════════════════════════════════════════════════════════


class TestJWTTokens:
    def test_access_token_roundtrip(self):
        user_id = str(uuid.uuid4())
        token = create_access_token({"sub": user_id})
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == user_id
        assert payload["type"] == "access"

    def test_refresh_token_roundtrip(self):
        user_id = str(uuid.uuid4())
        token = create_refresh_token({"sub": user_id})
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == user_id
        assert payload["type"] == "refresh"

    def test_invalid_token_returns_none(self):
        assert decode_token("invalid.token.here") is None

    def test_empty_token_returns_none(self):
        assert decode_token("") is None

    def test_tampered_token_returns_none(self):
        token = create_access_token({"sub": "user1"})
        tampered = token[:-5] + "XXXXX"
        assert decode_token(tampered) is None

    def test_token_has_expiry(self):
        token = create_access_token({"sub": "user1"})
        payload = decode_token(token)
        assert "exp" in payload
        # Expiry should be in the future
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        assert exp > datetime.now(timezone.utc)

    def test_extra_data_in_token(self):
        token = create_access_token({"sub": "user1", "role": "admin", "team": "alpha"})
        payload = decode_token(token)
        assert payload["role"] == "admin"
        assert payload["team"] == "alpha"


# ═══════════════════════════════════════════════════════════════════════════════
# get_current_user dependency
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetCurrentUser:

    @pytest.mark.asyncio
    async def test_no_token_raises_401(self):
        from fastapi import HTTPException
        from app.core.deps import get_current_user

        mock_request = MagicMock()
        mock_db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                request=mock_request,
                credentials=None,
                db=mock_db,
                access_token=None,
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_raises_401(self):
        from fastapi import HTTPException
        from app.core.deps import get_current_user

        mock_creds = MagicMock()
        mock_creds.credentials = "invalid.token"
        mock_request = MagicMock()
        mock_db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                request=mock_request,
                credentials=mock_creds,
                db=mock_db,
                access_token=None,
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_token_rejected_for_access(self):
        """A refresh token should not work as an access token."""
        from fastapi import HTTPException
        from app.core.deps import get_current_user

        token = create_refresh_token({"sub": str(uuid.uuid4())})
        mock_creds = MagicMock()
        mock_creds.credentials = token
        mock_request = MagicMock()
        mock_db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                request=mock_request,
                credentials=mock_creds,
                db=mock_db,
                access_token=None,
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_blacklisted_user_rejected(self):
        """If user is in blacklist (logged out), reject token."""
        from fastapi import HTTPException
        from app.core.deps import get_current_user

        user_id = str(uuid.uuid4())
        token = create_access_token({"sub": user_id})
        mock_creds = MagicMock()
        mock_creds.credentials = token
        mock_request = MagicMock()
        mock_db = AsyncMock()

        with patch("app.core.deps._is_user_blacklisted", new_callable=AsyncMock, return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(
                    request=mock_request,
                    credentials=mock_creds,
                    db=mock_db,
                    access_token=None,
                )
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_token_returns_user(self):
        from app.core.deps import get_current_user
        from app.models.user import UserRole

        user_id = uuid.uuid4()
        token = create_access_token({"sub": str(user_id)})
        mock_creds = MagicMock()
        mock_creds.credentials = token
        mock_request = MagicMock()

        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.is_active = True
        mock_user.role = UserRole.manager

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.core.deps._is_user_blacklisted", new_callable=AsyncMock, return_value=False):
            user = await get_current_user(
                request=mock_request,
                credentials=mock_creds,
                db=mock_db,
                access_token=None,
            )
        assert user.id == user_id

    @pytest.mark.asyncio
    async def test_cookie_token_accepted(self):
        """Token from httpOnly cookie should also work."""
        from app.core.deps import get_current_user
        from app.models.user import UserRole

        user_id = uuid.uuid4()
        token = create_access_token({"sub": str(user_id)})
        mock_request = MagicMock()

        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.is_active = True
        mock_user.role = UserRole.manager

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.core.deps._is_user_blacklisted", new_callable=AsyncMock, return_value=False):
            user = await get_current_user(
                request=mock_request,
                credentials=None,  # No Bearer header
                db=mock_db,
                access_token=token,  # Cookie instead
            )
        assert user.id == user_id


# ═══════════════════════════════════════════════════════════════════════════════
# require_role
# ═══════════════════════════════════════════════════════════════════════════════


class TestRequireRole:

    @pytest.mark.asyncio
    async def test_matching_role_passes(self):
        from app.core.deps import require_role
        from app.models.user import UserRole

        mock_user = MagicMock()
        mock_user.role = UserRole.admin

        checker = require_role("admin", "rop")
        # Inject mock user
        result = await checker(user=mock_user)
        assert result is mock_user

    @pytest.mark.asyncio
    async def test_wrong_role_raises_403(self):
        from fastapi import HTTPException
        from app.core.deps import require_role
        from app.models.user import UserRole

        mock_user = MagicMock()
        mock_user.role = UserRole.manager

        checker = require_role("admin", "rop")
        with pytest.raises(HTTPException) as exc_info:
            await checker(user=mock_user)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_manager_cannot_access_admin(self):
        from fastapi import HTTPException
        from app.core.deps import require_role
        from app.models.user import UserRole

        mock_user = MagicMock()
        mock_user.role = UserRole.manager

        checker = require_role("admin")
        with pytest.raises(HTTPException):
            await checker(user=mock_user)
