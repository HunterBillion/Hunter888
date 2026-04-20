"""Tool dataclass + ``@tool`` decorator.

A ``Tool`` wraps a single async handler and the metadata the LLM needs to decide
whether to call it — name, human-readable description, JSON Schema for its
parameters, and a few safety guards (timeout, rate limit, max result size,
required auth scope).

Every tool registered via ``@tool`` is placed into ``ToolRegistry`` at import
time — the Registry is the source of truth at runtime. Manual instantiation
(``Tool(...)``) is supported but discouraged outside tests.
"""

from __future__ import annotations

import functools
import inspect
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal

ToolScope = Literal["session", "user", "global"]

# Signature every tool handler must implement.
ToolHandler = Callable[[dict, "ToolContext"], Awaitable[dict]]


@dataclass(frozen=True)
class ToolContext:
    """Runtime context passed to every tool handler.

    Tools should read:
      - ``session_id``: bind the call to a training session (for audit / Redis
        rate-limit keying).
      - ``user_id``: who initiated the call chain. Nullable for background jobs.
      - ``manager_ip``: present during WS-authenticated sessions; used by
        ``get_geolocation_context``.
      - ``request_id``: correlation id, same value is emitted in the
        ``assistant.tool_call`` WS event.

    ``extras`` is free-form — tools can stash data in it during registration
    if they need per-instance state.
    """

    session_id: str | None = None
    user_id: str | None = None
    manager_ip: str | None = None
    request_id: str | None = None
    extras: dict[str, Any] = None  # type: ignore[assignment]

    def with_overrides(self, **overrides: Any) -> "ToolContext":
        """Return a copy with selected attributes replaced — handy for tests
        where we want to build a base context once and tweak fields."""

        data = {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "manager_ip": self.manager_ip,
            "request_id": self.request_id,
            "extras": dict(self.extras) if self.extras else None,
        }
        data.update(overrides)
        return ToolContext(**data)


@dataclass(frozen=True)
class Tool:
    """A registered MCP tool — the shape LLM providers expect.

    Fields are intentionally OpenAI-compatible so that converting to the
    ``{"type": "function", "function": {...}}`` format (see
    ``registry.openai_tools_spec``) is a direct mapping.
    """

    name: str
    description: str
    parameters_schema: dict  # JSON Schema for arguments
    handler: ToolHandler
    timeout_s: int = 30
    scope: ToolScope = "session"
    rate_limit_per_min: int = 30
    max_result_size_kb: int = 256
    # Auth gate: tools marked ``auth_required=True`` must run in a context
    # that has a non-None ``user_id``; system-level tools can run without.
    auth_required: bool = True
    # Operational hints — surfaced in admin dashboards, not enforced.
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:  # type: ignore[override]
        if not self.name or not self.name.replace("_", "").isalnum():
            raise ValueError(f"Tool name must be snake_case alphanumeric: {self.name!r}")
        if not inspect.iscoroutinefunction(self.handler):
            raise TypeError(f"Tool handler must be async: {self.handler!r}")


def tool(
    *,
    name: str,
    description: str,
    parameters_schema: dict,
    timeout_s: int = 30,
    scope: ToolScope = "session",
    rate_limit_per_min: int = 30,
    max_result_size_kb: int = 256,
    auth_required: bool = True,
    tags: tuple[str, ...] = (),
) -> Callable[[ToolHandler], ToolHandler]:
    """Decorator that registers an async function with ``ToolRegistry``.

    Usage::

        @tool(name="echo", description="Echo text", parameters_schema={...})
        async def echo(args: dict, ctx: ToolContext) -> dict:
            return {"echoed": args["text"]}

    The decorated function is returned unchanged (the Tool wrapper is stored
    in the registry), so the original callable can still be imported and
    unit-tested directly.
    """

    def decorator(handler: ToolHandler) -> ToolHandler:
        # Late import to avoid a circular ``mcp.registry -> mcp.tool`` cycle:
        # registry imports ``Tool`` from this module.
        from app.mcp.registry import ToolRegistry

        t = Tool(
            name=name,
            description=description,
            parameters_schema=parameters_schema,
            handler=handler,
            timeout_s=timeout_s,
            scope=scope,
            rate_limit_per_min=rate_limit_per_min,
            max_result_size_kb=max_result_size_kb,
            auth_required=auth_required,
            tags=tags,
        )
        ToolRegistry.register(t)

        # Return the original handler so tests can still call ``await echo(args, ctx)``.
        return functools.wraps(handler)(handler)

    return decorator
