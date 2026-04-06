"""
Rule-based archetype_weights generator for 60 scenarios × 100 archetypes (DOC_05 §12).

Instead of maintaining 6,000 manual weights, uses 4 rules:
1. Group × Group base weights
2. Tier difficulty modifier
3. Theme bonuses
4. Normalize to 100
"""

from __future__ import annotations

from typing import Any

# ─── Rule 1: Archetype group → Scenario group base weights ──────────────────
# HIGH=12, MED=5, LOW=1, VERY_HIGH=20

GROUP_BASE_WEIGHTS: dict[str, dict[str, int]] = {
    # archetype_group → {scenario_group: weight}
    "resistance":   {"cold": 12, "warm": 12, "inbound": 5, "special": 12, "follow_up": 5, "crisis": 5, "compliance": 12, "multi_party": 5},
    "emotional":    {"cold": 5, "warm": 5, "inbound": 12, "special": 12, "follow_up": 5, "crisis": 20, "compliance": 1, "multi_party": 5},
    "control":      {"cold": 5, "warm": 5, "inbound": 5, "special": 12, "follow_up": 5, "crisis": 1, "compliance": 12, "multi_party": 5},
    "avoidance":    {"cold": 12, "warm": 12, "inbound": 5, "special": 5, "follow_up": 20, "crisis": 5, "compliance": 1, "multi_party": 1},
    "special":      {"cold": 5, "warm": 5, "inbound": 5, "special": 12, "follow_up": 5, "crisis": 5, "compliance": 5, "multi_party": 12},
    "cognitive":    {"cold": 5, "warm": 1, "inbound": 5, "special": 5, "follow_up": 1, "crisis": 1, "compliance": 12, "multi_party": 1},
    "social":       {"cold": 1, "warm": 5, "inbound": 1, "special": 12, "follow_up": 5, "crisis": 5, "compliance": 1, "multi_party": 20},
    "temporal":     {"cold": 5, "warm": 12, "inbound": 12, "special": 12, "follow_up": 5, "crisis": 20, "compliance": 5, "multi_party": 5},
    "professional": {"cold": 1, "warm": 5, "inbound": 5, "special": 5, "follow_up": 1, "crisis": 5, "compliance": 12, "multi_party": 5},
    "compound":     {"cold": 1, "warm": 1, "inbound": 1, "special": 20, "follow_up": 1, "crisis": 12, "compliance": 1, "multi_party": 12},
}

# ─── Rule 2: Tier × difficulty modifier ──────────────────────────────────────

def _tier_modifier(tier: int, difficulty: int) -> float:
    """T1 archetypes boosted in easy scenarios, T4 only in hard ones."""
    if tier == 1:
        return 1.5 if difficulty <= 4 else (1.0 if difficulty <= 6 else 0.5)
    elif tier == 2:
        return 1.0
    elif tier == 3:
        return 0.5 if difficulty <= 4 else (1.0 if difficulty <= 6 else 1.5)
    else:  # T4
        return 0.0 if difficulty < 8 else 1.5


# ─── Rule 3: Theme bonuses ──────────────────────────────────────────────────

THEME_BONUSES: dict[tuple[str, str], float] = {
    ("couple", "special_couple"): 15.0,
    ("lawyer_client", "compliance_basic"): 10.0,
    ("lawyer_client", "compliance_docs"): 10.0,
    ("lawyer_client", "compliance_legal"): 15.0,
    ("lawyer_client", "compliance_advanced"): 10.0,
    ("lawyer_client", "compliance_full"): 15.0,
    ("desperate", "crisis_collector"): 10.0,
    ("desperate", "crisis_pre_court"): 10.0,
    ("desperate", "crisis_business"): 8.0,
    ("desperate", "crisis_criminal"): 10.0,
    ("desperate", "crisis_full"): 12.0,
    ("avoidant", "follow_up_first"): 10.0,
    ("avoidant", "follow_up_second"): 12.0,
    ("avoidant", "follow_up_third"): 12.0,
    ("avoidant", "follow_up_rescue"): 10.0,
    ("hostile", "cold_base"): 10.0,
    ("hostile", "cold_database"): 12.0,
    ("paranoid", "cold_base"): 8.0,
    ("paranoid", "cold_database"): 8.0,
    ("blamer", "crisis_collector"): 8.0,
    ("know_it_all", "compliance_legal"): 10.0,
    ("ultimate", "special_boss"): 50.0,
}


