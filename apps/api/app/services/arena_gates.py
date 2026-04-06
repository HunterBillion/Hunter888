"""
Arena level gates (DOC_09 + DOC_03 §27).

Checks if user has the required level to access each PvP mode.
"""

from __future__ import annotations

from app.models.pvp import DuelMode


# Level requirements per mode (from DOC_03 §27)
MODE_LEVEL_GATES: dict[str, int] = {
    DuelMode.classic.value: 5,     # PvP Classic Duel
    DuelMode.rapid.value: 9,       # Rapid Fire
    DuelMode.gauntlet.value: 10,   # Gauntlet + Boss Rush
    DuelMode.team2v2.value: 12,    # Team Battle 2v2
}

# PvE training match available from level 3
PVE_TRAINING_LEVEL = 3

# Additional arena features
FEATURE_LEVEL_GATES: dict[str, int] = {
    "pve_training": 3,
    "pvp_classic": 5,
    "knowledge_quiz": 5,
    "pvp_tournament": 7,
    "pvp_rapid_fire": 9,
    "bot_ladder": 9,
    "pvp_gauntlet": 10,
    "boss_rush": 10,
    "team_battle_2v2": 12,
}

# XP daily caps per mode
MODE_XP_DAILY_CAPS: dict[str, int] = {
    DuelMode.classic.value: 1500,
    DuelMode.rapid.value: 1200,
    DuelMode.team2v2.value: 1000,
    DuelMode.gauntlet.value: 500,
}

# Cooldowns per mode (seconds)
MODE_COOLDOWNS: dict[str, int] = {
    DuelMode.classic.value: 0,
    DuelMode.rapid.value: 300,       # 5 min
    DuelMode.team2v2.value: 0,
    DuelMode.gauntlet.value: 21600,  # 6 hours
}

# Time limits per mode (seconds per round/duel)
MODE_TIME_LIMITS: dict[str, int] = {
    DuelMode.classic.value: 600,     # 10 min per round
    DuelMode.rapid.value: 120,       # 2 min per mini-round
    DuelMode.team2v2.value: 600,     # 10 min per round
    DuelMode.gauntlet.value: 480,    # 8 min per duel
}


def can_access_mode(user_level: int, mode: str) -> bool:
    """Check if user level meets the gate for a PvP mode."""
    required = MODE_LEVEL_GATES.get(mode, 99)
    return user_level >= required


def can_access_feature(user_level: int, feature: str) -> bool:
    """Check if user level meets the gate for an arena feature."""
    required = FEATURE_LEVEL_GATES.get(feature, 99)
    return user_level >= required


def get_available_modes(user_level: int) -> list[dict]:
    """Get list of all modes with lock status."""
    return [
        {
            "mode": mode,
            "required_level": level,
            "unlocked": user_level >= level,
            "xp_daily_cap": MODE_XP_DAILY_CAPS.get(mode, 0),
            "cooldown_seconds": MODE_COOLDOWNS.get(mode, 0),
            "time_limit_seconds": MODE_TIME_LIMITS.get(mode, 600),
        }
        for mode, level in MODE_LEVEL_GATES.items()
    ]


def get_gauntlet_series_length(rating: float) -> int:
    """Determine gauntlet series length based on rating (DOC_09)."""
    if rating < 1600:
        return 3
    elif rating <= 2200:
        return 4
    else:
        return 5


# Gauntlet rating bonuses (fixed, not Glicko-2)
# ─── PvE Mode Gates (DOC_10) ────────────────────────────────────────────────

PVE_MODE_LEVEL_GATES: dict[str, int] = {
    "standard": 5,      # Standard bot (PvP queue fallback)
    "training": 3,      # Training Match with AI coach
    "ladder": 9,        # Bot Ladder (5 progressive bots)
    "boss": 10,         # Boss Rush (3 unique bosses)
    "mirror": 15,       # Mirror Match (fight your own style)
}

