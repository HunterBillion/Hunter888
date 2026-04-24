import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.training import upload_session_attachment
from app.models.client import Attachment, ClientInteraction
from app.services.attachment_storage import StoredAttachment, attachment_sha256


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
    db.added = []
    db.execute = AsyncMock(side_effect=[_Result(v) for v in values])

    async def _flush():
        for obj in db.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    db.flush = AsyncMock(side_effect=_flush)
    db.add = MagicMock(side_effect=lambda obj: db.added.append(obj))
    return db


@pytest.mark.asyncio
async def test_upload_session_attachment_creates_attachment_and_timeline(monkeypatch):
    user = SimpleNamespace(id=uuid.uuid4())
    client = SimpleNamespace(id=uuid.uuid4(), manager_id=user.id)
    session = _session(real_client_id=client.id)
    session.user_id = user.id
    data = b"passport scan"
    digest = attachment_sha256(data)
    db = _db_with_results(session, client, None)

    def fake_store_attachment_bytes(*, client_id: str, filename: str | None, data: bytes):
        return StoredAttachment(
            filename="passport.pdf",
            sha256=digest,
            file_size=len(data),
            storage_path=f"/tmp/{client_id}/passport.pdf",
            public_url=f"/api/uploads/attachments/{client_id}/passport.pdf",
        )

    monkeypatch.setattr("app.api.training.store_attachment_bytes", fake_store_attachment_bytes)

    async def fake_bind_attachment_to_lead_client(db, *, attachment, client):
        attachment.lead_client_id = client.id
        return client.id

    async def fake_create_crm_interaction_with_event(
        db,
        *,
        client,
        manager_id,
        interaction_type,
        content,
        result=None,
        duration_seconds=None,
        metadata=None,
        payload=None,
        **_,
    ):
        interaction = ClientInteraction(
            client_id=client.id,
            lead_client_id=client.id,
            manager_id=manager_id,
            interaction_type=interaction_type,
            content=content,
            result=result,
            duration_seconds=duration_seconds,
            metadata_=metadata,
        )
        db.add(interaction)
        await db.flush()
        event = SimpleNamespace(id=uuid.uuid4(), schema_version=1)
        return interaction, event

    monkeypatch.setattr("app.api.training.bind_attachment_to_lead_client", fake_bind_attachment_to_lead_client)
    monkeypatch.setattr("app.api.training.create_crm_interaction_with_event", fake_create_crm_interaction_with_event)

    attachment = await upload_session_attachment(
        session_id=session.id,
        request=SimpleNamespace(),
        file=_Upload(data),
        user=user,
        db=db,
    )

    timeline_event = next(obj for obj in db.added if isinstance(obj, ClientInteraction))
    created_attachment = next(obj for obj in db.added if isinstance(obj, Attachment))

    assert attachment is created_attachment
    assert created_attachment.client_id == client.id
    assert created_attachment.session_id == session.id
    assert created_attachment.document_type == "pdf"
    assert created_attachment.ocr_status == "pending"
    assert created_attachment.metadata_["source"] == "training_session_upload"
    assert created_attachment.lead_client_id == client.id
    assert "domain_event_id" in created_attachment.metadata_
    assert timeline_event.client_id == client.id
    assert timeline_event.lead_client_id == client.id
    assert timeline_event.result == "attachment_received"
    assert timeline_event.content == "Получен файл в сессии call: passport.pdf"
    assert timeline_event.metadata_["attachment_id"] == str(created_attachment.id)
    assert timeline_event.metadata_["training_session_id"] == str(session.id)


@pytest.mark.asyncio
async def test_upload_session_attachment_requires_crm_client():
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
