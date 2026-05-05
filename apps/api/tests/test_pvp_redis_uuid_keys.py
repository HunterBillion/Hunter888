"""Regression test for the UUID-key TypeError that silently killed every
PvE duel in production.

Symptom in prod logs (2026-05-05):
    TypeError: keys must be str, int, float, bool or None,
               not asyncpg.pgproto.pgproto.UUID
    File "/app/app/ws/pvp.py", line 85, in save_session
        await r.set(..., json.dumps(data, default=str), ...)

Root cause: ``session["player_names"]`` is built with the asyncpg
``duel.player1_id`` / ``player2_id`` UUIDs as **dict keys**.
``json.dumps(default=str)`` turns UUID **values** into strings, but
``default=`` is never called for keys — keys must already be of a
JSON-native type. Every PvE duel raised inside ``_handle_duel_ready``
and the bot opener never reached the user.

Fix: normalize ``player_names`` keys to ``str`` before ``json.dumps``.

This regression test exercises the SAME json.dumps call shape that
``PvPDuelRedis.save_session`` uses, with a UUID-keyed ``player_names``
dict, and asserts it round-trips through json without raising.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.ws.pvp import PvPDuelRedis


@pytest.mark.asyncio
async def test_save_session_round_trips_uuid_keyed_player_names():
    """The pre-fix json.dumps would raise on this exact session shape."""
    p1 = uuid.uuid4()
    p2 = uuid.uuid4()
    session = {
        "duel_id": uuid.uuid4(),
        "player1_id": p1,
        "player2_id": p2,
        # The poison field — UUID *keys*, not values.
        "player_names": {p1: "Alice", p2: "Bob"},
        "difficulty": "easy",
        "ready": {p1, p2},
        "round": 1,
        "started": False,
        "round_task": None,  # filtered out
        "round_started_at": None,
        "completed": False,
        "is_pve": True,
        "history": {1: [], 2: []},
        "player_names_extra": None,
    }

    # Capture what save_session would have written to Redis.
    written = {}

    class _FakeRedis:
        async def set(self, key, value, ex=None):  # noqa: D401
            written[key] = value
        async def expire(self, *a, **kw):
            return None

    fake = _FakeRedis()
    with patch.object(PvPDuelRedis, "_r", classmethod(lambda cls: fake)):
        # Pre-fix this raised TypeError. Post-fix it should complete.
        await PvPDuelRedis.save_session(str(session["duel_id"]), session)

    payload = written[f"pvp:duel:{session['duel_id']}"]
    decoded = json.loads(payload)

    # player_names keys must round-trip as the stringified UUIDs.
    assert decoded["player_names"] == {str(p1): "Alice", str(p2): "Bob"}
    # Other UUID-valued fields still serialize through default=str.
    assert decoded["player1_id"] == str(p1)
    assert decoded["player2_id"] == str(p2)


@pytest.mark.asyncio
async def test_save_session_handles_missing_player_names():
    """Defensive: if a session is built without player_names (e.g.
    spectator-only state), save_session must still work."""
    session = {
        "duel_id": uuid.uuid4(),
        "player1_id": uuid.uuid4(),
        "player2_id": uuid.uuid4(),
        "ready": set(),
        "round": 0,
        "started": False,
        "round_task": None,
        "completed": False,
        "history": {1: [], 2: []},
    }

    written = {}

    class _FakeRedis:
        async def set(self, key, value, ex=None):
            written[key] = value
        async def expire(self, *a, **kw):
            return None

    fake = _FakeRedis()
    with patch.object(PvPDuelRedis, "_r", classmethod(lambda cls: fake)):
        await PvPDuelRedis.save_session(str(session["duel_id"]), session)

    decoded = json.loads(written[f"pvp:duel:{session['duel_id']}"])
    assert "player_names" not in decoded
