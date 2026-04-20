"""Tool executor — the single entry point between LLM tool_calls and handlers.

``dispatch(name, args, ctx)`` is a coroutine that:

1. Looks up the Tool in the Registry.
2. Runs pre-guards (auth, rate-limit).
3. Executes the handler under ``asyncio.wait_for(..., timeout_s)``.
4. Validates the result (size cap, JSON-serializability).
5. Returns a ``ToolResult`` dataclass.

All exceptions are translated into ``ToolExecutionError`` with a short code
and human-readable message; the WS layer converts that into an
``assistant.tool_error`` event. A successful return becomes an
``assistant.tool_result`` event.

The executor itself does NOT emit WS events — that's the caller's job (see
``ws/training.py`` in Phase 1.7). We keep pure logic here so the executor is
testable without a WebSocket.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.mcp.guards import (
    GuardViolation,
    check_auth,
    check_rate_limit,
    check_result_size,
)
from app.mcp.registry import ToolNotFoundError, ToolRegistry
from app.mcp.tool import ToolContext

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolResult:
    """Returned by ``dispatch`` on success."""

    call_id: str
    name: str
    result: dict
    latency_ms: int


class ToolExecutionError(Exception):
    """Raised by ``dispatch`` on any failure.

    ``code`` is one of: ``tool_not_found``, ``auth_required``,
    ``rate_limited``, ``timeout``, ``handler_error``, ``result_too_large``,
    ``invalid_result``.

    ``fatal=True`` tells the WS layer to abort the LLM turn (e.g. the
    configured tool doesn't exist — no point trying to continue). Most
    runtime errors are non-fatal — the model is free to respond in text.
    """

    def __init__(
        self,
        *,
        call_id: str,
        name: str,
        code: str,
        message: str,
        fatal: bool = False,
    ):
        super().__init__(message)
        self.call_id = call_id
        self.name = name
        self.code = code
        self.message = message
        self.fatal = fatal

    def as_payload(self) -> dict:
        """Shape the error event payload that flows to the WS client."""

        return {
            "call_id": self.call_id,
            "name": self.name,
            "error": {"code": self.code, "message": self.message},
            "fatal": self.fatal,
        }


async def dispatch(
    name: str,
    arguments: dict,
    ctx: ToolContext,
    *,
    call_id: str | None = None,
) -> ToolResult:
    """Run the registered tool ``name`` with ``arguments`` under ``ctx``.

    Caller typically passes the ``call_id`` from the provider's tool_call
    payload; if absent we mint a UUID so every invocation is individually
    traceable.
    """

    call_id = call_id or str(uuid.uuid4())

    # 1. Lookup — unknown name is FATAL (LLM hallucinated a tool).
    try:
        tool = ToolRegistry.get(name)
    except ToolNotFoundError as exc:
        raise ToolExecutionError(
            call_id=call_id, name=name,
            code="tool_not_found", message=str(exc), fatal=True,
        )

    # 2. Pre-guards.
    try:
        check_auth(tool, ctx)
        await check_rate_limit(tool, ctx)
    except GuardViolation as gv:
        raise ToolExecutionError(
            call_id=call_id, name=name,
            code=gv.code, message=gv.message, fatal=False,
        )

    # 3. Handler execution under timeout.
    import time

    started_at = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            tool.handler(arguments, ctx),
            timeout=tool.timeout_s,
        )
    except asyncio.TimeoutError:
        raise ToolExecutionError(
            call_id=call_id, name=name,
            code="timeout",
            message=f"tool {name!r} did not complete in {tool.timeout_s}s",
            fatal=False,
        )
    except Exception as exc:  # noqa: BLE001 — anything from user handler
        logger.exception("tool %s raised", name)
        raise ToolExecutionError(
            call_id=call_id, name=name,
            code="handler_error",
            message=f"{type(exc).__name__}: {exc}",
            fatal=False,
        )

    # 4. Post-guards.
    if not isinstance(result, dict):
        raise ToolExecutionError(
            call_id=call_id, name=name,
            code="invalid_result",
            message=f"tool {name!r} returned {type(result).__name__}, expected dict",
            fatal=False,
        )
    try:
        check_result_size(tool, result)
    except GuardViolation as gv:
        raise ToolExecutionError(
            call_id=call_id, name=name,
            code=gv.code, message=gv.message, fatal=False,
        )

    latency_ms = int((time.perf_counter() - started_at) * 1000)
    logger.info(
        "mcp.dispatch ok: tool=%s call_id=%s latency_ms=%d",
        name, call_id, latency_ms,
    )
    return ToolResult(
        call_id=call_id, name=name, result=result, latency_ms=latency_ms,
    )
