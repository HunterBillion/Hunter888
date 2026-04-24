"""Projector replay (A2 — TZ-1 §16.3).

The dual-write producer path builds ClientInteraction directly and then
records projection-state. The `project_event_to_interaction` function was
previously dead code: nothing in runtime or tests exercised the "from
DomainEvent log, rebuild ClientInteraction" path required by §16.3.

These tests run the projector end-to-end against an in-memory DB stand-in:
  1. several DomainEvents of different types → projector → interactions
     with the right interaction_type, content, metadata.
  2. replaying the same event twice yields a single interaction (idempotent
     via projection-state unique constraint on domain_event_id).
  3. content_override and extra_metadata flow through to the projected row.

No real Postgres is needed — the project uses JSONB heavily which aiosqlite
cannot compile, so the test harness mocks add/flush/execute/get for the
specific table-less interaction path.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models.client import ClientInteraction, InteractionType
from app.models.domain_event import DomainEvent
from app.services.crm_timeline_projector import (
    PROJECTION_NAME,
    PROJECTION_VERSION,
    project_event_to_interaction,
)


class _ProjectionDb:
    """In-memory double that captures the DB writes the projector needs.

    Stores projection-state rows keyed by domain_event_id so the idempotency
    path (`existing_state.interaction_id is not None → return same interaction`)
    works without SQLAlchemy.
    """

    def __init__(self):
        self.states: dict[uuid.UUID, SimpleNamespace] = {}
        self.interactions: list[ClientInteraction] = []

    def add(self, obj):
        if isinstance(obj, ClientInteraction):
            self.interactions.append(obj)
        else:  # CrmTimelineProjectionState
            self.states[obj.domain_event_id] = obj

    async def flush(self):
        return None

    async def get(self, _cls, interaction_id):
        for i in self.interactions:
            if i.id == interaction_id:
                return i
        return None

    async def execute(self, stmt):
        # Match the two selects the projector issues: one for projection state,
        # one (inside record_projection) for the same. Both filter by
        # ``CrmTimelineProjectionState.domain_event_id == event.id``. We extract
        # the event UUID from the SQL's where clause parameters.
        whereclause = stmt.whereclause
        target_id = whereclause.right.value  # BinaryExpression(... == literal)
        result = MagicMock()
        result.scalar_one_or_none = lambda: self.states.get(target_id)
        return result


def _event(event_type: str, payload: dict, *, lead_id=None, correlation_id=None):
    return DomainEvent(
        id=uuid.uuid4(),
        lead_client_id=lead_id or uuid.uuid4(),
        event_type=event_type,
        aggregate_type="client_interaction",
        actor_type="user",
        source="test",
        payload_json=payload,
        idempotency_key=f"test:{uuid.uuid4()}",
        schema_version=1,
        correlation_id=correlation_id,
    )


@pytest.mark.asyncio
async def test_replay_lifecycle_change_builds_status_change_interaction():
    db = _ProjectionDb()
    client_id = uuid.uuid4()
    ev = _event(
        "lead_client.lifecycle_changed",
        {"old_status": "new", "new_status": "contacted"},
        correlation_id=str(uuid.uuid4()),
    )

    interaction = await project_event_to_interaction(
        db, event=ev, client_id=client_id, manager_id=None
    )

    assert interaction.interaction_type == InteractionType.status_change
    assert interaction.content == "Смена статуса: new → contacted"
    assert interaction.old_status == "new"
    assert interaction.new_status == "contacted"
    meta = interaction.metadata_
    assert meta["domain_event_id"] == str(ev.id)
    assert meta["schema_version"] == 1
    assert meta["projection_name"] == PROJECTION_NAME
    assert meta["projection_version"] == PROJECTION_VERSION
    assert meta["correlation_id"] == ev.correlation_id
    # One projection-state row, matching the event.
    assert ev.id in db.states
    assert db.states[ev.id].status == "projected"


@pytest.mark.asyncio
async def test_replay_is_idempotent_on_domain_event_id():
    """Second replay of the same event must return the same interaction,
    not create a duplicate."""
    db = _ProjectionDb()
    client_id = uuid.uuid4()
    ev = _event("crm.interaction_logged", {"content": "called the client"})

    i1 = await project_event_to_interaction(
        db, event=ev, client_id=client_id, manager_id=None
    )
    i2 = await project_event_to_interaction(
        db, event=ev, client_id=client_id, manager_id=None
    )

    assert i1 is i2
    # And only one ClientInteraction was ever added to the DB.
    assert len(db.interactions) == 1


@pytest.mark.asyncio
async def test_replay_training_call_maps_to_outbound_call_type():
    db = _ProjectionDb()
    ev = _event(
        "training.real_case_logged",
        {"session_mode": "call", "summary": "5-минутный разговор"},
    )
    interaction = await project_event_to_interaction(
        db, event=ev, client_id=uuid.uuid4(), manager_id=None
    )
    assert interaction.interaction_type == InteractionType.outbound_call
    assert interaction.content == "5-минутный разговор"


@pytest.mark.asyncio
async def test_replay_consent_event_renders_russian_content():
    db = _ProjectionDb()
    ev = _event(
        "consent.updated",
        {"state": "granted", "consent_type": "pdn"},
    )
    interaction = await project_event_to_interaction(
        db, event=ev, client_id=uuid.uuid4(), manager_id=None
    )
    assert interaction.interaction_type == InteractionType.consent_event
    assert interaction.content == "Согласие получено: pdn"


@pytest.mark.asyncio
async def test_replay_accepts_content_and_metadata_overrides():
    db = _ProjectionDb()
    ev = _event("crm.interaction_logged", {"content": "default content"})
    interaction = await project_event_to_interaction(
        db,
        event=ev,
        client_id=uuid.uuid4(),
        manager_id=None,
        content_override="manually-repaired content",
        extra_metadata={"repaired_at": "2026-04-24T12:00:00Z"},
    )
    assert interaction.content == "manually-repaired content"
    assert interaction.metadata_["repaired_at"] == "2026-04-24T12:00:00Z"
    # Canonical keys are still present alongside the override.
    assert interaction.metadata_["domain_event_id"] == str(ev.id)


@pytest.mark.asyncio
async def test_replay_rebuilds_timeline_from_mixed_event_stream():
    """§16.3 golden replay: given a heterogeneous event log, rebuild every
    corresponding ClientInteraction with correct type and canonical metadata.
    This is the end-to-end invariant previously missing from the test suite.
    """
    db = _ProjectionDb()
    client_id = uuid.uuid4()
    lead_id = uuid.uuid4()

    events = [
        _event(
            "lead_client.lifecycle_changed",
            {"old_status": "new", "new_status": "contacted"},
            lead_id=lead_id,
        ),
        _event(
            "consent.updated",
            {"state": "granted", "consent_type": "pdn"},
            lead_id=lead_id,
        ),
        _event(
            "training.real_case_logged",
            {"session_mode": "call", "summary": "follow-up звонок"},
            lead_id=lead_id,
        ),
    ]

    interactions = []
    for e in events:
        interactions.append(
            await project_event_to_interaction(
                db, event=e, client_id=client_id, manager_id=None
            )
        )

    types = [i.interaction_type for i in interactions]
    assert types == [
        InteractionType.status_change,
        InteractionType.consent_event,
        InteractionType.outbound_call,
    ]
    # Every projected interaction must link back to exactly one event.
    assert {i.metadata_["domain_event_id"] for i in interactions} == {str(e.id) for e in events}
    # Projection-state table has one entry per event (no dupes).
    assert set(db.states.keys()) == {e.id for e in events}

    # Replay the entire log again — must be a pure noop.
    replayed = []
    for e in events:
        replayed.append(
            await project_event_to_interaction(
                db, event=e, client_id=client_id, manager_id=None
            )
        )
    assert replayed == interactions
    assert len(db.interactions) == len(events)
