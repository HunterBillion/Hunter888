"""TZ-5 — attachment pipeline tests for the training_material branch.

Verifies the new helpers introduced for the import funnel:

  * :func:`ingest_training_material` -- creates an Attachment row with
    NULL client_id / lead_client_id, status='received',
    document_type='training_material', and emits a single
    ``attachment.uploaded`` event (no CRM interaction).

  * :func:`mark_scenario_draft_extracting` /
    :func:`mark_scenario_draft_ready` -- transition
    ``classification_status`` through the new TZ-5 states with the right
    event_type and the right pre-conditions on the input row.

The tests pin the contract that the existing TZ-4 client-attachment
pipeline keeps working unchanged, by exercising the training_material
helper alongside the same emit/db stubs the TZ-4 D2 tests use.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.client import Attachment
from app.models.domain_event import DomainEvent
from app.services import attachment_pipeline
from app.services.attachment_storage import StoredAttachment


def _stored(sha: str = "b" * 64, filename: str = "memo.txt") -> StoredAttachment:
    return StoredAttachment(
        filename=filename,
        sha256=sha,
        file_size=42,
        storage_path=f"/tmp/{filename}",
        public_url=f"/api/uploads/attachments/{filename}",
    )


def _make_event(event_type: str = "attachment.uploaded") -> DomainEvent:
    return DomainEvent(
        id=uuid.uuid4(),
        lead_client_id=None,
        event_type=event_type,
        actor_type="user",
        source="test",
        payload_json={},
        idempotency_key=f"{event_type}:test",
        schema_version=1,
        correlation_id="test",
    )


def _make_db():
    db = SimpleNamespace()
    db.added: list = []
    db.add = MagicMock(side_effect=lambda obj: db.added.append(obj))

    async def _flush():
        for obj in db.added:
            if isinstance(obj, Attachment) and obj.id is None:
                obj.id = uuid.uuid4()

    db.flush = AsyncMock(side_effect=_flush)
    db.execute = AsyncMock()
    return db


def _patch_storage_and_emit(monkeypatch, sha: str = "b" * 64):
    """Stub storage + emit so tests don't touch disk or the real
    domain-event log."""
    captured: dict = {"emit_calls": [], "stored_with": []}

    def _store(*, client_id, filename, data, allowed_extensions=None):
        captured["stored_with"].append(
            {"client_id": client_id, "filename": filename, "size": len(data)}
        )
        return _stored(sha=sha, filename=filename or "memo.txt")

    monkeypatch.setattr(attachment_pipeline.attachment_storage, "store_attachment_bytes", _store) if False else None
    # The pipeline imports store_attachment_bytes from attachment_storage
    # via a local import inside ingest_training_material; patch the
    # module-level attribute the helper resolves to.
    import app.services.attachment_storage as storage_mod

    monkeypatch.setattr(storage_mod, "store_attachment_bytes", _store)

    async def _emit(db, **kwargs):
        captured["emit_calls"].append(kwargs)
        return _make_event(kwargs.get("event_type", "test.ping"))

    monkeypatch.setattr(attachment_pipeline, "emit_domain_event", _emit)
    monkeypatch.setattr(attachment_pipeline, "is_event_persisted", lambda ev: True)
    return captured


# ── ingest_training_material ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_training_material_creates_row_without_client(monkeypatch):
    db = _make_db()
    captured = _patch_storage_and_emit(monkeypatch)

    attachment = await attachment_pipeline.ingest_training_material(
        db,
        uploaded_by=uuid.uuid4(),
        raw_bytes=b"# Memo\n\nHello.",
        raw_filename="memo.md",
        content_type="text/markdown",
    )

    # Attachment shape — TZ-5 §3 invariants
    assert isinstance(attachment, Attachment)
    assert attachment.client_id is None
    assert attachment.lead_client_id is None
    assert attachment.session_id is None
    assert attachment.message_id is None
    assert attachment.document_type == "training_material"
    assert attachment.status == "received"
    assert attachment.classification_status == "classification_pending"
    assert attachment.verification_status == "unverified"
    # Storage was invoked with the bucket directory, not a real client id.
    assert captured["stored_with"][0]["client_id"] == "_training_materials"
    # Exactly one event — no CRM interaction for training materials.
    types = [c["event_type"] for c in captured["emit_calls"]]
    assert types == ["attachment.uploaded"]
    # Event payload must mark the row as training_material so downstream
    # readers can branch on the kind without re-reading the row.
    assert captured["emit_calls"][0]["payload"]["kind"] == "training_material"


@pytest.mark.asyncio
async def test_ingest_training_material_rejects_empty_bytes(monkeypatch):
    db = _make_db()
    _patch_storage_and_emit(monkeypatch)
    with pytest.raises(ValueError):
        await attachment_pipeline.ingest_training_material(
            db,
            uploaded_by=uuid.uuid4(),
            raw_bytes=b"",
            raw_filename="memo.md",
            content_type="text/markdown",
        )


# ── mark_scenario_draft_extracting ───────────────────────────────────────


def _attachment_for_extraction() -> Attachment:
    """Build a freshly-classified training_material row in memory."""
    return Attachment(
        id=uuid.uuid4(),
        uploaded_by=uuid.uuid4(),
        client_id=None,
        lead_client_id=None,
        filename="memo.md",
        content_type="text/markdown",
        file_size=10,
        sha256="c" * 64,
        storage_path="/tmp/memo.md",
        public_url="/api/uploads/attachments/memo.md",
        document_type="training_material",
        status="received",
        ocr_status="not_required",
        classification_status="classified",
        verification_status="unverified",
        domain_event_id=uuid.uuid4(),
    )


@pytest.mark.asyncio
async def test_mark_scenario_draft_extracting_updates_column_and_emits(monkeypatch):
    db = _make_db()
    captured = _patch_storage_and_emit(monkeypatch)

    att = _attachment_for_extraction()
    event = await attachment_pipeline.mark_scenario_draft_extracting(
        db, attachment=att
    )
    assert att.classification_status == "scenario_draft_extracting"
    assert event.event_type == "attachment.scenario_draft_extracting"
    types = [c["event_type"] for c in captured["emit_calls"]]
    assert types[-1] == "attachment.scenario_draft_extracting"


@pytest.mark.asyncio
async def test_mark_scenario_draft_extracting_rejects_wrong_doc_type(monkeypatch):
    db = _make_db()
    _patch_storage_and_emit(monkeypatch)
    att = _attachment_for_extraction()
    att.document_type = "pdf"  # not training_material
    with pytest.raises(ValueError):
        await attachment_pipeline.mark_scenario_draft_extracting(db, attachment=att)


@pytest.mark.asyncio
async def test_mark_scenario_draft_extracting_rejects_wrong_status(monkeypatch):
    db = _make_db()
    _patch_storage_and_emit(monkeypatch)
    att = _attachment_for_extraction()
    att.classification_status = "classification_pending"
    with pytest.raises(ValueError):
        await attachment_pipeline.mark_scenario_draft_extracting(db, attachment=att)


# ── mark_scenario_draft_ready ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mark_scenario_draft_ready_emits_with_confidence(monkeypatch):
    db = _make_db()
    captured = _patch_storage_and_emit(monkeypatch)
    att = _attachment_for_extraction()
    att.classification_status = "scenario_draft_extracting"

    draft_id = uuid.uuid4()
    event = await attachment_pipeline.mark_scenario_draft_ready(
        db,
        attachment=att,
        draft_id=draft_id,
        confidence=0.71,
    )
    assert att.classification_status == "scenario_draft_ready"
    assert event.event_type == "attachment.scenario_draft_ready"
    last = captured["emit_calls"][-1]
    assert last["payload"]["draft_id"] == str(draft_id)
    assert last["payload"]["confidence"] == 0.71


@pytest.mark.asyncio
async def test_mark_scenario_draft_ready_rejects_wrong_status(monkeypatch):
    db = _make_db()
    _patch_storage_and_emit(monkeypatch)
    att = _attachment_for_extraction()  # classified, not extracting
    with pytest.raises(ValueError):
        await attachment_pipeline.mark_scenario_draft_ready(
            db,
            attachment=att,
            draft_id=uuid.uuid4(),
            confidence=0.5,
        )


@pytest.mark.asyncio
async def test_mark_scenario_draft_ready_rejects_out_of_range_confidence(monkeypatch):
    db = _make_db()
    _patch_storage_and_emit(monkeypatch)
    att = _attachment_for_extraction()
    att.classification_status = "scenario_draft_extracting"
    with pytest.raises(ValueError):
        await attachment_pipeline.mark_scenario_draft_ready(
            db,
            attachment=att,
            draft_id=uuid.uuid4(),
            confidence=1.5,
        )
    with pytest.raises(ValueError):
        await attachment_pipeline.mark_scenario_draft_ready(
            db,
            attachment=att,
            draft_id=uuid.uuid4(),
            confidence=-0.1,
        )
