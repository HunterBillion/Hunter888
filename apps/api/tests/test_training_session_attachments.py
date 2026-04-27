"""API-layer contract tests for ``POST /training/sessions/:id/attachment``.

This file pins the *endpoint* shape: routing, DB lookups, error paths, and
the hand-off into ``attachment_pipeline.ingest_upload``. The pipeline's
own contract (dedup, event emission, state transitions) is covered by
``test_attachment_pipeline.py`` — duplicating it here would only re-test
the mock.

History: prior to TZ-4 D2 the upload endpoint built ``Attachment`` rows
inline and called several ``client_domain`` helpers directly. The
endpoint is now a thin wrapper over ``ingest_upload``, so these tests
verify only that wrapper.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.training import upload_session_attachment
from app.models.client import Attachment
from app.services.attachment_pipeline import IngestResult


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _Upload:
    filename = "passport.pdf"
    content_type = "application/pdf"

    def __init__(self, data: bytes):
        self._data = data

    async def read(self, _limit: int):
        return self._data


def _session(*, real_client_id: uuid.UUID | None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        real_client_id=real_client_id,
        custom_params={"session_mode": "call"},
    )


def _db_with_results(*values):
    db = SimpleNamespace()
    db.execute = AsyncMock(side_effect=[_Result(v) for v in values])
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.mark.asyncio
async def test_upload_session_attachment_delegates_to_pipeline(monkeypatch):
    """Endpoint loads the session + client, then hands off to the
    pipeline with the call-shape required by TZ-4 §7.2: typed kwargs,
    ``source=SOURCE_TRAINING_UPLOAD``, ``session_mode`` carried in
    ``extra_metadata``. The endpoint returns the pipeline's
    ``Attachment`` unchanged.
    """
    user = SimpleNamespace(id=uuid.uuid4())
    client = SimpleNamespace(id=uuid.uuid4(), manager_id=user.id)
    session = _session(real_client_id=client.id)
    session.user_id = user.id
    db = _db_with_results(session, client)

    captured: dict = {}
    expected = Attachment(
        id=uuid.uuid4(),
        client_id=client.id,
        lead_client_id=client.id,
        filename="passport.pdf",
        sha256="x" * 64,
        file_size=11,
        storage_path="/tmp/x",
        document_type="pdf",
        status="received",
        ocr_status="pending",
        classification_status="pending",
        verification_status="unverified",
    )

    async def fake_ingest_upload(db, **kwargs):
        captured.update(kwargs)
        return IngestResult(
            attachment=expected,
            is_duplicate=False,
            upload_event=SimpleNamespace(id=uuid.uuid4()),
            interaction=None,
            interaction_event=None,
        )

    monkeypatch.setattr("app.api.training.ingest_upload", fake_ingest_upload)

    returned = await upload_session_attachment(
        session_id=session.id,
        request=SimpleNamespace(),
        file=_Upload(b"passport scan"),
        user=user,
        db=db,
    )

    assert returned is expected
    assert captured["client"] is client
    assert captured["session"] is session
    assert captured["uploaded_by"] == user.id
    assert captured["raw_filename"] == "passport.pdf"
    assert captured["content_type"] == "application/pdf"
    assert captured["source"] == "api.training.attachment"
    # session_mode is normalised by the endpoint and forwarded as
    # extra metadata so the pipeline can stamp it onto the row.
    assert captured["extra_metadata"] == {"session_mode": "call"}


@pytest.mark.asyncio
async def test_upload_session_attachment_requires_crm_client():
    """Sessions without a CRM-client binding cannot accept an
    attachment — the endpoint must reject before touching the
    pipeline (no orphan disk write)."""
    user = SimpleNamespace(id=uuid.uuid4())
    session = _session(real_client_id=None)
    session.user_id = user.id
    db = _db_with_results(session)

    with pytest.raises(HTTPException) as exc:
        await upload_session_attachment(
            session_id=session.id,
            request=SimpleNamespace(),
            file=_Upload(b"doc"),
            user=user,
            db=db,
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Сессия не привязана к CRM-клиенту"
