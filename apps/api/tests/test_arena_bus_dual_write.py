"""Tests for the WS-handler arena-bus dual-write (Эпик 2 PR-2).

Covers the contract that protects production stability while we roll
out the bus:

* Dual-write is OFF by default (flag must be explicitly enabled).
* When OFF, _send_to_user emits zero bus traffic.
* When ON, _send_to_user fires a publish with envelope shape:
    type = msg_type, producer = "ws.pvp.handler",
    correlation_id = current contextvar value (PR A foundation)
* When ON and bus raises, the WS path stays unaffected.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.core.correlation import bind_correlation_id, reset_correlation_id


@pytest.mark.asyncio
async def test_dual_write_disabled_by_default():
    from app.config import settings
    assert settings.arena_bus_dual_write_enabled is False


@pytest.mark.asyncio
async def test_send_to_user_skips_bus_when_flag_off():
    """Default state: no bus publish even though we have a connected user."""
    from app.ws import pvp as pvp_ws

    user_id = uuid.uuid4()
    fake_ws = AsyncMock()
    fake_ws.send_json = AsyncMock()

    with patch.dict(
        pvp_ws._active_connections,
        {user_id: (fake_ws, "conn-id")},
        clear=True,
    ), patch("app.services.arena_bus.publish", new_callable=AsyncMock) as mock_publish:
        await pvp_ws._send_to_user(user_id, "duel.message", {"text": "hi"})

    fake_ws.send_json.assert_awaited_once()
    mock_publish.assert_not_called()


@pytest.mark.asyncio
async def test_send_to_user_publishes_to_bus_when_flag_on():
    from app.ws import pvp as pvp_ws

    user_id = uuid.uuid4()
    fake_ws = AsyncMock()
    fake_ws.send_json = AsyncMock()

    cid_token = bind_correlation_id("duel-deadbeef")
    try:
        with patch.dict(
            pvp_ws._active_connections,
            {user_id: (fake_ws, "conn-id")},
            clear=True,
        ), patch.object(
            pvp_ws.settings, "arena_bus_dual_write_enabled", True,
        ), patch(
            "app.services.arena_bus.publish", new_callable=AsyncMock,
        ) as mock_publish:
            await pvp_ws._send_to_user(user_id, "judge.score", {"round": 1})

        # WS frame went out…
        fake_ws.send_json.assert_awaited_once_with({"type": "judge.score", "data": {"round": 1}})
        # …and the bus got a copy.
        mock_publish.assert_awaited_once()
        # Envelope shape contract.
        published_event = mock_publish.call_args.args[0]
        assert published_event.type == "judge.score"
        assert published_event.correlation_id == "duel-deadbeef"
        assert published_event.producer == "ws.pvp.handler"
        assert published_event.payload["round"] == 1
        assert published_event.payload["_recipient_user_id"] == str(user_id)
    finally:
        reset_correlation_id(cid_token)


@pytest.mark.asyncio
async def test_send_to_user_does_not_raise_when_bus_publish_fails():
    """Bus is best-effort — a Redis outage must not break the WS path."""
    from app.ws import pvp as pvp_ws

    user_id = uuid.uuid4()
    fake_ws = AsyncMock()
    fake_ws.send_json = AsyncMock()

    failing_publish = AsyncMock(side_effect=ConnectionError("Redis down"))

    with patch.dict(
        pvp_ws._active_connections,
        {user_id: (fake_ws, "conn-id")},
        clear=True,
    ), patch.object(
        pvp_ws.settings, "arena_bus_dual_write_enabled", True,
    ), patch(
        "app.services.arena_bus.publish", failing_publish,
    ):
        # No exception expected even though publish raises.
        await pvp_ws._send_to_user(user_id, "duel.message", {"text": "hi"})

    fake_ws.send_json.assert_awaited_once()
    failing_publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_to_user_publishes_even_when_user_not_connected():
    """If the recipient is offline, the WS frame is dropped (logged) but
    the bus copy still goes out — Notification Hub / audit consumers
    still need to see the event for replay-on-reconnect.
    """
    from app.ws import pvp as pvp_ws

    user_id = uuid.uuid4()

    cid_token = bind_correlation_id("duel-offline")
    try:
        with patch.dict(
            pvp_ws._active_connections,
            {},  # nobody connected
            clear=True,
        ), patch.object(
            pvp_ws.settings, "arena_bus_dual_write_enabled", True,
        ), patch(
            "app.services.arena_bus.publish", new_callable=AsyncMock,
        ) as mock_publish:
            await pvp_ws._send_to_user(user_id, "match.found", {"x": 1})

        mock_publish.assert_awaited_once()
    finally:
        reset_correlation_id(cid_token)


@pytest.mark.asyncio
async def test_publish_carries_empty_correlation_when_no_contextvar_bound():
    """Lobby / pre-duel events fire from a context with no duel_id bound.
    The bus still accepts them; they only hit the global stream
    (per-correlation publish is skipped — see test_arena_bus tests).
    """
    from app.ws import pvp as pvp_ws

    user_id = uuid.uuid4()
    fake_ws = AsyncMock()
    fake_ws.send_json = AsyncMock()

    with patch.dict(
        pvp_ws._active_connections,
        {user_id: (fake_ws, "conn-id")},
        clear=True,
    ), patch.object(
        pvp_ws.settings, "arena_bus_dual_write_enabled", True,
    ), patch(
        "app.services.arena_bus.publish", new_callable=AsyncMock,
    ) as mock_publish:
        await pvp_ws._send_to_user(user_id, "queue.status", {"position": 1})

    published_event = mock_publish.call_args.args[0]
    assert published_event.correlation_id == ""
