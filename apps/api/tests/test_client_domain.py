"""Unit tests for TZ-1 unified client domain helpers.

Covers:
- legacy status → (lifecycle_stage, work_state) mapping;
- JSON normalization for event payloads;
- deterministic idempotency key derivation (§9.1.4);
- CRM timeline projector metadata patch + replay idempotency;
- parity report shape.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.client import ClientStatus
from app.models.domain_event import DomainEvent
from app.services.client_domain import (
    _derive_idempotency_key,
    _hash_payload,
    _json_safe,
    map_legacy_client_status,
)
from app.services.crm_timeline_projector import (
    PROJECTION_NAME,
    PROJECTION_VERSION,
    infer_interaction_type,
    interaction_metadata_patch,
)

# ── map_legacy_client_status ─────────────────────────────────────────────


def test_map_legacy_client_status_maps_lifecycle_and_work_state():
    assert map_legacy_client_status(ClientStatus.new) == ("new", "active")
    assert map_legacy_client_status(ClientStatus.consent_given) == ("consent_received", "active")
    assert map_legacy_client_status(ClientStatus.in_process) == ("case_in_progress", "active")
    assert map_legacy_client_status(ClientStatus.paused) == ("case_in_progress", "paused")
    assert map_legacy_client_status(ClientStatus.consent_revoked) == (
        "consent_received",
        "consent_revoked",
    )


def test_map_legacy_client_status_accepts_strings_and_none():
    assert map_legacy_client_status(None) == ("new", "active")
    assert map_legacy_client_status("thinking") == ("thinking", "active")
    assert map_legacy_client_status("unknown_value") == ("new", "active")


# ── correlation_id fallback (TZ §15.1 invariant 4) ──────────────────────


@pytest.mark.asyncio
async def test_emit_domain_event_falls_back_to_session_id_for_correlation(monkeypatch):
    """Helper-side defense: when caller omits correlation_id, the session_id
    becomes the anchor. Without this, the upcoming NOT NULL migration would
    crash any forgetful caller; with it, the DB constraint is just a safety
    net for code that bypasses the helper entirely."""
    from app.services import client_domain

    # Disable persistence so we exercise the transient-stub branch which is
    # also subject to the same default.
    monkeypatch.setattr(
        client_domain.settings, "client_domain_dual_write_enabled", False, raising=False
    )

    lead_id = uuid.uuid4()
    session_id = uuid.uuid4()
    ev = await client_domain.emit_domain_event(
        db=SimpleNamespace(),
        lead_client_id=lead_id,
        event_type="test.ping",
        actor_type="system",
        actor_id=None,
        source="unit_test",
        session_id=session_id,
    )
    assert ev.correlation_id == str(session_id)


@pytest.mark.asyncio
async def test_emit_domain_event_falls_back_to_aggregate_id_when_no_session(monkeypatch):
    from app.services import client_domain

    monkeypatch.setattr(
        client_domain.settings, "client_domain_dual_write_enabled", False, raising=False
    )

    lead_id = uuid.uuid4()
    aggregate_id = uuid.uuid4()
    ev = await client_domain.emit_domain_event(
        db=SimpleNamespace(),
        lead_client_id=lead_id,
        event_type="test.ping",
        actor_type="system",
        actor_id=None,
        source="unit_test",
        aggregate_id=aggregate_id,
    )
    assert ev.correlation_id == str(aggregate_id)


@pytest.mark.asyncio
async def test_emit_domain_event_falls_back_to_lead_client_when_no_session_or_aggregate(monkeypatch):
    from app.services import client_domain

    monkeypatch.setattr(
        client_domain.settings, "client_domain_dual_write_enabled", False, raising=False
    )

    lead_id = uuid.uuid4()
    ev = await client_domain.emit_domain_event(
        db=SimpleNamespace(),
        lead_client_id=lead_id,
        event_type="test.ping",
        actor_type="system",
        actor_id=None,
        source="unit_test",
    )
    assert ev.correlation_id == str(lead_id)


@pytest.mark.asyncio
async def test_emit_domain_event_preserves_explicit_correlation_id(monkeypatch):
    """Explicit caller-supplied correlation wins over all fallbacks."""
    from app.services import client_domain

    monkeypatch.setattr(
        client_domain.settings, "client_domain_dual_write_enabled", False, raising=False
    )

    ev = await client_domain.emit_domain_event(
        db=SimpleNamespace(),
        lead_client_id=uuid.uuid4(),
        event_type="test.ping",
        actor_type="system",
        actor_id=None,
        source="unit_test",
        session_id=uuid.uuid4(),
        correlation_id="explicit-trace-id",
    )
    assert ev.correlation_id == "explicit-trace-id"


# ── _json_safe ───────────────────────────────────────────────────────────


def test_json_safe_normalizes_non_json_types():
    now = datetime.now(UTC)
    value = {
        "id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
        "when": now,
        "amount": Decimal("123.45"),
        "status": ClientStatus.completed,
        "nested": [Decimal("1.2"), {"client": ClientStatus.lost}],
    }

    normalized = _json_safe(value)

    assert normalized == {
        "id": "11111111-1111-1111-1111-111111111111",
        "when": now.isoformat(),
        "amount": "123.45",
        "status": "completed",
        "nested": ["1.2", {"client": "lost"}],
    }


def test_json_safe_keeps_bytes_untouched():
    raw = b"binary blob"
    # Bytes are kept as-is — caller is responsible for blob handling.
    assert _json_safe(raw) is raw


# ── Idempotency derivation ───────────────────────────────────────────────


def test_derive_idempotency_key_is_deterministic():
    agg = uuid.UUID("22222222-2222-2222-2222-222222222222")
    actor = uuid.UUID("33333333-3333-3333-3333-333333333333")
    session = uuid.UUID("44444444-4444-4444-4444-444444444444")
    payload = {"foo": 1, "bar": [2, 3]}

    first = _derive_idempotency_key(
        "lead_client.profile_updated",
        aggregate_id=agg,
        actor_id=actor,
        session_id=session,
        payload=payload,
    )
    second = _derive_idempotency_key(
        "lead_client.profile_updated",
        aggregate_id=agg,
        actor_id=actor,
        session_id=session,
        payload=payload,
    )

    assert first == second
    assert first.startswith("lead_client.profile_updated:")


def test_derive_idempotency_key_differs_on_payload_change():
    agg = uuid.UUID("22222222-2222-2222-2222-222222222222")
    first = _derive_idempotency_key(
        "crm.interaction_logged",
        aggregate_id=agg,
        actor_id=None,
        session_id=None,
        payload={"x": 1},
    )
    second = _derive_idempotency_key(
        "crm.interaction_logged",
        aggregate_id=agg,
        actor_id=None,
        session_id=None,
        payload={"x": 2},
    )
    assert first != second


def test_hash_payload_stable_across_key_order():
    a = {"a": 1, "b": 2}
    b = {"b": 2, "a": 1}
    assert _hash_payload(a) == _hash_payload(b)


# ── Projector helpers ────────────────────────────────────────────────────


def _event_stub(event_type: str, payload: dict | None = None) -> DomainEvent:
    ev = DomainEvent(
        id=uuid.uuid4(),
        lead_client_id=uuid.uuid4(),
        event_type=event_type,
        actor_type="user",
        source="test",
        payload_json=payload or {},
        idempotency_key=uuid.uuid4().hex,
        schema_version=1,
        correlation_id="corr-1",
    )
    return ev


def test_interaction_metadata_patch_includes_required_fields():
    event = _event_stub("crm.interaction_logged")
    patch = interaction_metadata_patch(event)
    assert patch["domain_event_id"] == str(event.id)
    assert patch["schema_version"] == 1
    assert patch["projection_name"] == PROJECTION_NAME
    assert patch["projection_version"] == PROJECTION_VERSION
    assert patch["correlation_id"] == "corr-1"


def test_interaction_metadata_patch_merges_extra():
    event = _event_stub("crm.interaction_logged")
    patch = interaction_metadata_patch(event, {"training_session_id": "abc"})
    assert patch["training_session_id"] == "abc"
    assert patch["domain_event_id"] == str(event.id)


def test_infer_interaction_type_lifecycle_changed():
    from app.models.client import InteractionType

    assert (
        infer_interaction_type("lead_client.lifecycle_changed", {}) == InteractionType.status_change
    )
    assert infer_interaction_type("consent.updated", {}) == InteractionType.consent_event
    assert (
        infer_interaction_type("training.real_case_logged", {"session_mode": "call"})
        == InteractionType.outbound_call
    )
    assert (
        infer_interaction_type("training.real_case_logged", {"session_mode": "chat"})
        == InteractionType.note
    )


def test_infer_interaction_type_respects_payload_override():
    from app.models.client import InteractionType

    assert (
        infer_interaction_type("crm.interaction_logged", {"interaction_type": "meeting"})
        == InteractionType.meeting
    )


# ── emit_domain_event idempotency (unit, async, mock DB) ─────────────────


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalar_one(self):
        return self._value


@pytest.mark.asyncio
async def test_emit_domain_event_returns_existing_on_duplicate_key(monkeypatch):
    from app.services import client_domain

    # force dual-write ON regardless of env
    monkeypatch.setattr(
        client_domain.settings, "client_domain_dual_write_enabled", True, raising=False
    )

    lead_id = uuid.uuid4()
    key = "test-idem:1"
    existing = DomainEvent(
        id=uuid.uuid4(),
        lead_client_id=lead_id,
        event_type="crm.interaction_logged",
        actor_type="user",
        source="test",
        payload_json={},
        idempotency_key=key,
        schema_version=1,
        correlation_id="corr-existing",
    )
    db = SimpleNamespace()
    db.execute = AsyncMock(return_value=_FakeResult(existing))
    db.add = MagicMock()
    db.flush = AsyncMock()

    result = await client_domain.emit_domain_event(
        db,
        lead_client_id=lead_id,
        event_type="crm.interaction_logged",
        actor_type="user",
        actor_id=None,
        source="test",
        idempotency_key=key,
    )

    assert result is existing
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_emit_counter_increments_on_each_branch(monkeypatch):
    """Prometheus counter exposes emit attempts so /admin/client-domain/metrics
    can show emit volume in real time. Each branch (skipped / deduped / emitted)
    must bump its own slot.
    """
    from app.services import client_domain

    # Snapshot baseline so parallel test runs don't contaminate the assertion.
    baseline = dict(client_domain._emit_counter)

    def delta(*labels) -> int:
        return client_domain._emit_counter.get(labels, 0) - baseline.get(labels, 0)

    # 1) skipped path — flag off
    monkeypatch.setattr(
        client_domain.settings, "client_domain_dual_write_enabled", False, raising=False
    )
    db = SimpleNamespace(
        execute=AsyncMock(),
        add=MagicMock(),
        flush=AsyncMock(),
    )
    await client_domain.emit_domain_event(
        db,
        lead_client_id=uuid.uuid4(),
        event_type="crm.interaction_logged",
        actor_type="user",
        actor_id=None,
        source="test",
        idempotency_key="k1",
    )
    assert delta("crm.interaction_logged", "test", "user", "skipped") == 1

    # 2) deduped path — pre-existing event returned
    monkeypatch.setattr(
        client_domain.settings, "client_domain_dual_write_enabled", True, raising=False
    )
    existing_event = DomainEvent(
        id=uuid.uuid4(),
        lead_client_id=uuid.uuid4(),
        event_type="crm.interaction_logged",
        actor_type="user",
        source="test",
        payload_json={},
        idempotency_key="k2",
        schema_version=1,
        correlation_id="corr-k2",
    )
    db.execute = AsyncMock(return_value=_FakeResult(existing_event))
    await client_domain.emit_domain_event(
        db,
        lead_client_id=uuid.uuid4(),
        event_type="crm.interaction_logged",
        actor_type="user",
        actor_id=None,
        source="test",
        idempotency_key="k2",
    )
    assert delta("crm.interaction_logged", "test", "user", "deduped") == 1


def test_lattice_constants_match_tz1_spec():
    """TZ-1 §8 catalog. If anyone adds a value to the runtime constant
    without updating the matching CHECK constraint in
    20260425_003_lead_clients_lattice_check.py, the DB will reject
    legitimate writes — keep them in lockstep.
    """
    from app.services.client_domain import LIFECYCLE_STAGES, WORK_STATES

    assert LIFECYCLE_STAGES == frozenset({
        "new", "contacted", "interested", "consultation", "thinking",
        "consent_received", "contract_signed", "documents_in_progress",
        "case_in_progress", "completed", "lost",
    })
    assert WORK_STATES == frozenset({
        "active", "callback_scheduled", "waiting_client", "waiting_documents",
        "consent_pending", "paused", "consent_revoked", "duplicate_review",
        "archived",
    })


def test_map_legacy_status_only_returns_lattice_values():
    """A schema-level guard: the legacy → canonical mapper must NEVER
    produce a value the CHECK constraint will reject."""
    from app.models.client import ClientStatus
    from app.services.client_domain import (
        LIFECYCLE_STAGES,
        WORK_STATES,
        map_legacy_client_status,
    )

    for status in list(ClientStatus) + [None, "garbage", ""]:
        lifecycle, work_state = map_legacy_client_status(status)
        assert lifecycle in LIFECYCLE_STAGES, (status, lifecycle)
        assert work_state in WORK_STATES, (status, work_state)


@pytest.mark.asyncio
async def test_emit_client_event_fills_correlation_from_client_id(monkeypatch):
    """A3: lifecycle events (lead_client.created/archived/profile_updated) never
    carry a session_id. emit_client_event must still produce a non-NULL
    correlation_id so §15.1 timeline-join invariants hold.
    """
    from app.services import client_domain

    monkeypatch.setattr(
        client_domain.settings, "client_domain_dual_write_enabled", False, raising=False
    )

    client_id = uuid.uuid4()
    client_row = SimpleNamespace(
        id=client_id,
        lead_client_id=client_id,
        manager_id=uuid.uuid4(),
        status=None,
    )
    lead = SimpleNamespace(
        id=client_id,
        lifecycle_stage="new",
        work_state="active",
        source_system="real_clients",
        source_ref=str(client_id),
    )
    db = SimpleNamespace(
        get=AsyncMock(return_value=lead),
        execute=AsyncMock(),
        add=MagicMock(),
        flush=AsyncMock(),
    )

    ev = await client_domain.emit_client_event(
        db,
        client=client_row,
        event_type="lead_client.created",
        actor_type="user",
        actor_id=uuid.uuid4(),
        source="client_service",
        aggregate_type="real_client",
        aggregate_id=client_id,
    )
    # Fallback chain: no session_id → aggregate_id; no aggregate → client.id.
    # Must never be None (the whole point of A3).
    assert ev.correlation_id is not None
    assert ev.correlation_id == str(client_id)


@pytest.mark.asyncio
async def test_emit_client_event_prefers_session_id_over_aggregate(monkeypatch):
    from app.services import client_domain

    monkeypatch.setattr(
        client_domain.settings, "client_domain_dual_write_enabled", False, raising=False
    )
    client_id = uuid.uuid4()
    session_id = uuid.uuid4()
    agg_id = uuid.uuid4()
    client_row = SimpleNamespace(
        id=client_id, lead_client_id=client_id, manager_id=uuid.uuid4(), status=None,
    )
    lead = SimpleNamespace(
        id=client_id,
        lifecycle_stage="new",
        work_state="active",
        source_system="real_clients",
        source_ref=str(client_id),
    )
    db = SimpleNamespace(
        get=AsyncMock(return_value=lead),
        execute=AsyncMock(),
        add=MagicMock(),
        flush=AsyncMock(),
    )

    ev = await client_domain.emit_client_event(
        db,
        client=client_row,
        event_type="crm.interaction_logged",
        actor_type="user",
        actor_id=None,
        source="test",
        session_id=session_id,
        aggregate_id=agg_id,
    )
    assert ev.correlation_id == str(session_id)


@pytest.mark.asyncio
async def test_ensure_lead_client_recovers_from_concurrent_insert(monkeypatch):
    """A9: two workers that both see `lead is None` must not both crash —
    the loser of the INSERT race catches IntegrityError on the SAVEPOINT,
    re-SELECTs, and returns the winner's row instead of poisoning the outer txn.
    """
    from sqlalchemy.exc import IntegrityError

    from app.models.client import RealClient
    from app.models.lead_client import LeadClient
    from app.services import client_domain

    client_id = uuid.uuid4()
    client_row = SimpleNamespace(
        id=client_id,
        lead_client_id=None,
        manager_id=uuid.uuid4(),
        status=None,
    )
    winner_row = LeadClient(
        id=client_id,
        owner_user_id=client_row.manager_id,
        lifecycle_stage="new",
        work_state="active",
        status_tags=[],
        source_system="real_clients",
        source_ref=str(client_id),
    )

    # First db.get: nothing there yet. Second (after rollback): winner's row.
    gets = iter([None, winner_row])
    exec_result = SimpleNamespace(scalar_one_or_none=lambda: None)

    # begin_nested() returns an async context manager whose __aexit__ raises
    # IntegrityError — the savepoint rolls back and the caller re-SELECTs.
    class _Savepoint:
        async def __aenter__(self): return self
        async def __aexit__(self, et, ev, tb):
            raise IntegrityError("insert", {}, Exception("duplicate"))

    db = SimpleNamespace()
    db.get = AsyncMock(side_effect=lambda *_a, **_kw: next(gets))
    db.execute = AsyncMock(return_value=exec_result)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.begin_nested = MagicMock(return_value=_Savepoint())

    result = await client_domain.ensure_lead_client(db, client=client_row)

    assert result is winner_row
    # client.lead_client_id must still be wired to the (now-resolved) lead id.
    assert client_row.lead_client_id == winner_row.id


@pytest.mark.asyncio
async def test_emit_domain_event_noop_when_flag_disabled(monkeypatch):
    from app.services import client_domain

    monkeypatch.setattr(
        client_domain.settings, "client_domain_dual_write_enabled", False, raising=False
    )
    db = SimpleNamespace()
    db.execute = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    result = await client_domain.emit_domain_event(
        db,
        lead_client_id=uuid.uuid4(),
        event_type="crm.interaction_logged",
        actor_type="user",
        actor_id=None,
        source="test",
        idempotency_key="whatever",
    )

    # When dual-write is disabled the helper returns an in-memory event
    # (not persisted) and does not touch the DB session at all.
    assert result.id is not None
    assert result.idempotency_key == "whatever"
    db.execute.assert_not_called()
    db.add.assert_not_called()

    # And when no key is passed we fall back to the "disabled" sentinel so
    # callers can distinguish the no-op path in tracing.
    result_no_key = await client_domain.emit_domain_event(
        db,
        lead_client_id=uuid.uuid4(),
        event_type="crm.interaction_logged",
        actor_type="user",
        actor_id=None,
        source="test",
    )
    assert result_no_key.idempotency_key == "disabled"
