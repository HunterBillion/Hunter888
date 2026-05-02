"""TZ-8 P0 #2 — ``call_rag_cache.get_call_rag_block`` contract.

Five contracts the cache must hold so the call hot path is safe:

  1. **Cache miss** → calls ``retrieve_all_context`` once with the
     resolved ``team_id``, returns ``UnifiedRAGResult.to_prompt()``.
  2. **Cache hit within TTL** → no extra ``retrieve_all_context``
     call; the cached prompt is returned verbatim.
  3. **TTL expiry** → the next call re-fanouts and updates the
     cache.
  4. **Failure mode** → if the retriever raises, the helper returns
     ``""`` and **does not crash** the surrounding call. The cache
     is updated with an empty string so we don't thundering-herd
     retries on the same turn.
  5. **team_id resolved once per session** — even on cache misses,
     the ``SELECT users.team_id`` only runs the first time. A
     manager without a team is cached as a sentinel so we don't
     re-query on every miss.
"""
from __future__ import annotations

import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
async def manager_with_team(db_session):
    """Real User row + Team so ``_resolve_team_id`` round-trips
    against the in-memory SQLite."""
    from app.models.user import Team, User

    team = Team(name="P0#2 team")
    db_session.add(team)
    await db_session.commit()
    await db_session.refresh(team)

    user = User(
        email=f"call_{uuid.uuid4().hex[:8]}@example.test",
        hashed_password="x",
        full_name="Call User",
        team_id=team.id,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user, team


@pytest.fixture
async def manager_without_team(db_session):
    from app.models.user import User

    user = User(
        email=f"call_solo_{uuid.uuid4().hex[:8]}@example.test",
        hashed_password="x",
        full_name="Solo Caller",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# ── Cache miss: full fanout + caches result ─────────────────────────────


class TestCacheMiss:
    @pytest.mark.asyncio
    async def test_first_call_fans_out_and_caches(
        self, db_session, manager_with_team
    ):
        from app.services import call_rag_cache

        user, team = manager_with_team
        state: dict = {}

        fake_result = MagicMock()
        fake_result.to_prompt = MagicMock(return_value="<RAG BLOCK>")

        with patch(
            "app.services.rag_unified.retrieve_all_context",
            new=AsyncMock(return_value=fake_result),
        ) as fake_fanout:
            out = await call_rag_cache.get_call_rag_block(
                state=state,
                user_id=user.id,
                query="как обработать возражение",
                db=db_session,
            )

        assert out == "<RAG BLOCK>"
        # Fanout called once with the resolved team_id
        fake_fanout.assert_awaited_once()
        kwargs = fake_fanout.await_args.kwargs
        assert kwargs["team_id"] == team.id
        assert kwargs["user_id"] == user.id
        assert kwargs["context_type"] == "training"
        # Cache row populated
        cache = state["_call_rag_cache"]
        assert cache["prompt"] == "<RAG BLOCK>"
        assert cache["team_id_resolved"] == team.id
        assert "обработать возражение" in cache["query_sig"]


# ── Cache hit within TTL: zero new retrievals ───────────────────────────


class TestCacheHit:
    @pytest.mark.asyncio
    async def test_second_call_within_ttl_uses_cache(
        self, db_session, manager_with_team
    ):
        from app.services import call_rag_cache

        user, _ = manager_with_team
        state: dict = {}

        fake_result = MagicMock()
        fake_result.to_prompt = MagicMock(return_value="<FIRST>")

        with patch(
            "app.services.rag_unified.retrieve_all_context",
            new=AsyncMock(return_value=fake_result),
        ) as fake_fanout:
            await call_rag_cache.get_call_rag_block(
                state=state, user_id=user.id, query="первый", db=db_session,
            )

            # Second call same session, query changed but TTL not expired
            fake_result.to_prompt = MagicMock(return_value="<SHOULD-NOT-FIRE>")
            out2 = await call_rag_cache.get_call_rag_block(
                state=state, user_id=user.id, query="второй", db=db_session,
            )

        assert out2 == "<FIRST>"  # cached value, not the new mock
        # Only one fanout total — the second was a cache hit.
        assert fake_fanout.await_count == 1


# ── TTL expiry: next call refreshes ─────────────────────────────────────


class TestTtlExpiry:
    @pytest.mark.asyncio
    async def test_zero_ttl_bypasses_cache(
        self, db_session, manager_with_team
    ):
        """``ttl_seconds=0`` is the test-mode bypass — every call
        re-fanouts. Used to exercise the no-double-fire contract
        directly without sleeping."""
        from app.services import call_rag_cache

        user, _ = manager_with_team
        state: dict = {}

        fake = MagicMock()
        fake.to_prompt = MagicMock(side_effect=["<A>", "<B>"])

        with patch(
            "app.services.rag_unified.retrieve_all_context",
            new=AsyncMock(return_value=fake),
        ) as fake_fanout:
            a = await call_rag_cache.get_call_rag_block(
                state=state, user_id=user.id, query="q1",
                db=db_session, ttl_seconds=0.0,
            )
            b = await call_rag_cache.get_call_rag_block(
                state=state, user_id=user.id, query="q2",
                db=db_session, ttl_seconds=0.0,
            )

        assert a == "<A>"
        assert b == "<B>"
        assert fake_fanout.await_count == 2

    @pytest.mark.asyncio
    async def test_expired_ttl_via_monotonic_rewind(
        self, db_session, manager_with_team, monkeypatch
    ):
        """Non-zero TTL: simulate elapsed time by rewriting the
        cache row's ``ts`` so the next call sees an expired entry.
        Less brittle than ``time.sleep`` and runs in microseconds."""
        from app.services import call_rag_cache

        user, _ = manager_with_team
        state: dict = {}

        fake = MagicMock()
        fake.to_prompt = MagicMock(side_effect=["<A>", "<B>"])

        with patch(
            "app.services.rag_unified.retrieve_all_context",
            new=AsyncMock(return_value=fake),
        ) as fake_fanout:
            await call_rag_cache.get_call_rag_block(
                state=state, user_id=user.id, query="q1",
                db=db_session, ttl_seconds=60.0,
            )
            # Simulate 90s passing.
            state["_call_rag_cache"]["ts"] -= 90.0

            out = await call_rag_cache.get_call_rag_block(
                state=state, user_id=user.id, query="q2",
                db=db_session, ttl_seconds=60.0,
            )

        assert out == "<B>"
        assert fake_fanout.await_count == 2


# ── Failure mode: retriever explodes → empty string, no crash ───────────


class TestFailureMode:
    @pytest.mark.asyncio
    async def test_retriever_exception_returns_empty_and_caches(
        self, db_session, manager_with_team
    ):
        from app.services import call_rag_cache

        user, _ = manager_with_team
        state: dict = {}

        with patch(
            "app.services.rag_unified.retrieve_all_context",
            new=AsyncMock(side_effect=RuntimeError("RAG provider down")),
        ):
            out = await call_rag_cache.get_call_rag_block(
                state=state, user_id=user.id, query="q",
                db=db_session,
            )

        # Did NOT raise.
        assert out == ""
        # Cached the empty string so we don't thundering-herd.
        assert state["_call_rag_cache"]["prompt"] == ""

    @pytest.mark.asyncio
    async def test_team_id_lookup_failure_falls_through_with_none(
        self, manager_with_team
    ):
        """If the team_id SELECT itself blows up, the helper still
        runs the RAG fanout with team_id=None (methodology branch
        skips, legal/wiki/personality still surface)."""
        from app.services import call_rag_cache

        user, _ = manager_with_team
        state: dict = {}

        bad_db = AsyncMock()
        bad_db.execute = AsyncMock(side_effect=RuntimeError("DB hiccup"))

        fake = MagicMock()
        fake.to_prompt = MagicMock(return_value="<NO TEAM RAG>")

        with patch(
            "app.services.rag_unified.retrieve_all_context",
            new=AsyncMock(return_value=fake),
        ) as fake_fanout:
            out = await call_rag_cache.get_call_rag_block(
                state=state, user_id=user.id, query="q", db=bad_db,
            )

        assert out == "<NO TEAM RAG>"
        # team_id lookup failed → fanout called with None
        assert fake_fanout.await_args.kwargs["team_id"] is None


# ── team_id resolved once per session ───────────────────────────────────


class TestTeamIdResolution:
    @pytest.mark.asyncio
    async def test_team_id_lookup_runs_once_across_misses(
        self, db_session, manager_with_team
    ):
        """Even with TTL=0 (every call is a miss), the ``SELECT
        users.team_id`` only runs on the first miss. Subsequent
        misses reuse the cached resolution."""
        from app.services import call_rag_cache
        from app.models.user import User
        from sqlalchemy import select

        user, team = manager_with_team
        state: dict = {}

        # Wrap db.execute to count user-team-id selects only.
        execute_calls: list = []
        original_execute = db_session.execute

        async def counting_execute(stmt, *args, **kwargs):
            try:
                # Detect SELECT users.team_id by stringifying.
                if "users.team_id" in str(stmt).lower():
                    execute_calls.append(1)
            except Exception:
                pass
            return await original_execute(stmt, *args, **kwargs)

        db_session.execute = counting_execute

        fake = MagicMock()
        fake.to_prompt = MagicMock(return_value="<R>")

        with patch(
            "app.services.rag_unified.retrieve_all_context",
            new=AsyncMock(return_value=fake),
        ):
            for _ in range(3):
                await call_rag_cache.get_call_rag_block(
                    state=state, user_id=user.id, query="q",
                    db=db_session, ttl_seconds=0.0,
                )

        # Restore.
        db_session.execute = original_execute

        # Three RAG misses, but only one team_id select.
        assert len(execute_calls) == 1, (
            f"team_id resolved {len(execute_calls)} times, expected 1"
        )

    @pytest.mark.asyncio
    async def test_user_without_team_caches_sentinel(
        self, db_session, manager_without_team
    ):
        """A manager with ``team_id IS NULL`` should resolve once,
        be cached as a sentinel (``False``), and not re-query on
        subsequent misses. Methodology RAG cleanly skips per
        TZ-8 §1."""
        from app.services import call_rag_cache

        user = manager_without_team
        state: dict = {}

        fake = MagicMock()
        fake.to_prompt = MagicMock(return_value="<NO TEAM>")

        with patch(
            "app.services.rag_unified.retrieve_all_context",
            new=AsyncMock(return_value=fake),
        ) as fake_fanout:
            await call_rag_cache.get_call_rag_block(
                state=state, user_id=user.id, query="q1",
                db=db_session, ttl_seconds=0.0,
            )
            await call_rag_cache.get_call_rag_block(
                state=state, user_id=user.id, query="q2",
                db=db_session, ttl_seconds=0.0,
            )

        # Both calls succeeded; both passed team_id=None to fanout.
        for call in fake_fanout.await_args_list:
            assert call.kwargs["team_id"] is None
        # Sentinel is False (looked up, came back None).
        assert state["_call_rag_cache"]["team_id_resolved"] is False


# ── reset_cache helper ──────────────────────────────────────────────────


class TestResetCache:
    @pytest.mark.asyncio
    async def test_reset_clears_state_entry(self):
        from app.services import call_rag_cache

        state = {"_call_rag_cache": {"ts": 1.0, "prompt": "x"}}
        call_rag_cache.reset_cache(state)
        assert "_call_rag_cache" not in state

    @pytest.mark.asyncio
    async def test_reset_on_empty_state_is_noop(self):
        from app.services import call_rag_cache

        state = {}
        call_rag_cache.reset_cache(state)
        assert state == {}
