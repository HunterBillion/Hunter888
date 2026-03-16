"""E2E WebSocket test: connect, start session, send text, receive echo, end session.

Requires running API server at WS_URL (default: ws://localhost:8000/ws/training).
Run with: pytest tests/e2e/test_websocket.py -v
"""

import asyncio
import json
import os

import httpx
import pytest
import websockets

API_URL = os.getenv("API_URL", "http://localhost:8000/api")
WS_URL = os.getenv("WS_URL", "ws://localhost:8000/ws/training")

TEST_EMAIL = "manager@trainer.local"
TEST_PASSWORD = "manager123"


async def get_auth_token() -> str:
    """Log in and return access token."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{API_URL}/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


async def get_first_scenario_id(token: str) -> str:
    """Create a training session and return session_id."""
    async with httpx.AsyncClient() as client:
        # Get scenarios
        resp = await client.get(
            f"{API_URL}/training/history",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
    return None  # Will use session.start with session_id


async def create_session(token: str) -> str:
    """Create a training session via REST and return session_id."""
    async with httpx.AsyncClient() as client:
        # List scenarios to get an ID
        resp = await client.get(
            f"{API_URL}/scenarios/",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 200 and resp.json():
            scenario_id = resp.json()[0]["id"]
        else:
            pytest.skip("No scenarios available — run seed_db first")
            return ""

        resp = await client.post(
            f"{API_URL}/training/sessions",
            json={"scenario_id": scenario_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return resp.json()["id"]


@pytest.mark.asyncio
async def test_websocket_connect_and_session_start():
    """Test: WS connects, sends session.start, receives session.started."""
    token = await get_auth_token()
    session_id = await create_session(token)

    ws_url = f"{WS_URL}?token={token}"
    async with websockets.connect(ws_url) as ws:
        # Send session.start
        await ws.send(json.dumps({
            "type": "session.start",
            "data": {"session_id": session_id},
        }))

        # Wait for session.started (timeout 5s)
        response = await asyncio.wait_for(ws.recv(), timeout=5.0)
        msg = json.loads(response)

        assert msg["type"] == "session.started"
        assert "character_name" in msg.get("data", {})


@pytest.mark.asyncio
async def test_websocket_text_message_echo():
    """Test: send text.message, receive character.response (echo mode)."""
    token = await get_auth_token()
    session_id = await create_session(token)

    ws_url = f"{WS_URL}?token={token}"
    async with websockets.connect(ws_url) as ws:
        # Start session
        await ws.send(json.dumps({
            "type": "session.start",
            "data": {"session_id": session_id},
        }))
        started = await asyncio.wait_for(ws.recv(), timeout=5.0)
        assert json.loads(started)["type"] == "session.started"

        # Send text message
        await ws.send(json.dumps({
            "type": "text.message",
            "data": {"content": "Здравствуйте, я хотел бы узнать о ваших услугах"},
        }))

        # Expect character.response within 2s (echo mode, no LLM)
        response = await asyncio.wait_for(ws.recv(), timeout=2.0)
        msg = json.loads(response)

        assert msg["type"] == "character.response"
        assert "content" in msg.get("data", {})
        assert len(msg["data"]["content"]) > 0


@pytest.mark.asyncio
async def test_websocket_session_end():
    """Test: session.end produces session.ended."""
    token = await get_auth_token()
    session_id = await create_session(token)

    ws_url = f"{WS_URL}?token={token}"
    async with websockets.connect(ws_url) as ws:
        # Start
        await ws.send(json.dumps({
            "type": "session.start",
            "data": {"session_id": session_id},
        }))
        await asyncio.wait_for(ws.recv(), timeout=5.0)

        # End session
        await ws.send(json.dumps({
            "type": "session.end",
            "data": {},
        }))

        response = await asyncio.wait_for(ws.recv(), timeout=5.0)
        msg = json.loads(response)

        assert msg["type"] == "session.ended"


@pytest.mark.asyncio
async def test_websocket_latency_under_500ms():
    """Test: echo response latency < 500ms (DoD requirement)."""
    token = await get_auth_token()
    session_id = await create_session(token)

    ws_url = f"{WS_URL}?token={token}"
    async with websockets.connect(ws_url) as ws:
        # Start
        await ws.send(json.dumps({
            "type": "session.start",
            "data": {"session_id": session_id},
        }))
        await asyncio.wait_for(ws.recv(), timeout=5.0)

        # Measure round-trip
        import time

        start = time.monotonic()
        await ws.send(json.dumps({
            "type": "text.message",
            "data": {"content": "тест задержки"},
        }))
        await asyncio.wait_for(ws.recv(), timeout=2.0)
        elapsed_ms = (time.monotonic() - start) * 1000

        assert elapsed_ms < 500, f"Response latency {elapsed_ms:.0f}ms exceeds 500ms limit"
