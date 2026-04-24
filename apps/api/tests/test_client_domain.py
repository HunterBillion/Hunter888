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
