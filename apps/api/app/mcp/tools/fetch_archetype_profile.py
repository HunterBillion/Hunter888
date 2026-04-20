"""MCP tool ``fetch_archetype_profile`` — give the LLM a canonical snapshot.

Intended audience: Game Director / coach LLM, not the client persona itself.
The client persona should stay "in character" and not know it's an archetype;
this tool exists so that auxiliary turns (e.g. between-call narration, post-call
coaching) can reason about a specific archetype structurally.

Returns only the public-safe subset (``ArchetypeProfile.as_public_dict``) —
prompt paths and raw md text are not exposed.
"""

from __future__ import annotations

import logging

from app.archetypes import ArchetypeRegistry
from app.mcp import ToolContext, tool
from app.mcp.schemas import object_schema, string_property

logger = logging.getLogger(__name__)


@tool(
    name="fetch_archetype_profile",
    description=(
        "Вернуть канонический профиль архетипа клиента: OCEAN, PAD, fears, "
        "soft_spots, breaking_points. Предназначен для аналитических/коучинговых "
        "задач, НЕ для роли самого клиента."
    ),
    parameters_schema=object_schema(
        required=["code"],
        properties={
            "code": string_property(
                "Код архетипа из enum (например 'skeptic', 'aggressive', "
                "'elderly_paranoid'). Список — 100 значений ArchetypeCode.",
                max_length=64,
            ),
        },
    ),
    scope="global",  # safe to expose to any tool-caller
    auth_required=True,
    rate_limit_per_min=60,
    max_result_size_kb=8,
    tags=("archetype", "read-only"),
)
async def fetch_archetype_profile(args: dict, ctx: ToolContext) -> dict:
    """Handler: ``{"code": "skeptic"}`` → ``{"profile": {...}}``."""

    code = (args.get("code") or "").strip()
    if not code:
        # Non-fatal: let the model see an explicit error message in its
        # tool_result round-trip instead of crashing the call.
        return {"error": "missing_code", "message": "argument 'code' is required"}

    # Don't raise on unknown — Registry falls through to a neutral profile.
    # We still flag it so the LLM knows the value wasn't recognised exactly.
    profile = ArchetypeRegistry.get(code)
    is_neutral_fallback = bool(profile.extras.get("fallback"))

    return {
        "profile": profile.as_public_dict(),
        "is_neutral_fallback": is_neutral_fallback,
    }
