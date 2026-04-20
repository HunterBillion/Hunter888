"""High-level helper: run an LLM turn that may invoke MCP tools.

Phase 1.6 (2026-04-18). This module is the bridge between ``services.llm``
(which generates text) and ``app.mcp`` (which runs tools). It:

1. Builds a tool spec from the Registry (session-scoped by default).
2. Calls the preferred OpenAI-compatible provider.
3. If the model returned ``tool_calls``:
   a) Emits ``assistant.tool_call`` via an optional emit callback.
   b) Dispatches each call through ``mcp.executor.dispatch``.
   c) Emits ``assistant.tool_result`` / ``assistant.tool_error`` for each.
   d) Re-calls the same provider with a ``tool`` role message per result.
4. Returns the final ``LLMResponse`` (no tool_calls in it).

Design decisions:

- **Streaming off for tool turns.** Tool-calling and token streaming together
  are messy across providers; we pay one extra round-trip latency in exchange
  for robust event ordering (call → result → final message).
- **Only OpenAI-compatible providers (``navy`` / OpenAI) go through this
  path.** Gemma/Ollama tool support is fragmented and explicitly out of scope.
  Callers that aren't using navy will silently skip the tools spec.
- **Non-fatal errors keep the loop alive.** If a tool fails with
  ``fatal=False``, the error goes into the prompt (so the LLM can decide to
  apologize in text), the loop continues to the second round-trip.
- **Max iterations.** ``MAX_TOOL_ITERATIONS`` bounds how many consecutive
  tool rounds the model can trigger before we force a text-only final turn.
  Prevents infinite call loops while still letting a chain of 2-3 tools work.

Typical usage:

    from app.services.llm_tools import generate_with_tool_dispatch
    from app.mcp import ToolContext

    ctx = ToolContext(session_id=str(session.id), user_id=str(user.id))
    resp = await generate_with_tool_dispatch(
        system_prompt=prompt,
        messages=history,
        ctx=ctx,
        emit=lambda event_type, payload: await websocket.send_json(...),
    )
    final_text = resp.content  # may be empty if the model just called tools
"""

from __future__ import annotations

import json
import logging
from typing import Awaitable, Callable, Literal

from app.config import settings
from app.mcp import ToolContext, dispatch
from app.mcp.executor import ToolExecutionError, ToolResult
from app.mcp.registry import ToolRegistry
from app.mcp.ws_events import (
    TOOL_CALL_EVENT,
    TOOL_ERROR_EVENT,
    TOOL_RESULT_EVENT,
)

logger = logging.getLogger(__name__)

# Bounded so a misbehaving model can't burn unbounded tokens chaining tools.
MAX_TOOL_ITERATIONS = 3

# Callback signature: coroutine that takes an event type and payload and
# forwards to the WebSocket. Nullable — if omitted we still dispatch tools
# but the frontend won't see the intermediate state.
EmitFn = Callable[[str, dict], Awaitable[None]]


