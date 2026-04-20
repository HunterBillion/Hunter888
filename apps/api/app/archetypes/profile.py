"""Canonical ArchetypeProfile — the shape of one archetype.

All 100 codes from ``app.models.roleplay.ArchetypeCode`` should eventually have
a matching ``ArchetypeProfile`` entry in ``catalog/<code>.py``.

This dataclass intentionally mirrors the *union* of data currently spread across:
- ``services/client_generator.ARCHETYPE_OCEAN`` (base OCEAN anchors, ±0.15 noise)
- ``services/client_generator.ARCHETYPE_PAD`` (PAD baseline, ±0.1 noise)
- ``services/client_generator.ARCHETYPE_FEARS``
- ``services/client_generator.ARCHETYPE_SOFT_SPOTS``
- ``services/client_generator.ARCHETYPE_BREAKING_POINTS``
- ``prompts/characters/<slug>_v{1,2}.md`` (narrative prompt)
- ``models.ArchetypeEmotionProfile`` (emotion transition matrix — stays in DB,
  referenced by ``emotion_profile_slug``)

The existing modules continue to work; this dataclass just gives a single
import surface.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ────────────────────────────────────────────────────────────────────
# Supporting types
# ────────────────────────────────────────────────────────────────────


class ArchetypeGroup(str, enum.Enum):
    """10 canonical groups — matches the comments in models.ArchetypeCode."""

    RESISTANCE = "resistance"
    EMOTIONAL = "emotional"
    CONTROL = "control"
    AVOIDANCE = "avoidance"
    SPECIAL = "special"
    COGNITIVE = "cognitive"
    SOCIAL = "social"
    TEMPORAL = "temporal"
    PROFESSIONAL = "professional"
    COMPOUND = "compound"


@dataclass(frozen=True)
class OceanRange:
    """Base OCEAN anchors (0.0–1.0). Noise ±0.15 applied at build_ocean time.

    Semantics match ``client_generator.ARCHETYPE_OCEAN`` — a single scalar per
    trait, not a min/max range. Kept as a dataclass instead of dict[str, float]
    so that linters catch missing traits early.
    """

    openness: float
    conscientiousness: float
    extraversion: float
    agreeableness: float
    neuroticism: float

    def as_dict(self) -> dict[str, float]:
        """OCEAN dict in ``{"O": ..., "C": ..., "E": ..., "A": ..., "N": ...}``
        single-letter format — the format every existing consumer uses."""

        return {
            "O": self.openness,
            "C": self.conscientiousness,
            "E": self.extraversion,
            "A": self.agreeableness,
            "N": self.neuroticism,
        }


@dataclass(frozen=True)
class OceanDelta:
    """Additive OCEAN shift used for profession modifiers and difficulty ramp.

    Same single-letter keys as OceanRange; unset traits default to 0.0.
    """

    O: float = 0.0
    C: float = 0.0
    E: float = 0.0
    A: float = 0.0
    N: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return {"O": self.O, "C": self.C, "E": self.E, "A": self.A, "N": self.N}


@dataclass(frozen=True)
class PadAnchor:
    """PAD baseline triple (-1.0 … +1.0). Noise ±0.1 applied at build_pad time.

    Matches ``client_generator.ARCHETYPE_PAD`` keys {"P","A","D"}.
    """

    pleasure: float
    arousal: float
    dominance: float

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.pleasure, self.arousal, self.dominance)

    def as_dict(self) -> dict[str, float]:
        return {"P": self.pleasure, "A": self.arousal, "D": self.dominance}


# ────────────────────────────────────────────────────────────────────
# Main profile dataclass
# ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ArchetypeProfile:
    """Canonical description of a single archetype.

    All fields are optional **except** ``code`` and ``group`` — the loader
    can synthesize safe defaults for anything missing in legacy data so that
    existing code keeps working while new features depend on the Registry.
    """

    # Identity ────────────────────────────────────────────────────
    code: str
    """Stable slug matching ``models.ArchetypeCode`` value, e.g. ``"skeptic"``."""

    group: ArchetypeGroup
    """One of the 10 canonical groups."""

    title_ru: str = ""
    """Short Russian display name, e.g. ``"Скептик"``."""

    # Psychology ──────────────────────────────────────────────────
    ocean_base: OceanRange = field(
        default_factory=lambda: OceanRange(0.5, 0.5, 0.5, 0.5, 0.5)
    )
    """Base OCEAN anchors (0.0–1.0)."""

    pad_anchor: PadAnchor = field(
        default_factory=lambda: PadAnchor(0.0, 0.0, 0.0)
    )
    """PAD baseline. For archetypes missing in legacy data we fall back
    to neutral zeros."""

    # Narrative ───────────────────────────────────────────────────
    fears: list[str] = field(default_factory=list)
    """Client's fears — shown to LLM in the `human_factors` injection."""

    soft_spots: list[str] = field(default_factory=list)
    """Emotional weak points — what breaks through the archetype's default
    defensive posture."""

    breaking_points: list[str] = field(default_factory=list)
    """Triggers that escalate the client emotionally (``rollback_severity +2``
    in the emotion graph)."""

    default_goals: list[str] = field(default_factory=list)
    """What this client *wants* to achieve in the call (used by GameDirector)."""

    default_objections: list[str] = field(default_factory=list)
    """Common objection templates — surfaced to Coach/WhisperPanel."""

    # External resources ─────────────────────────────────────────
    prompt_v1_path: Path | None = None
    """Path to the old-style (v1) character prompt md file."""

    prompt_v2_path: Path | None = None
    """Path to the current (v2) character prompt md file."""

    emotion_profile_slug: str | None = None
    """Key into ``models.ArchetypeEmotionProfile`` table — we do **not** duplicate
    the emotion transition matrix here. Usually equals ``code`` but some archetypes
    share a profile (e.g. Group 10 compounds may delegate to their primary)."""

    # Taxonomy & gating ──────────────────────────────────────────
    difficulty_tier: str = "intermediate"
    """One of ``"beginner" | "intermediate" | "advanced"``. Used by
    ``scenario_engine.select_scenario`` to filter archetypes by manager level."""

    unlock_condition: str | None = None
    """Optional storyline-gate code; ``None`` means always available."""

    profession_affinities: list[str] = field(default_factory=list)
    """Professions that "feel right" for this archetype — Gaussian boost on
    client-generation weighting. Optional."""

    # Extension point ────────────────────────────────────────────
    extras: dict[str, Any] = field(default_factory=dict)
    """Free-form overflow for archetype-specific knobs (e.g. maximum_state,
    fake_transitions toggle) that we don't want to hard-code as columns yet."""

    # ────────────────────────────────────────────────────────────
    # Builders — what the runtime actually calls
    # ────────────────────────────────────────────────────────────

    def build_ocean(
        self,
        *,
        difficulty: int = 5,
        profession: str | None = None,
        seed: int | None = None,
    ) -> dict[str, float]:
        """Return the OCEAN dict for a client generated with this archetype.

        Formula (Phase 3.3, 2026-04-19):
            final[dim] = ocean_base[dim]
                       + profession_modifier[dim]
                       + difficulty_shift[dim]
                       + noise ~ U(-0.15, +0.15)
            clamped to [0.0, 1.0].

        The ``difficulty_shift`` comes from
        ``adaptive_difficulty.DIFFICULTY_PARAMS[difficulty].ocean_shift``.
        It monotonically hardens the client as level rises — at L1 we
        boost Agreeableness and lower Neuroticism (easy to soften), at
        L10 we invert both. Callers who want the pre-Phase-3 behaviour
        can pass ``difficulty=5`` (neutral shift).
        """

        import random as _random

        # We keep our own deterministic-ish RNG so tests can pass seed=...
        rng = _random.Random(seed) if seed is not None else _random

        base = self.ocean_base.as_dict()
        prof_mod: dict[str, float] = {}
        if profession:
            # Late-import to keep the archetypes package free of service-layer
            # dependencies at import time.
            try:
                from app.services.client_generator import PROFESSION_OCEAN_MODIFIERS

                prof_mod = PROFESSION_OCEAN_MODIFIERS.get(profession, {}) or {}
            except Exception:  # pragma: no cover — legacy import path
                prof_mod = {}

        diff_shift: dict[str, float] = {}
        try:
            from app.services.adaptive_difficulty import resolve_params

            diff_shift = resolve_params(difficulty).ocean_shift.as_dict()
        except Exception:  # pragma: no cover — defensive
            diff_shift = {}

        out: dict[str, float] = {}
        for key in ("O", "C", "E", "A", "N"):
            value = (
                base[key]
                + prof_mod.get(key, 0.0)
                + diff_shift.get(key, 0.0)
                + rng.uniform(-0.15, 0.15)
            )
            out[key] = max(0.0, min(1.0, value))
        return out

    def build_pad(
        self,
        *,
        emotion_seed: str | None = None,  # reserved for Phase 3 adaptive shaping
        seed: int | None = None,
    ) -> dict[str, float]:
        """Return the same PAD dict the legacy client_generator would build
        (``{"P", "A", "D"}`` with ±0.1 noise)."""

        import random as _random

        rng = _random.Random(seed) if seed is not None else _random
        anchor = self.pad_anchor.as_dict()
        return {
            key: max(-1.0, min(1.0, anchor[key] + rng.uniform(-0.1, 0.1)))
            for key in ("P", "A", "D")
        }

    def render_system_prompt(self, *, version: int = 2) -> str:
        """Read the md prompt for this archetype and return its contents.

        Returns an empty string when the file doesn't exist — callers that
        *require* a prompt should fall back to a legacy path.
        """

        path = self.prompt_v2_path if version == 2 else self.prompt_v1_path
        if path is None:
            return ""
        try:
            return _read_prompt_cached(str(path))
        except OSError:
            return ""

    # Public serialization — for /api/archetypes and fetch_archetype_profile tool
    def as_public_dict(self) -> dict[str, Any]:
        """Serializable subset safe to expose via REST/MCP tool.

        Excludes absolute filesystem paths and the raw prompt text — those
        should be fetched separately when needed.
        """

        return {
            "code": self.code,
            "group": self.group.value,
            "title_ru": self.title_ru,
            "ocean_base": self.ocean_base.as_dict(),
            "pad_anchor": self.pad_anchor.as_dict(),
            "fears": list(self.fears),
            "soft_spots": list(self.soft_spots),
            "breaking_points": list(self.breaking_points),
            "default_goals": list(self.default_goals),
            "default_objections": list(self.default_objections),
            "difficulty_tier": self.difficulty_tier,
            "profession_affinities": list(self.profession_affinities),
            "emotion_profile_slug": self.emotion_profile_slug,
        }


# ────────────────────────────────────────────────────────────────────
# Internal helpers
# ────────────────────────────────────────────────────────────────────


from functools import lru_cache


@lru_cache(maxsize=256)
def _read_prompt_cached(path_str: str) -> str:
    """LRU-cached md read. Separate function so lru_cache key can be a str."""

    return Path(path_str).read_text(encoding="utf-8")
