"""TZ-8 PR-E — TTL auto-flip scheduler contract.

Three contracts under test, in priority order:

  1. ``run_review_ttl_pass`` flips ``actual → needs_review`` for
     overdue rows in BOTH ``methodology_chunks`` and ``wiki_pages``.
  2. The scheduler does NOT touch rows that are not yet due, that
     are already non-``actual``, or that have ``review_due_at IS NULL``.
  3. The scheduler does NOT auto-promote to ``outdated`` (TZ-4
     §8.3.1 day-of-cutover footgun avoidance).

Plus the alignment helper :func:`_seconds_until_top_of_next_hour`
returns sensible deltas (positive, ≤ 3600).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select


@pytest.fixture
async def team_id(db_session):
    from app.models.user import Team

    team = Team(name="TTL Team")
    db_session.add(team)
    await db_session.commit()
    await db_session.refresh(team)
    return team.id


@pytest.fixture
async def user_with_wiki(db_session):
    from app.models.manager_wiki import ManagerWiki
    from app.models.user import User

    user = User(
        email=f"ttl_{uuid.uuid4().hex[:8]}@example.test",
        hashed_password="x",
        full_name="TTL User",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    wiki = ManagerWiki(manager_id=user.id, status="active")
    db_session.add(wiki)
    await db_session.commit()
    await db_session.refresh(wiki)
    return user, wiki


# ── Auto-flip happy path ───────────────────────────────────────────────


class TestAutoFlipHappyPath:
    @pytest.mark.asyncio
    async def test_overdue_methodology_flips_to_needs_review(
        self, db_session, team_id
    ):
        from app.models.methodology import MethodologyChunk, MethodologyKind
        from app.services.review_ttl_scheduler import run_review_ttl_pass

        # One row past its TTL.
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        chunk = MethodologyChunk(
            team_id=team_id,
            title="Stale opener",
            body="Older than the hills",
            kind=MethodologyKind.opener.value,
            knowledge_status="actual",
            review_due_at=past,
        )
        db_session.add(chunk)
        await db_session.commit()

        result = await run_review_ttl_pass(db_session)
        assert result["methodology_flipped"] == 1

        await db_session.refresh(chunk)
        assert chunk.knowledge_status == "needs_review"

    @pytest.mark.asyncio
    async def test_overdue_wiki_flips_to_needs_review(
        self, db_session, user_with_wiki
    ):
        from app.models.manager_wiki import WikiPage, WikiPageType
        from app.services.review_ttl_scheduler import run_review_ttl_pass

        _, wiki = user_with_wiki
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        page = WikiPage(
            wiki_id=wiki.id,
            page_path="patterns/stale",
            content="…",
            page_type=WikiPageType.pattern.value,
            knowledge_status="actual",
            review_due_at=past,
        )
        db_session.add(page)
        await db_session.commit()

        result = await run_review_ttl_pass(db_session)
        assert result["wiki_flipped"] == 1

        await db_session.refresh(page)
        assert page.knowledge_status == "needs_review"


# ── Negative paths — what scheduler must NOT touch ─────────────────────


class TestAutoFlipNegativePaths:
    @pytest.mark.asyncio
    async def test_future_due_rows_unchanged(self, db_session, team_id):
        from app.models.methodology import MethodologyChunk, MethodologyKind
        from app.services.review_ttl_scheduler import run_review_ttl_pass

        future = datetime.now(timezone.utc) + timedelta(hours=1)
        chunk = MethodologyChunk(
            team_id=team_id,
            title="Future closing",
            body="Still fresh",
            kind=MethodologyKind.closing.value,
            knowledge_status="actual",
            review_due_at=future,
        )
        db_session.add(chunk)
        await db_session.commit()

        result = await run_review_ttl_pass(db_session)
        assert result["methodology_flipped"] == 0

        await db_session.refresh(chunk)
        assert chunk.knowledge_status == "actual"

    @pytest.mark.asyncio
    async def test_no_ttl_rows_unchanged(self, db_session, team_id):
        """``review_due_at IS NULL`` means the author opted out of
        TTL — the scheduler must skip such rows entirely."""
        from app.models.methodology import MethodologyChunk, MethodologyKind
        from app.services.review_ttl_scheduler import run_review_ttl_pass

        chunk = MethodologyChunk(
            team_id=team_id,
            title="No TTL",
            body="Permanent",
            kind=MethodologyKind.process.value,
            knowledge_status="actual",
            review_due_at=None,
        )
        db_session.add(chunk)
        await db_session.commit()

        result = await run_review_ttl_pass(db_session)
        assert result["methodology_flipped"] == 0

        await db_session.refresh(chunk)
        assert chunk.knowledge_status == "actual"

    @pytest.mark.asyncio
    async def test_already_needs_review_unchanged(
        self, db_session, team_id
    ):
        from app.models.methodology import MethodologyChunk, MethodologyKind
        from app.services.review_ttl_scheduler import run_review_ttl_pass

        past = datetime.now(timezone.utc) - timedelta(hours=2)
        chunk = MethodologyChunk(
            team_id=team_id,
            title="Already flagged",
            body="…",
            kind=MethodologyKind.objection.value,
            knowledge_status="needs_review",
            review_due_at=past,
        )
        db_session.add(chunk)
        await db_session.commit()

        result = await run_review_ttl_pass(db_session)
        # Idempotent: the second pass over the same row is a no-op.
        assert result["methodology_flipped"] == 0

    @pytest.mark.asyncio
    async def test_outdated_rows_never_promoted(self, db_session, team_id):
        """TZ-4 §8.3.1 critical contract: nothing ever flips a row
        AWAY from ``outdated``. If this test fails, a single
        scheduler tick on a day-of-cutover would silently delete the
        knowledge base."""
        from app.models.methodology import MethodologyChunk, MethodologyKind
        from app.services.review_ttl_scheduler import run_review_ttl_pass

        past = datetime.now(timezone.utc) - timedelta(days=30)
        chunk = MethodologyChunk(
            team_id=team_id,
            title="Soft-deleted",
            body="Should stay outdated",
            kind=MethodologyKind.other.value,
            knowledge_status="outdated",
            review_due_at=past,
        )
        db_session.add(chunk)
        await db_session.commit()

        await run_review_ttl_pass(db_session)
        await db_session.refresh(chunk)
        assert chunk.knowledge_status == "outdated"  # unchanged

    @pytest.mark.asyncio
    async def test_disputed_rows_unchanged(self, db_session, team_id):
        """Same protection for disputed as for outdated — auto-flip
        only ever transitions FROM ``actual``."""
        from app.models.methodology import MethodologyChunk, MethodologyKind
        from app.services.review_ttl_scheduler import run_review_ttl_pass

        past = datetime.now(timezone.utc) - timedelta(hours=2)
        chunk = MethodologyChunk(
            team_id=team_id,
            title="Disputed",
            body="…",
            kind=MethodologyKind.discovery.value,
            knowledge_status="disputed",
            review_due_at=past,
        )
        db_session.add(chunk)
        await db_session.commit()

        await run_review_ttl_pass(db_session)
        await db_session.refresh(chunk)
        assert chunk.knowledge_status == "disputed"


# ── Idempotency + bulk pattern ────────────────────────────────────────


class TestBulkAndIdempotency:
    @pytest.mark.asyncio
    async def test_multiple_overdue_rows_flip_in_one_pass(
        self, db_session, team_id
    ):
        from app.models.methodology import MethodologyChunk, MethodologyKind
        from app.services.review_ttl_scheduler import run_review_ttl_pass

        past = datetime.now(timezone.utc) - timedelta(hours=2)
        for i in range(5):
            db_session.add(
                MethodologyChunk(
                    team_id=team_id,
                    title=f"Bulk overdue {i}",
                    body="…",
                    kind=MethodologyKind.opener.value,
                    knowledge_status="actual",
                    review_due_at=past,
                )
            )
        await db_session.commit()

        result = await run_review_ttl_pass(db_session)
        assert result["methodology_flipped"] == 5

    @pytest.mark.asyncio
    async def test_second_pass_is_no_op(self, db_session, team_id):
        """Running twice in succession must flip the same rows only
        once — the second pass sees them as ``needs_review`` and
        skips. Important because cron + lifespan can run together."""
        from app.models.methodology import MethodologyChunk, MethodologyKind
        from app.services.review_ttl_scheduler import run_review_ttl_pass

        past = datetime.now(timezone.utc) - timedelta(hours=1)
        db_session.add(
            MethodologyChunk(
                team_id=team_id,
                title="Once flipped",
                body="…",
                kind=MethodologyKind.opener.value,
                knowledge_status="actual",
                review_due_at=past,
            )
        )
        await db_session.commit()

        first = await run_review_ttl_pass(db_session)
        second = await run_review_ttl_pass(db_session)
        assert first["methodology_flipped"] == 1
        assert second["methodology_flipped"] == 0


# ── Alignment helper ──────────────────────────────────────────────────


class TestAlignmentHelper:
    def test_returns_positive_delta_under_one_hour(self):
        from app.services.review_ttl_scheduler import (
            _seconds_until_top_of_next_hour,
        )

        now = datetime(2026, 5, 1, 14, 23, 17, tzinfo=timezone.utc)
        delta = _seconds_until_top_of_next_hour(_now=now)
        # 14:23:17 → 15:00:00 = 36m 43s = 2203 s
        assert 2200 <= delta <= 2210

    def test_at_exact_hour_returns_full_hour(self):
        from app.services.review_ttl_scheduler import (
            _seconds_until_top_of_next_hour,
        )

        now = datetime(2026, 5, 1, 14, 0, 0, tzinfo=timezone.utc)
        delta = _seconds_until_top_of_next_hour(_now=now)
        # At the top of the hour → wait the full next hour, never zero.
        assert delta == pytest.approx(3600.0, abs=1.0)

    def test_handles_day_rollover(self):
        from app.services.review_ttl_scheduler import (
            _seconds_until_top_of_next_hour,
        )

        # 23:45:00 → next "top" is 00:00:00 next day = 15 min.
        now = datetime(2026, 5, 1, 23, 45, 0, tzinfo=timezone.utc)
        delta = _seconds_until_top_of_next_hour(_now=now)
        assert delta == pytest.approx(900.0, abs=1.0)
