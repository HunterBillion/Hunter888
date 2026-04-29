"""Canonical persona memory service (TZ-4 §6.3 / §6.4 / §9).

Two layers ship together:

* :class:`MemoryPersona` (cross-session) — one row per ``lead_client_id``,
  carries identity facts and the "do not ask again" slot list. Updated
  through explicit ``persona.updated`` events with optimistic-concurrency
  versioning (§9.2.5). Behaviour-level fields (objections, traps) stay on
  the legacy ``ClientProfile`` per spec §6.6 coexistence rules.

* :class:`SessionPersonaSnapshot` (per-session) — immutable row keyed by
  ``training_sessions.id``. Captured at session start by
  :func:`capture_for_session`. After INSERT the row is *never* updated;
  any attempt is observed via :func:`record_conflict_attempt` which
  bumps ``mutation_blocked_count`` and emits
  ``persona.conflict_detected``. This is what closes the root cause
  behind hotfix PR #55: the prompt assembler reads identity from this
  snapshot and nothing else, so an in-flight ``custom_params`` write
  cannot make the AI silently switch personas.

The four canonical events emitted from this module:

  - ``persona.snapshot_captured``  — at session start
  - ``persona.updated``            — when MemoryPersona identity changes
  - ``persona.slot_locked``        — when a "do not ask again" slot is
                                     locked (with optional confirmed fact)
  - ``persona.conflict_detected``  — runtime tried to mutate the snapshot

All four are pre-registered in
``client_domain.ALLOWED_EVENT_TYPES`` (D1.1).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain_event import DomainEvent
from app.models.persona import (
    ADDRESS_FORMS,
    GENDERS,
    PERSONA_CAPTURED_FROM,
    TONES,
    MemoryPersona,
    SessionPersonaSnapshot,
)
from app.models.training import TrainingSession
from app.services.client_domain import emit_domain_event

logger = logging.getLogger(__name__)


# ── Source labels (spec §9 audit-trail) ──────────────────────────────────
#
# Pre-defined values for the ``captured_from`` column on
# ``SessionPersonaSnapshot``. Mirroring ``PERSONA_CAPTURED_FROM`` from
# the model layer so callers can use named constants instead of
# stringly-typed literals.
CAPTURED_FROM_REAL_CLIENT = "real_client"
CAPTURED_FROM_HOME_PREVIEW = "home_preview"
CAPTURED_FROM_TRAINING_SIM = "training_simulation"
CAPTURED_FROM_PVP = "pvp"
CAPTURED_FROM_CENTER = "center"


# ── Public types ─────────────────────────────────────────────────────────


class PersonaConflict(Exception):
    """Raised on optimistic-concurrency mismatch (§9.2.5).

    The caller passed ``expected_version=N`` but the row in the DB is at
    ``version=M`` (M ≠ N). Caller decides whether to retry, surface as
    409 to the API client, or merge fields manually.
    """

    def __init__(self, *, expected: int, actual: int, lead_client_id: uuid.UUID):
        self.expected = expected
        self.actual = actual
        self.lead_client_id = lead_client_id
        super().__init__(
            f"persona version conflict for lead_client_id={lead_client_id}: "
            f"expected={expected}, actual={actual}"
        )


@dataclass(frozen=True)
class PersonaIdentity:
    """Identity payload supplied at capture time when no MemoryPersona row
    exists yet (e.g. the home_preview path where there is no real CRM
    client). The pipeline copies these straight into the snapshot.
    """

    full_name: str
    gender: str = "unknown"
    role_title: str | None = None
    address_form: str = "auto"
    tone: str = "neutral"


# ── Validation helpers ───────────────────────────────────────────────────


def _validate_identity(
    *,
    full_name: str,
    gender: str,
    address_form: str,
    tone: str,
    captured_from: str | None = None,
) -> None:
    """Mirror DB CHECK constraints in Python so we fail at the call site
    instead of getting an ``IntegrityError`` after a flush."""
    if not full_name or not full_name.strip():
        raise ValueError("persona full_name is required (§6.3.1 NOT NULL)")
    if gender not in GENDERS:
        raise ValueError(f"persona gender {gender!r} not in {sorted(GENDERS)}")
    if address_form not in ADDRESS_FORMS:
        raise ValueError(
            f"persona address_form {address_form!r} not in {sorted(ADDRESS_FORMS)}"
        )
    if tone not in TONES:
        raise ValueError(f"persona tone {tone!r} not in {sorted(TONES)}")
    if captured_from is not None and captured_from not in PERSONA_CAPTURED_FROM:
        raise ValueError(
            f"persona captured_from {captured_from!r} not in "
            f"{sorted(PERSONA_CAPTURED_FROM)}"
        )


# ── MemoryPersona upsert ─────────────────────────────────────────────────


async def get_for_lead(
    db: AsyncSession, *, lead_client_id: uuid.UUID
) -> MemoryPersona | None:
    return (
        await db.execute(
            select(MemoryPersona).where(MemoryPersona.lead_client_id == lead_client_id)
        )
    ).scalar_one_or_none()


async def upsert_for_lead(
    db: AsyncSession,
    *,
    lead_client_id: uuid.UUID,
    full_name: str,
    gender: str = "unknown",
    role_title: str | None = None,
    address_form: str = "auto",
    tone: str = "neutral",
    expected_version: int | None = None,
    actor_id: uuid.UUID | None = None,
    source: str = "service.persona_memory",
) -> tuple[MemoryPersona, DomainEvent | None]:
    """Create or update the MemoryPersona row for ``lead_client_id``.

    Returns ``(persona, event)`` where ``event`` is the
    ``persona.updated`` DomainEvent emitted when identity actually
    changed. Returns ``(persona, None)`` when the call was a no-op
    (initial INSERT happened in another caller or all incoming fields
    matched the existing row).

    Optimistic concurrency: when ``expected_version`` is provided and
    differs from the current row's ``version``, raises
    :class:`PersonaConflict`. Pass ``None`` to skip the check (only the
    very first INSERT path may safely do that).
    """
    _validate_identity(
        full_name=full_name,
        gender=gender,
        address_form=address_form,
        tone=tone,
    )

    existing = await get_for_lead(db, lead_client_id=lead_client_id)
    if existing is None:
        persona = MemoryPersona(
            lead_client_id=lead_client_id,
            full_name=full_name,
            gender=gender,
            role_title=role_title,
            address_form=address_form,
            tone=tone,
        )
        db.add(persona)
        await db.flush()
        # First write — emit persona.updated so timeline has a "born"
        # marker. The UI uses this to render "идентичность создана".
        event = await emit_domain_event(
            db,
            lead_client_id=lead_client_id,
            event_type="persona.updated",
            actor_type="user" if actor_id else "system",
            actor_id=actor_id,
            source=source,
            aggregate_type="memory_persona",
            aggregate_id=persona.id,
            payload={
                "lead_client_id": str(lead_client_id),
                "full_name": full_name,
                "gender": gender,
                "role_title": role_title,
                "address_form": address_form,
                "tone": tone,
                "version": persona.version,
                "operation": "created",
            },
            idempotency_key=f"persona.updated:created:{lead_client_id}",
        )
        return persona, event

    if expected_version is not None and expected_version != existing.version:
        raise PersonaConflict(
            expected=expected_version,
            actual=existing.version,
            lead_client_id=lead_client_id,
        )

    # Detect actual changes — short-circuit no-op updates so we don't
    # bump version / emit events on every session start.
    changed = {
        field: new
        for field, new in (
            ("full_name", full_name),
            ("gender", gender),
            ("role_title", role_title),
            ("address_form", address_form),
            ("tone", tone),
        )
        if getattr(existing, field) != new
    }
    if not changed:
        return existing, None

    new_version = existing.version + 1
    for field, value in changed.items():
        setattr(existing, field, value)
    existing.version = new_version
    existing.source_profile_version = existing.source_profile_version + 1
    await db.flush()

    event = await emit_domain_event(
        db,
        lead_client_id=lead_client_id,
        event_type="persona.updated",
        actor_type="user" if actor_id else "system",
        actor_id=actor_id,
        source=source,
        aggregate_type="memory_persona",
        aggregate_id=existing.id,
        payload={
            "lead_client_id": str(lead_client_id),
            "version": new_version,
            "previous_version": new_version - 1,
            "changed_fields": sorted(changed),
            "operation": "updated",
        },
        # Idempotency anchor includes target version so a retry of the
        # SAME conceptual update converges, but a different update
        # (e.g. another field) gets its own event.
        idempotency_key=f"persona.updated:{lead_client_id}:v{new_version}",
    )
    return existing, event


# ── SessionPersonaSnapshot capture ───────────────────────────────────────


async def get_snapshot(
    db: AsyncSession, *, session_id: uuid.UUID
) -> SessionPersonaSnapshot | None:
    return await db.get(SessionPersonaSnapshot, session_id)


async def capture_for_session(
    db: AsyncSession,
    *,
    session: TrainingSession,
    captured_from: str,
    persona: MemoryPersona | None = None,
    fallback: PersonaIdentity | None = None,
    actor_id: uuid.UUID | None = None,
    source: str = "service.persona_memory",
) -> tuple[SessionPersonaSnapshot, DomainEvent | None]:
    """Freeze persona identity for the lifetime of ``session``.

    One snapshot per session (the table has session_id as PK). Calling
    this a second time for the same session is idempotent — the existing
    snapshot is returned and no event is emitted, so the state machine
    stays clean even if the API endpoint is retried.

    Field resolution order:

      1. If ``persona`` is provided → copy identity fields from it. This
         is the path used when the session is bound to a real CRM client
         (``real_client_id`` populated).
      2. Else if ``fallback`` is provided → use the explicit identity
         (the ``home_preview`` path, where there's no MemoryPersona
         because there's no CRM client).
      3. Else → raise ``ValueError``. A snapshot without identity would
         immediately violate the NOT NULL constraint on ``full_name``.
    """
    if captured_from not in PERSONA_CAPTURED_FROM:
        raise ValueError(
            f"persona captured_from {captured_from!r} not in "
            f"{sorted(PERSONA_CAPTURED_FROM)}"
        )

    if persona is None and fallback is None:
        raise ValueError(
            "capture_for_session requires either persona= or fallback="
            " — cannot snapshot identity from nothing"
        )

    existing = await get_snapshot(db, session_id=session.id)
    if existing is not None:
        return existing, None

    if persona is not None:
        identity_full_name = persona.full_name
        identity_gender = persona.gender
        identity_role_title = persona.role_title
        identity_address_form = persona.address_form
        identity_tone = persona.tone
        persona_version = persona.version
    else:
        # fallback is guaranteed non-None by the guard above
        assert fallback is not None
        identity_full_name = fallback.full_name
        identity_gender = fallback.gender
        identity_role_title = fallback.role_title
        identity_address_form = fallback.address_form
        identity_tone = fallback.tone
        persona_version = 1  # synthetic — no MemoryPersona row to track

    _validate_identity(
        full_name=identity_full_name,
        gender=identity_gender,
        address_form=identity_address_form,
        tone=identity_tone,
    )

    snapshot = SessionPersonaSnapshot(
        session_id=session.id,
        lead_client_id=session.lead_client_id,
        persona_version=persona_version,
        address_form=identity_address_form,
        full_name=identity_full_name,
        gender=identity_gender,
        role_title=identity_role_title,
        tone=identity_tone,
        captured_from=captured_from,
    )
    db.add(snapshot)
    await db.flush()

    # ── Domain event emission (TZ-1 §15.1 invariant 4) ─────────────────────
    # ``domain_events.lead_client_id`` is NOT NULL with FK→lead_clients.id.
    # The earlier fallback ``session.lead_client_id or session.id`` looked
    # tempting but ``session.id`` is a ``training_sessions`` PK, not a
    # ``lead_clients`` PK — every home_preview session triggered a
    # ForeignKeyViolationError that ``home.start`` swallowed silently.
    # Result on prod: 94/95 snapshots had **no** corresponding
    # ``persona.snapshot_captured`` event in the audit log.
    #
    # Behaviour now: when the session is not yet bound to a real CRM
    # lead (home_preview path), we skip the event emit. The snapshot
    # row itself survives (it's how persona-memory reads identity at
    # call time); the missing event is a known acceptable loss for
    # synthetic preview sessions. When the session is later upgraded
    # to a real lead (via a future "save to CRM" action), the persona
    # event chain starts at that point with a valid anchor.
    if session.lead_client_id is None:
        return snapshot, None

    event = await emit_domain_event(
        db,
        lead_client_id=session.lead_client_id,
        event_type="persona.snapshot_captured",
        actor_type="user" if actor_id else "system",
        actor_id=actor_id,
        source=source,
        aggregate_type="training_session",
        aggregate_id=session.id,
        session_id=session.id,
        payload={
            "session_id": str(session.id),
            "lead_client_id": str(session.lead_client_id),
            "captured_from": captured_from,
            "persona_version": persona_version,
            "full_name": identity_full_name,
            "gender": identity_gender,
            "address_form": identity_address_form,
            "tone": identity_tone,
        },
        idempotency_key=f"persona.snapshot_captured:{session.id}",
    )
    return snapshot, event


# ── Slot locking ─────────────────────────────────────────────────────────


async def lock_slot(
    db: AsyncSession,
    *,
    persona: MemoryPersona,
    slot_code: str,
    fact_value: Any | None = None,
    expected_version: int,
    session_id: uuid.UUID | None = None,
    source_ref: str | None = None,
    actor_id: uuid.UUID | None = None,
    source: str = "service.persona_memory",
) -> tuple[MemoryPersona, DomainEvent]:
    """Lock a slot in ``do_not_ask_again_slots`` and (optionally) record
    the confirmed fact.

    Optimistic concurrency: ``expected_version`` MUST match
    ``persona.version`` — caller is expected to read the row, decide on
    a slot to lock, then call back with the version they saw. On
    mismatch raises :class:`PersonaConflict` so the caller can re-read
    and retry.
    """
    if not slot_code or not slot_code.strip():
        raise ValueError("lock_slot requires a non-empty slot_code")

    if persona.version != expected_version:
        raise PersonaConflict(
            expected=expected_version,
            actual=persona.version,
            lead_client_id=persona.lead_client_id,
        )

    locked_slots = list(persona.do_not_ask_again_slots or [])
    already_locked = slot_code in locked_slots
    if not already_locked:
        locked_slots.append(slot_code)
        persona.do_not_ask_again_slots = locked_slots

    confirmed_facts: dict[str, Any] = dict(persona.confirmed_facts or {})
    if fact_value is not None:
        # TZ-4.5 PR 3: include captured_at for the prompt-render TTL
        # check (persona_slots.render_facts_for_prompt marks stale
        # facts with "(возможно устарело)" when age > slot.ttl_days).
        # ISO-8601 UTC for cross-timezone safety.
        from datetime import datetime as _dt, timezone as _tz
        confirmed_facts[slot_code] = {
            "value": fact_value,
            "source": source_ref or (str(session_id) if session_id else source),
            "captured_at": _dt.now(_tz.utc).isoformat(),
        }
        persona.confirmed_facts = confirmed_facts

    if already_locked and fact_value is None:
        # Idempotent re-lock — return without bumping version. We still
        # emit so the timeline has the audit hit, but with a stable
        # idempotency key so duplicates collapse.
        event = await emit_domain_event(
            db,
            lead_client_id=persona.lead_client_id,
            event_type="persona.slot_locked",
            actor_type="user" if actor_id else "system",
            actor_id=actor_id,
            source=source,
            aggregate_type="memory_persona",
            aggregate_id=persona.id,
            session_id=session_id,
            payload={
                "lead_client_id": str(persona.lead_client_id),
                "slot_code": slot_code,
                "operation": "noop_already_locked",
                "version": persona.version,
            },
            idempotency_key=f"persona.slot_locked:{persona.lead_client_id}:{slot_code}",
        )
        return persona, event

    persona.version = persona.version + 1
    await db.flush()

    event = await emit_domain_event(
        db,
        lead_client_id=persona.lead_client_id,
        event_type="persona.slot_locked",
        actor_type="user" if actor_id else "system",
        actor_id=actor_id,
        source=source,
        aggregate_type="memory_persona",
        aggregate_id=persona.id,
        session_id=session_id,
        payload={
            "lead_client_id": str(persona.lead_client_id),
            "slot_code": slot_code,
            "version": persona.version,
            "fact_value_present": fact_value is not None,
            "operation": "locked" if not already_locked else "fact_recorded",
        },
        idempotency_key=(
            f"persona.slot_locked:{persona.lead_client_id}:{slot_code}:v{persona.version}"
        ),
    )
    return persona, event


# ── Conflict detection (§9.3 / §9.2 invariant 1) ─────────────────────────


async def record_conflict_attempt(
    db: AsyncSession,
    *,
    snapshot: SessionPersonaSnapshot,
    attempted_field: str,
    attempted_value: Any,
    actor_id: uuid.UUID | None = None,
    source: str = "runtime.prompt_assembler",
) -> DomainEvent:
    """Caller noticed runtime tried to mutate identity mid-session.

    Bumps ``mutation_blocked_count`` (observability counter — healthy
    sessions stay at 0) and emits ``persona.conflict_detected``. The
    snapshot itself is *not* mutated — that's the §9.2 invariant 1
    guarantee. Callers do not pass through the value to anything; the
    AI keeps reading from the snapshot's frozen identity.
    """
    # Bump the counter via UPDATE rather than ORM mutation so we don't
    # accidentally trigger SQLAlchemy's full-row update (which would
    # appear as a snapshot mutation).
    await db.execute(
        update(SessionPersonaSnapshot)
        .where(SessionPersonaSnapshot.session_id == snapshot.session_id)
        .values(mutation_blocked_count=SessionPersonaSnapshot.mutation_blocked_count + 1)
    )

    return await emit_domain_event(
        db,
        lead_client_id=snapshot.lead_client_id or snapshot.session_id,
        event_type="persona.conflict_detected",
        actor_type="user" if actor_id else "system",
        actor_id=actor_id,
        source=source,
        aggregate_type="training_session",
        aggregate_id=snapshot.session_id,
        session_id=snapshot.session_id,
        payload={
            "session_id": str(snapshot.session_id),
            "lead_client_id": (
                str(snapshot.lead_client_id) if snapshot.lead_client_id else None
            ),
            "attempted_field": attempted_field,
            "attempted_value_repr": repr(attempted_value)[:200],
            "snapshot_value": getattr(snapshot, attempted_field, None),
        },
        # No idempotency dedup — every attempt should be a distinct row
        # so monitoring can count them. UUID4 in the key keeps collisions
        # at zero without losing audit fidelity.
        idempotency_key=(
            f"persona.conflict_detected:{snapshot.session_id}:"
            f"{attempted_field}:{uuid.uuid4()}"
        ),
    )


__all__ = [
    "CAPTURED_FROM_CENTER",
    "CAPTURED_FROM_HOME_PREVIEW",
    "CAPTURED_FROM_PVP",
    "CAPTURED_FROM_REAL_CLIENT",
    "CAPTURED_FROM_TRAINING_SIM",
    "PersonaConflict",
    "PersonaIdentity",
    "capture_for_session",
    "get_for_lead",
    "get_snapshot",
    "lock_slot",
    "record_conflict_attempt",
    "upsert_for_lead",
]
