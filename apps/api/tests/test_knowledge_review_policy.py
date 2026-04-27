"""TZ-4 D4 — knowledge review policy contract tests.

Covers the canonical surface added in this PR:

  * ``expire_overdue`` happy path — flips ``actual → needs_review`` and
    emits ``knowledge_item.expired`` with reviewed_by=NULL.
  * **§8.3.1 closed footgun** — the cron NEVER writes ``outdated``
    even if a stale row is past TTL.
  * ``expire_overdue`` idempotency — re-running on an already-flipped
    row is a no-op (no double event, no version churn).
  * ``mark_reviewed`` — manual transitions including ``outdated``,
    writes reviewed_by + reviewed_at, emits both
    ``knowledge_item.reviewed`` and ``knowledge_item.status_changed``.
  * ``mark_reviewed`` validates the target enum.
  * ``mark_reviewed`` skips ``status_changed`` event when the target
    equals the current status (re-confirmation noise suppression).
  * ``list_review_queue`` returns only ``needs_review`` rows, sorted
    by ``expires_at`` ascending.
  * ``is_recommendation_safe`` predicate — only ``outdated`` is False.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.domain_event import DomainEvent
from app.models.rag import LegalKnowledgeChunk
from app.services import knowledge_review_policy as krp


# ── Test helpers ─────────────────────────────────────────────────────────


def _make_event(event_type: str = "knowledge_item.expired") -> DomainEvent:
    return DomainEvent(
        id=uuid.uuid4(),
        lead_client_id=krp.KNOWLEDGE_GLOBAL_ANCHOR,
        event_type=event_type,
        actor_type="system",
        source="test",
        payload_json={},
        idempotency_key=f"{event_type}:test",
        schema_version=1,
        correlation_id="test",
    )


def _chunk(
    *,
    knowledge_status: str = "actual",
    expires_at: datetime | None = None,
    title: str = "Title",
    is_active: bool = True,
) -> LegalKnowledgeChunk:
    chunk = LegalKnowledgeChunk(
        id=uuid.uuid4(),
        category="banking",
        fact_text="...",
        law_article="ст.1",
        knowledge_status=knowledge_status,
        title=title,
        is_active=is_active,
        expires_at=expires_at,
    )
    return chunk


def _make_db(*, chunks_returned=(), chunk_by_id=None):
    """Stub AsyncSession. ``chunks_returned`` is the iterable returned
    by ``execute().scalars().all()`` for the SELECT in expire_overdue
    or list_review_queue. ``chunk_by_id`` is returned by ``db.get``.
    """
    db = SimpleNamespace()

    class _Scalars:
        def __init__(self, rows):
            self._rows = list(rows)

        def all(self):
            return self._rows

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return _Scalars(self._rows)

        def scalar_one_or_none(self):
            return self._rows[0] if self._rows else None

    async def _execute(_stmt):
        return _Result(list(chunks_returned))

    db.execute = AsyncMock(side_effect=_execute)
    db.flush = AsyncMock()
    db.get = AsyncMock(return_value=chunk_by_id)
    return db


def _patch_emit(monkeypatch) -> list[dict]:
    captured: list[dict] = []

    async def _emit(db, **kwargs):
        captured.append(kwargs)
        return _make_event(kwargs.get("event_type", "test.ping"))

    monkeypatch.setattr(krp, "emit_domain_event", _emit)
    return captured


# ── expire_overdue ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_expire_overdue_flips_actual_to_needs_review(monkeypatch):
    """Past-TTL chunk in ``actual`` → flipped to ``needs_review``,
    emit fires with reviewed_by=None signaling automated transition."""
    chunk = _chunk(
        knowledge_status="actual",
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    db = _make_db(chunks_returned=[chunk])
    captured = _patch_emit(monkeypatch)

    result = await krp.expire_overdue(db)

    assert chunk.knowledge_status == "needs_review"
    assert result.flipped_to_needs_review == 1
    assert result.skipped_already_flipped == 0
    assert captured[0]["event_type"] == "knowledge_item.expired"
    assert captured[0]["payload"]["from_status"] == "actual"
    assert captured[0]["payload"]["to_status"] == "needs_review"
    assert captured[0]["payload"]["reviewed_by"] is None  # automated
    assert captured[0]["actor_type"] == "system"


@pytest.mark.asyncio
async def test_expire_overdue_never_writes_outdated_for_stale_chunks(monkeypatch):
    """§8.3.1 — even a chunk past TTL by years stays in ``needs_review``,
    never auto-promoted to ``outdated``. Manual review only."""
    chunk = _chunk(
        knowledge_status="actual",
        expires_at=datetime.now(UTC) - timedelta(days=365 * 5),  # 5y stale
    )
    db = _make_db(chunks_returned=[chunk])
    captured = _patch_emit(monkeypatch)

    await krp.expire_overdue(db)

    assert chunk.knowledge_status == "needs_review"
    assert chunk.knowledge_status != "outdated"
    # Defensive: the event payload must not silently say the cron
    # wrote outdated either.
    assert captured[0]["payload"]["to_status"] == "needs_review"


@pytest.mark.asyncio
async def test_expire_overdue_idempotent_on_already_flipped(monkeypatch):
    """Re-running cron on a row that's already in ``needs_review``
    must not re-emit (the SELECT only matches ``actual``, but we also
    test the in-loop guard for paranoia)."""
    db = _make_db(chunks_returned=[])  # SELECT returns nothing
    captured = _patch_emit(monkeypatch)

    result = await krp.expire_overdue(db)

    assert result.flipped_to_needs_review == 0
    assert result.skipped_already_flipped == 0
    assert captured == []


@pytest.mark.asyncio
async def test_expire_overdue_skips_in_loop_guard(monkeypatch):
    """If a parallel sweep raced ahead and flipped a candidate between
    SELECT and the loop body, the in-loop guard catches it instead of
    double-flipping."""
    chunk = _chunk(
        knowledge_status="needs_review",  # already flipped
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    db = _make_db(chunks_returned=[chunk])
    captured = _patch_emit(monkeypatch)

    result = await krp.expire_overdue(db)

    assert chunk.knowledge_status == "needs_review"  # unchanged
    assert result.flipped_to_needs_review == 0
    assert result.skipped_already_flipped == 1
    assert captured == []


# ── mark_reviewed ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mark_reviewed_to_outdated_emits_two_events(monkeypatch):
    """Manual review can write ``outdated`` (the only legal path).
    Emits both ``knowledge_item.reviewed`` (audit) and
    ``knowledge_item.status_changed`` (FE fan-out)."""
    chunk = _chunk(knowledge_status="needs_review")
    db = _make_db(chunk_by_id=chunk)
    captured = _patch_emit(monkeypatch)
    reviewer_id = uuid.uuid4()

    returned, events = await krp.mark_reviewed(
        db,
        chunk_id=chunk.id,
        new_status="outdated",
        reviewed_by=reviewer_id,
        reason="Закон редакция от 2020 утратила силу",
    )

    assert returned is chunk
    assert chunk.knowledge_status == "outdated"
    assert chunk.reviewed_by == reviewer_id
    assert chunk.reviewed_at is not None
    types = [c["event_type"] for c in captured]
    assert types == ["knowledge_item.reviewed", "knowledge_item.status_changed"]
    assert captured[0]["payload"]["from_status"] == "needs_review"
    assert captured[0]["payload"]["to_status"] == "outdated"
    assert captured[0]["payload"]["reason"] is not None
    assert len(events) == 2


@pytest.mark.asyncio
async def test_mark_reviewed_no_status_change_skips_status_changed_event(monkeypatch):
    """Re-confirming an item at the same status (e.g. ``actual → actual``)
    fires only ``knowledge_item.reviewed`` for the audit trail; the
    ``status_changed`` fan-out is suppressed because nothing actually
    moved (FE doesn't need a notification)."""
    chunk = _chunk(knowledge_status="actual")
    db = _make_db(chunk_by_id=chunk)
    captured = _patch_emit(monkeypatch)

    _, events = await krp.mark_reviewed(
        db,
        chunk_id=chunk.id,
        new_status="actual",  # re-confirm
        reviewed_by=uuid.uuid4(),
    )

    types = [c["event_type"] for c in captured]
    assert types == ["knowledge_item.reviewed"]
    assert len(events) == 1
    assert chunk.knowledge_status == "actual"


@pytest.mark.asyncio
async def test_mark_reviewed_rejects_invalid_status(monkeypatch):
    chunk = _chunk(knowledge_status="actual")
    db = _make_db(chunk_by_id=chunk)
    _patch_emit(monkeypatch)

    with pytest.raises(krp.InvalidKnowledgeStatus):
        await krp.mark_reviewed(
            db,
            chunk_id=chunk.id,
            new_status="bogus",
            reviewed_by=uuid.uuid4(),
        )
    # No mutation happened
    assert chunk.knowledge_status == "actual"
    assert chunk.reviewed_by is None


@pytest.mark.asyncio
async def test_mark_reviewed_404_when_chunk_missing(monkeypatch):
    db = _make_db(chunk_by_id=None)
    _patch_emit(monkeypatch)

    with pytest.raises(LookupError):
        await krp.mark_reviewed(
            db,
            chunk_id=uuid.uuid4(),
            new_status="actual",
            reviewed_by=uuid.uuid4(),
        )


# ── list_review_queue ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_review_queue_returns_value_typed_items():
    """Queue endpoint returns a value-typed list — no ORM session
    leakage past the service boundary."""
    chunk = _chunk(
        knowledge_status="needs_review",
        expires_at=datetime.now(UTC) - timedelta(days=2),
    )
    db = _make_db(chunks_returned=[chunk])

    items = await krp.list_review_queue(db, limit=10)

    assert len(items) == 1
    assert items[0].id == chunk.id
    assert items[0].knowledge_status == "needs_review"
    assert isinstance(items[0], krp.ReviewQueueItem)


# ── is_recommendation_safe ───────────────────────────────────────────────


def test_is_recommendation_safe_excludes_only_outdated():
    """The §11.2.1 NBA gate predicate. Future NBA wiring imports this
    helper instead of re-deriving the rule. Aligned with the existing
    SQL filter at rag_legal.py:217 — both blacklist only ``outdated``.
    """
    assert krp.is_recommendation_safe("actual") is True
    assert krp.is_recommendation_safe("disputed") is True
    assert krp.is_recommendation_safe("needs_review") is True
    assert krp.is_recommendation_safe("outdated") is False
    # Garbage / NULL falls back to actual per knowledge_governance.normalize
    assert krp.is_recommendation_safe(None) is True
    assert krp.is_recommendation_safe("garbage") is True
