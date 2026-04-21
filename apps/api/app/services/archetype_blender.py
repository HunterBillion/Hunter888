"""
Hybrid archetype blending algorithms (DOC_01_FINAL Section 16).

Provides OCEAN, PAD, MoodBuffer and FakeTransition blending for compound archetypes.
Used by: client_generator, game_director, training session init.
"""

from __future__ import annotations

import random
from typing import Optional

from app.services.client_generator import ARCHETYPE_OCEAN
from app.models.emotion import ARCHETYPE_MOOD_DEFAULTS


# ─── OCEAN Blending ──────────────────────────────────────────────────────────

def blend_ocean(
    archetype_a: str,
    archetype_b: str,
    weight_a: float = 0.5,
    weight_b: float = 0.5,
    conflict_boost: float = 0.15,
) -> dict[str, float]:
    """
    Blend OCEAN profiles of two archetypes.

    Principle: not just average — CONFLICT average.
    When two parameters diverge strongly — increase N (neuroticism).
    Real people with internal conflict are more unstable.
    """
    ocean_a = ARCHETYPE_OCEAN.get(archetype_a, ARCHETYPE_OCEAN["skeptic"])
    ocean_b = ARCHETYPE_OCEAN.get(archetype_b, ARCHETYPE_OCEAN["skeptic"])

    result: dict[str, float] = {}
    total_divergence = 0.0

    for trait in ["O", "C", "E", "A", "N"]:
        val_a = ocean_a[trait]
        val_b = ocean_b[trait]

        blended = val_a * weight_a + val_b * weight_b

        divergence = abs(val_a - val_b)
        total_divergence += divergence

        # For N — add conflict (internal contradiction → anxiety)
        if trait == "N":
            blended = min(1.0, blended + total_divergence * conflict_boost)

        result[trait] = round(max(0.0, min(1.0, blended)), 2)

    return result


# ─── PAD Blending ────────────────────────────────────────────────────────────

def blend_pad(
    pad_a: dict[str, float],
    pad_b: dict[str, float],
    weight_a: float = 0.5,
    weight_b: float = 0.5,
    session_id: Optional[str] = None,
) -> dict[str, float]:
    """PAD blending — linear interpolation + noise.

    S4-05: When session_id is provided, noise is deterministic (reproducible).
    """
    rng = random.Random(hash(session_id)) if session_id else random
    return {
        "P": round(pad_a.get("P", 0) * weight_a + pad_b.get("P", 0) * weight_b + rng.uniform(-0.1, 0.1), 2),
        "A": round(pad_a.get("A", 0) * weight_a + pad_b.get("A", 0) * weight_b + rng.uniform(-0.1, 0.1), 2),
        "D": round(pad_a.get("D", 0) * weight_a + pad_b.get("D", 0) * weight_b + rng.uniform(-0.1, 0.1), 2),
    }


# ─── MoodBuffer Blending ────────────────────────────────────────────────────

def blend_mood_buffer(
    archetype_a: str,
    archetype_b: str,
    weight_a: float = 0.5,
    weight_b: float = 0.5,
) -> dict:
    """
    MoodBuffer blending: take WORST values for the manager.

    Principle: hybrid must be HARDER than each component individually.
    """
    a = ARCHETYPE_MOOD_DEFAULTS.get(archetype_a, ARCHETYPE_MOOD_DEFAULTS["skeptic"])
    b = ARCHETYPE_MOOD_DEFAULTS.get(archetype_b, ARCHETYPE_MOOD_DEFAULTS["skeptic"])

    return {
        # Positive threshold — MAXIMUM (harder to warm up)
        "threshold_pos": max(a["threshold_pos"], b["threshold_pos"]) + 5,
        # Negative threshold — CLOSER TO ZERO (easier to roll back)
        "threshold_neg": max(a["threshold_neg"], b["threshold_neg"]) + 5,
        # Decay — MINIMUM (remembers longer)
        "decay": round(min(a["decay"], b["decay"]) * 0.9, 3),
        # EMA — weighted average
        "ema_alpha": round(a["ema_alpha"] * weight_a + b["ema_alpha"] * weight_b, 2),
    }


# ─── FakeTransition Blending ────────────────────────────────────────────────

