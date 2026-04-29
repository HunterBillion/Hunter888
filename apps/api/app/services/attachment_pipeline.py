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
# TZ-5 §3 — scenario_extractor service writes through these helpers when
# transitioning training_material attachments through the post-classified
# branch. Distinct source label so the audit trail clearly attributes the
# transition to the import funnel rather than the generic classifier.
SOURCE_SCENARIO_EXTRACTOR = "service.scenario_extractor"
SOURCE_SCENARIO_IMPORT = "api.scenarios.import"


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

    # D7.3 emit-first refactor: the upload event is emitted INSIDE
    # ``_insert_with_dedup`` and the attachment is INSERTed with
    # ``domain_event_id`` already set, so the row never sits with
    # NULL FK in the DB. The savepoint that wraps emit + insert
    # rolls both back together on a dedup-race ``IntegrityError``,
    # so we never leave an orphan event referring to an attachment
    # that didn't make it.
    attachment, is_duplicate, original_id, upload_event = await _insert_with_dedup(
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
        source=source,
    )
    # The post-insert metadata patch keeps the legacy shape that
    # previous PRs encoded into payloads + audit logs. The FK is
    # already set; this is just bookkeeping for downstream readers
    # that look at metadata.domain_event_id directly.
    if is_event_persisted(upload_event):
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
    source: str,
) -> tuple[Attachment, bool, uuid.UUID | None, DomainEvent]:
    """Emit upload event + INSERT attachment as a single atomic unit.

    D7.3 emit-first refactor: the attachment row is INSERTed with
    ``domain_event_id`` already pointing at the freshly-emitted
    ``attachment.uploaded`` (or ``attachment.duplicate_detected``)
    event. The row therefore never sits with a NULL FK in the DB,
    which lets D7.3's migration promote ``attachments.domain_event_id``
    to NOT NULL.

    Both writes happen inside a single ``begin_nested()`` savepoint.
    On a dedup-race ``IntegrityError`` (the partial UNIQUE index
    ``uq_attachments_client_sha256_orig`` rejected our INSERT because
    another writer became the original first) the savepoint rolls
    BOTH the event AND the attachment INSERT back together — no
    orphan event in the canonical log.

    Returns ``(attachment, is_duplicate, original_id, upload_event)``.
    The event is the persisted one (or a transient stub when
    ``client_domain_dual_write_enabled`` is False — the ``is_event_
    persisted`` check downstream still applies).
    """
    existing_original = await _find_original(db, lead_id=lead_id, sha256=stored.sha256)
    duplicate_of: uuid.UUID | None = (
        existing_original.id if existing_original is not None else None
    )

    try:
        async with db.begin_nested():
            attachment, upload_event = await _emit_and_insert(
                db,
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
                source=source,
            )
    except IntegrityError:
        # Race: another writer won the partial UNIQUE index while we
        # were between SELECT and INSERT. Re-fetch the now-committed
        # original and emit + insert a duplicate row instead. The
        # outer business txn is still alive because the savepoint
        # rolled both the event AND the failed INSERT back together.
        original = await _find_original(db, lead_id=lead_id, sha256=stored.sha256)
        if original is None:
            # The partial-unique index can only raise when an original
            # exists — surface the inconsistency instead of silently
            # losing the upload.
            raise
        async with db.begin_nested():
            attachment, upload_event = await _emit_and_insert(
                db,
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
                source=source,
            )
        return attachment, True, original.id, upload_event

    is_duplicate = duplicate_of is not None
    return attachment, is_duplicate, duplicate_of, upload_event


