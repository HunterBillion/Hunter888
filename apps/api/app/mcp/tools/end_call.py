"""MCP tool ``end_call`` — explicit hangup signal from the persona LLM.

Background (P2, 2026-05-03)
---------------------------
The original explicit-hangup path (``[END_CALL]`` string marker, see
:mod:`app.services.end_call_marker`) requires the model to remember to
emit a literal token at the very tail of a 6-7K-token system prompt.
Production observation: the model frequently improvises a farewell
without the marker, so the marker fires < 50% of the time it should.

A real OpenAI-style tool gives the model a 1-line ``tools=[...]`` spec
right next to the messages array — the structural prominence dramatically
raises the probability the model will pick it when it decides to hang up.
The handler itself is intentionally a *no-op*: its job is to be invoked
so the WS handler (``apps.api.app.ws.training``) can read the tool-call
out of ``LLMResponse.tool_calls`` and fire the same hangup branch the
string marker fires.

Fallback chain (in priority order):
  1. ``end_call`` tool invocation  → this path (P2).
  2. ``[END_CALL]`` substring marker → :mod:`end_call_marker` (kept).
  3. Weighted decision from substring farewell heuristics → PR #212.
"""

from __future__ import annotations

import logging

from app.mcp import ToolContext, tool
from app.mcp.schemas import object_schema, string_property

logger = logging.getLogger(__name__)


@tool(
    name="end_call",
    description=(
        "Завершить телефонный разговор от лица клиента. Вызывай этот "
        "инструмент, когда ты решил повесить трубку: тебе грубят, тратят "
        "твоё время, ты уже принял решение и прощаешься, или ты сказал, "
        "что больше не хочешь общаться. Не вызывай инструмент для угроз "
        "('или я положу трубку!') — только когда ты ДЕЙСТВИТЕЛЬНО "
        "заканчиваешь звонок прямо сейчас."
    ),
    parameters_schema=object_schema(
        required=["reason"],
        properties={
            "reason": string_property(
                "Краткая причина в одном-двух словах: insulted, off_topic, "
                "no_value, polite_close, escalation, other.",
                max_length=64,
            ),
            "phrase": string_property(
                "Финальная фраза, которую персонаж говорит вслух перед тем "
                "как повесить трубку (1-2 предложения по-русски).",
                max_length=200,
            ),
        },
    ),
    scope="session",
    auth_required=True,
    rate_limit_per_min=5,
    max_result_size_kb=2,
    tags=("hangup", "session-control"),
)
async def end_call(args: dict, ctx: ToolContext) -> dict:
    """Handler is intentionally a no-op echo.

    The WS pipeline in ``app.ws.training`` inspects ``LLMResponse.tool_calls``
    *before* the dispatch round-trip — it doesn't need a meaningful return
    value here. We still echo the args so the model can see its own intent
    reflected if (in some other code path) the dispatch loop runs and the
    model asks for a follow-up text turn.
    """

    reason = (args.get("reason") or "").strip() or "other"
    phrase = (args.get("phrase") or "").strip()
    logger.info(
        "end_call tool invoked | session=%s | reason=%s | phrase=%r",
        ctx.session_id, reason, phrase[:80],
    )
    return {"ok": True, "reason": reason, "phrase": phrase}
