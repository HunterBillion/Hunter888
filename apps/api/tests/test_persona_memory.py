"""TZ-4 D3 — persona memory service contract tests.

Covers:

  * `upsert_for_lead` — first INSERT path emits ``persona.updated``,
    second call with same identity is a no-op (no version bump, no
    event), third call with changed identity bumps version + emits.
  * Optimistic concurrency: ``expected_version`` mismatch raises
    ``PersonaConflict``.
  * `capture_for_session` — happy path with persona, fallback path,
    idempotent re-capture.
  * `lock_slot` — append-only slot list, version bump, idempotency on
    repeat.
  * `record_conflict_attempt` — emits ``persona.conflict_detected``
    without mutating the snapshot identity.
  * Validation: invalid enum / empty full_name raises before touching
    the DB.

Real-DB coverage of the UNIQUE / CHECK constraints lives in the D1
foundation tests (``test_tz4_d1_lifecycle_fields``); these tests
mock the DB at the AsyncSession boundary to assert behaviour.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.domain_event import DomainEvent
from app.models.persona import MemoryPersona, SessionPersonaSnapshot
from app.services import persona_memory


# ── Test helpers ─────────────────────────────────────────────────────────


def _make_event(event_type: str = "persona.updated") -> DomainEvent:
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


def _make_db(*, scalar_results=None, get_result=None):
    """Stub AsyncSession. ``scalar_results`` queues values for ``execute``
    SELECTs; ``get_result`` is returned by ``db.get`` (used by
    ``get_snapshot``)."""
    db = SimpleNamespace()
    db.added: list = []
    results_iter = iter(scalar_results or [])

    class _Result:
        def __init__(self, value):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

    async def _execute(_stmt):
        try:
            return _Result(next(results_iter))
        except StopIteration:
            return _Result(None)

    db.execute = AsyncMock(side_effect=_execute)
    db.add = MagicMock(side_effect=lambda obj: db.added.append(obj))
    db.get = AsyncMock(return_value=get_result)

    async def _flush():
        for obj in db.added:
            if isinstance(obj, MemoryPersona) and obj.id is None:
                obj.id = uuid.uuid4()
                # mirror server defaults so post-flush reads see them
                if obj.version is None:
                    obj.version = 1
                if obj.source_profile_version is None:
                    obj.source_profile_version = 1
            if isinstance(obj, SessionPersonaSnapshot):
                if obj.mutation_blocked_count is None:
                    obj.mutation_blocked_count = 0

    db.flush = AsyncMock(side_effect=_flush)
    return db


def _patch_emit(monkeypatch) -> list[dict]:
    """Replace ``emit_domain_event`` with a recorder; returns the call
    list so tests can assert on event_type / idempotency_key shape."""
    captured: list[dict] = []

    async def _emit(db, **kwargs):
        captured.append(kwargs)
        return _make_event(kwargs.get("event_type", "test.ping"))

    monkeypatch.setattr(persona_memory, "emit_domain_event", _emit)
    return captured


def _existing_persona(
    *,
    lead_client_id: uuid.UUID | None = None,
    full_name: str = "Иванов Иван",
    gender: str = "male",
    role_title: str | None = "должник",
    address_form: str = "вы",
    tone: str = "neutral",
    version: int = 1,
) -> MemoryPersona:
    return MemoryPersona(
        id=uuid.uuid4(),
        lead_client_id=lead_client_id or uuid.uuid4(),
        full_name=full_name,
        gender=gender,
        role_title=role_title,
        address_form=address_form,
        tone=tone,
        version=version,
        source_profile_version=version,
        do_not_ask_again_slots=[],
        confirmed_facts={},
    )


# ── upsert_for_lead ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_for_lead_creates_new_row_emits_created_event(monkeypatch):
    """First contact with a lead → MemoryPersona INSERTed at version=1
    and ``persona.updated`` event emitted with operation=created."""
    db = _make_db(scalar_results=[None])  # no existing row
    captured = _patch_emit(monkeypatch)
    lead_id = uuid.uuid4()

    persona, event = await persona_memory.upsert_for_lead(
        db,
        lead_client_id=lead_id,
        full_name="Макаров Григорий",
        gender="male",
        role_title="должник",
        address_form="вы",
    )

    assert persona.full_name == "Макаров Григорий"
    assert persona.version == 1
    assert event is not None
    assert captured[0]["event_type"] == "persona.updated"
    assert captured[0]["payload"]["operation"] == "created"
    assert "v1" not in captured[0]["idempotency_key"]  # created path uses :created:
    assert "created" in captured[0]["idempotency_key"]


@pytest.mark.asyncio
async def test_upsert_for_lead_noop_when_identity_unchanged(monkeypatch):
    """Second call with identical identity → no version bump, no event.
    This is the hot path on every session start, so quietness matters."""
    existing = _existing_persona()
    db = _make_db(scalar_results=[existing])
    captured = _patch_emit(monkeypatch)

    persona, event = await persona_memory.upsert_for_lead(
        db,
        lead_client_id=existing.lead_client_id,
        full_name=existing.full_name,
        gender=existing.gender,
        role_title=existing.role_title,
        address_form=existing.address_form,
        tone=existing.tone,
    )

    assert persona is existing
    assert persona.version == 1  # unchanged
    assert event is None
    assert captured == []


@pytest.mark.asyncio
async def test_upsert_for_lead_bumps_version_on_change(monkeypatch):
    """Identity change → version bumps + event with operation=updated."""
    existing = _existing_persona(version=3, full_name="Старое имя")
    db = _make_db(scalar_results=[existing])
    captured = _patch_emit(monkeypatch)

    persona, event = await persona_memory.upsert_for_lead(
        db,
        lead_client_id=existing.lead_client_id,
        full_name="Новое имя",
        gender=existing.gender,
        role_title=existing.role_title,
        address_form=existing.address_form,
        tone=existing.tone,
    )

    assert persona.full_name == "Новое имя"
    assert persona.version == 4
    assert event is not None
    assert captured[0]["event_type"] == "persona.updated"
    assert captured[0]["payload"]["operation"] == "updated"
    assert captured[0]["payload"]["changed_fields"] == ["full_name"]
    assert ":v4" in captured[0]["idempotency_key"]


@pytest.mark.asyncio
async def test_upsert_for_lead_optimistic_concurrency_raises(monkeypatch):
    """Caller passed expected_version=N but DB has version=M → conflict."""
    existing = _existing_persona(version=5)
    db = _make_db(scalar_results=[existing])
    _patch_emit(monkeypatch)

    with pytest.raises(persona_memory.PersonaConflict) as excinfo:
        await persona_memory.upsert_for_lead(
            db,
            lead_client_id=existing.lead_client_id,
            full_name="Что-то новое",
            expected_version=3,  # stale
        )

    assert excinfo.value.expected == 3
    assert excinfo.value.actual == 5
    assert excinfo.value.lead_client_id == existing.lead_client_id


@pytest.mark.asyncio
async def test_upsert_for_lead_validates_enums_before_db(monkeypatch):
    """Invalid enum value should raise ValueError before touching DB —
    avoids round-tripping to Postgres just to get an IntegrityError."""
    db = _make_db()
    captured = _patch_emit(monkeypatch)

    with pytest.raises(ValueError, match="gender"):
        await persona_memory.upsert_for_lead(
            db,
            lead_client_id=uuid.uuid4(),
            full_name="Имя",
            gender="bogus",
        )
    db.execute.assert_not_called()
    assert captured == []


@pytest.mark.asyncio
async def test_upsert_for_lead_rejects_empty_full_name(monkeypatch):
    """``full_name`` is NOT NULL with no server default — refuse blank
    strings here so D3 callers don't paper over a missing field with a
    silent ''."""
    db = _make_db()
    _patch_emit(monkeypatch)

    with pytest.raises(ValueError, match="full_name"):
        await persona_memory.upsert_for_lead(
            db,
            lead_client_id=uuid.uuid4(),
            full_name="   ",
        )


# ── capture_for_session ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_capture_for_session_with_persona_emits_snapshot_event(monkeypatch):
    """Real-client path: copy identity from MemoryPersona, INSERT
    snapshot, emit persona.snapshot_captured."""
    persona = _existing_persona(version=2)
    session = SimpleNamespace(id=uuid.uuid4(), lead_client_id=persona.lead_client_id)
    db = _make_db(get_result=None)  # no existing snapshot
    captured = _patch_emit(monkeypatch)

    snapshot, event = await persona_memory.capture_for_session(
        db,
        session=session,
        captured_from=persona_memory.CAPTURED_FROM_REAL_CLIENT,
        persona=persona,
    )

    assert snapshot.session_id == session.id
    assert snapshot.full_name == persona.full_name
    assert snapshot.persona_version == persona.version
    assert snapshot.captured_from == "real_client"
    assert event is not None
    assert captured[0]["event_type"] == "persona.snapshot_captured"
    assert captured[0]["payload"]["captured_from"] == "real_client"


@pytest.mark.asyncio
async def test_capture_for_session_with_fallback_emits_snapshot_event(monkeypatch):
    """home_preview path: no MemoryPersona, identity from PersonaIdentity
    fallback. lead_client_id may be NULL on the snapshot, but the
    DomainEvent must still get a non-NULL lead_client_id (TZ-1 invariant
    — falls back to session.id when no canonical lead exists)."""
    session = SimpleNamespace(id=uuid.uuid4(), lead_client_id=None)
    db = _make_db(get_result=None)
    captured = _patch_emit(monkeypatch)

    snapshot, event = await persona_memory.capture_for_session(
        db,
        session=session,
        captured_from=persona_memory.CAPTURED_FROM_HOME_PREVIEW,
        fallback=persona_memory.PersonaIdentity(
            full_name="Алёна Васильева",
            gender="female",
            role_title="должник",
        ),
    )

    assert snapshot.full_name == "Алёна Васильева"
    assert snapshot.lead_client_id is None
    assert snapshot.captured_from == "home_preview"
    # DomainEvent.lead_client_id falls back to session.id when snapshot
    # has none — required by TZ-1 NOT NULL constraint.
    assert captured[0]["lead_client_id"] == session.id


@pytest.mark.asyncio
async def test_capture_for_session_is_idempotent(monkeypatch):
    """Second call for the same session_id → returns existing snapshot,
    no INSERT, no event. Protects against double-fire from API retries."""
    existing = SessionPersonaSnapshot(
        session_id=uuid.uuid4(),
        lead_client_id=uuid.uuid4(),
        full_name="Уже есть",
        gender="male",
        captured_from="real_client",
        persona_version=1,
    )
    session = SimpleNamespace(id=existing.session_id, lead_client_id=existing.lead_client_id)
    db = _make_db(get_result=existing)
    captured = _patch_emit(monkeypatch)

    snapshot, event = await persona_memory.capture_for_session(
        db,
        session=session,
        captured_from=persona_memory.CAPTURED_FROM_REAL_CLIENT,
        persona=_existing_persona(),
    )

    assert snapshot is existing
    assert event is None
    assert captured == []
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_capture_for_session_requires_persona_or_fallback(monkeypatch):
    """Caller must supply either a MemoryPersona or a PersonaIdentity —
    snapshotting without identity would IntegrityError on full_name
    NOT NULL."""
    session = SimpleNamespace(id=uuid.uuid4(), lead_client_id=None)
    db = _make_db(get_result=None)
    _patch_emit(monkeypatch)

    with pytest.raises(ValueError, match="persona= or fallback="):
        await persona_memory.capture_for_session(
            db,
            session=session,
            captured_from=persona_memory.CAPTURED_FROM_HOME_PREVIEW,
        )


# ── lock_slot ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lock_slot_appends_and_bumps_version(monkeypatch):
    """First lock of a slot → appended, version bumped, event emitted."""
    persona = _existing_persona(version=2)
    db = _make_db()
    captured = _patch_emit(monkeypatch)

    result, event = await persona_memory.lock_slot(
        db,
        persona=persona,
        slot_code="city",
        fact_value="Рязань",
        expected_version=2,
        session_id=uuid.uuid4(),
    )

    assert result is persona
    assert "city" in persona.do_not_ask_again_slots
    assert persona.confirmed_facts["city"]["value"] == "Рязань"
    assert persona.version == 3
    assert captured[0]["event_type"] == "persona.slot_locked"
    assert captured[0]["payload"]["slot_code"] == "city"
    assert ":v3" in captured[0]["idempotency_key"]


@pytest.mark.asyncio
async def test_lock_slot_idempotent_on_already_locked(monkeypatch):
    """Re-locking an already-locked slot without a new fact → noop. The
    version doesn't bump and the event uses a stable idempotency key so
    duplicates collapse in the canonical event log."""
    persona = _existing_persona(version=2)
    persona.do_not_ask_again_slots = ["city"]
    db = _make_db()
    captured = _patch_emit(monkeypatch)

    _, event = await persona_memory.lock_slot(
        db,
        persona=persona,
        slot_code="city",
        expected_version=2,
    )

    assert persona.version == 2  # unchanged
    assert event is not None  # still emit for audit trail
    assert captured[0]["payload"]["operation"] == "noop_already_locked"


@pytest.mark.asyncio
async def test_lock_slot_optimistic_concurrency_raises(monkeypatch):
    """Stale expected_version → PersonaConflict before any mutation."""
    persona = _existing_persona(version=5)
    db = _make_db()
    _patch_emit(monkeypatch)

    with pytest.raises(persona_memory.PersonaConflict):
        await persona_memory.lock_slot(
            db,
            persona=persona,
            slot_code="city",
            expected_version=2,  # stale
        )
    # No mutation happened
    assert persona.do_not_ask_again_slots == []


# ── record_conflict_attempt ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_conflict_attempt_emits_event_without_mutating_snapshot(monkeypatch):
    """The whole point of the conflict event is to log a *blocked*
    mutation — the snapshot identity must remain unchanged. The counter
    is bumped via raw UPDATE so the AST guard doesn't trip on it."""
    snapshot = SessionPersonaSnapshot(
        session_id=uuid.uuid4(),
        lead_client_id=uuid.uuid4(),
        full_name="Каноничное Имя",
        gender="male",
        captured_from="real_client",
        persona_version=1,
        mutation_blocked_count=0,
    )
    db = _make_db()
    captured = _patch_emit(monkeypatch)

    event = await persona_memory.record_conflict_attempt(
        db,
        snapshot=snapshot,
        attempted_field="full_name",
        attempted_value="Подменное Имя",
    )

    # Snapshot identity unchanged
    assert snapshot.full_name == "Каноничное Имя"
    # Counter is bumped via raw UPDATE — verify db.execute was called
    db.execute.assert_called()  # the UPDATE
    assert event is not None
    assert captured[0]["event_type"] == "persona.conflict_detected"
    assert captured[0]["payload"]["attempted_field"] == "full_name"
    assert captured[0]["payload"]["snapshot_value"] == "Каноничное Имя"
    assert "Подменное Имя" in captured[0]["payload"]["attempted_value_repr"]