PVE_MODE_COOLDOWNS: dict[str, int] = {
    "standard": 0,
    "training": 0,
    "ladder": 14400,     # 4 hours
    "boss": 86400,       # 24 hours
    "mirror": 28800,     # 8 hours
}

PVE_RATING_MULTIPLIERS: dict[str, float] = {
    "standard": 0.50,
    "ladder": 0.30,
    "boss": 0.00,        # No rating impact
    "training": 0.00,    # No rating impact
    "mirror": 0.25,
}

PVE_XP_CAPS: dict[str, dict] = {
    "standard": {"per_match": 200, "daily": 1500},
    "ladder": {"per_run": 225, "daily": 450},
    "boss": {"per_run": 425, "daily": 425},
    "training": {"per_match": 100, "daily": 500},
    "mirror": {"per_match": 80, "daily": 240},
}

# Boss Rush configurations (DOC_10 §2.3)
BOSS_CONFIGS = [
    {"index": 0, "type": "perfectionist", "name": "Юрист-перфекционист", "archetype": "know_it_all",
     "mechanic": "strict_legal", "hint": "Этот бот не терпит юридических неточностей.", "xp": 50},
    {"index": 1, "type": "emotional_vampire", "name": "Эмоциональный вампир", "archetype": "custom",
     "mechanic": "composure_drain", "hint": "Ваше самообладание — ограниченный ресурс.", "xp": 75},
    {"index": 2, "type": "chameleon", "name": "Хамелеон", "archetype": "dynamic",
     "mechanic": "archetype_shift", "hint": "Каждые 2 сообщения клиент меняет стиль.", "xp": 100},
]

# Bot Ladder configurations (DOC_10 §2.2)
def get_ladder_bot_configs(player_rating: float) -> list[dict]:
    """Generate 5-bot ladder config based on player rating."""
    return [
        {"index": 0, "difficulty": "easy", "rating_offset": -200},
        {"index": 1, "difficulty": "medium", "rating_offset": -100},
        {"index": 2, "difficulty": "hard", "rating_offset": 0},
        {"index": 3, "difficulty": "hard", "rating_offset": 100},
        {"index": 4, "difficulty": "hard", "rating_offset": 200},
    ]


def get_available_pve_modes(user_level: int) -> list[dict]:
    """Get PvE modes with lock status."""
    return [
        {
            "mode": mode,
            "required_level": level,
            "unlocked": user_level >= level,
            "cooldown_seconds": PVE_MODE_COOLDOWNS.get(mode, 0),
            "rating_multiplier": PVE_RATING_MULTIPLIERS.get(mode, 0),
        }
        for mode, level in PVE_MODE_LEVEL_GATES.items()
    ]


# ─── Knowledge Quiz Mode Gates (DOC_11) ─────────────────────────────────────

KNOWLEDGE_MODE_LEVEL_GATES: dict[str, int] = {
    "free_dialog": 1,
    "blitz": 1,
    "themed": 1,
    "srs_review": 1,
    "daily_challenge": 4,
    "article_deep_dive": 5,
    "case_study": 6,
    "rapid_blitz": 7,
    "debate": 8,
    "pvp": 5,
    "team_quiz": 10,
    "mock_court": 11,
}


def get_available_knowledge_modes(user_level: int) -> list[dict]:
    """Get knowledge quiz modes with lock status."""
    return [
        {"mode": mode, "required_level": level, "unlocked": user_level >= level}
        for mode, level in KNOWLEDGE_MODE_LEVEL_GATES.items()
    ]


GAUNTLET_RATING_BONUSES: dict[tuple[int, bool], tuple[float, float]] = {
    # (total_duels, clean_sweep): (rating_bonus, rd_bonus)
    (3, True): (20.0, -10.0),
    (3, False): (12.0, -5.0),
    (4, True): (28.0, -15.0),
    (4, False): (18.0, -8.0),
    (5, True): (40.0, -20.0),
    (5, False): (25.0, -12.0),
}
