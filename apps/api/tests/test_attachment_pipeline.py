"""TZ-4 D2 — attachment pipeline contract tests.

Covers the canonical surface added in this PR:

  * happy-path original upload (``attachment.uploaded`` + ``attachment.linked``)
  * dedup on existing original (``attachment.duplicate_detected``)
  * dedup race resolution (IntegrityError → re-select → duplicate row)
  * empty payload guard
  * state-transition helpers (mark_av_passed/rejected, ocr/classified/
    verified/rejected) — each emits the right event_type and updates the
    right column in isolation (§7.2 #3 — the four state machines do not
    cross-contaminate).

The tests intentionally mock ``client_domain.emit_domain_event`` and
``create_crm_interaction_with_event`` rather than running against an
in-memory DB — pipeline correctness lives in (a) the SQL the function
emits and (b) the event fan-out, both of which are visible at this
boundary. Real-DB coverage of the partial UNIQUE index is provided by
the D1 migration tests (``test_tz4_d1_lifecycle_fields``) and the
production migration verification.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.client import Attachment
from app.models.domain_event import DomainEvent
from app.services import attachment_pipeline
from app.services.attachment_storage import StoredAttachment


# ── Helpers ──────────────────────────────────────────────────────────────


def _client(*, client_id: uuid.UUID | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=client_id or uuid.uuid4(),
        manager_id=uuid.uuid4(),
        status="active",
    )


def _stored(sha: str = "a" * 64) -> StoredAttachment:
    return StoredAttachment(
        filename="passport.pdf",
        sha256=sha,
        file_size=24,
        storage_path="/tmp/passport.pdf",
        public_url="/api/uploads/attachments/passport.pdf",
    )


def _make_event(event_type: str = "attachment.uploaded") -> DomainEvent:
    return DomainEvent(
        id=uuid.uuid4(),
        lead_client_id=uuid.uuid4(),
        event_type=event_type,
        actor_type="user",
        source="test",
        payload_json={},
        idempotency_key=f"{event_type}:test",
        schema_version=1,
        correlation_id="test",
    )


def _make_db(*, find_results=()):
    """Build a minimal AsyncSession stub. ``find_results`` queues return
    values for ``_find_original`` SELECTs (one per call). ``flush`` is a
    no-op AsyncMock so the savepoint context manager is exercised
    without actually hitting Postgres."""
    db = SimpleNamespace()
    db.added: list = []
    results_iter = iter(find_results)

    class _Result:
        def __init__(self, value):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

    def _execute(_stmt):
        try:
            return _Result(next(results_iter))
        except StopIteration:
            return _Result(None)

    db.execute = AsyncMock(side_effect=_execute)
    db.add = MagicMock(side_effect=lambda obj: db.added.append(obj))

    flush_calls: list[int] = []

    async def _flush():
        flush_calls.append(len(db.added))
        for obj in db.added:
            if isinstance(obj, Attachment) and obj.id is None:
                obj.id = uuid.uuid4()

    db.flush = AsyncMock(side_effect=_flush)
    db.flush_calls = flush_calls

    # Savepoint context manager — must be an async cm that catches and
    # re-raises IntegrityError so the pipeline's try/except sees it.
    class _Savepoint:
        async def __aenter__(self_):
            return self_

        async def __aexit__(self_, exc_type, exc, tb):
            return False  # propagate exceptions

    db.begin_nested = MagicMock(return_value=_Savepoint())

    return db


def _patch_pipeline_deps(
    monkeypatch,
    *,
    storage_sha: str = "a" * 64,
    emit_events: list[DomainEvent] | None = None,
    interaction=None,
    interaction_event: DomainEvent | None = None,
):
    """Stub the pipeline's external collaborators.

    Returns a dict the test can introspect to assert on emit call
    sequences.
    """
    captured: dict = {"emit_calls": [], "create_crm_calls": [], "ensure_lead_calls": 0}

    monkeypatch.setattr(
        attachment_pipeline,
        "store_attachment_bytes",
        lambda *, client_id, filename, data: _stored(storage_sha),
    )

    async def _ensure_lead(db, *, client):
        captured["ensure_lead_calls"] += 1
        return SimpleNamespace(id=uuid.UUID("00000000-0000-0000-0000-000000000fff"))

    monkeypatch.setattr(attachment_pipeline, "ensure_lead_client", _ensure_lead)

    events = list(emit_events or [_make_event(), _make_event("attachment.linked")])
    events_iter = iter(events)

    async def _emit(db, **kwargs):
        captured["emit_calls"].append(kwargs)
        try:
            return next(events_iter)
        except StopIteration:
            return _make_event(kwargs.get("event_type", "test.ping"))

    monkeypatch.setattr(attachment_pipeline, "emit_domain_event", _emit)

    async def _create_crm(db, **kwargs):
        captured["create_crm_calls"].append(kwargs)
        return interaction, interaction_event

    monkeypatch.setattr(
        attachment_pipeline, "create_crm_interaction_with_event", _create_crm
    )

    monkeypatch.setattr(attachment_pipeline, "is_event_persisted", lambda ev: True)

    return captured


# ── Happy-path original upload ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_upload_creates_original_when_no_existing(monkeypatch):
    """First upload of a sha256 for a client → original row, single
    ``attachment.uploaded`` event, ``duplicate_of`` is None."""
    db = _make_db(find_results=[None])
    captured = _patch_pipeline_deps(monkeypatch)

    result = await attachment_pipeline.ingest_upload(
        db,
        client=_client(),
        uploaded_by=uuid.uuid4(),
        raw_bytes=b"file body",
        raw_filename="passport.pdf",
        content_type="application/pdf",
        source=attachment_pipeline.SOURCE_CRM_UPLOAD,
    )

    assert result.is_duplicate is False
    assert result.attachment.duplicate_of is None
    assert result.attachment.status == "received"
    assert result.attachment.verification_status == "unverified"
    # Exactly one upload event (linked is gated on session/message — neither
    # supplied here).
    upload_event_types = [c["event_type"] for c in captured["emit_calls"]]
    assert upload_event_types == ["attachment.uploaded"]
    # No CRM interaction either — those are linkage-only.
    assert captured["create_crm_calls"] == []


@pytest.mark.asyncio
async def test_ingest_upload_emits_linked_event_when_session_provided(monkeypatch):
    """Session/message attached → pipeline emits ``attachment.linked`` in
    addition to ``attachment.uploaded`` and creates the legacy
    ``session.attachment_linked`` interaction so existing FE consumers
    don't break (§7.3 dual-emit during transition)."""
    session = SimpleNamespace(id=uuid.uuid4(), custom_params={"session_mode": "call"})
    interaction = SimpleNamespace(id=uuid.uuid4())
    db = _make_db(find_results=[None])
    captured = _patch_pipeline_deps(
        monkeypatch,
        emit_events=[_make_event("attachment.uploaded"), _make_event("attachment.linked")],
        interaction=interaction,
        interaction_event=_make_event("session.attachment_linked"),
    )

    result = await attachment_pipeline.ingest_upload(
        db,
        client=_client(),
        uploaded_by=uuid.uuid4(),
        raw_bytes=b"file body",
        raw_filename="passport.pdf",
        content_type="application/pdf",
        source=attachment_pipeline.SOURCE_TRAINING_UPLOAD,
        session=session,
    )

    types = [c["event_type"] for c in captured["emit_calls"]]
    assert types == ["attachment.uploaded", "attachment.linked"]
    assert len(captured["create_crm_calls"]) == 1
    assert captured["create_crm_calls"][0]["event_type"] == "session.attachment_linked"
    assert result.interaction is interaction
    assert result.attachment.interaction_id == interaction.id


