"""ToolRegistry — process-wide registry of MCP tools.

Registration happens at module-import time (via ``@tool`` decorator); lookup
happens at request-build time and at tool-dispatch time.

``openai_tools_spec(scope)`` produces the ``tools=[{"type":"function", ...}]``
list that OpenAI-compatible APIs (including ``api.navy``) expect.
"""

from __future__ import annotations

import logging
import threading
from typing import Iterable

from app.mcp.tool import Tool, ToolScope

logger = logging.getLogger(__name__)

_LOCK = threading.RLock()
_TOOLS: dict[str, Tool] = {}


class ToolNotFoundError(KeyError):
    """Raised by ``ToolRegistry.get(name)`` when the tool is not registered."""


class ToolRegistry:
    """Singleton registry. All methods are classmethods."""

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    @classmethod
    def register(cls, tool: Tool) -> None:
        """Add ``tool`` to the registry. Overwriting an existing name is
        allowed (useful for tests) but logged at WARNING level."""

        with _LOCK:
            if tool.name in _TOOLS and _TOOLS[tool.name] is not tool:
                logger.warning(
                    "ToolRegistry: overwriting existing tool %r", tool.name,
                )
            _TOOLS[tool.name] = tool

    @classmethod
    def unregister(cls, name: str) -> None:
        """Remove a tool. Used in tests between fixtures."""

        with _LOCK:
            _TOOLS.pop(name, None)

    @classmethod
    def clear(cls) -> None:
        """Wipe the registry entirely. Used in tests."""

        with _LOCK:
            _TOOLS.clear()

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    @classmethod
    def get(cls, name: str) -> Tool:
        """Return the tool or raise ``ToolNotFoundError``."""

        with _LOCK:
            try:
                return _TOOLS[name]
            except KeyError as exc:
                raise ToolNotFoundError(f"tool {name!r} not registered") from exc

    @classmethod
    def has(cls, name: str) -> bool:
        with _LOCK:
            return name in _TOOLS

    @classmethod
    def all(cls) -> list[Tool]:
        with _LOCK:
            return list(_TOOLS.values())

    @classmethod
    def iter_scope(cls, scope: ToolScope) -> Iterable[Tool]:
        """Yield tools matching ``scope``.

        ``scope="global"`` selects globals only; ``scope="session"`` includes
        both session-scoped and global tools (a session can call everything
        a global context could). ``scope="user"`` is the middle tier.
        """

        hierarchy = {
            "global": {"global"},
            "user": {"user", "global"},
            "session": {"session", "user", "global"},
        }
        allowed = hierarchy.get(scope, {"session"})
        with _LOCK:
            for tool in _TOOLS.values():
                if tool.scope in allowed:
                    yield tool

    # ------------------------------------------------------------------
    # Output format for LLM providers
    # ------------------------------------------------------------------

    @classmethod
    def openai_tools_spec(cls, *, scope: ToolScope = "session") -> list[dict]:
        """Return the ``tools`` array expected by OpenAI-compatible APIs.

        Each entry is ``{"type": "function", "function": {name, description,
        parameters}}``. Unlike the raw ``Tool`` dataclass, we strip
        operational fields (timeout, rate limit, etc.) — the model doesn't
        need them, and exposing rate limits might let it game the system.
        """

        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters_schema,
                },
            }
            for tool in cls.iter_scope(scope)
        ]