# ─── Archetype metadata (group + tier) ──────────────────────────────────────

ARCHETYPE_META: dict[str, tuple[str, int]] = {
    # (group, tier) — from DOC_01
    "skeptic": ("resistance", 1), "blamer": ("resistance", 2), "sarcastic": ("resistance", 2),
    "aggressive": ("resistance", 3), "hostile": ("resistance", 4), "stubborn": ("resistance", 1),
    "conspiracy": ("resistance", 2), "righteous": ("resistance", 3), "litigious": ("resistance", 3),
    "scorched_earth": ("resistance", 4),
    "grateful": ("emotional", 1), "anxious": ("emotional", 1), "ashamed": ("emotional", 2),
    "overwhelmed": ("emotional", 2), "desperate": ("emotional", 3), "crying": ("emotional", 3),
    "guilty": ("emotional", 1), "mood_swinger": ("emotional", 2), "frozen": ("emotional", 3),
    "hysteric": ("emotional", 4),
    "pragmatic": ("control", 1), "shopper": ("control", 1), "negotiator": ("control", 2),
    "know_it_all": ("control", 3), "manipulator": ("control", 3), "lawyer_client": ("control", 4),
    "auditor": ("control", 2), "strategist": ("control", 2), "power_player": ("control", 3),
    "puppet_master": ("control", 4),
    "passive": ("avoidance", 1), "delegator": ("avoidance", 1), "avoidant": ("avoidance", 2),
    "paranoid": ("avoidance", 3), "procrastinator": ("avoidance", 1), "ghosting": ("avoidance", 2),
    "deflector": ("avoidance", 2), "agreeable_ghost": ("avoidance", 2), "fortress": ("avoidance", 3),
    "smoke_screen": ("avoidance", 4),
    "referred": ("special", 1), "returner": ("special", 2), "rushed": ("special", 2),
    "couple": ("special", 3), "elderly": ("special", 1), "young_debtor": ("special", 1),
    "foreign_speaker": ("special", 2), "intermediary": ("special", 2), "repeat_caller": ("special", 3),
    "celebrity": ("special", 4),
    "overthinker": ("cognitive", 1), "concrete": ("cognitive", 1), "storyteller": ("cognitive", 2),
    "misinformed": ("cognitive", 2), "selective_listener": ("cognitive", 2), "black_white": ("cognitive", 3),
    "memory_issues": ("cognitive", 3), "technical": ("cognitive", 2), "magical_thinker": ("cognitive", 3),
    "lawyer_level_2": ("cognitive", 4),
    "family_man": ("social", 1), "influenced": ("social", 1), "reputation_guard": ("social", 2),
    "community_leader": ("social", 2), "breadwinner": ("social", 2), "divorced": ("social", 3),
    "guarantor": ("social", 3), "widow": ("social", 3), "caregiver": ("social", 3),
    "multi_debtor_family": ("social", 4),
    "just_fired": ("temporal", 1), "collector_call": ("temporal", 2), "court_notice": ("temporal", 2),
    "salary_arrest": ("temporal", 2), "pre_court": ("temporal", 3), "post_refusal": ("temporal", 3),
    "inheritance_trap": ("temporal", 3), "business_collapse": ("temporal", 3),
    "medical_crisis": ("temporal", 4), "criminal_risk": ("temporal", 4),
    "teacher": ("professional", 1), "doctor": ("professional", 1), "military": ("professional", 2),
    "accountant": ("professional", 2), "salesperson": ("professional", 2), "it_specialist": ("professional", 2),
    "government": ("professional", 3), "journalist": ("professional", 3), "psychologist": ("professional", 3),
    "competitor_employee": ("professional", 4),
    "aggressive_desperate": ("compound", 3), "manipulator_crying": ("compound", 3),
    "know_it_all_paranoid": ("compound", 3), "passive_aggressive": ("compound", 3),
    "couple_disagreeing": ("compound", 4), "elderly_paranoid": ("compound", 4),
    "hysteric_litigious": ("compound", 4), "puppet_master_lawyer": ("compound", 4),
    "shifting": ("compound", 4), "ultimate": ("compound", 4),
}

