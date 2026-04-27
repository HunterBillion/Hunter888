"""Canonical attachment pipeline (TZ-4 §6.1 / §7).

Single entry point for every code path that creates or transitions an
``Attachment`` row. Replaces the two ad-hoc constructor sites that lived in
``app/api/clients.py`` and ``app/api/training.py`` before this module — both
of them are migrated by this PR to call ``ingest_upload`` instead.

Why this module exists
----------------------

* The two old call sites duplicated ~50 lines of "compute sha256, store
  bytes, bind lead_client, look up existing duplicate, INSERT, emit
  session.attachment_linked event, write audit log". Drift between them
  showed up in metadata keys and idempotency-key shapes.
* Spec §7.2.6 mandates a deterministic dedup contract anchored on a
  partial UNIQUE index (D1 migration ``20260427_001``). Implementing that
  in two places risks one of them silently growing a TOCTOU race.
* Spec §7.3 enumerates 9 canonical event types covering the four state
  machines (status / ocr / classification / verification). Routing every
  state transition through a single module is the only way an AST guard
  can prove no other module is mutating those columns.

Public API
----------

* :func:`ingest_upload` — happy-path entry. Stores the file, looks up an
  existing ``original`` row by sha256, inserts either an original (with
  ``duplicate_of=NULL``) or a duplicate (with ``duplicate_of=<original.id>``)
  in a single attempt, falls back to an explicit re-fetch on
  ``IntegrityError`` from the partial UNIQUE index. Emits one of
  ``attachment.uploaded`` / ``attachment.duplicate_detected`` plus
  optionally ``attachment.linked`` and threads the resulting
  ``domain_event_id`` back onto the row.

* State-transition helpers (one per remaining canonical event):

  - :func:`mark_av_passed`           emits ``attachment.av_passed``
  - :func:`mark_av_rejected`         emits ``attachment.av_rejected`` and
                                     sets ``status='rejected'``
  - :func:`mark_ocr_completed`       emits ``attachment.ocr_completed``
                                     and updates ``ocr_status``
  - :func:`mark_classified`          emits ``attachment.classified`` and
                                     updates ``classification_status`` /
                                     ``document_type``
  - :func:`mark_verified`            emits ``attachment.verified`` and
                                     sets ``verification_status='verified'``
  - :func:`mark_rejected`            emits ``attachment.rejected`` and
                                     sets ``verification_status=
                                     'rejected_review'`` (terminal)

Each helper is the **only** sanctioned writer of its target column. The
AST guard ``test_attachment_invariants.py`` walks the source tree and
fails the build on any other writer.

Race resolution (§7.2.6)
------------------------

Two concurrent uploads of the same ``(lead_client_id, sha256)`` race for
the partial UNIQUE index ``uq_attachments_client_sha256_orig``. We do
not pre-lock with ``SELECT FOR UPDATE`` — the index alone is sufficient.
The algorithm:

  1. Compute sha256 from bytes.
  2. SELECT existing original ``WHERE lead_client_id = X AND sha256 = Y
     AND duplicate_of IS NULL`` — if one is found, INSERT a duplicate
     (no UNIQUE conflict because ``duplicate_of IS NOT NULL`` bypasses
     the partial index) and emit ``attachment.duplicate_detected``.
  3. If none was found, INSERT as original (``duplicate_of=NULL``):

     - on success → emit ``attachment.uploaded``;
     - on ``IntegrityError`` (raced with a sibling that won the index)
       → re-SELECT the now-committed original, INSERT a duplicate row,
       emit ``attachment.duplicate_detected``. Both writers return a
       valid ``Attachment`` row; neither sees a 5xx.

The re-select branch is the symptom-test target for §4.1 lessons —
``asyncio.gather`` of N parallel ``ingest_upload`` calls must produce
exactly one ``duplicate_of IS NULL`` row and ``N - 1`` rows pointing
at it.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import (
    Attachment,
    ClientInteraction,
    InteractionType,
    RealClient,
)
from app.models.domain_event import DomainEvent
from app.models.training import TrainingSession
from app.services.attachment_storage import (
    StoredAttachment,
    infer_document_type,
    ocr_status_for,
    store_attachment_bytes,
)
from app.services.client_domain import (
    bind_attachment_to_lead_client,
    create_crm_interaction_with_event,
    emit_domain_event,
    ensure_lead_client,
    is_event_persisted,
)

logger = logging.getLogger(__name__)


# ── Source labels (spec §7.2 audit-trail) ─────────────────────────────────
#
# ``source`` is a free-form column on DomainEvent capped at 30 chars; using
# this set centrally lets the AST guard verify producers don't invent new
# values at the call site.
SOURCE_CRM_UPLOAD = "api.clients.attachment"
SOURCE_TRAINING_UPLOAD = "api.training.attachment"
SOURCE_AV_WORKER = "worker.av"
SOURCE_OCR_WORKER = "worker.ocr"
SOURCE_CLASSIFIER_WORKER = "worker.classifier"
SOURCE_VERIFICATION_REVIEW = "review.verification"


# ── Public types ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class IngestResult:
    """Return shape of :func:`ingest_upload`.

    Holding the duplicate-vs-original signal as a flag (rather than just a
    nullable ``duplicate_of`` field on the row) lets callers branch on it
    without re-reading the row, and keeps the type annotation clean for
    the API layer that must produce different responses for the two
    paths.
    """

    attachment: Attachment
    is_duplicate: bool
    upload_event: DomainEvent
    interaction: ClientInteraction | None
    interaction_event: DomainEvent | None


# ── Main entry point ──────────────────────────────────────────────────────


async def ingest_upload(
    db: AsyncSession,
    *,
    client: RealClient,
    uploaded_by: uuid.UUID | None,
    raw_bytes: bytes,
    raw_filename: str | None,
    content_type: str | None,
    source: str,
    session: TrainingSession | None = None,
    message_id: uuid.UUID | None = None,
    call_attempt_id: uuid.UUID | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> IngestResult:
    """Persist a new attachment for ``client``.

    See module docstring for the dedup algorithm. Callers do **not**
    construct ``Attachment`` rows themselves — the AST guard rejects any
    such code path. The interaction + ``session.attachment_linked`` event
    are emitted in the same transaction so the CRM timeline and the
    canonical event log stay aligned (spec §7.4).

    Parameters intentionally mirror the old call-site shape (typed
    kwargs, no positional args) so the migration of
    ``api/clients.py`` and ``api/training.py`` is mechanical — only the
    function name and the metadata-key set change.
    """
    if not raw_bytes:
        raise ValueError("attachment payload is empty")

    stored: StoredAttachment = store_attachment_bytes(
        client_id=str(client.id),
        filename=raw_filename,
        data=raw_bytes,
    )
    document_type = infer_document_type(stored.filename, content_type)

    lead = await ensure_lead_client(db, client=client)

    base_metadata: dict[str, Any] = {
        "source": source,
        "original_filename": raw_filename,
    }
    if extra_metadata:
        base_metadata.update(extra_metadata)

    attachment, is_duplicate, original_id = await _insert_with_dedup(
        db,
        client=client,
        lead_id=lead.id,
        uploaded_by=uploaded_by,
        session=session,
        message_id=message_id,
        call_attempt_id=call_attempt_id,
        stored=stored,
        content_type=content_type,
        document_type=document_type,
        base_metadata=base_metadata,
    )

    upload_event = await _emit_upload_event(
        db,
        attachment=attachment,
        lead_id=lead.id,
        uploaded_by=uploaded_by,
        source=source,
        session=session,
        message_id=message_id,
        is_duplicate=is_duplicate,
        original_id=original_id,
    )
    if is_event_persisted(upload_event):
        attachment.domain_event_id = upload_event.id
        if attachment.metadata_ is None:
            attachment.metadata_ = {}
        attachment.metadata_ = {
            **(attachment.metadata_ or {}),
            "domain_event_id": str(upload_event.id),
            "duplicate_of": str(original_id) if original_id else None,
        }

    interaction: ClientInteraction | None = None
    interaction_event: DomainEvent | None = None
    if session is not None or message_id is not None:
        interaction, interaction_event = await _emit_linkage_event(
            db,
            client=client,
            attachment=attachment,
            stored=stored,
            document_type=document_type,
            uploaded_by=uploaded_by,
            session=session,
            message_id=message_id,
            source=source,
            is_duplicate=is_duplicate,
            original_id=original_id,
        )
        if interaction is not None:
            attachment.interaction_id = interaction.id

    await db.flush()
    return IngestResult(
        attachment=attachment,
        is_duplicate=is_duplicate,
        upload_event=upload_event,
        interaction=interaction,
        interaction_event=interaction_event,
    )


async def _insert_with_dedup(
    db: AsyncSession,
    *,
    client: RealClient,
    lead_id: uuid.UUID,
    uploaded_by: uuid.UUID | None,
    session: TrainingSession | None,
    message_id: uuid.UUID | None,
    call_attempt_id: uuid.UUID | None,
    stored: StoredAttachment,
    content_type: str | None,
    document_type: str,
    base_metadata: dict[str, Any],
) -> tuple[Attachment, bool, uuid.UUID | None]:
    """Insert the attachment row, resolving the dedup race with a single
    re-select on IntegrityError.

    Returns ``(attachment, is_duplicate, original_id)`` where
    ``original_id`` is the id of the existing original when the new row is
    a duplicate, otherwise ``None``.
    """
    existing_original = await _find_original(db, lead_id=lead_id, sha256=stored.sha256)

    duplicate_of: uuid.UUID | None = (
        existing_original.id if existing_original is not None else None
    )

    attachment = _build_attachment_row(
        client=client,
        lead_id=lead_id,
        uploaded_by=uploaded_by,
        session=session,
        message_id=message_id,
        call_attempt_id=call_attempt_id,
        stored=stored,
        content_type=content_type,
        document_type=document_type,
        duplicate_of=duplicate_of,
        base_metadata=base_metadata,
    )
    db.add(attachment)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        # Race: another writer won ``uq_attachments_client_sha256_orig``
        # while we were between the SELECT and the INSERT. The savepoint
        # context manager rolled the failed INSERT back automatically,
        # so the outer transaction is still alive — we re-SELECT the
        # now-committed original and insert ourselves as a duplicate.
        original = await _find_original(db, lead_id=lead_id, sha256=stored.sha256)
        if original is None:
            # Should not happen: the only way the partial-unique index
            # raises is when an original exists. Surface anyway so the
            # caller learns about the inconsistency instead of silently
            # losing the upload.
            raise
        attachment = _build_attachment_row(
            client=client,
            lead_id=lead_id,
            uploaded_by=uploaded_by,
            session=session,
            message_id=message_id,
            call_attempt_id=call_attempt_id,
            stored=stored,
            content_type=content_type,
            document_type=document_type,
            duplicate_of=original.id,
            base_metadata=base_metadata,
        )
        db.add(attachment)
        await db.flush()
        return attachment, True, original.id

    is_duplicate = duplicate_of is not None
    return attachment, is_duplicate, duplicate_of


async def _find_original(
    db: AsyncSession, *, lead_id: uuid.UUID, sha256: str
) -> Attachment | None:
    return (
        await db.execute(
            select(Attachment)
            .where(
                Attachment.lead_client_id == lead_id,
                Attachment.sha256 == sha256,
                Attachment.duplicate_of.is_(None),
            )
            .order_by(Attachment.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()


def _build_attachment_row(
    *,
    client: RealClient,
    lead_id: uuid.UUID,
    uploaded_by: uuid.UUID | None,
    session: TrainingSession | None,
    message_id: uuid.UUID | None,
    call_attempt_id: uuid.UUID | None,
    stored: StoredAttachment,
    content_type: str | None,
    document_type: str,
    duplicate_of: uuid.UUID | None,
    base_metadata: dict[str, Any],
) -> Attachment:
    metadata: dict[str, Any] = dict(base_metadata)
    metadata["duplicate_of"] = str(duplicate_of) if duplicate_of else None
    return Attachment(
        uploaded_by=uploaded_by,
        client_id=client.id,
        lead_client_id=lead_id,
        session_id=session.id if session is not None else None,
        message_id=message_id,
        call_attempt_id=call_attempt_id,
        filename=stored.filename,
        content_type=content_type,
        file_size=stored.file_size,
        sha256=stored.sha256,
        storage_path=stored.storage_path,
        public_url=stored.public_url,
        document_type=document_type,
        status="received",
        ocr_status=ocr_status_for(document_type),
        classification_status="pending",
        verification_status="unverified",
        duplicate_of=duplicate_of,
        metadata_=metadata,
    )


# ── Event emit helpers ────────────────────────────────────────────────────


async def _emit_upload_event(
    db: AsyncSession,
    *,
    attachment: Attachment,
    lead_id: uuid.UUID,
    uploaded_by: uuid.UUID | None,
    source: str,
    session: TrainingSession | None,
    message_id: uuid.UUID | None,
    is_duplicate: bool,
    original_id: uuid.UUID | None,
) -> DomainEvent:
    event_type = "attachment.duplicate_detected" if is_duplicate else "attachment.uploaded"
    payload: dict[str, Any] = {
        "attachment_id": str(attachment.id),
        "client_id": str(attachment.client_id),
        "sha256": attachment.sha256,
        "filename": attachment.filename,
        "document_type": attachment.document_type,
        "file_size": attachment.file_size,
        "status": attachment.status,
    }
    if is_duplicate and original_id is not None:
        payload["duplicate_of"] = str(original_id)
    if session is not None:
        payload["session_id"] = str(session.id)
    if message_id is not None:
        payload["message_id"] = str(message_id)

    # Idempotency key includes the row id so a retry inside the same txn
    # converges on the same DomainEvent. The two distinct event types
    # never share a key so a duplicate row's emit can't be deduped against
    # an original's emit (or vice versa).
    idempotency_key = f"{event_type}:{attachment.id}"

    return await emit_domain_event(
        db,
        lead_client_id=lead_id,
        event_type=event_type,
        actor_type="user" if uploaded_by else "system",
        actor_id=uploaded_by,
        source=source,
        aggregate_type="attachment",
        aggregate_id=attachment.id,
        session_id=session.id if session is not None else None,
        payload=payload,
        idempotency_key=idempotency_key,
    )


async def _emit_linkage_event(
    db: AsyncSession,
    *,
    client: RealClient,
    attachment: Attachment,
    stored: StoredAttachment,
    document_type: str,
    uploaded_by: uuid.UUID | None,
    session: TrainingSession | None,
    message_id: uuid.UUID | None,
    source: str,
    is_duplicate: bool,
    original_id: uuid.UUID | None,
) -> tuple[ClientInteraction | None, DomainEvent | None]:
    """Mirror the existing CRM interaction + ``session.attachment_linked``
    contract that the legacy call sites produced. Adding
    ``attachment.linked`` (TZ-4 §7.3) on top of the legacy event keeps
    new readers happy without breaking the two existing CRM-timeline
    consumers (the FE timeline + the parity tests).
    """
    session_mode = None
    if session is not None:
        custom = (session.custom_params or {})
        session_mode = (custom.get("session_mode") or "chat").lower()
    base_payload: dict[str, Any] = {
        "attachment_id": str(attachment.id),
        "session_id": str(session.id) if session is not None else None,
        "training_session_id": str(session.id) if session is not None else None,
        "session_mode": session_mode,
        "message_id": str(message_id) if message_id else None,
        "sha256": stored.sha256,
        "document_type": document_type,
        "ocr_status": attachment.ocr_status,
        "classification_status": attachment.classification_status,
        "duplicate_of": str(original_id) if original_id else None,
    }
    metadata = dict(base_payload)
    content = (
        f"Получен файл в сессии {session_mode}: {stored.filename}"
        if session is not None
        else f"Получен файл: {stored.filename}"
    )

    interaction, legacy_event = await create_crm_interaction_with_event(
        db,
        client=client,
        manager_id=uploaded_by,
        interaction_type=InteractionType.system,
        content=content,
        result="attachment_received" if not is_duplicate else "attachment_duplicate",
        metadata=metadata,
        payload=base_payload,
        event_type="session.attachment_linked",
        source=source,
        actor_type="user" if uploaded_by else "system",
        actor_id=uploaded_by,
        session_id=session.id if session is not None else None,
        idempotency_key=f"attachment-link:{attachment.id}",
    )

    # TZ-4 §7.3 mandates ``attachment.linked`` in addition to the legacy
    # ``session.attachment_linked``. The two co-exist intentionally — the
    # legacy event powers the FE timeline today; the canonical
    # ``attachment.linked`` is the read path for new TZ-4 surfaces (NBA,
    # ClientAttachments rev 2). Different idempotency keys keep them
    # independent.
    await emit_domain_event(
        db,
        lead_client_id=attachment.lead_client_id,
        event_type="attachment.linked",
        actor_type="user" if uploaded_by else "system",
        actor_id=uploaded_by,
        source=source,
        aggregate_type="attachment",
        aggregate_id=attachment.id,
        session_id=session.id if session is not None else None,
        payload=base_payload,
        idempotency_key=f"attachment.linked:{attachment.id}",
    )
    return interaction, legacy_event


# ── State transition helpers ──────────────────────────────────────────────
#
# Each helper is the only sanctioned writer of its target column. Adding
# another writer requires either calling these helpers or extending the
# ``test_attachment_status_writes_are_gated_through_pipeline`` allow-list
# under TZ-4 §13.2.1 review.


async def mark_av_passed(
    db: AsyncSession,
    *,
    attachment: Attachment,
    actor_id: uuid.UUID | None = None,
    source: str = SOURCE_AV_WORKER,
    notes: str | None = None,
) -> DomainEvent:
    """Antivirus scan succeeded. ``status`` stays ``received`` — the AV
    decision lives in the event log, not in the lifecycle column."""
    payload: dict[str, Any] = {"attachment_id": str(attachment.id)}
    if notes:
        payload["notes"] = notes
    return await emit_domain_event(
        db,
        lead_client_id=attachment.lead_client_id,
        event_type="attachment.av_passed",
        actor_type="system" if actor_id is None else "user",
        actor_id=actor_id,
        source=source,
        aggregate_type="attachment",
        aggregate_id=attachment.id,
        payload=payload,
        idempotency_key=f"attachment.av_passed:{attachment.id}",
    )


async def mark_av_rejected(
    db: AsyncSession,
    *,
    attachment: Attachment,
    reason: str,
    actor_id: uuid.UUID | None = None,
    source: str = SOURCE_AV_WORKER,
) -> DomainEvent:
    """Antivirus scan failed → terminal ``status='rejected'``. The file
    bytes are still on disk; the row is preserved so the CRM timeline
    keeps a record of the rejection."""
    attachment.status = "rejected"
    return await emit_domain_event(
        db,
        lead_client_id=attachment.lead_client_id,
        event_type="attachment.av_rejected",
        actor_type="system" if actor_id is None else "user",
        actor_id=actor_id,
        source=source,
        aggregate_type="attachment",
        aggregate_id=attachment.id,
        payload={"attachment_id": str(attachment.id), "reason": reason},
        idempotency_key=f"attachment.av_rejected:{attachment.id}",
    )


async def mark_ocr_completed(
    db: AsyncSession,
    *,
    attachment: Attachment,
    extracted_chars: int | None = None,
    actor_id: uuid.UUID | None = None,
    source: str = SOURCE_OCR_WORKER,
) -> DomainEvent:
    """OCR worker reports completion. ``ocr_status`` flips to ``completed``
    even if zero characters were extracted — empty OCR is a valid result,
    distinct from ``failed``."""
    attachment.ocr_status = "completed"
    payload: dict[str, Any] = {"attachment_id": str(attachment.id)}
    if extracted_chars is not None:
        payload["extracted_chars"] = extracted_chars
    return await emit_domain_event(
        db,
        lead_client_id=attachment.lead_client_id,
        event_type="attachment.ocr_completed",
        actor_type="system" if actor_id is None else "user",
        actor_id=actor_id,
        source=source,
        aggregate_type="attachment",
        aggregate_id=attachment.id,
        payload=payload,
        idempotency_key=f"attachment.ocr_completed:{attachment.id}",
    )


async def mark_classified(
    db: AsyncSession,
    *,
    attachment: Attachment,
    document_type: str,
    confidence: float | None = None,
    actor_id: uuid.UUID | None = None,
    source: str = SOURCE_CLASSIFIER_WORKER,
) -> DomainEvent:
    """Classifier produced a ``document_type``. We update the row column
    too because downstream readers (NBA, ClientAttachments) join on
    ``document_type`` rather than chasing the latest event payload."""
    attachment.document_type = document_type
    attachment.classification_status = "completed"
    payload: dict[str, Any] = {
        "attachment_id": str(attachment.id),
        "document_type": document_type,
    }
    if confidence is not None:
        payload["confidence"] = confidence
    return await emit_domain_event(
        db,
        lead_client_id=attachment.lead_client_id,
        event_type="attachment.classified",
        actor_type="system" if actor_id is None else "user",
        actor_id=actor_id,
        source=source,
        aggregate_type="attachment",
        aggregate_id=attachment.id,
        payload=payload,
        idempotency_key=f"attachment.classified:{attachment.id}",
    )


async def mark_verified(
    db: AsyncSession,
    *,
    attachment: Attachment,
    reviewer_id: uuid.UUID,
    notes: str | None = None,
) -> DomainEvent:
    """Manual review accepted the document — ``verification_status`` ends
    in ``verified`` (terminal per spec §7.1.1). Future re-uploads create a
    new ``Attachment`` row rather than mutating this one."""
    attachment.verification_status = "verified"
    payload: dict[str, Any] = {
        "attachment_id": str(attachment.id),
        "reviewer_id": str(reviewer_id),
    }
    if notes:
        payload["notes"] = notes
    return await emit_domain_event(
        db,
        lead_client_id=attachment.lead_client_id,
        event_type="attachment.verified",
        actor_type="user",
        actor_id=reviewer_id,
        source=SOURCE_VERIFICATION_REVIEW,
        aggregate_type="attachment",
        aggregate_id=attachment.id,
        payload=payload,
        idempotency_key=f"attachment.verified:{attachment.id}",
    )


async def mark_rejected(
    db: AsyncSession,
    *,
    attachment: Attachment,
    reviewer_id: uuid.UUID,
    reason: str,
) -> DomainEvent:
    """Manual review rejected the document — ``verification_status`` ends
    in ``rejected_review`` (terminal). Distinct from ``av_rejected``: that
    one writes ``status='rejected'`` because the AV scan failed at intake;
    this one writes ``verification_status='rejected_review'`` after a
    person looked at the file."""
    attachment.verification_status = "rejected_review"
    return await emit_domain_event(
        db,
        lead_client_id=attachment.lead_client_id,
        event_type="attachment.rejected",
        actor_type="user",
        actor_id=reviewer_id,
        source=SOURCE_VERIFICATION_REVIEW,
        aggregate_type="attachment",
        aggregate_id=attachment.id,
        payload={
            "attachment_id": str(attachment.id),
            "reviewer_id": str(reviewer_id),
            "reason": reason,
        },
        idempotency_key=f"attachment.rejected:{attachment.id}",
    )


__all__ = [
    "IngestResult",
    "SOURCE_AV_WORKER",
    "SOURCE_CLASSIFIER_WORKER",
    "SOURCE_CRM_UPLOAD",
    "SOURCE_OCR_WORKER",
    "SOURCE_TRAINING_UPLOAD",
    "SOURCE_VERIFICATION_REVIEW",
    "ingest_upload",
    "mark_av_passed",
    "mark_av_rejected",
    "mark_classified",
    "mark_ocr_completed",
    "mark_rejected",
    "mark_verified",
]
