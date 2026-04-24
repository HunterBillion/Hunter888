"""Auth refresh concurrency grace window (A10 fix).

Replay-detector previously blacklisted the entire user when two concurrent
/auth/refresh requests raced the same refresh_token (legitimate scenario:
multi-tab, mobile burst, service worker prefetch). The grace window lets
losers of SETNX read the winner's cached reissued pair and return it,
instead of triggering user-level blacklist.

Outside the grace window, SETNX loss remains a true replay and still
blacklists the user.

Calls the handler function directly so the test does not need the full
SQLAlchemy schema (project models use Postgres-specific JSONB which the
in-memory SQLite test harness cannot create).
"""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from fastapi import HTTPException

from app.api.auth import refresh
from app.core.security import create_refresh_token
from app.schemas.auth import RefreshRequest


class _FakeRedis:
    """Redis stand-in that mimics the SETNX / GET / SETEX semantics used by
    the refresh handler. Tests drive grace-window expiry by popping the
    reissued key manually.
    """

    def __init__(self):
        self.store: dict[str, str] = {}

    async def get(self, key):
        val = self.store.get(key)
        return val.encode() if isinstance(val, str) else val

    async def set(self, key, value, *, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value if isinstance(value, str) else str(value)
        return True

    async def setex(self, key, _ttl, value):
        self.store[key] = value if isinstance(value, str) else str(value)
        return True

    async def delete(self, key):
        self.store.pop(key, None)
        return 1

    async def incr(self, key):
        new = int(self.store.get(key, 0)) + 1
        self.store[key] = str(new)
        return new


def _jti(token: str) -> str:
    return jwt.decode(token, options={"verify_signature": False})["jti"]


def _fake_db_returning_no_user():
    """The refresh handler falls back to role='manager' when no user row
    is found; we use this to skip a real DB roundtrip in the test."""
    db = AsyncMock()
    exec_result = AsyncMock()
    exec_result.scalar_one_or_none = lambda: None
    db.execute = AsyncMock(return_value=exec_result)
    return db


async def _call_refresh(token: str, fake_redis: _FakeRedis):
    request = SimpleNamespace(cookies={})
    body = RefreshRequest(refresh_token=token)
    db = _fake_db_returning_no_user()
    with (
        patch("app.api.auth.get_redis", return_value=fake_redis),
        patch("app.core.deps.get_redis", return_value=fake_redis),
        patch("app.core.security.get_redis", return_value=fake_redis),
    ):
        return await refresh(request, body, db)


@pytest.mark.asyncio
async def test_first_refresh_caches_reissued_pair():
    fr = _FakeRedis()
    user_id = str(uuid.uuid4())
    token = create_refresh_token({"sub": user_id})

    response = await _call_refresh(token, fr)
    payload = json.loads(response.body)
    assert payload["access_token"]
    assert payload["refresh_token"]

    jti = _jti(token)
    # Winner wrote the reissued key so a concurrent loser can return the same pair.
    assert f"token:reissued:{jti}" in fr.store
    # And the old jti is revoked for the full refresh TTL.
    assert f"token:revoked:{jti}" in fr.store


@pytest.mark.asyncio
async def test_concurrent_refresh_within_grace_returns_same_pair():
    """Two tabs racing the same refresh_token inside the grace window get
    the same reissued pair and the user is NOT blacklisted."""
    fr = _FakeRedis()
    user_id = str(uuid.uuid4())
    token = create_refresh_token({"sub": user_id})

    r1 = await _call_refresh(token, fr)
    r2 = await _call_refresh(token, fr)

    pair1 = json.loads(r1.body)
    pair2 = json.loads(r2.body)
    assert pair2["access_token"] == pair1["access_token"]
    assert pair2["refresh_token"] == pair1["refresh_token"]
    assert f"blacklist:user:{user_id}" not in fr.store


@pytest.mark.asyncio
async def test_replay_after_grace_expiry_blacklists_user():
    """After the reissued cache expires, reusing the same refresh is a true replay."""
    fr = _FakeRedis()
    user_id = str(uuid.uuid4())
    token = create_refresh_token({"sub": user_id})

    await _call_refresh(token, fr)
    # Simulate grace-window expiry: reissued entry is gone; revoked key survives.
    fr.store.pop(f"token:reissued:{_jti(token)}", None)

    with pytest.raises(HTTPException) as exc:
        await _call_refresh(token, fr)
    assert exc.value.status_code == 401
    assert f"blacklist:user:{user_id}" in fr.store


@pytest.mark.asyncio
async def test_corrupted_cache_falls_through_to_replay():
    """Garbage in the cache (crash mid-write, schema change) is treated as replay,
    not silently accepted."""
    fr = _FakeRedis()
    user_id = str(uuid.uuid4())
    token = create_refresh_token({"sub": user_id})

    await _call_refresh(token, fr)
    fr.store[f"token:reissued:{_jti(token)}"] = "not-json{{"

    with pytest.raises(HTTPException) as exc:
        await _call_refresh(token, fr)
    assert exc.value.status_code == 401
    assert f"blacklist:user:{user_id}" in fr.store
