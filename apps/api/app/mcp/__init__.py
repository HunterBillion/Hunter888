"""MCP (Model Context Protocol) tooling layer for Hunter888.

Phase 1 (2026-04-18) introduces the contract — no concrete tools yet. Phase 2
will register ``generate_image``, ``get_geolocation_context``, and
``fetch_archetype_profile``.

High-level flow:

    # 1. Ops code registers a tool at import time:
    from app.mcp import tool, ToolContext

    @tool(name="echo", description="Echo a string back", parameters_schema={...})
    async def echo(args: dict, ctx: ToolContext) -> dict:
        return {"echoed": args["text"]}

    # 2. LLM request builder passes the OpenAI tools spec when MCP_ENABLED:
    from app.mcp import ToolRegistry
    tools = ToolRegistry.openai_tools_spec(scope="session")

    # 3. When the model returns tool_calls, the request pipeline dispatches:
    from app.mcp import dispatch
    for call in message.tool_calls:
        result = await dispatch(call.function.name, call.arguments, ctx)
"""

from app.mcp.tool import Tool, ToolContext, tool
from app.mcp.registry import ToolRegistry, ToolNotFoundError
from app.mcp.executor import dispatch, ToolExecutionError, ToolResult
from app.mcp.ws_events import (
    TOOL_CALL_EVENT,
    TOOL_RESULT_EVENT,
    TOOL_ERROR_EVENT,
)

__all__ = [
    "Tool",
    "ToolContext",
    "tool",
    "ToolRegistry",
    "ToolNotFoundError",
    "dispatch",
    "ToolExecutionError",
    "ToolResult",
    "TOOL_CALL_EVENT",
    "TOOL_RESULT_EVENT",
    "TOOL_ERROR_EVENT",
]