EMOTION_ORDER = {
    "hostile": 0, "hangup": 0, "cold": 1, "guarded": 2, "testing": 3,
    "curious": 4, "callback": 5, "considering": 6, "negotiating": 7, "deal": 8,
}


def blend_fake_transitions(
    ft_a: Optional[dict],
    ft_b: Optional[dict],
) -> Optional[dict]:
    """
    If at least one component has FakeTransition — hybrid inherits it.
    If both have — use the more deceptive one (larger real-fake gap).
    """
    if ft_a and ft_b:
        gap_a = abs(
            EMOTION_ORDER.get(ft_a.get("real_state", "cold"), 0)
            - EMOTION_ORDER.get(ft_a.get("fake_state", "cold"), 0)
        )
        gap_b = abs(
            EMOTION_ORDER.get(ft_b.get("real_state", "cold"), 0)
            - EMOTION_ORDER.get(ft_b.get("fake_state", "cold"), 0)
        )
        return ft_a if gap_a >= gap_b else ft_b
    return ft_a or ft_b


# ─── Trap Blending ───────────────────────────────────────────────────────────

def blend_traps(a_traps: list[str], b_traps: list[str]) -> list[str]:
    """
    Traps: union of ALL unique traps + cross-trap placeholder.
    Cross-trap = trap exploiting CONFLICT between archetypes.
    """
    combined = list(set(a_traps + b_traps))
    # Cross-trap is generated dynamically by LLM at session start
    combined.append("cross_trap")
    return combined


# ─── Shifting Archetype Controller ───────────────────────────────────────────

class ShiftingArchetype:
    """
    Archetype #99: changes base archetype every 3-4 replies.

    Rules:
    1. Starts with one random archetype from pool
    2. Every 3-4 replies — shift
    3. Emotion state NOT reset — carried over
    4. Traps ACCUMULATE
    5. Pool: 5-8 archetypes from different groups (max 2 per group)
    """

    ARCHETYPE_GROUPS_MAP: dict[str, str] = {
        "skeptic": "resistance", "blamer": "resistance", "sarcastic": "resistance",
        "aggressive": "resistance", "hostile": "resistance",
        "anxious": "emotional", "desperate": "emotional", "crying": "emotional",
        "manipulator": "control", "know_it_all": "control", "negotiator": "control",
        "passive": "avoidance", "avoidant": "avoidance", "paranoid": "avoidance",
        "referred": "special", "rushed": "special",
        "overthinker": "cognitive", "concrete": "cognitive",
        "family_man": "social", "guarantor": "social",
        "collector_call": "temporal", "salary_arrest": "temporal",
        "salesperson": "professional", "psychologist": "professional",
    }

    def __init__(self, difficulty: int = 10, session_id: Optional[str] = None):
        # S4-05: Local RNG seeded by session_id for deterministic replay
        self._rng = random.Random(hash(session_id)) if session_id else random.Random()
        self.pool = self._generate_pool(difficulty)
        self.current_idx = 0
        self.replies_since_shift = 0
        self.shift_interval = self._rng.randint(3, 4)
        self.accumulated_traps: list[str] = []

    def _generate_pool(self, difficulty: int) -> list[str]:
        """5-8 archetypes, difficulty ±2, from different groups."""
        candidates = list(self.ARCHETYPE_GROUPS_MAP.keys())
        self._rng.shuffle(candidates)

        pool: list[str] = []
        group_counts: dict[str, int] = {}

        for code in candidates:
            group = self.ARCHETYPE_GROUPS_MAP.get(code, "")
            if group_counts.get(group, 0) >= 2:
                continue
            pool.append(code)
            group_counts[group] = group_counts.get(group, 0) + 1
            if len(pool) >= self._rng.randint(5, 8):
                break

        return pool or ["skeptic", "anxious", "manipulator", "passive", "overthinker"]

    @property
    def current(self) -> str:
        return self.pool[self.current_idx]

    def check_shift(self) -> Optional[str]:
        """Called every reply. Returns new archetype code or None."""
        self.replies_since_shift += 1
        if self.replies_since_shift >= self.shift_interval:
            self.replies_since_shift = 0
            self.shift_interval = self._rng.randint(3, 4)
            self.current_idx = (self.current_idx + 1) % len(self.pool)
            return self.pool[self.current_idx]
        return None
