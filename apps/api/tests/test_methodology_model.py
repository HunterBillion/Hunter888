"""TZ-8 PR-A — schema-level smoke tests for the new RAG foundations.

Three contracts the migration / model declaration must hold:

  1. The ``KnowledgeStatus`` enum is the single source of truth and
     its visible/hidden frozensets match what the RAG retrievers
     filter on.
  2. ``MethodologyChunk`` rows persist with the right defaults, the
     ``UNIQUE(team_id, title)`` constraint fires, and team-scoping
     is structural (not "trust the application layer").
  3. ``WikiPage.knowledge_status`` defaults to ``actual`` so existing
     pages keep showing up after the new SQL filter lands.

The full functional matrix (CRUD endpoints, authz, retrieval,
filter) lives in PR-B. This file is the schema-only beachhead.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


# ═══════════════════════════════════════════════════════════════════════
# KnowledgeStatus enum + frozenset contracts
# ═══════════════════════════════════════════════════════════════════════


class TestKnowledgeStatusVocabulary:
    def test_enum_has_exactly_four_values(self):
        from app.models.knowledge_status import KnowledgeStatus

        assert {s.value for s in KnowledgeStatus} == {
            "actual",
            "disputed",
            "outdated",
            "needs_review",
        }

    def test_visible_set_is_actual_plus_disputed(self):
        from app.models.knowledge_status import (
            KnowledgeStatus,
            STATUSES_VISIBLE_IN_RAG,
        )

        assert STATUSES_VISIBLE_IN_RAG == {
            KnowledgeStatus.actual.value,
            KnowledgeStatus.disputed.value,
        }

    def test_hidden_set_is_outdated_plus_needs_review(self):
        from app.models.knowledge_status import (
            KnowledgeStatus,
            STATUSES_HIDDEN_FROM_RAG,
        )

        assert STATUSES_HIDDEN_FROM_RAG == {
            KnowledgeStatus.outdated.value,
            KnowledgeStatus.needs_review.value,
        }

    def test_visible_and_hidden_partition_the_enum(self):
        """Every value in :class:`KnowledgeStatus` is in exactly one set."""
        from app.models.knowledge_status import (
            KnowledgeStatus,
            STATUSES_HIDDEN_FROM_RAG,
            STATUSES_VISIBLE_IN_RAG,
        )

        all_values = {s.value for s in KnowledgeStatus}
        assert STATUSES_VISIBLE_IN_RAG.isdisjoint(STATUSES_HIDDEN_FROM_RAG)
        assert STATUSES_VISIBLE_IN_RAG | STATUSES_HIDDEN_FROM_RAG == all_values

    @pytest.mark.parametrize(
        ("status", "visible"),
        [
            ("actual", True),
            ("disputed", True),
            ("outdated", False),
            ("needs_review", False),
            (None, True),  # legacy NULL rows treated as actual
            ("garbage", False),
            ("", False),
        ],
    )
    def test_is_visible_in_rag_handles_str_enum_none_garbage(self, status, visible):
        from app.models.knowledge_status import KnowledgeStatus, is_visible_in_rag

        assert is_visible_in_rag(status) is visible

    def test_is_visible_in_rag_accepts_enum_member(self):
        from app.models.knowledge_status import KnowledgeStatus, is_visible_in_rag

        assert is_visible_in_rag(KnowledgeStatus.actual) is True
        assert is_visible_in_rag(KnowledgeStatus.outdated) is False


# ═══════════════════════════════════════════════════════════════════════
# MethodologyChunk schema persistence
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
async def team_id(db_session):
    """A persisted ``Team`` row to satisfy the FK on ``methodology_chunks``."""
    from app.models.user import Team

    team = Team(name="Pilot team A")
    db_session.add(team)
    await db_session.commit()
    await db_session.refresh(team)
    return team.id


class TestMethodologyChunkPersistence:
    @pytest.mark.asyncio
    async def test_minimum_required_fields_persist(self, db_session, team_id):
        from app.models.methodology import MethodologyChunk, MethodologyKind

        chunk = MethodologyChunk(
            team_id=team_id,
            title="Opener for warm leads",
            body="1. Greet by first name…\n2. State the goal…",
            kind=MethodologyKind.opener.value,
        )
        db_session.add(chunk)
        await db_session.commit()
        await db_session.refresh(chunk)

        assert chunk.id is not None
        assert chunk.knowledge_status == "actual"  # server_default
        assert chunk.version == 1
        assert chunk.tags == []
        assert chunk.keywords == []
        assert chunk.embedding is None
        assert chunk.created_at is not None

    @pytest.mark.asyncio
    async def test_unique_team_title_constraint_fires(self, db_session, team_id):
        """Two chunks with the same title in the same team must collide.

        This is the structural answer to "Closing v1 / v2 / v3" drift —
        ROPs have to mark old versions ``outdated`` rather than accrete
        homonyms.
        """
        from app.models.methodology import MethodologyChunk, MethodologyKind

        first = MethodologyChunk(
            team_id=team_id,
            title="Закрытие сделки",
            body="Original closing playbook.",
            kind=MethodologyKind.closing.value,
        )
        db_session.add(first)
        await db_session.commit()

        duplicate = MethodologyChunk(
            team_id=team_id,
            title="Закрытие сделки",  # same title, same team
            body="Different body — trying to sneak in a v2.",
            kind=MethodologyKind.closing.value,
        )
        db_session.add(duplicate)
        with pytest.raises(IntegrityError):
            await db_session.commit()
        await db_session.rollback()

    @pytest.mark.asyncio
    async def test_same_title_different_teams_is_allowed(self, db_session):
        """The UNIQUE is per-team — both teams owning a "Closing playbook"
        must be fine. Each team's RAG only sees its own anyway."""
        from app.models.methodology import MethodologyChunk, MethodologyKind
        from app.models.user import Team

        team_a = Team(name="A")
        team_b = Team(name="B")
        db_session.add_all([team_a, team_b])
        await db_session.commit()
        await db_session.refresh(team_a)
        await db_session.refresh(team_b)

        chunk_a = MethodologyChunk(
            team_id=team_a.id,
            title="Universal opener",
            body="Team A version.",
            kind=MethodologyKind.opener.value,
        )
        chunk_b = MethodologyChunk(
            team_id=team_b.id,
            title="Universal opener",
            body="Team B version.",
            kind=MethodologyKind.opener.value,
        )
        db_session.add_all([chunk_a, chunk_b])
        await db_session.commit()

        # Both rows persisted.
        rows = (
            await db_session.execute(select(MethodologyChunk))
        ).scalars().all()
        assert len(rows) == 2
        assert {r.team_id for r in rows} == {team_a.id, team_b.id}

    @pytest.mark.asyncio
    async def test_kind_accepts_all_enum_values(self, db_session, team_id):
        """Smoke: every defined kind round-trips through the column.

        If a future PR adds a new value to :class:`MethodologyKind`
        without remembering this column is ``String(30)``, the
        ``len(value) > 30`` would silently truncate. This catches it.
        """
        from app.models.methodology import MethodologyChunk, MethodologyKind

        for i, kind in enumerate(MethodologyKind):
            db_session.add(
                MethodologyChunk(
                    team_id=team_id,
                    title=f"Sample {i}",
                    body="…",
                    kind=kind.value,
                )
            )
            assert len(kind.value) <= 30, (
                f"MethodologyKind.{kind.name} value {kind.value!r} won't fit "
                "in the String(30) column — bump the column or shorten the kind."
            )
        await db_session.commit()


