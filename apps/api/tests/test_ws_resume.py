"""Smoke tests for Block E: WS Session Resume + Token Refresh.

Tests are unit-level — they verify handler logic in isolation
without requiring a running server, database, or Redis.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
)


# ── Token creation / refresh tests ──────────────────────────────────────────


def test_refresh_token_creation():
    """Refresh token should have type=refresh and valid sub."""
    user_id = str(uuid.uuid4())
    token = create_refresh_token({"sub": user_id})
    payload = decode_token(token)
    assert payload is not None
    assert payload["sub"] == user_id
    assert payload["type"] == "refresh"


def test_access_token_from_refresh_sub():
    """New access token created from refresh sub should be valid."""
    user_id = str(uuid.uuid4())
    new_access = create_access_token({"sub": user_id})
    payload = decode_token(new_access)
    assert payload is not None
    assert payload["sub"] == user_id
    assert payload["type"] == "access"


# ── Session resume handler tests (mocked) ──────────────────────────────────


@pytest.mark.asyncio
async def test_handle_session_resume_missing_session_id():
    """session.resume with no session_id should send error."""
    from app.ws.training import _handle_session_resume

    ws = AsyncMock()
    state = {"user_id": uuid.uuid4()}
    ws_id = str(uuid.uuid4())

    await _handle_session_resume(ws, {}, state, ws_id)

    ws.send_json.assert_called_once()
    call_data = ws.send_json.call_args[0][0]
    assert call_data["type"] == "error"
    assert call_data["data"]["code"] == "missing_session_id"


@pytest.mark.asyncio
async def test_handle_session_resume_invalid_session_id():
    """session.resume with invalid UUID should send error."""
    from app.ws.training import _handle_session_resume

    ws = AsyncMock()
    state = {"user_id": uuid.uuid4()}
    ws_id = str(uuid.uuid4())

    await _handle_session_resume(ws, {"session_id": "not-a-uuid"}, state, ws_id)

    ws.send_json.assert_called_once()
    call_data = ws.send_json.call_args[0][0]
    assert call_data["type"] == "error"
    assert call_data["data"]["code"] == "invalid_session_id"


# ── Auth refresh handler tests (mocked) ─────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_auth_refresh_no_token():
    """auth.refresh with no refresh_token should send error."""
    from app.ws.training import _handle_auth_refresh

    ws = AsyncMock()
    state = {"user_id": uuid.uuid4()}

    await _handle_auth_refresh(ws, {}, state)

    ws.send_json.assert_called_once()
    call_data = ws.send_json.call_args[0][0]
    assert call_data["type"] == "auth.refresh_error"
    assert call_data["data"]["reason"] == "no_token"


@pytest.mark.asyncio
async def test_handle_auth_refresh_valid_token():
    """auth.refresh with valid refresh token should return new tokens."""
    from app.ws.training import _handle_auth_refresh

    user_id = uuid.uuid4()
    refresh_token = create_refresh_token({"sub": str(user_id)})

    ws = AsyncMock()
    state = {"user_id": user_id}

    await _handle_auth_refresh(ws, {"refresh_token": refresh_token}, state)

    ws.send_json.assert_called_once()
    call_data = ws.send_json.call_args[0][0]
    assert call_data["type"] == "auth.refreshed"
    assert "access_token" in call_data["data"]
    assert "refresh_token" in call_data["data"]

    # Verify new tokens are valid
    new_access = decode_token(call_data["data"]["access_token"])
    assert new_access is not None
    assert new_access["sub"] == str(user_id)
    assert new_access["type"] == "access"


@pytest.mark.asyncio
async def test_handle_auth_refresh_wrong_user():
    """auth.refresh with token for different user should fail."""
    from app.ws.training import _handle_auth_refresh

    other_user = uuid.uuid4()
    refresh_token = create_refresh_token({"sub": str(other_user)})

    ws = AsyncMock()
    state = {"user_id": uuid.uuid4()}  # Different user

    await _handle_auth_refresh(ws, {"refresh_token": refresh_token}, state)

    ws.send_json.assert_called_once()
    call_data = ws.send_json.call_args[0][0]
    assert call_data["type"] == "auth.refresh_error"
    assert call_data["data"]["reason"] == "user_mismatch"


@pytest.mark.asyncio
async def test_handle_auth_refresh_invalid_token():
    """auth.refresh with garbage token should fail gracefully."""
    from app.ws.training import _handle_auth_refresh

    ws = AsyncMock()
    state = {"user_id": uuid.uuid4()}

    await _handle_auth_refresh(ws, {"refresh_token": "garbage.token.here"}, state)

    ws.send_json.assert_called_once()
    call_data = ws.send_json.call_args[0][0]
    assert call_data["type"] == "auth.refresh_error"
    assert call_data["data"]["reason"] == "invalid_token"


# ── Session lock tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_acquire_session_lock():
    """Lock acquire should call Redis SET with NX."""
    from app.ws.training import _acquire_session_lock

    session_id = uuid.uuid4()
    ws_id = str(uuid.uuid4())

    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)

    with patch("app.ws.training.get_redis", return_value=mock_redis):
        result = await _acquire_session_lock(session_id, ws_id)

    assert result is True
    mock_redis.set.assert_called_once()
    call_args = mock_redis.set.call_args
    assert call_args[1].get("nx") is True


@pytest.mark.asyncio
async def test_acquire_session_lock_already_taken():
    """Lock should fail if already held by another connection."""
    from app.ws.training import _acquire_session_lock

    session_id = uuid.uuid4()
    ws_id = str(uuid.uuid4())

    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=None)  # NX fails

    with patch("app.ws.training.get_redis", return_value=mock_redis):
        result = await _acquire_session_lock(session_id, ws_id)

    assert result is False


@pytest.mark.asyncio
async def test_release_session_lock_owner():
    """Lock release should delete key only if we own it."""
    from app.ws.training import _release_session_lock

    session_id = uuid.uuid4()
    ws_id = str(uuid.uuid4())

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=ws_id)  # We own it
    mock_redis.delete = AsyncMock()

    with patch("app.ws.training.get_redis", return_value=mock_redis):
        await _release_session_lock(session_id, ws_id)

    mock_redis.delete.assert_called_once()


@pytest.mark.asyncio
async def test_release_session_lock_not_owner():
    """Lock release should NOT delete if someone else owns it."""
    from app.ws.training import _release_session_lock

    session_id = uuid.uuid4()
    ws_id = str(uuid.uuid4())
    other_ws_id = str(uuid.uuid4())

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=other_ws_id)  # Someone else owns it
    mock_redis.delete = AsyncMock()

    with patch("app.ws.training.get_redis", return_value=mock_redis):
        await _release_session_lock(session_id, ws_id)

    mock_redis.delete.assert_not_called()


# ── Session manager: TTL refresh test ───────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_session_ttl():
    """refresh_session_ttl should call EXPIRE on all session keys."""
    from app.services.session_manager import refresh_session_ttl

    session_id = uuid.uuid4()

    mock_pipe = AsyncMock()
    mock_pipe.expire = MagicMock()
    mock_pipe.execute = AsyncMock()

    mock_redis = MagicMock()
    mock_redis.pipeline = MagicMock(return_value=mock_pipe)

    with patch("app.services.session_manager._redis", return_value=mock_redis):
        await refresh_session_ttl(session_id)

    # Should have called expire for multiple keys
    assert mock_pipe.expire.call_count >= 5
