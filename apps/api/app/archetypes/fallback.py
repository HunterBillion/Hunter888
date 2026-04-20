"""Safety-net profiles for unknown / malformed archetype codes.

We never want a production request to crash because a legacy DB row carries
an archetype code that was deprecated, misspelled, or belongs to a feature
branch. ``neutral_profile(code)`` returns a valid ``ArchetypeProfile`` with
centre-of-range OCEAN and empty narrative data.

All lookups here are **last resort** — Registry only calls into this module
when both the catalog and the legacy loader returned nothing. Each fallback
hit is counted (Registry.fallback_hits) so ops can monitor the migration.
"""

from __future__ import annotations

from app.archetypes.profile import (
    ArchetypeGroup,
    ArchetypeProfile,
    OceanRange,
    PadAnchor,
)


_NEUTRAL_OCEAN = OceanRange(0.5, 0.5, 0.5, 0.5, 0.5)
_NEUTRAL_PAD = PadAnchor(0.0, 0.0, 0.0)


def neutral_profile(code: str) -> ArchetypeProfile:
    """Build a safe, uninteresting profile keyed by ``code``.

    The group is ``SPECIAL`` (catch-all). Tier is ``intermediate`` so the
    scenario selector doesn't accidentally serve this to a level-1 user.
    Prompts are empty — the LLM falls back to the scenario-level system prompt
    and the client behaves like a generic Russian borrower.
    """

    return ArchetypeProfile(
        code=code,
        group=ArchetypeGroup.SPECIAL,
        title_ru=code.replace("_", " ").title(),
        ocean_base=_NEUTRAL_OCEAN,
        pad_anchor=_NEUTRAL_PAD,
        fears=[],
        soft_spots=[],
        breaking_points=[],
        default_goals=[],
        default_objections=[],
        prompt_v1_path=None,
        prompt_v2_path=None,
        emotion_profile_slug=None,
        difficulty_tier="intermediate",
        unlock_condition=None,
        profession_affinities=[],
        extras={"fallback": True},
    )
