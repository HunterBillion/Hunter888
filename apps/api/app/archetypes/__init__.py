"""Archetype Registry — canonical source of truth for all 100 client archetypes.

Phase 1 foundation (2026-04-18):
- Before: archetype data scattered across 15+ locations (models.ArchetypeCode enum,
  client_generator.ARCHETYPE_OCEAN/PAD/FEARS, prompts/characters/*.md,
  ArchetypeEmotionProfile DB rows, Trap.archetype_codes filters, etc.)
- After: single ArchetypeProfile dataclass per code, accessed via ArchetypeRegistry.

The Registry does not replace existing data — it wraps and normalizes it. Callers
opt in gradually. Fallback to legacy dicts is automatic (see fallback.py) so any
archetype that is not in the catalog still works.

Import API:

    from app.archetypes import ArchetypeRegistry, ArchetypeProfile

    profile = ArchetypeRegistry.get("skeptic")
    ocean = profile.build_ocean(difficulty=7, profession="entrepreneur")
    pad = profile.build_pad()
    system_prompt = profile.render_system_prompt(version=2)
"""

from app.archetypes.profile import (
    ArchetypeProfile,
    ArchetypeGroup,
    OceanRange,
    OceanDelta,
)
from app.archetypes.registry import ArchetypeRegistry

__all__ = [
    "ArchetypeProfile",
    "ArchetypeGroup",
    "OceanRange",
    "OceanDelta",
    "ArchetypeRegistry",
]
