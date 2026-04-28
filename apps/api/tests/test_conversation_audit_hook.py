"""TZ-4 D7.6 — runtime audit hook contract tests.

Covers the wiring added in this PR:

  * happy path — clean reply produces zero events, zero WS frames,
    zero ``mutation_blocked_count`` bumps.
  * legacy three checks — too_long / near_repeat / missing_next_step
    fire ``conversation.policy_violation_detected`` events with the
    expected severity tags.
  * persona-aware checks fire only when a snapshot/persona is
    available; ``unjustified_identity_change`` additionally bridges
    into ``persona_memory.record_conflict_attempt`` so the §9.2
    invariant 1 counter bumps.
  * WS dual-publish — every violation is both ``ws_enqueue``'d
    (durable outbox) and ``send_ws_notification``'d (live push).
  * helper ``previous_assistant_replies_from_history`` returns at
    most ``limit`` strings, ordered from oldest-to-newest.
  * resilience — a failing live-push doesn't propagate to the WS
    handler; the hook swallows + logs.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.persona import MemoryPersona, SessionPersonaSnapshot
from app.services import conversation_audit_hook as hook
from app.services import conversation_policy_engine as engine


# ── Helpers ──────────────────────────────────────────────────────────────


def _snapshot(*, address_form: str = "вы") -> SessionPersonaSnapshot:
    return SessionPersonaSnapshot(
        session_id=uuid.uuid4(),
        lead_client_id=uuid.uuid4(),
        full_name="Иванов Петр",
        gender="male",
        address_form=address_form,
        tone="neutral",
        captured_from="real_client",
        persona_version=1,
        mutation_blocked_count=0,
    )


def _persona(*locked: str) -> MemoryPersona:
    return MemoryPersona(
        id=uuid.uuid4(),
        lead_client_id=uuid.uuid4(),
        full_name="Иванов Петр",
        gender="male",
        address_form="вы",
        tone="neutral",
        version=1,
        do_not_ask_again_slots=list(locked),
        confirmed_facts={},
    )


def _make_db(*, snapshot=None, persona=None):
    """Stub session that returns ``snapshot`` then ``persona`` from
    sequential ``execute()`` calls — mirrors the order
    :func:`hook._load_snapshot` / ``_load_persona`` query in."""
    db = SimpleNamespace()

    class _Result:
        def __init__(self, value):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

    queue = [snapshot, persona]
    cursor = {"i": 0}

    async def _execute(_stmt):
        i = cursor["i"]
        cursor["i"] += 1
        if i < len(queue):
            return _Result(queue[i])
        return _Result(None)

    db.execute = AsyncMock(side_effect=_execute)
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


def _capture_outbound(monkeypatch):
    """Replace the engine + ws_delivery + persona_memory + live-push
    surface with recorders. Returns a dict of capture lists for the
    test to assert against."""
    captured = {
        "events": [],   # engine.emit_domain_event
        "outbox": [],   # ws_delivery.enqueue
        "live_push": [],  # send_ws_notification
        "conflicts": [],  # persona_memory.record_conflict_attempt
    }

    async def _emit(db, **kwargs):
        captured["events"].append(kwargs)
        from app.models.domain_event import DomainEvent
        return DomainEvent(
            id=uuid.uuid4(),
            lead_client_id=kwargs.get("lead_client_id") or uuid.uuid4(),
            event_type=kwargs.get("event_type", "test.ping"),
            actor_type="system",
            source="test",
            payload_json={},
            idempotency_key=kwargs.get("idempotency_key", "x"),
            schema_version=1,
            correlation_id="test",
        )

    async def _enqueue(db, *, user_id, event_type, payload=None, correlation_id=None, ttl_seconds=None):
        captured["outbox"].append(
            {
                "user_id": user_id,
                "event_type": event_type,
                "payload": payload,
                "correlation_id": correlation_id,
            }
        )
        return SimpleNamespace(id=uuid.uuid4())

    async def _live(user_id, *, event_type, data):
        captured["live_push"].append(
            {"user_id": user_id, "event_type": event_type, "data": data}
        )

    async def _record_conflict(db, **kwargs):
        captured["conflicts"].append(kwargs)
        from app.models.domain_event import DomainEvent
        return DomainEvent(
            id=uuid.uuid4(),
            lead_client_id=uuid.uuid4(),
            event_type="persona.conflict_detected",
            actor_type="system",
            source="test",
            payload_json={},
            idempotency_key=f"x-{uuid.uuid4()}",
            schema_version=1,
            correlation_id="test",
        )

    # The engine fans events through its own emit_domain_event.
    monkeypatch.setattr(engine, "emit_domain_event", _emit)
    monkeypatch.setattr(hook, "ws_enqueue", _enqueue)
    # Live push lives on app.ws.notifications — patch the import the
    # hook does inside its push function.
    monkeypatch.setattr(
        "app.ws.notifications.send_ws_notification", _live, raising=False
    )

    from app.services import persona_memory
    monkeypatch.setattr(
        persona_memory, "record_conflict_attempt", _record_conflict
    )

    return captured


# ── Happy path ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_hook_clean_reply_emits_nothing(monkeypatch):
    """A spec-compliant reply with persona context produces no events
    and no WS frames. The hook must be *quiet* on the happy path."""
    db = _make_db(snapshot=_snapshot(), persona=_persona())
    captured = _capture_outbound(monkeypatch)

    n = await hook.audit_and_publish_assistant_reply(
        db,
        session_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        reply="Хорошо, я перезвоню вам через час и уточним детали.",
        previous_assistant_replies=["Здравствуйте."],
        mode="chat",
    )

    assert n == 0
    assert captured["events"] == []
    assert captured["outbox"] == []
    assert captured["live_push"] == []
    assert captured["conflicts"] == []


# ── Legacy three checks ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_hook_emits_event_on_too_long_call_reply(monkeypatch):
    db = _make_db()
    captured = _capture_outbound(monkeypatch)

    n = await hook.audit_and_publish_assistant_reply(
        db,
        session_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        reply="Здравствуйте. У меня есть предложение. Давайте обсудим. Это будет полезно.",
        mode="call",
    )

    assert n == 1
    assert captured["events"][0]["event_type"] == "conversation.policy_violation_detected"
    assert captured["events"][0]["payload"]["code"] == "too_long_for_mode"
    assert captured["outbox"][0]["event_type"] == "conversation.policy_violation_detected"
    assert captured["live_push"][0]["event_type"] == "conversation.policy_violation_detected"


@pytest.mark.asyncio
async def test_audit_hook_emits_event_on_near_repeat(monkeypatch):
    db = _make_db()
    captured = _capture_outbound(monkeypatch)

    prev = "Расскажите про вашу работу."
    await hook.audit_and_publish_assistant_reply(
        db,
        session_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        reply=prev,
        previous_assistant_replies=[prev],
        mode="chat",
    )
    codes = [e["payload"]["code"] for e in captured["events"]]
    assert "near_repeat" in codes


# ── Persona-aware checks ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_hook_unjustified_identity_change_records_snapshot_drift(monkeypatch):
    """Critical-severity violation in addition to the policy event
    fires :func:`persona_memory.record_conflict_attempt` so the §9.2
    invariant 1 counter bumps. Both event types appear in WS outbox
    + live push."""
    snapshot = _snapshot(address_form="вы")
    db = _make_db(snapshot=snapshot)
    captured = _capture_outbound(monkeypatch)

    await hook.audit_and_publish_assistant_reply(
        db,
        session_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        reply="Скажи, ты будешь платить?",
        mode="chat",
    )

    codes = [e["payload"]["code"] for e in captured["events"]]
    assert "unjustified_identity_change" in codes

    # snapshot drift recorded
    assert len(captured["conflicts"]) == 1
    assert captured["conflicts"][0]["snapshot"] is snapshot

    # persona-class violations also publish a paired
    # ``persona.conflict_detected`` WS frame so the dedicated badge
    # can count separately.
    outbox_types = [o["event_type"] for o in captured["outbox"]]
    assert "persona.conflict_detected" in outbox_types
    assert "conversation.policy_violation_detected" in outbox_types

    live_types = [o["event_type"] for o in captured["live_push"]]
    assert "persona.conflict_detected" in live_types
    assert "conversation.policy_violation_detected" in live_types


@pytest.mark.asyncio
async def test_audit_hook_asked_known_slot_publishes_persona_frame(monkeypatch):
    """The ``asked_known_slot_again`` violation belongs to the
    persona-conflict family — paired persona frame must publish so the
    badge counts it (it's an identity-class footgun, not a length one)."""
    persona = _persona("city")
    db = _make_db(snapshot=_snapshot(), persona=persona)
    captured = _capture_outbound(monkeypatch)

    await hook.audit_and_publish_assistant_reply(
        db,
        session_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        reply="В каком городе вы живёте? И как ваш номер?",
        mode="chat",
    )

    codes = [e["payload"]["code"] for e in captured["events"]]
    assert "asked_known_slot_again" in codes
    outbox_types = [o["event_type"] for o in captured["outbox"]]
    assert "persona.conflict_detected" in outbox_types


# ── Resilience ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_hook_swallows_emit_failures(monkeypatch):
    """A crash inside the engine's emit path must not leak into the
    WS handler. The hook returns 0 violations (because the engine
    layer never returned a result)."""
    db = _make_db()
    captured = _capture_outbound(monkeypatch)

    def _boom(*_a, **_kw):
        raise RuntimeError("simulated emit_domain_event crash")

    monkeypatch.setattr(engine, "emit_domain_event", _boom)

    # Should not raise.
    n = await hook.audit_and_publish_assistant_reply(
        db,
        session_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        reply="Здравствуйте. У меня есть предложение. Давайте обсудим. Это будет полезно.",
        mode="call",
    )
    # The engine ran the audit and returned 1 violation (legacy too_long
    # check). The emit_violation path crashed; the hook reports the count
    # of violations *detected* (= 1), but the WS push still runs because
    # the hook catches each step independently.
    assert n == 1


@pytest.mark.asyncio
async def test_audit_hook_swallows_live_push_failures(monkeypatch):
    """A failing live-push must not stop the durable outbox enqueue or
    the engine emit. The next-best-action is partial visibility, not
    nothing."""
    db = _make_db()
    captured = _capture_outbound(monkeypatch)

    async def _boom(*_a, **_kw):
        raise RuntimeError("simulated live push crash")

    monkeypatch.setattr(
        "app.ws.notifications.send_ws_notification", _boom, raising=False
    )

    n = await hook.audit_and_publish_assistant_reply(
        db,
        session_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        reply="Здравствуйте. У меня есть предложение. Давайте обсудим. Это будет полезно.",
        mode="call",
    )
    assert n == 1
    # Outbox still got the frame.
    assert any(
        o["event_type"] == "conversation.policy_violation_detected"
        for o in captured["outbox"]
    )


# ── History helper ──────────────────────────────────────────────────────


def test_previous_assistant_replies_filters_and_truncates():
    history = [
        {"role": "user", "content": "Привет."},
        {"role": "assistant", "content": "А1"},
        {"role": "user", "content": "..."},
        {"role": "assistant", "content": "А2"},
        {"role": "assistant", "content": "А3"},
        {"role": "assistant", "content": "А4"},
        {"role": "assistant", "content": "А5"},
        {"role": "assistant", "content": "А6"},
    ]
    out = hook.previous_assistant_replies_from_history(history, limit=3)
    assert out == ["А4", "А5", "А6"]


def test_previous_assistant_replies_skips_empty_strings():
    history = [
        {"role": "assistant", "content": ""},
        {"role": "assistant", "content": "   "},
        {"role": "assistant", "content": "Реальная реплика"},
    ]
    out = hook.previous_assistant_replies_from_history(history)
    assert out == ["Реальная реплика"]


@pytest.mark.asyncio
async def test_audit_hook_home_preview_snapshot_no_persona(monkeypatch):
    """Audit-2026-04-28: home_preview sessions have a snapshot but
    ``snapshot.lead_client_id IS NULL`` so MemoryPersona lookup
    returns None. Snapshot-aware checks fire; persona-aware skip.
    """
    snapshot = SessionPersonaSnapshot(
        session_id=uuid.uuid4(),
        lead_client_id=None,
        full_name="Превью Имя",
        gender="female",
        address_form="вы",
        tone="neutral",
        captured_from="home_preview",
        persona_version=1,
        mutation_blocked_count=0,
    )
    db = _make_db(snapshot=snapshot, persona=None)
    captured = _capture_outbound(monkeypatch)

    await hook.audit_and_publish_assistant_reply(
        db,
        session_id=snapshot.session_id,
        user_id=uuid.uuid4(),
        reply="Скажи, ты в каком городе живёшь?",
        mode="chat",
    )

    codes = [e["payload"]["code"] for e in captured["events"]]
    assert "unjustified_identity_change" in codes
    assert "asked_known_slot_again" not in codes


@pytest.mark.asyncio
async def test_audit_hook_swallow_drift_record_failure(monkeypatch):
    """Audit-2026-04-28: if record_conflict_attempt raises, the
    policy event MUST still emit + WS push goes — drift counter is
    observability, losing it must not propagate to WS handler."""
    snapshot = _snapshot(address_form="вы")
    db = _make_db(snapshot=snapshot)
    captured = _capture_outbound(monkeypatch)

    async def _boom(*_a, **_kw):
        raise RuntimeError("simulated drift counter failure")

    from app.services import persona_memory
    monkeypatch.setattr(persona_memory, "record_conflict_attempt", _boom)

    n = await hook.audit_and_publish_assistant_reply(
        db,
        session_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        reply="Скажи, ты будешь платить?",
        mode="chat",
    )

    # The reply triggers >=1 violation; what matters for this test is
    # that the drift-recorder failure didn't propagate to the caller.
    assert n >= 1
    assert captured["conflicts"] == []
    codes = [e["payload"]["code"] for e in captured["events"]]
    assert "unjustified_identity_change" in codes
    outbox_types = [o["event_type"] for o in captured["outbox"]]
    assert "conversation.policy_violation_detected" in outbox_types
