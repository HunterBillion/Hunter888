"""Auth refresh concurrency grace window (A10 fix, v2 race-safe).

A10 v1 had a race: when N requests landed in the same Redis tick, the
SETNX winner had not yet written the reissued cache when losers checked
it, so all N-1 losers fell through to user-blacklist. v2 reserves the
cache slot with a "PENDING" sentinel BEFORE the slow DB lookup, and
losers poll the cache for up to ~2s waiting for the winner to publish
the real pair.

These tests exercise:
  * winner reserves PENDING then overwrites with real pair
  * lock-stepped two-tab concurrent refresh both get same pair
  * GENUINELY parallel asyncio.gather race (the v1 regression scenario)
  * post-grace replay still blacklists user
  * corrupted cache treated as replay, not silently accepted

Calls the handler function directly so the test does not need the full
SQLAlchemy schema (project models use Postgres-specific JSONB which the
in-memory SQLite test harness cannot create).
"""

import asyncio
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
    """Redis stand-in that mimics SETNX / GET / SETEX semantics. Tests
    drive grace-window expiry by popping the reissued key manually.
    asyncio-safe: the underlying dict is single-thread + each await is a
    cooperative yield point, which matches single-worker uvicorn under
    asyncio.gather."""

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
async def test_first_refresh_writes_real_pair_after_pending():
    fr = _FakeRedis()
    user_id = str(uuid.uuid4())
    token = create_refresh_token({"sub": user_id})

    response = await _call_refresh(token, fr)
    payload = json.loads(response.body)
    assert payload["access_token"]
    assert payload["refresh_token"]

    jti = _jti(token)
    # Final cache content is the JSON-serialized pair, not the PENDING sentinel.
    cached = fr.store[f"token:reissued:{jti}"]
    assert cached != "PENDING"
    assert json.loads(cached)["access_token"] == payload["access_token"]
    # And the old jti is revoked for the full refresh TTL.
    assert f"token:revoked:{jti}" in fr.store


@pytest.mark.asyncio
async def test_lockstep_concurrent_refresh_returns_same_pair():
    """Sequential two-tab race: second call after winner publishes."""
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
async def test_genuinely_parallel_refresh_burst_no_blacklist():
    """A10 v1 regression: 5 truly parallel refreshes (asyncio.gather) where
    losers used to race past an empty cache before the winner finished
    its DB lookup. Now they see PENDING and poll. All 5 must succeed
    and the user must NOT be blacklisted."""
    fr = _FakeRedis()
    user_id = str(uuid.uuid4())
    token = create_refresh_token({"sub": user_id})

    results = await asyncio.gather(
        *[_call_refresh(token, fr) for _ in range(5)],
        return_exceptions=True,
    )

    for r in results:
        assert not isinstance(r, Exception), f"unexpected exception: {r!r}"

    pairs = [json.loads(r.body) for r in results]
    # Exactly one access_token value across all 5 (the winner's pair,
    # served by all losers from the cache).
    distinct_access = {p["access_token"] for p in pairs}
    assert len(distinct_access) == 1, (
        "concurrent losers should converge on the winner's pair, "
        f"saw {len(distinct_access)} distinct: {distinct_access}"
    )
    assert f"blacklist:user:{user_id}" not in fr.store, (
        "user must not be blacklisted after a legitimate concurrent burst"
    )


@pytest.mark.asyncio
async def test_replay_after_grace_expiry_blacklists_user():
    """After the reissued cache expires, reusing the same refresh is a true replay."""
    fr = _FakeRedis()
    user_id = str(uuid.uuid4())
    token = create_refresh_token({"sub": user_id})

    await _call_refresh(token, fr)
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


@pytest.mark.asyncio
async def test_loser_polls_pending_until_winner_publishes():
    """If the loser hits the cache while it still holds PENDING, the poll
    loop must wait for the winner to publish, then return the same pair —
    not blacklist the user."""
    fr = _FakeRedis()
    user_id = str(uuid.uuid4())
    token = create_refresh_token({"sub": user_id})
    jti = _jti(token)

    # Pre-populate as if a winner is in flight: revoked + PENDING reissued.
    fr.store[f"token:revoked:{jti}"] = "1"
    fr.store[f"token:reissued:{jti}"] = "PENDING"

    # Schedule a "winner" that publishes the real pair after 200ms.
    real_payload = json.dumps({
        "access_token": "AT.real",
        "refresh_token": "RT.real",
        "token_type": "bearer",
        "must_change_password": False,
        "needs_onboarding": False,
    })

    async def winner_publishes():
        await asyncio.sleep(0.2)
        fr.store[f"token:reissued:{jti}"] = real_payload

    publisher = asyncio.create_task(winner_publishes())
    response = await _call_refresh(token, fr)
    await publisher

    pair = json.loads(response.body)
    assert pair["access_token"] == "AT.real"
    assert f"blacklist:user:{user_id}" not in fr.store