async def _emit_and_insert(
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
    duplicate_of: uuid.UUID | None,
    base_metadata: dict[str, Any],
    source: str,
) -> tuple[Attachment, DomainEvent]:
    """Inside-savepoint helper: emit the upload event with the future
    attachment id baked in, then INSERT the attachment with
    ``domain_event_id`` pre-set. Caller is responsible for the
    surrounding savepoint and IntegrityError handling.
    """
    attachment_id = uuid.uuid4()
    is_duplicate = duplicate_of is not None
    upload_event = await _emit_upload_event(
        db,
        attachment_id=attachment_id,
        lead_id=lead_id,
        uploaded_by=uploaded_by,
        source=source,
        session=session,
        message_id=message_id,
        is_duplicate=is_duplicate,
        original_id=duplicate_of,
        sha256=stored.sha256,
        filename=stored.filename,
        document_type=document_type,
        file_size=stored.file_size,
    )
    domain_event_id = upload_event.id if is_event_persisted(upload_event) else None

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
        attachment_id=attachment_id,
        domain_event_id=domain_event_id,
    )
    db.add(attachment)
    await db.flush()
    return attachment, upload_event


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
    attachment_id: uuid.UUID | None = None,
    domain_event_id: uuid.UUID | None = None,
) -> Attachment:
    """Construct an Attachment ORM row.

    D7.3 added ``attachment_id`` + ``domain_event_id`` kwargs so the
    pipeline can pre-emit the canonical event and INSERT the row
    with the FK pre-set, making
    ``attachments.domain_event_id NOT NULL`` a hard constraint.
    Both kwargs default to None to keep the helper usable from
    legacy / repair paths during the migration window.
    """
    metadata: dict[str, Any] = dict(base_metadata)
    metadata["duplicate_of"] = str(duplicate_of) if duplicate_of else None
    if domain_event_id is not None:
        metadata["domain_event_id"] = str(domain_event_id)
    return Attachment(
        id=attachment_id if attachment_id is not None else uuid.uuid4(),
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
        # B1 — spec §7.1.1 canonical ``classification_pending`` (was
        # ``pending``). Migration ``20260427_004`` updates legacy rows.
        classification_status="classification_pending",
        verification_status="unverified",
        duplicate_of=duplicate_of,
        domain_event_id=domain_event_id,
        metadata_=metadata,
    )


# ── Event emit helpers ────────────────────────────────────────────────────


