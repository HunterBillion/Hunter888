"""Concrete MCP tools registered on import.

Merely importing this package registers all tools with ``ToolRegistry``. The
app's startup (``app.main:lifespan``) imports it once so tools are available
from the first LLM turn.

Adding a new tool:
    1. Create ``app/mcp/tools/<name>.py`` with a single ``@tool`` decorated
       async function.
    2. Append the module to ``__all__`` below (alphabetical).
    3. Re-run the test suite.
"""

# Importing each module triggers ``@tool`` decorator → ToolRegistry.register.
# Ordering is stable so the openai_tools_spec list is deterministic.
from app.mcp.tools import (  # noqa: F401 — side-effect registration
    fetch_archetype_profile,
    generate_image,
    get_geolocation_context,
)

__all__ = [
    "fetch_archetype_profile",
    "generate_image",
    "get_geolocation_context",
]