# ═══════════════════════════════════════════════════════════════════════
# WikiPage governance carry-over
# ═══════════════════════════════════════════════════════════════════════


class TestWikiPageGovernance:
    @pytest.mark.asyncio
    async def test_existing_pages_default_to_actual(self, db_session):
        """A WikiPage created without an explicit ``knowledge_status``
        lands as ``actual``. This is the contract that lets the
        backfill-by-default pattern in the migration stay safe — a
        legacy page row created via ``WikiPage(...)`` with no status
        kwarg must still surface in retrieval after the filter ships.
        """
        from app.models.manager_wiki import (
            ManagerWiki,
            WikiPage,
            WikiPageType,
        )
        from app.models.user import User

        user = User(
            email="page-default@example.test",
            hashed_password="x",
            full_name="Page Default",
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        wiki = ManagerWiki(manager_id=user.id, status="active")
        db_session.add(wiki)
        await db_session.commit()
        await db_session.refresh(wiki)

        page = WikiPage(
            wiki_id=wiki.id,
            page_path="overview/intro",
            content="hello",
            page_type=WikiPageType.overview.value,
        )
        db_session.add(page)
        await db_session.commit()
        await db_session.refresh(page)

        assert page.knowledge_status == "actual"
        assert page.last_reviewed_at is None
        assert page.last_reviewed_by is None
        assert page.review_due_at is None

    @pytest.mark.asyncio
    async def test_explicit_status_persists(self, db_session):
        """Setting ``knowledge_status`` to a non-default value on
        creation persists round-trip. Smoke for the new column being
        wired into the SQLAlchemy mapper, not server_default behaviour.
        """
        from app.models.knowledge_status import KnowledgeStatus
        from app.models.manager_wiki import (
            ManagerWiki,
            WikiPage,
            WikiPageType,
        )
        from app.models.user import User

        user = User(
            email="page-explicit@example.test",
            hashed_password="x",
            full_name="Page Explicit",
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        wiki = ManagerWiki(manager_id=user.id, status="active")
        db_session.add(wiki)
        await db_session.commit()
        await db_session.refresh(wiki)

        page = WikiPage(
            wiki_id=wiki.id,
            page_path="patterns/old",
            content="…",
            page_type=WikiPageType.pattern.value,
            knowledge_status=KnowledgeStatus.outdated.value,
        )
        db_session.add(page)
        await db_session.commit()
        await db_session.refresh(page)

        assert page.knowledge_status == "outdated"