# ── Dedup paths ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_upload_creates_duplicate_when_original_exists(monkeypatch):
    """Pre-existing original (same lead+sha) → second call inserts a
    duplicate row, emits ``attachment.duplicate_detected`` instead of
    ``attachment.uploaded``."""
    original = SimpleNamespace(id=uuid.uuid4())
    db = _make_db(find_results=[original])
    captured = _patch_pipeline_deps(
        monkeypatch,
        emit_events=[_make_event("attachment.duplicate_detected")],
    )

    result = await attachment_pipeline.ingest_upload(
        db,
        client=_client(),
        uploaded_by=uuid.uuid4(),
        raw_bytes=b"file body",
        raw_filename="passport.pdf",
        content_type="application/pdf",
        source=attachment_pipeline.SOURCE_CRM_UPLOAD,
    )

    assert result.is_duplicate is True
    assert result.attachment.duplicate_of == original.id
    types = [c["event_type"] for c in captured["emit_calls"]]
    assert types == ["attachment.duplicate_detected"]
    # The duplicate_detected event payload must carry the original's id so
    # FE can render the "this file was sent before" tooltip without
    # another query.
    assert captured["emit_calls"][0]["payload"]["duplicate_of"] == str(original.id)


@pytest.mark.asyncio
async def test_ingest_upload_resolves_dedup_race_via_integrity_error(monkeypatch):
    """The §7.2.6 race: ``_find_original`` returned None (no original
    yet), the INSERT raced with another writer that just won the partial
    UNIQUE index. Pipeline catches the IntegrityError, re-fetches the
    now-committed original, and inserts a duplicate row instead of
    propagating a 5xx to the user."""
    winning_original = SimpleNamespace(id=uuid.uuid4())
    # First _find_original → None (we think we're the original).
    # Second _find_original (after IntegrityError) → the winning row.
    db = _make_db(find_results=[None, winning_original])

    # First flush raises IntegrityError to simulate the partial-index
    # collision; subsequent flushes (the duplicate insert + the final
    # outer flush) succeed. Using a counter avoids StopIteration leaking
    # out of an async side_effect.
    flush_calls = {"n": 0}

    async def _flush():
        flush_calls["n"] += 1
        if flush_calls["n"] == 1:
            raise IntegrityError(
                "uq_attachments_client_sha256_orig", {}, Exception()
            )
        for obj in db.added:
            if isinstance(obj, Attachment) and obj.id is None:
                obj.id = uuid.uuid4()

    db.flush = AsyncMock(side_effect=_flush)

    captured = _patch_pipeline_deps(
        monkeypatch,
        # D7.3 emit-first refactor: the pipeline emits BEFORE the
        # INSERT, so when the INSERT raises IntegrityError both the
        # event and the row attempt are rolled back together at the
        # savepoint. In a real PG session both emits happen but only
        # the second persists; the test stub doesn't simulate
        # rollback so we just queue both emits and assert the
        # outcome is the duplicate row + duplicate event.
        emit_events=[
            _make_event("attachment.uploaded"),         # rolled back
            _make_event("attachment.duplicate_detected"),  # survives
        ],
    )

    result = await attachment_pipeline.ingest_upload(
        db,
        client=_client(),
        uploaded_by=uuid.uuid4(),
        raw_bytes=b"file body",
        raw_filename="passport.pdf",
        content_type="application/pdf",
        source=attachment_pipeline.SOURCE_CRM_UPLOAD,
    )

    assert result.is_duplicate is True
    assert result.attachment.duplicate_of == winning_original.id
    # The terminal emit must be the duplicate-detected one. The first
    # ``attachment.uploaded`` lives only inside the rolled-back
    # savepoint — in a real DB it never persists, but the in-memory
    # mock doesn't simulate that, so we validate the pipeline's
    # emit *order* instead.
    types = [c["event_type"] for c in captured["emit_calls"]]
    assert types[-1] == "attachment.duplicate_detected"
    # Final IngestResult.upload_event must be the duplicate event,
    # not the rolled-back uploaded one — this is the contract D7.3
    # depends on (downstream readers branch on event_type).
    assert result.upload_event.event_type == "attachment.duplicate_detected"
    # Two Attachment rows were attempted: the losing original + the
    # winning duplicate. The losing one stays in db.added because we
    # don't actually expire the session in the test stub — what
    # matters is that the SECOND row carries duplicate_of, not the
    # first.
    attachments = [obj for obj in db.added if isinstance(obj, Attachment)]
    assert attachments[-1].duplicate_of == winning_original.id


