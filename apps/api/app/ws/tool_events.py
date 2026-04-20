"""WebSocket emit helper for MCP tool lifecycle events.

``make_tool_emit(ws)`` returns an async callable that ``llm_tools`` can use to
forward ``assistant.tool_call`` / ``assistant.tool_result`` / ``assistant.tool_error``
events to the frontend. Kept in a separate module so the training WS file
doesn't need to learn about MCP types, and so unit tests can substitute a
plain list-recorder for the emitter.

Frontend contracts documented in ``app.mcp.ws_events``.
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# Same signature as ``llm_tools.EmitFn``.
ToolEmitFn = Callable[[str, dict], Awaitable[None]]


def make_tool_emit(ws: WebSocket, *, send: Callable | None = None) -> ToolEmitFn:
    """Return a function that wraps MCP tool events into the session's WS.

    Args:
        ws: the live FastAPI WebSocket.
        send: optional injection for tests. Defaults to importing the
            training WS ``_send`` helper.
    """

    if send is None:
        # Lazy import to avoid a circular ws.training → ws.tool_events → ws.training
        from app.ws.training import _send as default_send

        send = default_send

    async def _emit(event_type: str, payload: dict) -> None:
        try:
            await send(ws, event_type, payload)
        except Exception as exc:  # noqa: BLE001
            # Never let a WS hiccup crash the LLM pipeline. We log + swallow.
            logger.warning("tool_events emit(%s) failed: %s", event_type, exc)

    return _emit