async def generate_with_tool_dispatch(
    *,
    system_prompt: str,
    messages: list[dict],
    ctx: ToolContext,
    provider: Literal["local", "openai"] = "local",
    timeout: float = 60.0,
    scope: Literal["session", "user", "global"] = "session",
    emit: EmitFn | None = None,
):
    """Return the final ``LLMResponse`` for a turn that may invoke MCP tools.

    If ``settings.mcp_enabled`` is False, degenerates into a plain
    ``_call_local_llm`` / ``_call_openai`` call with no ``tools`` arg.

    ``provider="local"`` targets the OpenAI-compatible branch of
    ``_call_local_llm`` (e.g. navy.api). Private-network Ollama rejects this
    path up-stream; callers should use ``provider="openai"`` as a fallback.
    """

    # Late import to avoid circular dep during llm.py loading.
    from app.services.llm import (
        LLMResponse,
        _call_local_llm,
        _call_openai,
    )

    def _call(
        *, raw_messages=None, tools=None,
    ) -> Awaitable[LLMResponse]:
        if provider == "openai":
            return _call_openai(
                system_prompt, messages, timeout,
                tools=tools, raw_messages=raw_messages,
            )
        return _call_local_llm(
            system_prompt, messages, timeout,
            tools=tools, raw_messages=raw_messages,
        )

    tools_spec: list[dict] | None = None
    if settings.mcp_enabled and ToolRegistry.all():
        tools_spec = ToolRegistry.openai_tools_spec(scope=scope)
        if not tools_spec:
            tools_spec = None

    if not tools_spec:
        # Fast path — no registered tools or MCP disabled. One call, no loop.
        return await _call()

    # Iterative loop. We maintain a growing ``conversation`` list that's fed
    # to the provider via ``raw_messages`` in rounds 2+. Round 1 uses the
    # standard ``messages`` arg so existing callers see no behaviour change
    # when the model decides not to invoke a tool.
    conversation: list[dict] = []
    resp: LLMResponse | None = None

    for iteration in range(MAX_TOOL_ITERATIONS):
        if iteration == 0:
            # First round: full history via the standard path.
            resp = await _call(tools=tools_spec)
        else:
            resp = await _call(raw_messages=conversation, tools=tools_spec)

        if not resp.tool_calls:
            return resp  # model decided to answer in text — we're done.

        # Persist the assistant turn verbatim so the next call_id can see it.
        _assistant_msg: dict = {"role": "assistant", "content": resp.content or None}
        _assistant_msg["tool_calls"] = [
            {
                "id": tc["id"],
                "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
                },
            }
            for tc in resp.tool_calls
        ]
        if iteration == 0:
            # Seed the conversation for round 2 with the original history.
            for m in messages:
                conversation.append({"role": m["role"], "content": m["content"]})
        conversation.append(_assistant_msg)

        # Dispatch every call; append results (one ``role=tool`` per call_id).
        for tc in resp.tool_calls:
            call_id = tc.get("id") or f"auto-{iteration}"
            name = tc["name"]
            args = tc["arguments"] if isinstance(tc["arguments"], dict) else {}

            if emit is not None:
                await _safe_emit(
                    emit, TOOL_CALL_EVENT,
                    {"call_id": call_id, "name": name, "arguments": args},
                )

            try:
                result: ToolResult = await dispatch(name, args, ctx, call_id=call_id)
            except ToolExecutionError as exc:
                if emit is not None:
                    await _safe_emit(emit, TOOL_ERROR_EVENT, exc.as_payload())
                if exc.fatal:
                    # The model asked for something we can't execute. Fall
                    # through to a final text-only turn so the model can at
                    # least produce a reply.
                    return await _call_final_text_turn(
                        system_prompt=system_prompt,
                        messages=messages,
                        provider=provider,
                        timeout=timeout,
                    )
                # Non-fatal: feed the error back to the model as a tool result
                # so it can decide to apologise or retry.
                conversation.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": name,
                    "content": json.dumps({"error": exc.code, "message": exc.message}),
                })
                continue

            if emit is not None:
                await _safe_emit(
                    emit, TOOL_RESULT_EVENT,
                    {"call_id": call_id, "name": name, "result": result.result},
                )
            conversation.append({
                "role": "tool",
                "tool_call_id": call_id,
                "name": name,
                "content": json.dumps(result.result, ensure_ascii=False),
            })

    # Hit iteration cap — force a text-only final turn so we always return
    # something coherent.
    logger.warning(
        "llm_tools: MAX_TOOL_ITERATIONS=%d reached, forcing text-only turn",
        MAX_TOOL_ITERATIONS,
    )
    return await _call_final_text_turn(
        system_prompt=system_prompt,
        messages=messages,
        provider=provider,
        timeout=timeout,
    )


async def _call_final_text_turn(
    *,
    system_prompt: str,
    messages: list[dict],
    provider: str,
    timeout: float,
):
    """Make one last LLM call with tools disabled — used when we bail out
    of the loop (fatal tool error or iteration cap)."""

    from app.services.llm import _call_local_llm, _call_openai

    if provider == "openai":
        return await _call_openai(system_prompt, messages, timeout, tools=None)
    return await _call_local_llm(system_prompt, messages, timeout, tools=None)


async def _safe_emit(emit: EmitFn, event_type: str, payload: dict) -> None:
    """Swallow exceptions from the emit callback so a broken WS doesn't crash
    the LLM pipeline."""

    try:
        await emit(event_type, payload)
    except Exception as exc:  # noqa: BLE001
        logger.warning("llm_tools.emit(%s) failed: %s", event_type, exc)