@pytest.mark.asyncio
async def test_ingest_upload_rejects_empty_payload():
    """Zero-byte upload is a client error — fail fast before touching
    the disk or the DB."""
    with pytest.raises(ValueError):
        await attachment_pipeline.ingest_upload(
            _make_db(),
            client=_client(),
            uploaded_by=uuid.uuid4(),
            raw_bytes=b"",
            raw_filename="empty.pdf",
            content_type="application/pdf",
            source=attachment_pipeline.SOURCE_CRM_UPLOAD,
        )


# ── State transitions (§7.1.1 four state machines) ──────────────────────


@pytest.mark.asyncio
async def test_state_transitions_emit_canonical_events(monkeypatch):
    """Each ``mark_*`` helper emits its own canonical event_type and
    updates the column it owns. The four state machines do not
    cross-contaminate (§7.2 #3) — verifying ``status`` and
    ``verification_status`` independently is the regression guard.
    """
    captured: list[dict] = []

    async def _emit(db, **kwargs):
        captured.append(kwargs)
        return _make_event(kwargs["event_type"])

    monkeypatch.setattr(attachment_pipeline, "emit_domain_event", _emit)

    att = Attachment(
        id=uuid.uuid4(),
        client_id=uuid.uuid4(),
        lead_client_id=uuid.uuid4(),
        filename="x.pdf",
        sha256="a" * 64,
        file_size=1,
        storage_path="/tmp/x.pdf",
        status="received",
        ocr_status="pending",
        classification_status="pending",
        verification_status="unverified",
    )

    await attachment_pipeline.mark_av_passed(_make_db(), attachment=att)
    assert att.status == "received"  # unchanged — av_passed does not flip lifecycle

    await attachment_pipeline.mark_ocr_completed(_make_db(), attachment=att, extracted_chars=42)
    assert att.ocr_status == "completed"
    assert att.status == "received"  # still independent

    await attachment_pipeline.mark_classified(
        _make_db(), attachment=att, document_type="passport", confidence=0.9
    )
    assert att.document_type == "passport"
    assert att.classification_status == "completed"
    assert att.verification_status == "unverified"  # untouched

    await attachment_pipeline.mark_verified(_make_db(), attachment=att, reviewer_id=uuid.uuid4())
    assert att.verification_status == "verified"
    assert att.status == "received"  # still independent

    types = [c["event_type"] for c in captured]
    assert types == [
        "attachment.av_passed",
        "attachment.ocr_completed",
        "attachment.classified",
        "attachment.verified",
    ]
    # Every emit must carry an attachment-scoped idempotency key so a
    # retry from a queue worker collapses to a single row in
    # domain_events instead of duplicating.
    assert all(str(att.id) in c["idempotency_key"] for c in captured)


@pytest.mark.asyncio
async def test_mark_av_rejected_writes_status_terminal(monkeypatch):
    """``av_rejected`` is the only path that flips ``status`` to
    ``rejected``. Verifying it lives in the lifecycle column (not in
    verification_status) protects §7.1.1 — those are separate machines.
    """
    captured: list[dict] = []

    async def _emit(db, **kwargs):
        captured.append(kwargs)
        return _make_event("attachment.av_rejected")

    monkeypatch.setattr(attachment_pipeline, "emit_domain_event", _emit)

    att = Attachment(
        id=uuid.uuid4(),
        client_id=uuid.uuid4(),
        lead_client_id=uuid.uuid4(),
        filename="virus.exe",
        sha256="b" * 64,
        file_size=1,
        storage_path="/tmp/virus",
        status="received",
        ocr_status="not_required",
        classification_status="pending",
        verification_status="unverified",
    )

    await attachment_pipeline.mark_av_rejected(
        _make_db(), attachment=att, reason="signature match: trojan"
    )

    assert att.status == "rejected"
    assert att.verification_status == "unverified"  # not touched
    assert captured[0]["event_type"] == "attachment.av_rejected"
    assert captured[0]["payload"]["reason"] == "signature match: trojan"
