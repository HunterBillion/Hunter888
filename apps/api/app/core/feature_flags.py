"""
Feature flags for phased rollout (DOC_18).

16 flags controlling gradual feature activation.
All default OFF. Enable via env vars or runtime config.
Supports percentage-based rollout.
"""

from __future__ import annotations

import hashlib
import os
from uuid import UUID


# ─── Flag Definitions ────────────────────────────────────────────────────────

class FeatureFlags:
    """Runtime feature flag checks."""

    # Phase 1: Foundation
    FF_100_ARCHETYPES = "FF_100_ARCHETYPES"
    FF_CONSTRUCTOR_V2 = "FF_CONSTRUCTOR_V2"
    FF_CHECKPOINTS = "FF_CHECKPOINTS"

    # Phase 2: Training
    FF_60_SCENARIOS = "FF_60_SCENARIOS"
    FF_12_SCORING = "FF_12_SCORING"
    FF_10_SKILLS = "FF_10_SKILLS"
    FF_140_ACHIEVEMENTS = "FF_140_ACHIEVEMENTS"
    FF_EMOTION_V2 = "FF_EMOTION_V2"

    # Phase 3: Arena
    FF_PVP_MODES = "FF_PVP_MODES"
    FF_PVE_MODES = "FF_PVE_MODES"
    FF_KNOWLEDGE_V2 = "FF_KNOWLEDGE_V2"
    FF_8_TIERS = "FF_8_TIERS"
    FF_ARENA_POINTS = "FF_ARENA_POINTS"
    FF_SEASON_PASS = "FF_SEASON_PASS"

    # Phase 4: Polish
    FF_PROMPT_VERSIONING = "FF_PROMPT_VERSIONING"
    FF_FRONTEND_V2 = "FF_FRONTEND_V2"

    ALL_FLAGS = [
        FF_100_ARCHETYPES, FF_CONSTRUCTOR_V2, FF_CHECKPOINTS,
        FF_60_SCENARIOS, FF_12_SCORING, FF_10_SKILLS, FF_140_ACHIEVEMENTS, FF_EMOTION_V2,
        FF_PVP_MODES, FF_PVE_MODES, FF_KNOWLEDGE_V2, FF_8_TIERS, FF_ARENA_POINTS, FF_SEASON_PASS,
        FF_PROMPT_VERSIONING, FF_FRONTEND_V2,
    ]


def is_flag_enabled(flag: str) -> bool:
    """Check if a feature flag is globally enabled."""
    return os.environ.get(flag, "off").lower() in ("on", "true", "1", "yes")


def is_flag_enabled_for_user(flag: str, user_id: UUID) -> bool:
    """Check if flag is enabled for a specific user (percentage rollout)."""
    if not is_flag_enabled(flag):
        return False

    pct_key = f"{flag}_PCT"
    pct = int(os.environ.get(pct_key, "100"))
    if pct >= 100:
        return True
    if pct <= 0:
        return False

    # Deterministic hash for consistent user bucketing
    h = hashlib.md5(f"{flag}:{user_id}".encode()).hexdigest()
    bucket = int(h[:8], 16) % 100
    return bucket < pct


def get_enabled_flags() -> list[str]:
    """Get list of all globally enabled flags."""
    return [f for f in FeatureFlags.ALL_FLAGS if is_flag_enabled(f)]


def get_rollout_status() -> dict[str, dict]:
    """Get status of all flags for admin dashboard."""
    result = {}
    for flag in FeatureFlags.ALL_FLAGS:
        enabled = is_flag_enabled(flag)
        pct = int(os.environ.get(f"{flag}_PCT", "100")) if enabled else 0
        result[flag] = {"enabled": enabled, "percentage": pct}
    return result
