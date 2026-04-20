"""Legacy loader — synthesizes an ArchetypeProfile from current data sources.

Data sources (read-only, not modified):
  * ``app.services.client_generator.ARCHETYPE_OCEAN``
  * ``app.services.client_generator.ARCHETYPE_PAD``
  * ``app.services.client_generator.ARCHETYPE_FEARS``
  * ``app.services.client_generator.ARCHETYPE_SOFT_SPOTS``
  * ``app.services.client_generator.ARCHETYPE_BREAKING_POINTS``
  * ``apps/api/prompts/characters/<slug>_v{1,2}.md``
  * ``app.models.roleplay.ArchetypeCode`` (enum — source of truth for group
    classification, inferred by membership)

Why a loader instead of hard-coded defaults? The legacy dicts are NOT complete:
``ARCHETYPE_PAD`` only lists ~25 of 100 codes, ``ARCHETYPE_FEARS`` is ~20.
This loader gracefully degrades — fills what's available, leaves the rest empty,
and the resulting ArchetypeProfile still passes all Registry invariants.

This module is **only** imported lazily from ``registry.py`` — it pulls in
``services.client_generator`` which in turn imports SQLAlchemy mappings.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.archetypes.profile import (
    ArchetypeGroup,
    ArchetypeProfile,
    OceanRange,
    PadAnchor,
)

logger = logging.getLogger(__name__)


# Maps (group, list_of_codes) — matches comments in models.ArchetypeCode.
# Keeping it hand-maintained is fine; the enum defines source of truth, and this
# dict just adds group metadata that isn't encoded there.
_GROUP_MEMBERS: dict[ArchetypeGroup, frozenset[str]] = {
    ArchetypeGroup.RESISTANCE: frozenset({
        "skeptic", "blamer", "sarcastic", "aggressive", "hostile",
        "stubborn", "conspiracy", "righteous", "litigious", "scorched_earth",
    }),
    ArchetypeGroup.EMOTIONAL: frozenset({
        "grateful", "anxious", "ashamed", "overwhelmed", "desperate",
        "crying", "guilty", "mood_swinger", "frozen", "hysteric",
    }),
    ArchetypeGroup.CONTROL: frozenset({
        "pragmatic", "shopper", "negotiator", "know_it_all", "manipulator",
        "lawyer_client", "auditor", "strategist", "power_player", "puppet_master",
    }),
    ArchetypeGroup.AVOIDANCE: frozenset({
        "passive", "delegator", "avoidant", "paranoid", "procrastinator",
        "ghosting", "deflector", "agreeable_ghost", "fortress", "smoke_screen",
    }),
    ArchetypeGroup.SPECIAL: frozenset({
        "referred", "returner", "rushed", "couple", "elderly",
        "young_debtor", "foreign_speaker", "intermediary", "repeat_caller", "celebrity",
    }),
    ArchetypeGroup.COGNITIVE: frozenset({
        "overthinker", "concrete", "storyteller", "misinformed", "selective_listener",
        "black_white", "memory_issues", "technical", "magical_thinker", "lawyer_level_2",
    }),
    ArchetypeGroup.SOCIAL: frozenset({
        "family_man", "influenced", "reputation_guard", "community_leader",
        "breadwinner", "divorced", "guarantor", "widow", "caregiver",
        "multi_debtor_family",
    }),
    ArchetypeGroup.TEMPORAL: frozenset({
        "just_fired", "collector_call", "court_notice", "salary_arrest",
        "pre_court", "post_refusal", "inheritance_trap", "business_collapse",
        "medical_crisis", "criminal_risk",
    }),
    ArchetypeGroup.PROFESSIONAL: frozenset({
        "teacher", "doctor", "military", "accountant", "salesperson",
        "it_specialist", "government", "journalist", "psychologist",
        "competitor_employee",
    }),
    ArchetypeGroup.COMPOUND: frozenset({
        "aggressive_desperate", "manipulator_crying", "know_it_all_paranoid",
        "passive_aggressive", "couple_disagreeing", "elderly_paranoid",
        "hysteric_litigious", "puppet_master_lawyer", "shifting", "ultimate",
    }),
}


# Difficulty-tier heuristic: beginners see emotional/avoidance groups;
# advanced hunters get compound/control.
_TIER_BY_GROUP: dict[ArchetypeGroup, str] = {
    ArchetypeGroup.EMOTIONAL: "beginner",
    ArchetypeGroup.AVOIDANCE: "beginner",
    ArchetypeGroup.SPECIAL: "beginner",
    ArchetypeGroup.SOCIAL: "intermediate",
    ArchetypeGroup.RESISTANCE: "intermediate",
    ArchetypeGroup.COGNITIVE: "intermediate",
    ArchetypeGroup.PROFESSIONAL: "intermediate",
    ArchetypeGroup.TEMPORAL: "intermediate",
    ArchetypeGroup.CONTROL: "advanced",
    ArchetypeGroup.COMPOUND: "advanced",
}


# Default OCEAN when the legacy dict lacks an entry — centre of each axis.
_NEUTRAL_OCEAN = OceanRange(0.5, 0.5, 0.5, 0.5, 0.5)
# Neutral PAD — used when ARCHETYPE_PAD doesn't cover the code.
_NEUTRAL_PAD = PadAnchor(0.0, 0.0, 0.0)


def _infer_group(code: str) -> ArchetypeGroup:
    for group, members in _GROUP_MEMBERS.items():
        if code in members:
            return group
    logger.warning(
        "archetype loader: %r not in any group — defaulting to SPECIAL", code,
    )
    return ArchetypeGroup.SPECIAL


def _legacy_prompt_path(code: str, version: int) -> Path | None:
    """Return the on-disk path to ``prompts/characters/<code>_v{version}.md`` if
    it exists. Repo layout: api package root is ``apps/api/app/`` so prompts
    live four parents up."""

    prompts_dir = Path(__file__).resolve().parents[2] / "prompts" / "characters"
    candidate = prompts_dir / f"{code}_v{version}.md"
    return candidate if candidate.is_file() else None


def build_profile_from_legacy(code: str) -> ArchetypeProfile | None:
    """Build an ArchetypeProfile by reading legacy data sources.

    Returns ``None`` if the code is not even recognized by the enum — Registry
    will then fall through to ``fallback.neutral_profile``.
    """

    # Validate the code is in the enum first — otherwise we don't even try.
    try:
        from app.models.roleplay import ArchetypeCode

        ArchetypeCode(code)
    except ValueError:
        logger.debug("archetype loader: %r not in ArchetypeCode enum", code)
        return None

    # Lazy import — keeps the archetypes package light.
    try:
        from app.services.client_generator import (
            ARCHETYPE_OCEAN,
            ARCHETYPE_PAD,
            ARCHETYPE_FEARS,
            ARCHETYPE_SOFT_SPOTS,
            ARCHETYPE_BREAKING_POINTS,
        )
    except Exception as exc:  # pragma: no cover — circular import guard
        logger.warning("archetype loader: legacy dicts import failed: %s", exc)
        return None

    group = _infer_group(code)

    # OCEAN — every code in ARCHETYPE_OCEAN (99 of 100 in current code);
    # neutral fallback when missing.
    ocean_raw = ARCHETYPE_OCEAN.get(code, {})
    ocean = (
        OceanRange(
            openness=float(ocean_raw.get("O", 0.5)),
            conscientiousness=float(ocean_raw.get("C", 0.5)),
            extraversion=float(ocean_raw.get("E", 0.5)),
            agreeableness=float(ocean_raw.get("A", 0.5)),
            neuroticism=float(ocean_raw.get("N", 0.5)),
        )
        if ocean_raw
        else _NEUTRAL_OCEAN
    )

    # PAD — only ~25 codes populated; rest get neutral.
    pad_raw = ARCHETYPE_PAD.get(code, {})
    pad = (
        PadAnchor(
            pleasure=float(pad_raw.get("P", 0.0)),
            arousal=float(pad_raw.get("A", 0.0)),
            dominance=float(pad_raw.get("D", 0.0)),
        )
        if pad_raw
        else _NEUTRAL_PAD
    )

    return ArchetypeProfile(
        code=code,
        group=group,
        title_ru=_DEFAULT_TITLES.get(code, code.replace("_", " ").title()),
        ocean_base=ocean,
        pad_anchor=pad,
        fears=list(ARCHETYPE_FEARS.get(code, [])),
        soft_spots=list(ARCHETYPE_SOFT_SPOTS.get(code, [])),
        breaking_points=list(ARCHETYPE_BREAKING_POINTS.get(code, [])),
        default_goals=[],  # legacy doesn't track — filled by catalog modules
        default_objections=[],
        prompt_v1_path=_legacy_prompt_path(code, 1),
        prompt_v2_path=_legacy_prompt_path(code, 2),
        emotion_profile_slug=code,  # legacy convention — one profile per code
        difficulty_tier=_TIER_BY_GROUP.get(group, "intermediate"),
        unlock_condition=None,
        profession_affinities=[],
        extras={},
    )


# Lightweight Russian titles — populated opportunistically, not authoritative.
# Catalog modules will override with curated values.
_DEFAULT_TITLES: dict[str, str] = {
    "skeptic": "Скептик",
    "aggressive": "Агрессор",
    "anxious": "Тревожный",
    "passive": "Пассивный",
    "manipulator": "Манипулятор",
    "hostile": "Враждебный",
    "desperate": "Отчаявшийся",
    "crying": "Плачущий",
    "grateful": "Благодарный",
    "pragmatic": "Прагматик",
    "know_it_all": "Всезнайка",
    "lawyer_client": "Клиент-юрист",
    "elderly": "Пожилой",
    "young_debtor": "Молодой должник",
    "celebrity": "VIP-клиент",
    "overthinker": "Переосмысливающий",
    "family_man": "Семьянин",
    "fortress": "Крепость",
}
