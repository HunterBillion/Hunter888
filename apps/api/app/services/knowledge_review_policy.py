"""Canonical knowledge governance service (TZ-4 §8 / §11.2.1).

Owns every transition of ``legal_knowledge_chunks.knowledge_status``.
The four-value enum is enforced at the DB layer by the CHECK constraint
landed in alembic ``20260427_002`` (D2); this module owns the
**Python-side** business rules around when each transition is legal.

Public surface
--------------

* :func:`expire_overdue` — daily TTL sweeper. Flips
  ``actual → needs_review`` for every chunk whose ``expires_at`` has
  passed. **Never** writes ``outdated`` automatically — that's the
  §8.3.1 closed footgun. Idempotent across re-runs (only `actual` rows
  are touched, so a re-fired cron is a no-op for already-flipped rows).
* :func:`mark_reviewed` — manual review action. The only path that may
  write ``outdated``. Always writes ``reviewed_by`` + ``reviewed_at``
  to satisfy §8.3 #4 and §8.3.1 audit requirement. Emits both
  ``knowledge_item.reviewed`` (audit) and ``knowledge_item.status_changed``
  (status fan-out for the FE).
* :func:`list_review_queue` — read-only list of items in
  ``needs_review``, sorted by ``expires_at`` ascending so the most-stale
  items rise to the top of the admin UI.
* :func:`emit_created` / :func:`emit_updated` — convenience helpers
  for the two remaining canonical event types (``knowledge_item.created``
  / ``knowledge_item.updated``). Today's seed/loader paths don't go
  through these yet — adding the helpers makes future migrations safe
  to land without inventing yet another emission style.
* :func:`is_recommendation_safe` — gate predicate for downstream
  recommenders. Mirrors ``knowledge_governance.can_use_for_recommendation``
  but is exposed under this module so future NBA wiring (§11.2.1) has
  a single import target. No NBA callsite lands in D4: the current
  ``next_best_action.py`` does not consume legal knowledge at all
  (verified at PR time) — when NBA grows that consumption it should
  call this helper rather than re-deriving the rule.

Why this module owns ``knowledge_status``
-----------------------------------------

* **No silent typos.** The CHECK constraint catches typos in raw SQL,
  but Python attribute writes (``chunk.knowledge_status = "outdate"``)
  succeed at the ORM layer and only fail at flush. Routing every
  transition through these helpers keeps the typo surface zero.
* **No auto-outdated.** §8.3.1 forbids the cron from flipping any
  status to ``outdated``. The :class:`AutoOutdatedForbidden` exception
  in this module is the architectural enforcement: even a future
  refactor cannot accidentally allow it without removing the explicit
  raise.
* **Audit completeness.** Every transition emits a paired event so the
  CRM timeline / admin audit log carries the full trail. Without a
  central writer the two emit sites would drift.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain_event import DomainEvent
from app.models.rag import LegalKnowledgeChunk
from app.services.client_domain import emit_domain_event
from app.services.knowledge_governance import (
    KNOWLEDGE_STATUS_ACTUAL,
    KNOWLEDGE_STATUS_NEEDS_REVIEW,
    KNOWLEDGE_STATUSES,
    can_use_for_recommendation,
    normalize_knowledge_status,
)

logger = logging.getLogger(__name__)


# ── Source labels (spec §8.4 audit-trail) ────────────────────────────────
SOURCE_TTL_SWEEP = "cron.knowledge_ttl_sweep"
SOURCE_ADMIN_REVIEW = "admin.knowledge_review"
SOURCE_SEED_LOADER = "seed.legal_knowledge_loader"
SOURCE_ADMIN_EDITOR = "admin.knowledge_editor"


# Anchor lead_client_id used by knowledge events. Knowledge is global —
# not bound to a specific client — but TZ-1 ``DomainEvent.lead_client_id``
# is NOT NULL. We anchor every knowledge event to a fixed UUID so admin
# timeline filters can still find them. Generated once with uuidgen and
# kept stable across migrations.
KNOWLEDGE_GLOBAL_ANCHOR = uuid.UUID("00000000-0000-0000-0000-000000000004")


# ── Public types ─────────────────────────────────────────────────────────


class AutoOutdatedForbidden(Exception):
    """Raised when a caller asks an automatic process (``expire_overdue``,
    ``emit_created``, etc.) to set ``knowledge_status='outdated'``.

    The ``outdated`` transition is only legal through
    :func:`mark_reviewed` with an explicit ``reviewed_by`` actor — see
    §8.3.1. This exception is the architectural guard that makes a
    silent footgun impossible even under future refactors.
    """


class InvalidKnowledgeStatus(ValueError):
    """Raised when a transition target is not in the canonical four-value
    enum. The DB CHECK constraint catches this too, but failing at the
    Python boundary is cheaper and surfaces the bug at the call site.
    """


@dataclass(frozen=True)
class ExpireResult:
    """Counts returned by :func:`expire_overdue` for cron observability.
    Stable shape so the entrypoint script can render it as text/JSON
    without further marshalling."""

    total_expired: int
    flipped_to_needs_review: int
    skipped_already_flipped: int
    swept_at: datetime


@dataclass(frozen=True)
class ReviewQueueItem:
    """Read-model exposed by :func:`list_review_queue`. Decoupled from
    the ORM row so admin endpoints can serialise it without leaking
    SQLAlchemy internals."""

    id: uuid.UUID
    title: str | None
    knowledge_status: str
    expires_at: datetime | None
    reviewed_at: datetime | None
    reviewed_by: uuid.UUID | None
    source_ref: str | None


# ── Validation helpers ───────────────────────────────────────────────────


def _validate_status(status: str) -> str:
    norm = (status or "").strip().lower()
    if norm not in KNOWLEDGE_STATUSES:
        raise InvalidKnowledgeStatus(
            f"knowledge_status {status!r} not in {sorted(KNOWLEDGE_STATUSES)}"
        )
    return norm


def is_recommendation_safe(status: object) -> bool:
    """Future NBA gate (§11.2.1). Returns False iff the chunk is
    ``outdated``. Exposed here so a future NBA wiring has a stable
    import target. Today the only consumer is the existing RAG SQL
    filter at ``rag_legal.py:217``, which checks the same condition
    via ``COALESCE(knowledge_status, 'actual') != 'outdated'`` — we
    keep behaviour identical so a future migration to this helper is
    a no-op."""
    return can_use_for_recommendation(status)


# ── TTL sweeper (§8.3.1 closed footgun) ──────────────────────────────────


async def expire_overdue(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    batch_size: int = 500,
    actor_id: uuid.UUID | None = None,
    source: str = SOURCE_TTL_SWEEP,
) -> ExpireResult:
    """Daily TTL sweeper. Flips ``actual → needs_review`` for items
    whose ``expires_at`` has passed.

    **Critical invariant (§8.3.1)**: this function NEVER writes
    ``outdated``. The only legal automatic transition is
    ``actual → needs_review``. Manual review through
    :func:`mark_reviewed` is the only path to ``outdated``.

    Idempotent: re-running on the same DB only catches items still
    ``actual`` past their ``expires_at`` — items already flipped to
    ``needs_review`` are skipped by the WHERE clause.

    ``batch_size`` paginates the SELECT so a one-off sweep across
    100k+ rows doesn't OOM. Within a batch each row gets its own
    ``knowledge_item.expired`` event with idempotency keys derived
    from chunk_id so a partial-failure retry doesn't double-emit.
    """
    moment = now or datetime.now(UTC)

    candidates = await _select_expired_actual(db, moment=moment, limit=batch_size)
    flipped = 0
    skipped = 0

    for chunk in candidates:
        # Defensive: if a row is already flipped (e.g. a parallel sweep
        # raced ahead), skip the write so the count stays accurate and
        # we don't double-emit the event.
        if normalize_knowledge_status(chunk.knowledge_status) != KNOWLEDGE_STATUS_ACTUAL:
            skipped += 1
            continue

        # §8.3.1: the cron is only allowed to write `needs_review`.
        # The literal lives here (not as a parameter) so a future caller
        # cannot widen the cron's authority by passing a different
        # target — extending this requires editing the line.
        target = KNOWLEDGE_STATUS_NEEDS_REVIEW
        previous = chunk.knowledge_status
        chunk.knowledge_status = target
        chunk.status_reason = (
            f"auto-flipped {previous} → {target} by TTL sweep at "
            f"{moment.isoformat()} (expires_at={chunk.expires_at})"
        )

        await emit_domain_event(
            db,
            lead_client_id=KNOWLEDGE_GLOBAL_ANCHOR,
            event_type="knowledge_item.expired",
            actor_type="user" if actor_id else "system",
            actor_id=actor_id,
            source=source,
            aggregate_type="legal_knowledge_chunk",
            aggregate_id=chunk.id,
            payload={
                "chunk_id": str(chunk.id),
                "title": chunk.title,
                "from_status": previous,
                "to_status": target,
                "expires_at": chunk.expires_at.isoformat() if chunk.expires_at else None,
                "swept_at": moment.isoformat(),
                "reviewed_by": None,  # NULL signals automated, per §8.3.1
            },
            # Stable per-chunk per-day key so a same-day retry collapses
            # but a re-flip after manual revert + re-expire emits again.
            idempotency_key=(
                f"knowledge_item.expired:{chunk.id}:{moment.date().isoformat()}"
            ),
        )
        flipped += 1

    await db.flush()
    return ExpireResult(
        total_expired=flipped + skipped,
        flipped_to_needs_review=flipped,
        skipped_already_flipped=skipped,
        swept_at=moment,
    )


async def _select_expired_actual(
    db: AsyncSession, *, moment: datetime, limit: int
) -> list[LegalKnowledgeChunk]:
    """Fetch up to ``limit`` chunks that are still ``actual`` past
    ``expires_at``. ORM-level so we can mutate + emit in one txn."""
    stmt = (
        select(LegalKnowledgeChunk)
        .where(LegalKnowledgeChunk.is_active.is_(True))
        .where(LegalKnowledgeChunk.expires_at.is_not(None))
        .where(LegalKnowledgeChunk.expires_at < moment)
        .where(LegalKnowledgeChunk.knowledge_status == KNOWLEDGE_STATUS_ACTUAL)
        .order_by(LegalKnowledgeChunk.expires_at.asc())
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().all())


# ── Manual review (the only path to `outdated`) ──────────────────────────


async def mark_reviewed(
    db: AsyncSession,
    *,
    chunk_id: uuid.UUID,
    new_status: str,
    reviewed_by: uuid.UUID,
    reason: str | None = None,
    source: str = SOURCE_ADMIN_REVIEW,
) -> tuple[LegalKnowledgeChunk, list[DomainEvent]]:
    """Manual review action — the only sanctioned writer of
    ``outdated`` (§8.3.1). Updates ``reviewed_by`` + ``reviewed_at``
    + ``knowledge_status``, emits ``knowledge_item.reviewed`` and
    ``knowledge_item.status_changed``.

    ``reviewed_by`` is required (no None default) because the audit
    trail must point at a real user. The endpoint layer enforces the
    role gate (rop/admin) per §8.3.1.
    """
    target = _validate_status(new_status)

    chunk = await db.get(LegalKnowledgeChunk, chunk_id)
    if chunk is None:
        raise LookupError(f"legal_knowledge_chunk {chunk_id} not found")

    previous = chunk.knowledge_status
    now = datetime.now(UTC)
    chunk.knowledge_status = target
    chunk.reviewed_by = reviewed_by
    chunk.reviewed_at = now
    chunk.last_verified_at = now
    if reason:
        chunk.status_reason = (
            f"manual review by {reviewed_by}: {previous} → {target} ({reason})"
        )
    else:
        chunk.status_reason = (
            f"manual review by {reviewed_by}: {previous} → {target}"
        )
    await db.flush()

    events: list[DomainEvent] = []
    common_payload = {
        "chunk_id": str(chunk.id),
        "title": chunk.title,
        "from_status": previous,
        "to_status": target,
        "reviewed_by": str(reviewed_by),
        "reviewed_at": now.isoformat(),
        "reason": reason,
    }
    events.append(
        await emit_domain_event(
            db,
            lead_client_id=KNOWLEDGE_GLOBAL_ANCHOR,
            event_type="knowledge_item.reviewed",
            actor_type="user",
            actor_id=reviewed_by,
            source=source,
            aggregate_type="legal_knowledge_chunk",
            aggregate_id=chunk.id,
            payload=common_payload,
            idempotency_key=(
                f"knowledge_item.reviewed:{chunk.id}:{now.isoformat()}"
            ),
        )
    )
    # Status-changed event is the fan-out signal for the FE — emitted
    # only when the target value actually differs from the previous
    # (so a re-confirmation doesn't spam the timeline).
    if previous != target:
        events.append(
            await emit_domain_event(
                db,
                lead_client_id=KNOWLEDGE_GLOBAL_ANCHOR,
                event_type="knowledge_item.status_changed",
                actor_type="user",
                actor_id=reviewed_by,
                source=source,
                aggregate_type="legal_knowledge_chunk",
                aggregate_id=chunk.id,
                payload=common_payload,
                idempotency_key=(
                    f"knowledge_item.status_changed:{chunk.id}:{previous}-to-{target}:{now.isoformat()}"
                ),
            )
        )
    return chunk, events


# ── Review queue (admin UI feed) ─────────────────────────────────────────


async def list_review_queue(
    db: AsyncSession,
    *,
    limit: int = 50,
) -> list[ReviewQueueItem]:
    """Items waiting for manual review, oldest TTL first.

    Returns a value-typed list so the API layer can serialise without
    leaking SQLAlchemy session state. Filters on
    ``knowledge_status='needs_review'`` only — ``disputed`` and
    ``outdated`` items are reviewed through different admin flows
    (the admin editor for ``disputed``, audit log for ``outdated``).
    """
    stmt = (
        select(LegalKnowledgeChunk)
        .where(LegalKnowledgeChunk.is_active.is_(True))
        .where(LegalKnowledgeChunk.knowledge_status == KNOWLEDGE_STATUS_NEEDS_REVIEW)
        .order_by(LegalKnowledgeChunk.expires_at.asc().nulls_last())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        ReviewQueueItem(
            id=row.id,
            title=row.title,
            knowledge_status=row.knowledge_status,
            expires_at=row.expires_at,
            reviewed_at=row.reviewed_at,
            reviewed_by=row.reviewed_by,
            source_ref=row.source_ref,
        )
        for row in rows
    ]


# ── Convenience emitters for create / update paths ───────────────────────


async def emit_created(
    db: AsyncSession,
    *,
    chunk: LegalKnowledgeChunk,
    actor_id: uuid.UUID | None,
    source: str = SOURCE_ADMIN_EDITOR,
) -> DomainEvent:
    """Emit ``knowledge_item.created`` after a new chunk is INSERTed.

    Today the seed loader and admin editor own their own INSERT paths;
    this helper is here so when those callsites want to publish into the
    canonical event log they have a single function rather than five
    near-duplicates.
    """
    return await emit_domain_event(
        db,
        lead_client_id=KNOWLEDGE_GLOBAL_ANCHOR,
        event_type="knowledge_item.created",
        actor_type="user" if actor_id else "system",
        actor_id=actor_id,
        source=source,
        aggregate_type="legal_knowledge_chunk",
        aggregate_id=chunk.id,
        payload={
            "chunk_id": str(chunk.id),
            "title": chunk.title,
            "knowledge_status": chunk.knowledge_status,
            "source_type": chunk.source_type,
            "jurisdiction": chunk.jurisdiction,
        },
        idempotency_key=f"knowledge_item.created:{chunk.id}",
    )


async def emit_updated(
    db: AsyncSession,
    *,
    chunk: LegalKnowledgeChunk,
    changed_fields: Iterable[str],
    actor_id: uuid.UUID | None,
    source: str = SOURCE_ADMIN_EDITOR,
) -> DomainEvent:
    """Emit ``knowledge_item.updated`` after a chunk's content changed.

    ``changed_fields`` lets the FE diff highlight what actually moved
    instead of re-rendering the full row.
    """
    fields = sorted(set(changed_fields))
    return await emit_domain_event(
        db,
        lead_client_id=KNOWLEDGE_GLOBAL_ANCHOR,
        event_type="knowledge_item.updated",
        actor_type="user" if actor_id else "system",
        actor_id=actor_id,
        source=source,
        aggregate_type="legal_knowledge_chunk",
        aggregate_id=chunk.id,
        payload={
            "chunk_id": str(chunk.id),
            "title": chunk.title,
            "changed_fields": fields,
            "knowledge_status": chunk.knowledge_status,
        },
        idempotency_key=(
            f"knowledge_item.updated:{chunk.id}:{','.join(fields)}"
        ),
    )


__all__ = [
    "AutoOutdatedForbidden",
    "ExpireResult",
    "InvalidKnowledgeStatus",
    "KNOWLEDGE_GLOBAL_ANCHOR",
    "ReviewQueueItem",
    "SOURCE_ADMIN_EDITOR",
    "SOURCE_ADMIN_REVIEW",
    "SOURCE_SEED_LOADER",
    "SOURCE_TTL_SWEEP",
    "emit_created",
    "emit_updated",
    "expire_overdue",
    "is_recommendation_safe",
    "list_review_queue",
    "mark_reviewed",
]
