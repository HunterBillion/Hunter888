"""Barge-in orphan-audio suppression (2026-05-30) — turn-epoch stamping.

When the manager barges in (starts speaking over the AI) the call client calls
``tts.stop()`` and flushes its TTS queue. But the WS receive loop is blocked
awaiting the in-flight ``_generate_character_reply``, so the backend keeps
streaming the *interrupted* turn's TTS chunks. They arrive AFTER the flush and
the client's gap-skip logic forces them through → orphaned audio plays over the
manager (the "garbage / artefacts" symptom).

The fix stamps every ``tts.audio`` / ``tts.audio_chunk`` with a monotonic
per-turn ``turn_seq`` (via a ContextVar consulted in ``_send``) so the client
can drop audio from a turn it already barged over. These tests pin the wire
contract and — critically — the cross-session isolation guarantee: a ContextVar
(not a module global) so two calls served by the same worker never stamp each
other's audio.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.ws import training as t


def _fake_ws():
    """Minimal WebSocket stand-in for ``_send`` (records every send_json)."""
    ws = SimpleNamespace()
    ws.state = SimpleNamespace()
    ws.sent: list[dict] = []

    async def _send_json(obj):
        ws.sent.append(obj)

    ws.send_json = _send_json
    return ws


@pytest.fixture(autouse=True)
def _reset_turn_seq():
    """Each test starts/ends with the epoch unset (no cross-test leakage)."""
    token = t._current_turn_seq.set(None)
    try:
        yield
    finally:
        t._current_turn_seq.reset(token)


# ── Wire contract ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("msg_type", ["tts.audio", "tts.audio_chunk"])
async def test_streaming_tts_gets_turn_seq_when_epoch_set(msg_type):
    ws = _fake_ws()
    t._current_turn_seq.set(7)
    await t._send(ws, msg_type, {"audio_b64": "x", "sentence_index": 0})
    assert ws.sent[-1]["data"]["turn_seq"] == 7, (
        "streaming TTS must carry the live turn epoch so the client can drop "
        "orphans from a barged-over turn"
    )


@pytest.mark.asyncio
async def test_no_turn_seq_when_epoch_unset():
    """Flag off ⇒ ``_generate_character_reply`` never sets the epoch ⇒ no stamp.

    This is the default-OFF guarantee: behaviour is bit-for-bit identical to
    pre-fix because the client only suppresses when ``turn_seq`` is present.
    """
    ws = _fake_ws()
    assert t._current_turn_seq.get() is None
    await t._send(ws, "tts.audio", {"audio_b64": "x"})
    assert "turn_seq" not in ws.sent[-1]["data"]


@pytest.mark.asyncio
async def test_barge_reaction_is_never_stamped():
    """``interruption_reaction`` is the desired post-barge sound — never drop it.

    If it carried the (already-barged) turn_seq the client would suppress the
    very reaction the interrupt is supposed to produce.
    """
    ws = _fake_ws()
    t._current_turn_seq.set(3)
    await t._send(
        ws, "tts.audio", {"audio_b64": "x", "interruption_reaction": True}
    )
    assert "turn_seq" not in ws.sent[-1]["data"]


@pytest.mark.asyncio
async def test_non_tts_messages_are_not_stamped():
    ws = _fake_ws()
    t._current_turn_seq.set(5)
    await t._send(ws, "character.response", {"text": "привет"})
    assert "turn_seq" not in ws.sent[-1]["data"]


@pytest.mark.asyncio
async def test_existing_turn_seq_is_not_overwritten():
    """Defensive: if a caller ever pre-stamps, _send respects it."""
    ws = _fake_ws()
    t._current_turn_seq.set(9)
    await t._send(ws, "tts.audio_chunk", {"audio_b64": "x", "turn_seq": 2})
    assert ws.sent[-1]["data"]["turn_seq"] == 2


# ── Cross-session isolation (§4.1 concurrency proof) ───────────────────────


async def _one_turn(seq: int, ws, barrier: asyncio.Barrier) -> None:
    """Simulate one WS connection's turn: set its epoch, then (after BOTH
    connections have set theirs) emit a TTS frame. The barrier guarantees the
    two ``set()`` calls interleave before either ``_send`` runs — the exact
    shape that would cross-contaminate under a plain module global."""
    t._current_turn_seq.set(seq)
    await barrier.wait()
    await t._send(ws, "tts.audio", {"audio_b64": f"audio-{seq}"})


@pytest.mark.asyncio
async def test_concurrent_turns_do_not_cross_contaminate():
    """Two simultaneous calls on one worker must each stamp their OWN epoch.

    ``asyncio.gather`` wraps each coro in its own Task, and a Task copies the
    current context at creation — so each ``set()`` is private to its task.
    On a shared global both sends would read whichever ran ``set()`` last
    (here: 22), proving why this MUST be a ContextVar.
    """
    ws_a, ws_b = _fake_ws(), _fake_ws()
    barrier = asyncio.Barrier(2)

    await asyncio.gather(
        _one_turn(11, ws_a, barrier),
        _one_turn(22, ws_b, barrier),
    )

    assert ws_a.sent[-1]["data"]["turn_seq"] == 11
    assert ws_b.sent[-1]["data"]["turn_seq"] == 22