async def _emit_upload_event(
    db: AsyncSession,
    *,
    attachment_id: uuid.UUID,
    lead_id: uuid.UUID,
    uploaded_by: uuid.UUID | None,
    source: str,
    session: TrainingSession | None,
    message_id: uuid.UUID | None,
    is_duplicate: bool,
    original_id: uuid.UUID | None,
    sha256: str,
    filename: str,
    document_type: str,
    file_size: int,
) -> DomainEvent:
    """D7.3 — accepts the future ``attachment_id`` (UUID) instead of
    a constructed Attachment object so the canonical event can be
    emitted BEFORE the attachment row is INSERTed. Lets us land the
    attachment with ``domain_event_id`` pre-filled and the
    ``NOT NULL`` constraint becomes safe."""
    event_type = "attachment.duplicate_detected" if is_duplicate else "attachment.uploaded"
    payload: dict[str, Any] = {
        "attachment_id": str(attachment_id),
        "sha256": sha256,
        "filename": filename,
        "document_type": document_type,
        "file_size": file_size,
        # Status is always 'received' at intake; the four state
        # machines fan out from here via the ``mark_*`` helpers.
        "status": "received",
    }
    if is_duplicate and original_id is not None:
        payload["duplicate_of"] = str(original_id)
    if session is not None:
        payload["session_id"] = str(session.id)
    if message_id is not None:
        payload["message_id"] = str(message_id)

    # Idempotency key includes the row id so a retry inside the same
    # txn converges on the same DomainEvent. The two distinct event
    # types never share a key so a duplicate row's emit can't be
    # deduped against an original's emit (or vice versa).
    idempotency_key = f"{event_type}:{attachment_id}"

    return await emit_domain_event(
        db,
        lead_client_id=lead_id,
        event_type=event_type,
        actor_type="user" if uploaded_by else "system",
        actor_id=uploaded_by,
        source=source,
        aggregate_type="attachment",
        aggregate_id=attachment_id,
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


async def ingest_training_material(
    db: AsyncSession,
    *,
    uploaded_by: uuid.UUID,
    raw_bytes: bytes,
    raw_filename: str | None,
    content_type: str | None,
    source: str = SOURCE_SCENARIO_IMPORT,
    extra_metadata: dict[str, Any] | None = None,
    allowed_extensions: frozenset[str] | None = None,
) -> Attachment:
    """TZ-5 §3 — sibling of :func:`ingest_upload` for ROP-uploaded
    training materials.

    Differences from :func:`ingest_upload`:
      * No ``client``: training materials live outside the CRM domain.
        ``client_id`` and ``lead_client_id`` are both NULL on the row;
        ``call_attempt_id`` / ``session_id`` / ``message_id`` are also
        unused.
      * No interaction event: there's no CRM timeline to project onto.
      * Document type is forced to ``training_material`` (the API endpoint
        signals intent — we don't infer this from the extension because
        the same .pdf may be a passport scan in another flow).
      * Larger size budget (caller validates with
        ``MAX_TRAINING_MATERIAL_BYTES``); this helper itself doesn't gate.

    The dedup contract still applies: the same bytes uploaded twice by
    different ROPs return the same ``original`` row + a duplicate marker
    via the partial UNIQUE index, but only when both share the same
    ``lead_client_id`` (NULL for training materials, so dedup is per
    ``(NULL, sha256)``). PostgreSQL treats NULLs as distinct in UNIQUE
    indexes by default — so cross-ROP dedup is not enforced for training
    materials. That's intentional: we don't want one ROP's "delete this
    course material" to surface another ROP's still-needed copy.

    Returns the persisted Attachment row in state
    ``status=received, ocr_status=*, classification_status=classification_pending``
    with ``document_type='training_material'``. The caller is responsible
    for calling :func:`mark_classified` (with ``document_type='training_material'``)
    before transitioning into the scenario_extractor branch via
    :func:`mark_scenario_draft_extracting`.
    """
    if not raw_bytes:
        raise ValueError("training material payload is empty")

    from app.services.attachment_storage import (
        ALLOWED_EXTENSIONS,
        StoredAttachment,
        ocr_status_for,
        store_attachment_bytes,
    )

    # Storage layer handles extension whitelist + safe filename + sha256.
    # Training-material API passes the narrower ``TRAINING_MATERIAL_EXTENSIONS``
    # set so the rejection error points at the correct allowlist.
    #
    # Audit fix (PR-1.1): bucket per-uploader so a guessed URL under the
    # shared bucket directory cannot cross-reference another ROP's
    # uploads. Reads are also gated by the auth'd /rop/scenarios/drafts/
    # {id}/download endpoint — the generic StaticFiles mount returns
    # 403 for `_training_materials/...` paths now.
    stored: StoredAttachment = store_attachment_bytes(
        client_id=f"_training_materials/{uploaded_by}",
        filename=raw_filename,
        data=raw_bytes,
        allowed_extensions=allowed_extensions or ALLOWED_EXTENSIONS,
    )
    document_type = "training_material"

    base_metadata: dict[str, Any] = {
        "source": source,
        "original_filename": raw_filename,
        "kind": "training_material",
    }
    if extra_metadata:
        base_metadata.update(extra_metadata)

    attachment_id = uuid.uuid4()
    upload_event = await emit_domain_event(
        db,
        # Training materials have no lead_client; the canonical event log
        # accepts NULL here (events without a lead_client_id still anchor
        # via aggregate_id=attachment_id).
        lead_client_id=None,
        event_type="attachment.uploaded",
        actor_type="user",
        actor_id=uploaded_by,
        source=source,
        aggregate_type="attachment",
        aggregate_id=attachment_id,
        payload={
            "attachment_id": str(attachment_id),
            "sha256": stored.sha256,
            "filename": stored.filename,
            "document_type": document_type,
            "file_size": stored.file_size,
            "kind": "training_material",
            "status": "received",
        },
        idempotency_key=f"attachment.uploaded.training_material:{attachment_id}",
    )
    domain_event_id = upload_event.id if is_event_persisted(upload_event) else None

    attachment = Attachment(
        id=attachment_id,
        uploaded_by=uploaded_by,
        # No CRM bindings — training materials are team assets.
        client_id=None,
        lead_client_id=None,
        session_id=None,
        message_id=None,
        call_attempt_id=None,
        filename=stored.filename,
        content_type=content_type,
        file_size=stored.file_size,
        sha256=stored.sha256,
        storage_path=stored.storage_path,
        public_url=stored.public_url,
        document_type=document_type,
        status="received",
        ocr_status=ocr_status_for(document_type),
        classification_status="classification_pending",
        verification_status="unverified",
        duplicate_of=None,
        domain_event_id=domain_event_id,
        metadata_={**base_metadata, "domain_event_id": str(domain_event_id) if domain_event_id else None},
    )
    db.add(attachment)
    await db.flush()
    return attachment


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
    """OCR worker reports completion. ``ocr_status`` flips to ``ocr_done``
    (spec §7.1.1 canonical) even if zero characters were extracted —
    empty OCR is a valid result, distinct from ``ocr_failed``."""
    attachment.ocr_status = "ocr_done"
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
    ``document_type`` rather than chasing the latest event payload.

    B1 — terminal value is ``classified`` per spec §7.1.1 (replaces the
    legacy ``completed`` token shared with ocr/lifecycle status).

    Audit-2026-04-28: refuse empty / blank ``document_type`` outright.
    A classifier returning a blank string would silently overwrite the
    row's previously-known ``document_type`` (from intake) and then
    flag classification as terminal — downstream readers would see a
    "classified" row with no class. Better to fail fast at the helper
    so the worker retries instead.
    """
    if not document_type or not document_type.strip():
        raise ValueError(
            "mark_classified requires a non-empty document_type "
            "(empty / blank values would corrupt downstream reads)"
        )
    attachment.document_type = document_type
    attachment.classification_status = "classified"
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


async def mark_scenario_draft_extracting(
    db: AsyncSession,
    *,
    attachment: Attachment,
    actor_id: uuid.UUID | None = None,
    source: str = SOURCE_SCENARIO_EXTRACTOR,
) -> DomainEvent:
    """TZ-5 §3 — scenario_extractor picked up a ``training_material`` row
    for parsing. Transitions ``classification_status`` from ``classified``
    to ``scenario_draft_extracting`` so concurrent extractor workers can
    see the row is taken (a second worker SELECT-WHERE-classified misses
    it). The terminal ``classified`` token is preserved on
    ``document_type`` so downstream readers still see the row classified
    as a training material.

    Asymmetry note: only attachments with ``document_type='training_material'``
    are valid for this transition. The helper enforces it -- a misrouted
    row (e.g. a passport scan that the classifier mis-typed) would
    otherwise sit in ``scenario_draft_extracting`` forever because no
    extractor would touch it.
    """
    if attachment.document_type != "training_material":
        raise ValueError(
            "mark_scenario_draft_extracting requires "
            f"document_type='training_material', got "
            f"{attachment.document_type!r}"
        )
    if attachment.classification_status != "classified":
        raise ValueError(
            "mark_scenario_draft_extracting requires "
            f"classification_status='classified', got "
            f"{attachment.classification_status!r}"
        )
    attachment.classification_status = "scenario_draft_extracting"
    payload: dict[str, Any] = {"attachment_id": str(attachment.id)}
    return await emit_domain_event(
        db,
        lead_client_id=attachment.lead_client_id,
        event_type="attachment.scenario_draft_extracting",
        actor_type="system" if actor_id is None else "user",
        actor_id=actor_id,
        source=source,
        aggregate_type="attachment",
        aggregate_id=attachment.id,
        payload=payload,
        idempotency_key=f"attachment.scenario_draft_extracting:{attachment.id}",
    )


async def mark_scenario_draft_ready(
    db: AsyncSession,
    *,
    attachment: Attachment,
    draft_id: uuid.UUID,
    confidence: float,
    actor_id: uuid.UUID | None = None,
    source: str = SOURCE_SCENARIO_EXTRACTOR,
) -> DomainEvent:
    """TZ-5 §3 — extractor finished and persisted a ``ScenarioDraft`` row.
    Transitions ``classification_status`` to ``scenario_draft_ready``;
    the FE polls on this token to know when to stop showing the spinner
    and switch to the editable preview surface.

    ``confidence`` is included in the event payload so downstream readers
    (analytics, audit) can compute precision over time without reading
    the draft row directly.
    """
    if attachment.classification_status != "scenario_draft_extracting":
        raise ValueError(
            "mark_scenario_draft_ready requires "
            f"classification_status='scenario_draft_extracting', got "
            f"{attachment.classification_status!r}"
        )
    if not (0.0 <= confidence <= 1.0):
        raise ValueError(
            f"confidence must be in [0.0, 1.0], got {confidence!r}"
        )
    attachment.classification_status = "scenario_draft_ready"
    payload: dict[str, Any] = {
        "attachment_id": str(attachment.id),
        "draft_id": str(draft_id),
        "confidence": confidence,
    }
    return await emit_domain_event(
        db,
        lead_client_id=attachment.lead_client_id,
        event_type="attachment.scenario_draft_ready",
        actor_type="system" if actor_id is None else "user",
        actor_id=actor_id,
        source=source,
        aggregate_type="attachment",
        aggregate_id=attachment.id,
        payload=payload,
        idempotency_key=f"attachment.scenario_draft_ready:{attachment.id}",
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
    "SOURCE_SCENARIO_EXTRACTOR",
    "SOURCE_SCENARIO_IMPORT",
    "SOURCE_TRAINING_UPLOAD",
    "SOURCE_VERIFICATION_REVIEW",
    "ingest_training_material",
    "ingest_upload",
    "mark_av_passed",
    "mark_av_rejected",
    "mark_classified",
    "mark_ocr_completed",
    "mark_rejected",
    "mark_scenario_draft_extracting",
    "mark_scenario_draft_ready",
    "mark_verified",
]
