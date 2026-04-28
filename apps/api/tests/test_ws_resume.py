"""Smoke tests for Block E: WS Session Resume + Token Refresh.

Tests are unit-level — they verify handler logic in isolation
without requiring a running server, database, or Redis.

Mocking notes (post-refactor):
* ``_send`` reads ``ws.state._outgoing_count`` and compares it to an int;
  AsyncMock auto-creates the attribute as a MagicMock so the comparison
  short-circuits the queue-overflow guard. Tests build ``ws`` via
  :func:`_make_ws` which sets the counter to a concrete ``0``.
* ``_release_session_lock`` was moved to a Lua ``eval`` for atomic
  check-and-delete (TOCTOU fix); the tests assert ``r.eval`` is called
  and pass the right ARGV[1] (ws_id).
* ``_handle_session_resume`` runs a blacklist check via
  ``app.core.deps._is_user_blacklisted`` before parsing the UUID; the
  short-circuit tests patch it so the early-return branch is reachable.
* ``_handle_auth_refresh`` valid-token path needs both the DB lookup
  for the role and the ``get_role_version`` Redis call mocked.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
)


def _make_ws() -> AsyncMock:
    """Build a WebSocket mock that survives the ``_send`` overflow guard."""
    ws = AsyncMock()
    ws.state = SimpleNamespace(_outgoing_count=0)
    return ws


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
    """session.resume with no session_id should send error before any I/O."""
    from app.ws.training import _handle_session_resume

    ws = _make_ws()
    state = {"user_id": uuid.uuid4()}
    ws_id = str(uuid.uuid4())

    await _handle_session_resume(ws, {}, state, ws_id)

    ws.send_json.assert_called_once()
    call_data = ws.send_json.call_args[0][0]
    assert call_data["type"] == "error"
    assert call_data["data"]["code"] == "missing_session_id"


@pytest.mark.asyncio
async def test_handle_session_resume_invalid_session_id():
    """session.resume with invalid UUID should short-circuit to error.

    The blacklist check runs before UUID parsing — patched to False so
    the test exercises the parse-failure branch.
    """
    from app.ws.training import _handle_session_resume

    ws = _make_ws()
    state = {"user_id": uuid.uuid4()}
    ws_id = str(uuid.uuid4())

    with patch("app.core.deps._is_user_blacklisted", AsyncMock(return_value=False)):
        await _handle_session_resume(
            ws, {"session_id": "not-a-uuid"}, state, ws_id,
        )

    ws.send_json.assert_called_once()
    call_data = ws.send_json.call_args[0][0]
    assert call_data["type"] == "error"
    assert call_data["data"]["code"] == "invalid_session_id"


# ── Auth refresh handler tests (mocked) ─────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_auth_refresh_no_token():
    """auth.refresh with no refresh_token should send error."""
    from app.ws.training import _handle_auth_refresh

    ws = _make_ws()
    state = {"user_id": uuid.uuid4()}

    await _handle_auth_refresh(ws, {}, state)

    ws.send_json.assert_called_once()
    call_data = ws.send_json.call_args[0][0]
    assert call_data["type"] == "auth.refresh_error"
    assert call_data["data"]["reason"] == "no_token"


@pytest.mark.asyncio
async def test_handle_auth_refresh_valid_token():
    """auth.refresh with valid refresh token should return new tokens.

    Mocks both the DB role lookup (``async_session``) and the
    ``get_role_version`` Redis call so the handler stays unit-level.
    """
    from app.ws.training import _handle_auth_refresh

    user_id = uuid.uuid4()
    refresh_token = create_refresh_token({"sub": str(user_id)})

    ws = _make_ws()
    state = {"user_id": user_id}

    # Mock the role lookup: scalar_one_or_none() returns "manager"
    role_result = MagicMock()
    role_result.scalar_one_or_none = MagicMock(return_value="manager")
    db_mock = AsyncMock()
    db_mock.execute = AsyncMock(return_value=role_result)

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=db_mock)
    session_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.ws.training.async_session", return_value=session_cm), \
         patch("app.core.security.get_role_version", AsyncMock(return_value=0)):
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

    ws = _make_ws()
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

    ws = _make_ws()
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

    with patch("app.core.redis_pool.get_redis", return_value=mock_redis):
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

    with patch("app.core.redis_pool.get_redis", return_value=mock_redis):
        result = await _acquire_session_lock(session_id, ws_id)

    assert result is False


@pytest.mark.asyncio
async def test_release_session_lock_uses_atomic_eval():
    """Release runs a Lua ``eval`` that compares ws_id atomically.

    The function takes the check-and-delete path via ``r.eval`` to avoid
    the TOCTOU race that existed when ``get`` and ``delete`` were issued
    separately.
    """
    from app.ws.training import _release_session_lock

    session_id = uuid.uuid4()
    ws_id = str(uuid.uuid4())

    mock_redis = AsyncMock()
    mock_redis.eval = AsyncMock(return_value=1)

    with patch("app.core.redis_pool.get_redis", return_value=mock_redis):
        await _release_session_lock(session_id, ws_id)

    mock_redis.eval.assert_called_once()
    call_args = mock_redis.eval.call_args
    # eval(script, numkeys, *keys_and_args) — ws_id is the first ARGV
    assert ws_id in call_args[0]


@pytest.mark.asyncio
async def test_release_session_lock_eval_returns_zero_when_not_owner():
    """If the Lua script returns 0 (not owner), the call still completes
    without raising — the script encodes the ownership check itself."""
    from app.ws.training import _release_session_lock

    session_id = uuid.uuid4()
    ws_id = str(uuid.uuid4())

    mock_redis = AsyncMock()
    mock_redis.eval = AsyncMock(return_value=0)  # someone else owns it

    with patch("app.core.redis_pool.get_redis", return_value=mock_redis):
        await _release_session_lock(session_id, ws_id)

    mock_redis.eval.assert_called_once()


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
