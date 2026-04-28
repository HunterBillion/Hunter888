"""TZ-4 §6.3 / §6.4 — per-client persona memory read endpoint tests."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.persona_view import get_client_persona_memory
from app.models.client import RealClient
from app.models.persona import MemoryPersona, SessionPersonaSnapshot


def _user(role: str = "manager", *, uid=None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uid or uuid.uuid4(),
        role=SimpleNamespace(value=role),
        team_id=None,
        full_name="Менеджер",
        email="m@x",
    )


def _client(*, manager_id: uuid.UUID, lead_id: uuid.UUID | None = None) -> SimpleNamespace:
    """Stub instead of real ORM row — the endpoint only reads
    `id`, `manager_id`, `lead_client_id` so we don't have to mirror
    every NOT NULL column the real schema requires."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        manager_id=manager_id,
        lead_client_id=lead_id,
    )


def _make_db(*, queue: list[object]):
    """Return successive ``execute`` results from ``queue``."""
    db = SimpleNamespace()
    cursor = {"i": 0}

    class _Result:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            if isinstance(self._value, list):
                return self._value[0] if self._value else None
            return self._value

        def all(self):
            if isinstance(self._value, list):
                return self._value
            return []

    async def _execute(_stmt):
        i = cursor["i"]
        cursor["i"] += 1
        if i < len(queue):
            return _Result(queue[i])
        return _Result(None)

    db.execute = AsyncMock(side_effect=_execute)
    return db


@pytest.mark.asyncio
async def test_persona_memory_returns_full_shape_when_data_present():
    user = _user(role="manager")
    client = _client(manager_id=user.id, lead_id=uuid.uuid4())
    persona = MemoryPersona(
        id=uuid.uuid4(),
        lead_client_id=client.lead_client_id,
        full_name="Иванов Иван",
        gender="male",
        role_title="должник",
        address_form="вы",
        tone="neutral",
        do_not_ask_again_slots=["full_name", "city"],
        confirmed_facts={
            "city": {"value": "Рязань", "source": "session/abc"},
        },
        version=3,
        last_confirmed_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        source_profile_version=1,
    )
    snapshot = SessionPersonaSnapshot(
        session_id=uuid.uuid4(),
        lead_client_id=client.lead_client_id,
        persona_version=3,
        full_name="Иванов Иван",
        gender="male",
        address_form="вы",
        tone="neutral",
        captured_from="real_client",
        captured_at=datetime.now(UTC),
        mutation_blocked_count=2,
    )

    db = _make_db(
        queue=[
            client,                                 # 1) RealClient lookup
            persona,                                # 2) MemoryPersona
            snapshot,                               # 3) latest snapshot
            [("persona.snapshot_captured", 4),      # 4) event counts (rows iterable)
             ("persona.slot_locked", 2),
             ("persona.conflict_detected", 1)],
        ]
    )

    resp = await get_client_persona_memory(
        client_id=client.id, days=30, user=user, db=db,
    )

    assert resp.real_client_id == client.id
    assert resp.lead_client_id == client.lead_client_id
    assert resp.persona is not None
    assert resp.persona.version == 3
    assert "city" in resp.persona.do_not_ask_again_slots
    assert resp.persona.confirmed_facts["city"]["value"] == "Рязань"

    assert resp.last_snapshot is not None
    assert resp.last_snapshot.mutation_blocked_count == 2

    assert resp.event_counts.snapshot_captured == 4
    assert resp.event_counts.slot_locked == 2
    assert resp.event_counts.conflict_detected == 1


@pytest.mark.asyncio
async def test_persona_memory_404_when_client_missing():
    user = _user()
    db = _make_db(queue=[None])
    with pytest.raises(HTTPException) as exc:
        await get_client_persona_memory(
            client_id=uuid.uuid4(), days=30, user=user, db=db,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_persona_memory_403_when_other_managers_client():
    user = _user(role="manager")
    other_manager_id = uuid.uuid4()
    client = _client(manager_id=other_manager_id)
    db = _make_db(queue=[client])
    with pytest.raises(HTTPException) as exc:
        await get_client_persona_memory(
            client_id=client.id, days=30, user=user, db=db,
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_persona_memory_returns_empty_persona_without_lead_anchor():
    """Client without lead_client_id (TZ-1 expand-phase residue) returns
    an empty persona view + empty event counts."""
    user = _user(role="rop")
    client = _client(manager_id=uuid.uuid4(), lead_id=None)
    db = _make_db(
        queue=[
            client,    # RealClient lookup
            None,      # snapshot lookup (joined via real_client_id)
        ]
    )
    resp = await get_client_persona_memory(
        client_id=client.id, days=30, user=user, db=db,
    )
    assert resp.persona is None
    assert resp.last_snapshot is None
    assert resp.event_counts.snapshot_captured == 0
    assert resp.event_counts.conflict_detected == 0


@pytest.mark.asyncio
async def test_persona_memory_admin_can_see_any_client():
    user = _user(role="admin")
    client = _client(manager_id=uuid.uuid4(), lead_id=uuid.uuid4())
    db = _make_db(
        queue=[
            client,
            None,        # no MemoryPersona
            None,        # no snapshot
            [],          # no event rows
        ]
    )
    resp = await get_client_persona_memory(
        client_id=client.id, days=30, user=user, db=db,
    )
    assert resp.real_client_id == client.id
    assert resp.persona is None