# Scenario code → group mapping
SCENARIO_GROUP_MAP: dict[str, str] = {}
for prefix, group in [
    ("cold", "cold"), ("warm", "warm"), ("in_", "inbound"),
    ("follow_up", "follow_up"), ("crisis", "crisis"),
    ("compliance", "compliance"), ("multi_party", "multi_party"),
]:
    pass  # populated dynamically below

def _get_scenario_group(scenario_code: str) -> str:
    if scenario_code.startswith("cold"): return "cold"
    if scenario_code.startswith("warm"): return "warm"
    if scenario_code.startswith("in_"): return "inbound"
    if scenario_code.startswith("follow_up"): return "follow_up"
    if scenario_code.startswith("crisis"): return "crisis"
    if scenario_code.startswith("compliance"): return "compliance"
    if scenario_code.startswith("multi_party"): return "multi_party"
    return "special"


# ─── Main generator ──────────────────────────────────────────────────────────

def generate_archetype_weights(
    scenario_code: str,
    difficulty: int,
    available_archetypes: list[str] | None = None,
) -> dict[str, float]:
    """
    Generate archetype_weights for a scenario using rule-based system.
    Returns dict[archetype_code, weight_pct] summing to ~100.
    """
    scenario_group = _get_scenario_group(scenario_code)
    archetypes = available_archetypes or list(ARCHETYPE_META.keys())

    raw_weights: dict[str, float] = {}
    for arch_code in archetypes:
        meta = ARCHETYPE_META.get(arch_code)
        if not meta:
            continue
        arch_group, arch_tier = meta

        # Rule 1: base weight from group matrix
        base = GROUP_BASE_WEIGHTS.get(arch_group, {}).get(scenario_group, 3)

        # Rule 2: tier modifier
        tier_mod = _tier_modifier(arch_tier, difficulty)

        # Rule 3: theme bonus
        bonus = THEME_BONUSES.get((arch_code, scenario_code), 0.0)

        weight = base * tier_mod + bonus
        if weight > 0:
            raw_weights[arch_code] = weight

    # Rule 4: normalize to 100
    total = sum(raw_weights.values())
    if total == 0:
        return {}

    return {k: round(v / total * 100, 1) for k, v in raw_weights.items()}


# ─── Scoring modifiers per scenario group (DOC_05 §13) ──────────────────────

SCORING_MODIFIERS: dict[str, dict[str, float]] = {
    "cold": {
        "script_adherence": 0.05, "stress_resistance": 0.03, "legal_accuracy": 0.03,
        "empathy": -0.03, "result": -0.03, "human_factor": -0.02,
    },
    "warm": {
        "empathy": 0.03, "consistency": 0.03, "objection_handling": 0.02,
        "script_adherence": -0.03, "stress_resistance": -0.02,
    },
    "inbound": {
        "qualification": 0.03, "knowledge": 0.03, "result": 0.02,
        "script_adherence": -0.03, "stress_resistance": -0.02,
    },
    "special": {
        "adaptation": 0.05, "human_factor": 0.03,
        "script_adherence": -0.05, "consistency": -0.03,
    },
    "follow_up": {
        "empathy": 0.05, "consistency": 0.05,
        "result": -0.02, "stress_resistance": -0.03, "legal_accuracy": -0.03,
    },
    "crisis": {
        "human_factor": 0.05, "empathy": 0.05, "knowledge": 0.03, "legal_accuracy": 0.02,
        "script_adherence": -0.05, "result": -0.05, "objection_handling": -0.03,
    },
    "compliance": {
        "legal_accuracy": 0.15, "knowledge": 0.05,
        "empathy": -0.05, "stress_resistance": -0.03, "human_factor": -0.03, "result": -0.05,
    },
    "multi_party": {
        "adaptation": 0.10, "human_factor": 0.05, "empathy": 0.03,
        "script_adherence": -0.05, "stress_resistance": -0.03, "consistency": -0.03, "legal_accuracy": -0.02,
    },
}


def get_scoring_modifiers(scenario_code: str) -> dict[str, float]:
    """Get scoring layer modifiers for a scenario based on its group."""
    group = _get_scenario_group(scenario_code)
    return SCORING_MODIFIERS.get(group, {})
