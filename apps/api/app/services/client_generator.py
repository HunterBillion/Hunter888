"""Client profile generator v3 for Hunter888 roleplay simulator.

Generates unique client profiles by combining:
archetype × profession × OCEAN personality × PAD baseline × human_factors
× backstory_events × fears × family × debt (DTI-validated) × region

Key upgrades over v2:
- OCEAN (Big Five) anchors per archetype with ±0.15 noise
- PAD (Pleasure-Arousal-Dominance) baseline per archetype with ±0.1 noise
- 20 backstory_events in 4 categories (stressors, social, cognitive, situational)
- human_factors assignment by difficulty (3-7 factors)
- All 25 archetypes covered (fears, soft_spots, breaking_points, age, trust, resistance)
- Family status + children generation
- DTI ratio validation (0.5-2.0 for realistic bankruptcy clients)
- Regional income multipliers + 30 cities
- Redis-based uniqueness checking
- Difficulty-to-level archetype filtering
- LLM backstory generation with template fallback
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
#  OCEAN (Big Five) Anchors per Archetype
#  O=Openness, C=Conscientiousness, E=Extraversion, A=Agreeableness, N=Neuroticism
#  Values: 0.0-1.0, noise ±0.15 applied at generation
# ══════════════════════════════════════════════════════════════════════

ARCHETYPE_OCEAN: dict[str, dict[str, float]] = {
    # ── Group 1: RESISTANCE ──
    "skeptic":        {"O": 0.45, "C": 0.65, "E": 0.40, "A": 0.30, "N": 0.55},
    "blamer":         {"O": 0.35, "C": 0.50, "E": 0.60, "A": 0.20, "N": 0.70},
    "sarcastic":      {"O": 0.55, "C": 0.45, "E": 0.50, "A": 0.20, "N": 0.60},
    "aggressive":     {"O": 0.30, "C": 0.25, "E": 0.70, "A": 0.10, "N": 0.80},
    "hostile":        {"O": 0.20, "C": 0.20, "E": 0.75, "A": 0.05, "N": 0.90},
    "stubborn":       {"O": 0.25, "C": 0.70, "E": 0.30, "A": 0.35, "N": 0.40},
    "conspiracy":     {"O": 0.55, "C": 0.40, "E": 0.45, "A": 0.20, "N": 0.70},
    "righteous":      {"O": 0.30, "C": 0.85, "E": 0.35, "A": 0.50, "N": 0.55},
    "litigious":      {"O": 0.50, "C": 0.75, "E": 0.55, "A": 0.15, "N": 0.65},
    "scorched_earth": {"O": 0.20, "C": 0.15, "E": 0.15, "A": 0.30, "N": 0.90},
    # ── Group 2: EMOTIONAL ──
    "grateful":       {"O": 0.55, "C": 0.55, "E": 0.55, "A": 0.85, "N": 0.25},
    "anxious":        {"O": 0.40, "C": 0.50, "E": 0.35, "A": 0.60, "N": 0.75},
    "ashamed":        {"O": 0.30, "C": 0.60, "E": 0.20, "A": 0.65, "N": 0.75},
    "overwhelmed":    {"O": 0.35, "C": 0.30, "E": 0.40, "A": 0.55, "N": 0.80},
    "desperate":      {"O": 0.25, "C": 0.25, "E": 0.45, "A": 0.50, "N": 0.85},
    "crying":         {"O": 0.30, "C": 0.35, "E": 0.30, "A": 0.60, "N": 0.90},
    "guilty":         {"O": 0.35, "C": 0.60, "E": 0.30, "A": 0.65, "N": 0.75},
    "mood_swinger":   {"O": 0.55, "C": 0.25, "E": 0.80, "A": 0.45, "N": 0.85},
    "frozen":         {"O": 0.20, "C": 0.55, "E": 0.10, "A": 0.40, "N": 0.80},
    "hysteric":       {"O": 0.40, "C": 0.15, "E": 0.90, "A": 0.35, "N": 0.95},
    # ── Group 3: CONTROL ──
    "pragmatic":      {"O": 0.50, "C": 0.75, "E": 0.45, "A": 0.50, "N": 0.30},
    "shopper":        {"O": 0.60, "C": 0.55, "E": 0.50, "A": 0.45, "N": 0.40},
    "negotiator":     {"O": 0.55, "C": 0.65, "E": 0.65, "A": 0.35, "N": 0.35},
    "know_it_all":    {"O": 0.65, "C": 0.70, "E": 0.60, "A": 0.15, "N": 0.50},
    "manipulator":    {"O": 0.70, "C": 0.80, "E": 0.55, "A": 0.10, "N": 0.25},
    "lawyer_client":  {"O": 0.60, "C": 0.90, "E": 0.50, "A": 0.20, "N": 0.35},
    "auditor":        {"O": 0.45, "C": 0.90, "E": 0.35, "A": 0.55, "N": 0.35},
    "strategist":     {"O": 0.65, "C": 0.70, "E": 0.50, "A": 0.40, "N": 0.35},
    "power_player":   {"O": 0.50, "C": 0.75, "E": 0.80, "A": 0.25, "N": 0.30},
    "puppet_master":  {"O": 0.70, "C": 0.80, "E": 0.55, "A": 0.10, "N": 0.25},
    # ── Group 4: AVOIDANCE ──
    "passive":        {"O": 0.30, "C": 0.30, "E": 0.20, "A": 0.75, "N": 0.55},
    "delegator":      {"O": 0.35, "C": 0.25, "E": 0.30, "A": 0.70, "N": 0.60},
    "avoidant":       {"O": 0.30, "C": 0.35, "E": 0.25, "A": 0.55, "N": 0.65},
    "paranoid":       {"O": 0.25, "C": 0.65, "E": 0.35, "A": 0.15, "N": 0.85},
    "procrastinator": {"O": 0.45, "C": 0.30, "E": 0.40, "A": 0.70, "N": 0.50},
    "ghosting":       {"O": 0.30, "C": 0.20, "E": 0.15, "A": 0.50, "N": 0.70},
    "deflector":      {"O": 0.55, "C": 0.35, "E": 0.60, "A": 0.55, "N": 0.50},
    "agreeable_ghost": {"O": 0.40, "C": 0.25, "E": 0.35, "A": 0.90, "N": 0.55},
    "fortress":       {"O": 0.15, "C": 0.65, "E": 0.10, "A": 0.20, "N": 0.70},
    "smoke_screen":   {"O": 0.65, "C": 0.30, "E": 0.75, "A": 0.55, "N": 0.45},
    # ── Group 5: SPECIAL ──
    "referred":       {"O": 0.55, "C": 0.50, "E": 0.50, "A": 0.70, "N": 0.30},
    "returner":       {"O": 0.45, "C": 0.55, "E": 0.45, "A": 0.40, "N": 0.60},
    "rushed":         {"O": 0.40, "C": 0.70, "E": 0.65, "A": 0.35, "N": 0.45},
    "couple":         {"O": 0.50, "C": 0.50, "E": 0.60, "A": 0.40, "N": 0.60},
    "elderly":        {"O": 0.30, "C": 0.60, "E": 0.35, "A": 0.75, "N": 0.50},
    "young_debtor":   {"O": 0.70, "C": 0.30, "E": 0.65, "A": 0.55, "N": 0.55},
    "foreign_speaker": {"O": 0.50, "C": 0.50, "E": 0.40, "A": 0.60, "N": 0.60},
    "intermediary":   {"O": 0.45, "C": 0.50, "E": 0.45, "A": 0.60, "N": 0.45},
    "repeat_caller":  {"O": 0.40, "C": 0.55, "E": 0.60, "A": 0.30, "N": 0.70},
    "celebrity":      {"O": 0.50, "C": 0.80, "E": 0.50, "A": 0.30, "N": 0.50},
    # ── Group 6: COGNITIVE ──
    "overthinker":    {"O": 0.75, "C": 0.70, "E": 0.40, "A": 0.50, "N": 0.65},
    "concrete":       {"O": 0.35, "C": 0.80, "E": 0.55, "A": 0.40, "N": 0.30},
    "storyteller":    {"O": 0.70, "C": 0.30, "E": 0.80, "A": 0.65, "N": 0.40},
    "misinformed":    {"O": 0.55, "C": 0.40, "E": 0.50, "A": 0.50, "N": 0.60},
    "selective_listener": {"O": 0.40, "C": 0.55, "E": 0.45, "A": 0.30, "N": 0.65},
    "black_white":    {"O": 0.20, "C": 0.65, "E": 0.50, "A": 0.35, "N": 0.60},
    "memory_issues":  {"O": 0.35, "C": 0.40, "E": 0.35, "A": 0.65, "N": 0.55},
    "technical":      {"O": 0.65, "C": 0.85, "E": 0.40, "A": 0.50, "N": 0.25},
    "magical_thinker": {"O": 0.60, "C": 0.20, "E": 0.45, "A": 0.55, "N": 0.70},
    "lawyer_level_2": {"O": 0.65, "C": 0.60, "E": 0.55, "A": 0.20, "N": 0.55},
    # ── Group 7: SOCIAL ──
    "family_man":     {"O": 0.40, "C": 0.65, "E": 0.45, "A": 0.75, "N": 0.55},
    "influenced":     {"O": 0.35, "C": 0.45, "E": 0.30, "A": 0.70, "N": 0.65},
    "reputation_guard": {"O": 0.35, "C": 0.70, "E": 0.40, "A": 0.45, "N": 0.65},
    "community_leader": {"O": 0.55, "C": 0.60, "E": 0.70, "A": 0.50, "N": 0.40},
    "breadwinner":    {"O": 0.40, "C": 0.70, "E": 0.45, "A": 0.55, "N": 0.65},
    "divorced":       {"O": 0.40, "C": 0.50, "E": 0.50, "A": 0.25, "N": 0.75},
    "guarantor":      {"O": 0.45, "C": 0.55, "E": 0.55, "A": 0.35, "N": 0.70},
    "widow":          {"O": 0.30, "C": 0.50, "E": 0.25, "A": 0.65, "N": 0.85},
    "caregiver":      {"O": 0.40, "C": 0.60, "E": 0.35, "A": 0.70, "N": 0.70},
    "multi_debtor_family": {"O": 0.45, "C": 0.55, "E": 0.50, "A": 0.40, "N": 0.75},
    # ── Group 8: TEMPORAL ──
    "just_fired":     {"O": 0.40, "C": 0.45, "E": 0.40, "A": 0.55, "N": 0.75},
    "collector_call": {"O": 0.40, "C": 0.40, "E": 0.50, "A": 0.55, "N": 0.80},
    "court_notice":   {"O": 0.45, "C": 0.50, "E": 0.50, "A": 0.50, "N": 0.75},
    "salary_arrest":  {"O": 0.35, "C": 0.45, "E": 0.60, "A": 0.40, "N": 0.80},
    "pre_court":      {"O": 0.50, "C": 0.60, "E": 0.50, "A": 0.45, "N": 0.70},
    "post_refusal":   {"O": 0.40, "C": 0.50, "E": 0.40, "A": 0.40, "N": 0.80},
    "inheritance_trap": {"O": 0.50, "C": 0.50, "E": 0.45, "A": 0.55, "N": 0.65},
    "business_collapse": {"O": 0.55, "C": 0.65, "E": 0.50, "A": 0.40, "N": 0.70},
    "medical_crisis": {"O": 0.40, "C": 0.45, "E": 0.40, "A": 0.60, "N": 0.85},
    "criminal_risk":  {"O": 0.45, "C": 0.55, "E": 0.45, "A": 0.45, "N": 0.90},
    # ── Group 9: PROFESSIONAL ──
    "teacher":        {"O": 0.60, "C": 0.70, "E": 0.50, "A": 0.70, "N": 0.35},
    "doctor":         {"O": 0.55, "C": 0.80, "E": 0.45, "A": 0.50, "N": 0.30},
    "military":       {"O": 0.25, "C": 0.90, "E": 0.55, "A": 0.35, "N": 0.30},
    "accountant":     {"O": 0.40, "C": 0.90, "E": 0.30, "A": 0.50, "N": 0.35},
    "salesperson":    {"O": 0.65, "C": 0.60, "E": 0.75, "A": 0.40, "N": 0.35},
    "it_specialist":  {"O": 0.70, "C": 0.75, "E": 0.35, "A": 0.45, "N": 0.30},
    "government":     {"O": 0.30, "C": 0.85, "E": 0.40, "A": 0.40, "N": 0.40},
    "journalist":     {"O": 0.75, "C": 0.65, "E": 0.65, "A": 0.35, "N": 0.40},
    "psychologist":   {"O": 0.80, "C": 0.70, "E": 0.50, "A": 0.55, "N": 0.25},
    "competitor_employee": {"O": 0.50, "C": 0.65, "E": 0.55, "A": 0.15, "N": 0.35},
    # ── Group 10: COMPOUND (calculated via blending) ──
    "aggressive_desperate":  {"O": 0.28, "C": 0.25, "E": 0.58, "A": 0.30, "N": 0.90},
    "manipulator_crying":    {"O": 0.50, "C": 0.58, "E": 0.43, "A": 0.35, "N": 0.72},
    "know_it_all_paranoid":  {"O": 0.45, "C": 0.68, "E": 0.48, "A": 0.15, "N": 0.82},
    "passive_aggressive":    {"O": 0.43, "C": 0.38, "E": 0.35, "A": 0.48, "N": 0.72},
    "couple_disagreeing":    {"O": 0.40, "C": 0.38, "E": 0.65, "A": 0.25, "N": 0.82},
    "elderly_paranoid":      {"O": 0.28, "C": 0.63, "E": 0.33, "A": 0.45, "N": 0.82},
    "hysteric_litigious":    {"O": 0.45, "C": 0.45, "E": 0.73, "A": 0.25, "N": 0.92},
    "puppet_master_lawyer":  {"O": 0.65, "C": 0.85, "E": 0.53, "A": 0.15, "N": 0.40},
    "shifting":              {"O": 0.45, "C": 0.50, "E": 0.50, "A": 0.40, "N": 0.60},
    "ultimate":              {"O": 0.45, "C": 0.50, "E": 0.55, "A": 0.30, "N": 0.75},
}


# ══════════════════════════════════════════════════════════════════════
#  PROFESSION OCEAN Modifiers (DOC_02 §5.5)
#  Applied: modified_OCEAN[dim] = base + prof_mod + noise(±0.15)
# ══════════════════════════════════════════════════════════════════════

PROFESSION_OCEAN_MODIFIERS: dict[str, dict[str, float]] = {
    "budget":          {"C": 0.10, "A": 0.05},
    "government":      {"C": 0.15, "O": -0.05},
    "medical":         {"A": 0.15, "N": 0.10},
    "education":       {"O": 0.10, "C": 0.05, "A": 0.10},
    "military":        {"C": 0.20, "A": -0.10, "E": -0.05},
    "law_enforcement": {"C": 0.15, "A": -0.15, "N": -0.05},
    "entrepreneur":    {"E": 0.10, "O": 0.10, "C": 0.05},
    "finance":         {"C": 0.20, "O": -0.05, "A": -0.05},
    "freelancer":      {"O": 0.15, "C": -0.10, "E": 0.05},
    "worker":          {"O": -0.10, "C": 0.05, "A": 0.05},
    "construction":    {"C": 0.05, "A": -0.05, "E": 0.05},
    "transport":       {"E": 0.05, "C": -0.05, "N": 0.05},
    "agriculture":     {"O": -0.15, "C": 0.10, "A": 0.05},
    "it_office":       {"O": 0.10, "C": 0.10, "E": -0.05},
    "science":         {"O": 0.20, "C": 0.10, "E": -0.10},
    "creative":        {"O": 0.25, "C": -0.15, "E": 0.10, "N": 0.10},
    "trade_service":   {"E": 0.10, "A": 0.05},
    "sports":          {"C": 0.15, "E": 0.15, "A": -0.05},
    "pensioner":       {"O": -0.10, "C": 0.10, "N": 0.10},
    "homemaker":       {"A": 0.15, "C": -0.05, "N": 0.10},
    "student":         {"O": 0.15, "C": -0.10, "E": 0.10},
    "unemployed":      {"N": 0.15, "C": -0.10, "E": -0.10},
    "disabled":        {"N": 0.10, "A": 0.05, "E": -0.10},
    "clergy":          {"A": 0.20, "C": 0.15, "O": 0.05, "N": -0.05},
    "special":         {},
}

# Speech modifiers per profession
PROFESSION_SPEECH_MODIFIERS: dict[str, dict] = {
    "budget":          {"formality": 0.5, "vocabulary": "standard",     "jargon": []},
    "government":      {"formality": 0.8, "vocabulary": "bureaucratic", "jargon": ["нормативный акт", "регламент"]},
    "medical":         {"formality": 0.5, "vocabulary": "medical",      "jargon": ["диагноз", "выписка"]},
    "education":       {"formality": 0.7, "vocabulary": "literary",     "jargon": ["учебный план", "аттестация"]},
    "military":        {"formality": 0.8, "vocabulary": "military",     "jargon": ["рапорт", "приказ", "часть"]},
    "law_enforcement": {"formality": 0.8, "vocabulary": "legal",        "jargon": ["протокол", "дело"]},
    "entrepreneur":    {"formality": 0.5, "vocabulary": "business",     "jargon": ["маржа", "выручка", "контрагент"]},
    "finance":         {"formality": 0.8, "vocabulary": "financial",    "jargon": ["ставка", "портфель", "БКИ"]},
    "freelancer":      {"formality": 0.3, "vocabulary": "modern",       "jargon": ["дедлайн", "тикет", "самозанятый"]},
    "worker":          {"formality": 0.3, "vocabulary": "colloquial",   "jargon": ["смена", "бригада"]},
    "construction":    {"formality": 0.3, "vocabulary": "colloquial",   "jargon": ["объект", "подряд", "смета"]},
    "transport":       {"formality": 0.3, "vocabulary": "colloquial",   "jargon": ["рейс", "маршрут"]},
    "agriculture":     {"formality": 0.2, "vocabulary": "rural",        "jargon": ["урожай", "субсидия"]},
    "it_office":       {"formality": 0.5, "vocabulary": "tech",         "jargon": ["спринт", "деплой", "ревью"]},
    "science":         {"formality": 0.8, "vocabulary": "academic",     "jargon": ["грант", "публикация", "диссертация"]},
    "creative":        {"formality": 0.3, "vocabulary": "expressive",   "jargon": ["проект", "гонорар"]},
    "trade_service":   {"formality": 0.4, "vocabulary": "colloquial",   "jargon": ["выручка", "смена"]},
    "sports":          {"formality": 0.3, "vocabulary": "sports",       "jargon": ["тренировка", "контракт"]},
    "pensioner":       {"formality": 0.5, "vocabulary": "dated",        "jargon": ["пенсия", "собес", "стаж"]},
    "homemaker":       {"formality": 0.3, "vocabulary": "domestic",     "jargon": ["кредитка", "рассрочка"]},
    "student":         {"formality": 0.3, "vocabulary": "youth",        "jargon": ["стипендия", "общага"]},
    "unemployed":      {"formality": 0.3, "vocabulary": "subdued",      "jargon": ["биржа труда", "пособие"]},
    "disabled":        {"formality": 0.5, "vocabulary": "standard",     "jargon": ["группа", "МСЭ", "льготы"]},
    "clergy":          {"formality": 0.8, "vocabulary": "religious",    "jargon": ["приход", "благословение"]},
    "special":         {"formality": 0.5, "vocabulary": "standard",     "jargon": []},
}


# ══════════════════════════════════════════════════════════════════════
#  LEAD SOURCE Awareness + Trust (DOC_02 §6.5)
# ══════════════════════════════════════════════════════════════════════

LEAD_SOURCE_AWARENESS: dict[str, int] = {
    "cold_base": 0, "cold_social": 1, "cold_event": 1,
    "website_form": 2, "social_media": 1, "webinar": 2,
    "warm_complaint": 0, "warm_competitor": 3, "lead_nurture": 2,
    "ad_retarget": 1, "incoming": 2, "in_chat": 1,
    "chatbot": 1, "in_referral_direct": 2, "in_urgent": 1,
    "referral": 1, "repeat_call": 2, "partner": 1,
    "churned": 3, "callback_scheduled": 2,
}

LEAD_SOURCE_TRUST_MODIFIER: dict[str, int] = {
    "cold_base": -2, "cold_social": -1, "cold_event": 0,
    "website_form": 1, "social_media": 0, "webinar": 2,
    "warm_complaint": 0, "warm_competitor": -1, "lead_nurture": 1,
    "ad_retarget": 0, "incoming": 2, "in_chat": 1,
    "chatbot": 1, "in_referral_direct": 3, "in_urgent": 1,
    "referral": 2, "repeat_call": 0, "partner": 1,
    "churned": -1, "callback_scheduled": 2,
}


# ══════════════════════════════════════════════════════════════════════
#  EMOTION PRESETS (DOC_02 §8.3) — MoodBuffer modifiers
# ══════════════════════════════════════════════════════════════════════

EMOTION_PRESET_MODIFIERS: dict[str, dict[str, float]] = {
    "neutral":  {"threshold_pos": 0,     "threshold_neg": 0,     "decay": 0,     "ema": 0},
    "anxious":  {"threshold_pos": 0.05,  "threshold_neg": -0.15, "decay": 0.02,  "ema": 0.05},
    "angry":    {"threshold_pos": -0.10, "threshold_neg": -0.20, "decay": -0.01, "ema": 0.08},
    "hopeful":  {"threshold_pos": -0.10, "threshold_neg": 0.10,  "decay": 0.01,  "ema": -0.03},
    "tired":    {"threshold_pos": 0.10,  "threshold_neg": 0.05,  "decay": 0.04,  "ema": -0.05},
    "rushed":   {"threshold_pos": -0.05, "threshold_neg": -0.10, "decay": -0.02, "ema": 0.10},
    "trusting": {"threshold_pos": -0.15, "threshold_neg": 0.15,  "decay": 0.01,  "ema": -0.05},
}


# ══════════════════════════════════════════════════════════════════════
#  ENVIRONMENT Modifiers (DOC_02 §10)
# ══════════════════════════════════════════════════════════════════════

ENVIRONMENT_AROUSAL_MOD: dict[str, float] = {
    "none": 0, "office": 0.05, "street": 0.10, "children": 0.15, "tv": 0.03,
}

TIME_TRUST_MOD: dict[str, int] = {
    "morning": -1, "afternoon": 0, "evening": 1, "night": -2,
}

TIME_ENERGY_MOD: dict[str, float] = {
    "morning": 0.05, "afternoon": 0, "evening": -0.05, "night": -0.15,
}

FATIGUE_DECAY_MOD: dict[str, float] = {
    "fresh": -0.02, "normal": 0, "tired": 0.03, "exhausted": 0.06,
}

FATIGUE_THRESHOLD_MOD: dict[str, float] = {
    "fresh": -0.05, "normal": 0, "tired": 0.05, "exhausted": 0.10,
}


# ══════════════════════════════════════════════════════════════════════
#  PAD (Pleasure-Arousal-Dominance) Baselines per Archetype
#  P/A/D: -1.0 to +1.0, noise ±0.1
# ══════════════════════════════════════════════════════════════════════

ARCHETYPE_PAD: dict[str, dict[str, float]] = {
    # ── Defensive ──
    "skeptic":       {"P": -0.2, "A": 0.1,  "D": 0.3},
    "anxious":       {"P": -0.5, "A": 0.6,  "D": -0.4},
    "passive":       {"P": -0.3, "A": -0.3, "D": -0.5},
    "avoidant":      {"P": -0.4, "A": -0.2, "D": -0.3},
    "paranoid":      {"P": -0.6, "A": 0.5,  "D": 0.1},
    "ashamed":       {"P": -0.6, "A": 0.3,  "D": -0.6},

    # ── Aggressive ──
    "aggressive":    {"P": -0.3, "A": 0.7,  "D": 0.6},
    "hostile":       {"P": -0.5, "A": 0.8,  "D": 0.5},
    "blamer":        {"P": -0.4, "A": 0.5,  "D": 0.4},
    "sarcastic":     {"P": -0.1, "A": 0.3,  "D": 0.3},

    # ── Active ──
    "manipulator":   {"P":  0.1, "A": 0.3,  "D": 0.7},
    "pragmatic":     {"P":  0.0, "A": 0.1,  "D": 0.4},
    "delegator":     {"P": -0.1, "A": -0.2, "D": -0.3},
    "know_it_all":   {"P":  0.1, "A": 0.2,  "D": 0.6},
    "negotiator":    {"P":  0.0, "A": 0.3,  "D": 0.5},
    "shopper":       {"P":  0.0, "A": 0.2,  "D": 0.3},

    # ── Emotional ──
    "desperate":     {"P": -0.8, "A": 0.7,  "D": -0.7},
    "crying":        {"P": -0.9, "A": 0.6,  "D": -0.8},
    "grateful":      {"P":  0.4, "A": 0.1,  "D": -0.2},
    "overwhelmed":   {"P": -0.7, "A": 0.5,  "D": -0.6},

    # ── Situational ──
    "returner":      {"P": -0.3, "A": 0.2,  "D": 0.0},
    "referred":      {"P": -0.1, "A": 0.1,  "D": 0.0},
    "rushed":        {"P": -0.2, "A": 0.6,  "D": 0.3},
    "lawyer_client": {"P": -0.2, "A": 0.2,  "D": 0.4},
    "couple":        {"P": -0.3, "A": 0.3,  "D": 0.0},
}


# ══════════════════════════════════════════════════════════════════════
#  Backstory Events (20 шт, 4 категории)
# ══════════════════════════════════════════════════════════════════════

@dataclass
class BackstoryEvent:
    code: str
    category: str   # stressor | social | cognitive | situational
    name_ru: str
    intensity: str  # mild | moderate | severe
    description_template: str
    compatible_archetypes: list[str] = field(default_factory=list)


BACKSTORY_EVENTS: list[BackstoryEvent] = [
    # ── Стрессоры ──
    BackstoryEvent("job_loss", "stressor", "Потеря работы", "severe",
                   "Потерял(а) работу {months_ago} месяцев назад, с тех пор перебивается подработками",
                   ["desperate", "anxious", "passive", "overwhelmed"]),
    BackstoryEvent("divorce", "stressor", "Развод", "severe",
                   "Недавно развёлся/развелась, делят имущество и долги",
                   ["blamer", "aggressive", "ashamed", "crying"]),
    BackstoryEvent("illness", "stressor", "Серьёзная болезнь", "severe",
                   "Перенёс(ла) серьёзную болезнь, большая часть долгов — на лечение",
                   ["desperate", "crying", "grateful", "overwhelmed"]),
    BackstoryEvent("death_relative", "stressor", "Смерть близкого", "severe",
                   "Потерял(а) близкого родственника, унаследовал(а) долги",
                   ["overwhelmed", "passive", "ashamed"]),
    BackstoryEvent("lawsuit", "stressor", "Судебное разбирательство", "moderate",
                   "Находится под судебным преследованием от кредитора, получил(а) повестку",
                   ["anxious", "paranoid", "desperate", "rushed"]),

    # ── Социальные ──
    BackstoryEvent("loneliness", "social", "Одиночество", "moderate",
                   "Живёт один/одна, не с кем посоветоваться о финансовых вопросах",
                   ["passive", "avoidant", "anxious"]),
    BackstoryEvent("family_pressure", "social", "Давление семьи", "moderate",
                   "Семья настаивает на решении проблемы, постоянные конфликты из-за денег",
                   ["blamer", "aggressive", "ashamed", "couple"]),
    BackstoryEvent("shame_stigma", "social", "Стыд и стигма", "moderate",
                   "Скрывает долги от окружающих, боится осуждения",
                   ["ashamed", "avoidant", "passive"]),
    BackstoryEvent("spouse_control", "social", "Контроль супруга", "moderate",
                   "Супруг(а) контролирует финансы, клиент звонит тайком",
                   ["couple", "avoidant", "passive", "ashamed"]),
    BackstoryEvent("dependency", "social", "Финансовая зависимость", "mild",
                   "Финансово зависит от родственников, чувствует себя обузой",
                   ["ashamed", "passive", "grateful"]),

    # ── Когнитивные ──
    BackstoryEvent("low_fin_literacy", "cognitive", "Низкая финграмотность", "mild",
                   "Плохо разбирается в финансовых и юридических вопросах, путает понятия",
                   ["passive", "anxious", "overwhelmed", "delegator"]),
    BackstoryEvent("magical_thinking", "cognitive", "Магическое мышление", "mild",
                   "Верит что «само рассосётся», надеется на чудо или помощь государства",
                   ["avoidant", "passive", "desperate"]),
    BackstoryEvent("learned_helplessness", "cognitive", "Выученная беспомощность", "moderate",
                   "Уже пробовал(а) решить проблему несколько раз, разочаровался/лась",
                   ["passive", "overwhelmed", "returner"]),
    BackstoryEvent("past_fixation", "cognitive", "Фиксация на прошлом", "mild",
                   "Постоянно вспоминает как дошёл до такой ситуации, не может сосредоточиться на решении",
                   ["blamer", "crying", "desperate"]),
    BackstoryEvent("distrust_system", "cognitive", "Недоверие к системе", "moderate",
                   "Не доверяет юристам, банкам и государству — считает всех мошенниками",
                   ["paranoid", "skeptic", "hostile"]),

    # ── Ситуативные ──
    BackstoryEvent("court_tomorrow", "situational", "Суд завтра", "severe",
                   "Заседание суда через 1-3 дня, паника и срочность",
                   ["rushed", "desperate", "anxious"]),
    BackstoryEvent("competitor_active", "situational", "Конкурент уже работает", "moderate",
                   "Уже консультировался в другой компании, сравнивает предложения",
                   ["shopper", "skeptic", "pragmatic"]),
    BackstoryEvent("child_dependent", "situational", "Ребёнок на иждивении", "moderate",
                   "Есть несовершеннолетний ребёнок, боится за его будущее",
                   ["anxious", "crying", "desperate", "couple"]),
    BackstoryEvent("pregnancy", "situational", "Беременность", "severe",
                   "Беременна или жена беременна, дополнительный стресс",
                   ["anxious", "desperate", "couple"]),
    BackstoryEvent("disability", "situational", "Инвалидность", "moderate",
                   "Имеет инвалидность, ограниченные возможности",
                   ["passive", "grateful", "desperate", "overwhelmed"]),
]

BACKSTORY_EVENT_MAP: dict[str, BackstoryEvent] = {e.code: e for e in BACKSTORY_EVENTS}


# ══════════════════════════════════════════════════════════════════════
#  Human Factors (25 behavioural traits from ТЗ v5)
# ══════════════════════════════════════════════════════════════════════

HUMAN_FACTORS: list[dict[str, Any]] = [
    {"code": "stubbornness",   "name_ru": "Упрямство",         "archetype_affinity": ["aggressive", "hostile", "blamer", "know_it_all"]},
    {"code": "forgetfulness",  "name_ru": "Забывчивость",      "archetype_affinity": ["passive", "overwhelmed", "delegator"]},
    {"code": "pride",          "name_ru": "Гордость",          "archetype_affinity": ["aggressive", "know_it_all", "sarcastic", "manipulator"]},
    {"code": "impatience",     "name_ru": "Нетерпеливость",    "archetype_affinity": ["rushed", "aggressive", "hostile"]},
    {"code": "suspicion",      "name_ru": "Подозрительность",  "archetype_affinity": ["paranoid", "skeptic", "hostile"]},
    {"code": "indecisiveness", "name_ru": "Нерешительность",   "archetype_affinity": ["passive", "avoidant", "anxious", "delegator"]},
    {"code": "anger",          "name_ru": "Гнев",              "archetype_affinity": ["aggressive", "hostile", "blamer"]},
    {"code": "authority",      "name_ru": "Авторитарность",    "archetype_affinity": ["aggressive", "manipulator", "know_it_all"]},
    {"code": "guilt",          "name_ru": "Чувство вины",      "archetype_affinity": ["ashamed", "crying", "desperate"]},
    {"code": "denial",         "name_ru": "Отрицание",         "archetype_affinity": ["avoidant", "passive", "sarcastic"]},
    {"code": "victimhood",     "name_ru": "Жертвенность",      "archetype_affinity": ["crying", "desperate", "blamer"]},
    {"code": "perfectionism",  "name_ru": "Перфекционизм",     "archetype_affinity": ["know_it_all", "pragmatic", "lawyer_client"]},
    {"code": "distraction",    "name_ru": "Рассеянность",      "archetype_affinity": ["overwhelmed", "passive", "rushed"]},
    {"code": "people_pleasing","name_ru": "Угодничество",      "archetype_affinity": ["passive", "grateful", "ashamed"]},
    {"code": "competitiveness","name_ru": "Соперничество",     "archetype_affinity": ["manipulator", "negotiator", "shopper"]},
    {"code": "pessimism",      "name_ru": "Пессимизм",         "archetype_affinity": ["desperate", "overwhelmed", "passive"]},
    {"code": "impulsiveness",  "name_ru": "Импульсивность",    "archetype_affinity": ["aggressive", "rushed", "desperate"]},
    {"code": "secrecy",        "name_ru": "Скрытность",        "archetype_affinity": ["avoidant", "ashamed", "paranoid"]},
    {"code": "fatalism",       "name_ru": "Фатализм",          "archetype_affinity": ["passive", "avoidant", "overwhelmed"]},
    {"code": "grandiosity",    "name_ru": "Грандиозность",     "archetype_affinity": ["manipulator", "know_it_all", "sarcastic"]},
    {"code": "dependency_trait","name_ru": "Зависимость",      "archetype_affinity": ["delegator", "passive", "couple"]},
    {"code": "rigidity",       "name_ru": "Ригидность",        "archetype_affinity": ["skeptic", "know_it_all", "paranoid"]},
    {"code": "self_pity",      "name_ru": "Жалость к себе",    "archetype_affinity": ["crying", "desperate", "overwhelmed"]},
    {"code": "deflection",     "name_ru": "Перенаправление",   "archetype_affinity": ["blamer", "manipulator", "sarcastic"]},
    {"code": "hyper_vigilance","name_ru": "Сверхбдительность", "archetype_affinity": ["paranoid", "anxious", "lawyer_client"]},
]

HUMAN_FACTOR_MAP: dict[str, dict] = {f["code"]: f for f in HUMAN_FACTORS}


# ══════════════════════════════════════════════════════════════════════
#  Russian Identity Data
# ══════════════════════════════════════════════════════════════════════

MALE_NAMES = [
    "Алексей Михайлович", "Дмитрий Игоревич", "Сергей Александрович",
    "Андрей Викторович", "Максим Сергеевич", "Иван Петрович",
    "Николай Андреевич", "Павел Дмитриевич", "Артём Олегович",
    "Владимир Николаевич", "Евгений Валерьевич", "Константин Юрьевич",
    "Михаил Владимирович", "Роман Алексеевич", "Олег Станиславович",
    "Денис Анатольевич", "Юрий Васильевич", "Виктор Геннадьевич",
    "Антон Романович", "Кирилл Павлович", "Григорий Львович",
    "Тимур Рашидович", "Вадим Борисович", "Руслан Маратович",
    "Станислав Евгеньевич", "Игорь Фёдорович", "Борис Константинович",
    "Александр Ильич", "Геннадий Петрович", "Валерий Семёнович",
]

FEMALE_NAMES = [
    "Елена Сергеевна", "Ольга Владимировна", "Наталья Александровна",
    "Анна Дмитриевна", "Мария Игоревна", "Татьяна Викторовна",
    "Ирина Николаевна", "Светлана Андреевна", "Екатерина Михайловна",
    "Юлия Олеговна", "Марина Валерьевна", "Людмила Петровна",
    "Оксана Юрьевна", "Галина Фёдоровна", "Дарья Романовна",
    "Анастасия Павловна", "Виктория Станиславовна", "Валентина Ивановна",
    "Надежда Васильевна", "Кристина Алексеевна", "Алина Тимуровна",
    "Полина Денисовна", "Вера Константиновна", "Диана Маратовна",
    "Лариса Геннадьевна", "Жанна Борисовна", "Тамара Григорьевна",
    "Регина Рустамовна", "Евгения Львовна", "Софья Артёмовна",
]

SURNAMES_MALE = [
    "Иванов", "Петров", "Сидоров", "Козлов", "Морозов",
    "Волков", "Соколов", "Лебедев", "Новиков", "Кузнецов",
    "Попов", "Васильев", "Смирнов", "Фёдоров", "Николаев",
    "Орлов", "Андреев", "Макаров", "Захаров", "Белов",
    "Тарасов", "Григорьев", "Романов", "Степанов", "Павлов",
    "Семёнов", "Голубев", "Виноградов", "Богданов", "Крылов",
]

SURNAMES_FEMALE = [
    "Иванова", "Петрова", "Сидорова", "Козлова", "Морозова",
    "Волкова", "Соколова", "Лебедева", "Новикова", "Кузнецова",
    "Попова", "Васильева", "Смирнова", "Фёдорова", "Николаева",
    "Орлова", "Андреева", "Макарова", "Захарова", "Белова",
    "Тарасова", "Григорьева", "Романова", "Степанова", "Павлова",
    "Семёнова", "Голубева", "Виноградова", "Богданова", "Крылова",
]


# ══════════════════════════════════════════════════════════════════════
#  Cities with Regional Income Multipliers
# ══════════════════════════════════════════════════════════════════════

CITIES: list[dict[str, Any]] = [
    # Миллионники
    {"name": "Москва",            "income_mult": 1.80, "tier": 1},
    {"name": "Санкт-Петербург",   "income_mult": 1.40, "tier": 1},
    {"name": "Краснодар",         "income_mult": 1.10, "tier": 1},
    {"name": "Новосибирск",       "income_mult": 1.05, "tier": 1},
    {"name": "Екатеринбург",      "income_mult": 1.15, "tier": 1},
    {"name": "Казань",            "income_mult": 1.10, "tier": 1},
    {"name": "Ростов-на-Дону",    "income_mult": 1.05, "tier": 1},
    {"name": "Самара",            "income_mult": 1.00, "tier": 1},
    {"name": "Воронеж",           "income_mult": 0.95, "tier": 1},
    {"name": "Челябинск",         "income_mult": 1.00, "tier": 1},
    {"name": "Омск",              "income_mult": 0.95, "tier": 1},
    {"name": "Уфа",               "income_mult": 1.00, "tier": 1},
    {"name": "Красноярск",        "income_mult": 1.10, "tier": 1},
    {"name": "Пермь",             "income_mult": 1.00, "tier": 1},
    {"name": "Волгоград",         "income_mult": 0.90, "tier": 1},
    # Средние города 100-500K
    {"name": "Тверь",             "income_mult": 0.85, "tier": 2},
    {"name": "Калуга",            "income_mult": 0.90, "tier": 2},
    {"name": "Брянск",            "income_mult": 0.80, "tier": 2},
    {"name": "Тольятти",          "income_mult": 0.85, "tier": 2},
    {"name": "Рязань",            "income_mult": 0.85, "tier": 2},
    {"name": "Иваново",           "income_mult": 0.75, "tier": 2},
    {"name": "Курск",             "income_mult": 0.85, "tier": 2},
    {"name": "Ставрополь",        "income_mult": 0.85, "tier": 2},
    {"name": "Тула",              "income_mult": 0.90, "tier": 2},
    {"name": "Саратов",           "income_mult": 0.80, "tier": 2},
    {"name": "Оренбург",          "income_mult": 0.85, "tier": 2},
    {"name": "Липецк",            "income_mult": 0.85, "tier": 2},
    {"name": "Чебоксары",         "income_mult": 0.80, "tier": 2},
    {"name": "Владимир",          "income_mult": 0.80, "tier": 2},
    {"name": "Смоленск",          "income_mult": 0.80, "tier": 2},
]


# ══════════════════════════════════════════════════════════════════════
#  Archetype-Level Unlocks (по уровню менеджера)
# ══════════════════════════════════════════════════════════════════════

ARCHETYPE_LEVEL_TIERS: dict[str, int] = {
    # Level 1-5: лёгкие (12 шт)
    "passive": 1, "anxious": 1, "grateful": 1, "desperate": 1,
    "referred": 1, "delegator": 1, "ashamed": 1, "crying": 1,
    "overwhelmed": 1, "avoidant": 1, "returner": 1, "skeptic": 3,
    # Level 6-10: средние (+6 = 18 шт)
    "pragmatic": 6, "blamer": 6, "shopper": 6,
    "negotiator": 7, "rushed": 7, "aggressive": 8,
    # Level 11-15: сложные (+5 = 23 шт)
    "hostile": 11, "sarcastic": 11, "paranoid": 12,
    "know_it_all": 13, "manipulator": 14,
    # Level 16-20: все + гибриды
    "lawyer_client": 16, "couple": 17,
}


# ══════════════════════════════════════════════════════════════════════
#  Fears / Soft Spots / Breaking Points — ALL 25 archetypes
# ══════════════════════════════════════════════════════════════════════

ARCHETYPE_FEARS: dict[str, list[str]] = {
    "skeptic": [
        "Обманут с документами и заберут квартиру",
        "Юристы — мошенники, деньги возьмут и пропадут",
        "Где-то есть подвох, слишком хорошо звучит",
        "После банкротства не дадут кредит 10 лет",
        "Коллекторы станут звонить ещё чаще",
        "Испортят кредитную историю навсегда",
    ],
    "anxious": [
        "Придут приставы и опишут всё имущество",
        "Уволят с работы, если узнают про долги",
        "Банк подаст в суд и заберут зарплату",
        "Родственники узнают про долги",
        "Коллекторы придут домой",
        "Посадят за невыплату кредита",
    ],
    "passive": [
        "Всё равно ничего не поможет",
        "Уже пробовали — не получилось",
        "Ситуация безнадёжная",
        "Нет сил разбираться с бумагами",
        "Потеряю последнее, что есть",
        "Слишком поздно что-то менять",
    ],
    "avoidant": [
        "Не хочу думать об этом сейчас",
        "Может, долги просто спишут сами",
        "Процедура слишком сложная",
        "Придётся ходить по инстанциям",
        "Не хочу никого видеть по этому поводу",
        "Лучше просто не брать трубку",
    ],
    "paranoid": [
        "Это схема по выкачиванию денег",
        "Мои данные продадут мошенникам",
        "Управляющий работает на банк",
        "Суд подкуплен кредиторами",
        "Записывают звонок для использования против меня",
        "Откуда они знают мой номер и долги",
    ],
    "ashamed": [
        "Все узнают, что я банкрот",
        "Дети будут стыдиться",
        "На работе узнают — позор",
        "Соседи увидят объявление в газете",
        "Это клеймо на всю жизнь",
        "Я сам виноват в долгах",
    ],
    "aggressive": [
        "Навязывают ненужные услуги",
        "Хотят заработать на моей беде",
        "Могу справиться сам, без юристов",
        "Банки специально запугивают",
        "Государство на стороне банков",
        "Суд всегда против должника",
    ],
    "hostile": [
        "Все мошенники, никому нельзя верить",
        "Менеджер — обманщик, как все",
        "Государство создало эту ситуацию",
        "Меня уже обманывали десять раз",
        "Зачем мне ваши услуги — ещё денег вытянуть",
        "Я лучше буду должен, чем платить юристам",
    ],
    "blamer": [
        "Это банк виноват, что дал кредит",
        "Жена/муж набрал(а) долгов",
        "Государство не защищает людей",
        "Работодатель уволил без причины",
        "Коллекторы довели до этого",
        "Никто не предупредил о последствиях",
    ],
    "sarcastic": [
        "Конечно, всё решится одним звонком",
        "Юристы — святые люди, бесплатно работают",
        "Судья прочитает мою историю и заплачет",
        "Банки просто простят всё из доброты",
        "Очередной «спаситель» с волшебной таблеткой",
        "Наверное, вы звоните мне из альтруизма",
    ],
    "manipulator": [
        "Специально давлю на эмоции, чтобы продать",
        "Знаю все ваши приёмы продаж",
        "Сначала бесплатная консультация, потом доплаты",
        "Читал отзывы — половина негативных",
        "Попрошу скидку или уйду к конкурентам",
        "Хочу поговорить с руководителем, не с менеджером",
    ],
    "pragmatic": [
        "Стоимость услуг не окупится",
        "Можно разобраться самому через МФЦ",
        "Нет гарантий результата",
        "Сроки затянутся на годы",
        "Скрытые платежи и доплаты",
        "Конкуренты предлагают дешевле",
    ],
    "delegator": [
        "Не хочу вникать в детали, просто сделайте",
        "Жена/муж будет решать, мне некогда",
        "Позвоните позже, сейчас не удобно",
        "Перезвоню сам, когда буду готов",
        "Мне нужно посоветоваться с родственниками",
        "Пришлите всё на почту, я потом посмотрю",
    ],
    "know_it_all": [
        "Я сам юрист, знаю всё лучше вас",
        "Читал закон — там всё по-другому",
        "Ваша информация устарела",
        "Знакомый юрист сказал, что это не работает",
        "Вы не знаете последних изменений в законе",
        "Я проверю каждое ваше слово",
    ],
    "negotiator": [
        "Готов обсуждать, но на моих условиях",
        "Какие у вас есть варианты оплаты",
        "Конкуренты предлагают дешевле и быстрее",
        "Хочу встречу с юристом до оплаты",
        "Мне нужен индивидуальный подход",
        "Стандартные условия меня не устраивают",
    ],
    "shopper": [
        "Сейчас обзваниваю пять компаний",
        "У конкурентов дешевле на 30%",
        "Не буду решать сегодня — мне нужно сравнить",
        "А что входит в эту цену?",
        "Есть бесплатные консультации у других",
        "Скидку на второе обращение дадите?",
    ],
    "desperate": [
        "Мне конец, уже нечем платить",
        "Приставы придут на следующей неделе",
        "Не могу купить ребёнку еду",
        "Думал(а) о самом плохом",
        "Звонят каждый день, больше не могу",
        "Последний шанс — если не поможете, не знаю что делать",
    ],
    "crying": [
        "Не могу перестать плакать от стресса",
        "Ночью не сплю, думаю о долгах",
        "Дети видят, что мне плохо",
        "Чувствую себя полным неудачником",
        "Стыдно просить о помощи",
        "Муж/жена не знает, как мне плохо",
    ],
    "grateful": [
        "Так рад(а), что кто-то наконец помогает",
        "Спасибо что выслушали",
        "Надеюсь, вы действительно можете помочь",
        "Друг посоветовал — он вам доверяет",
        "Боюсь, что ожидания не оправдаются",
        "Готов(а) делать всё что скажете",
    ],
    "overwhelmed": [
        "Слишком много всего навалилось",
        "Не понимаю с чего начать",
        "Голова идёт кругом от информации",
        "Не могу сосредоточиться",
        "Забываю половину того что мне говорят",
        "Каждый день новая проблема",
    ],
    "returner": [
        "В прошлый раз не сложилось",
        "Поменял компанию — стало только хуже",
        "Боюсь, что опять потеряю время и деньги",
        "Уже слышал все обещания",
        "Хочу гарантий, что в этот раз получится",
        "Раньше другой менеджер обещал то же самое",
    ],
    "referred": [
        "Друг/подруга посоветовал(а) вашу компанию",
        "Знакомый сказал что помогли",
        "Пришёл по рекомендации, но всё равно осторожен",
        "Мне обещали индивидуальный подход",
        "Ожидаю такой же сервис, как рассказали",
        "Если обманете — весь офис узнает",
    ],
    "rushed": [
        "У меня пять минут, говорите быстро",
        "Я в машине, давайте по существу",
        "Перезвоните через час, сейчас совещание",
        "Быстро: сколько стоит и сколько по времени?",
        "Мне некогда ездить к вам в офис",
        "Можно всё сделать удалённо?",
    ],
    "lawyer_client": [
        "Мой юрист сказал что это не поможет",
        "Я проверю ваши слова у своего адвоката",
        "Знаю свои права — не надо мне рассказывать",
        "Какая у вас лицензия?",
        "Ваш управляющий в реестре ЕФРСБ?",
        "Покажите договор перед разговором",
    ],
    "couple": [
        "Муж/жена против банкротства",
        "Мы не можем договориться между собой",
        "Один хочет, другой нет",
        "А совместное имущество не пострадает?",
        "Супруг(а) боится больше меня",
        "Нам нужно обоим быть на консультации",
    ],
}

ARCHETYPE_SOFT_SPOTS: dict[str, list[str]] = {
    "skeptic":       ["Хочет защитить семью от приставов", "Устал от постоянных звонков коллекторов", "Боится потерять единственное жильё"],
    "anxious":       ["Не может спать из-за долгов", "Здоровье ухудшается от стресса", "Дети видят, как мама/папа плачет", "Боится оставить долги детям"],
    "passive":       ["Втайне надеется что кто-то поможет", "Устал нести груз один", "Мечтает начать жизнь с чистого листа"],
    "avoidant":      ["Хочет чтобы проблема исчезла", "Устал прятаться от звонков", "Тайно ищет решение"],
    "paranoid":      ["В глубине души хочет довериться", "Устал от постоянного напряжения", "Хочет найти «своего» специалиста"],
    "ashamed":       ["Хочет снять груз стыда", "Мечтает рассказать правду близким", "Готов на всё ради чистой совести"],
    "aggressive":    ["В глубине души боится за семью", "Хочет доказать что может решить проблему", "Злится на себя, а не на менеджера"],
    "hostile":       ["За маской злости — страх", "Когда-то кому-то доверял", "Хочет быть услышанным"],
    "blamer":        ["Хочет справедливости", "Устал быть жертвой обстоятельств", "Ищет союзника против системы"],
    "sarcastic":     ["За иронией — глубокая боль", "Ценит остроумных людей", "Уважает тех кто не обижается"],
    "manipulator":   ["Боится потери контроля", "Привык контролировать — хочет сохранить ощущение власти", "Уважает тех кого не может продавить"],
    "pragmatic":     ["Готов платить если увидит конкретный план", "Ценит экспертизу и цифры", "Хочет понять ROI от банкротства"],
    "delegator":     ["Перегружен проблемами", "Хочет чтобы кто-то взял ответственность", "Готов действовать если путь простой"],
    "know_it_all":   ["Хочет чтобы признали его экспертизу", "Уважает тех кто знает больше", "Боится выглядеть глупо"],
    "negotiator":    ["Хочет чувствовать что получил лучшую сделку", "Ценит гибкость", "Уважает профессионализм"],
    "shopper":       ["Ищет лучшее соотношение цена/качество", "Устал от сравнений", "Хочет наконец принять решение"],
    "desperate":     ["Любой шанс — последний", "Готов на всё ради семьи", "Хочет верить что выход есть"],
    "crying":        ["Хочет чтобы кто-то просто выслушал", "Нуждается в эмоциональной поддержке", "За слезами — сила"],
    "grateful":      ["Хочет отблагодарить тех кто помогает", "Ценит человеческое отношение", "Готов рекомендовать друзьям"],
    "overwhelmed":   ["Хочет простой пошаговый план", "Нуждается в структуре", "Благодарен за терпение"],
    "returner":      ["Хочет верить что в этот раз получится", "Знает чего не хочет", "Опыт — сила"],
    "referred":      ["Доверяет мнению друга", "Готов к действию", "Хочет подтвердить ожидания"],
    "rushed":        ["За спешкой — реальная проблема", "Ценит эффективность", "Уважает тех кто не тратит время"],
    "lawyer_client": ["Хочет профессионала одного уровня", "За критикой — уважение к знаниям", "Готов платить за экспертизу"],
    "couple":        ["Хотят сохранить семью", "За конфликтом — общая цель", "Нуждаются в медиаторе"],
}

ARCHETYPE_BREAKING_POINTS: dict[str, list[str]] = {
    "skeptic":       ["Покажите конкретное судебное решение", "Назовите точную статью закона", "Дайте письменную гарантию"],
    "anxious":       ["Пообещайте что звонки прекратятся", "Скажите что ситуация не безнадёжная", "Объясните пошагово"],
    "passive":       ["Предложите сделать первый шаг за меня", "Скажите что нужна одна подпись", "Покажите что другие справились"],
    "avoidant":      ["Минимум усилий с моей стороны", "Всё можно сделать удалённо", "Не нужно никуда ходить"],
    "paranoid":      ["Покажите лицензии и сертификаты", "Дайте номер дела для проверки", "Прозрачность на каждом этапе"],
    "ashamed":       ["Гарантируйте конфиденциальность", "Скажите что это нормально", "Никто не узнает"],
    "aggressive":    ["Не бойтесь моего напора", "Ответьте фактами", "Признайте моё право злиться"],
    "hostile":       ["Не сдавайтесь когда я ругаюсь", "Покажите реальные результаты", "Будьте честны до конца"],
    "blamer":        ["Согласитесь что система несправедлива", "Покажите как исправить", "Станьте союзником"],
    "sarcastic":     ["Отвечайте юмором", "Не обижайтесь", "Покажите что вы тоже человек"],
    "manipulator":   ["Не ведитесь на провокации", "Покажите что знаете больше", "VIP-условия"],
    "pragmatic":     ["Точные цифры экономии", "Сравнение стоимости vs продолжения выплат", "Чёткий таймлайн"],
    "delegator":     ["Одна подпись — и мы всё делаем", "Один визит решает всё", "Не нужно ничего изучать"],
    "know_it_all":   ["Процитируйте статью точнее чем я", "Покажите знание деталей", "Дайте новую информацию"],
    "negotiator":    ["Индивидуальные условия", "Гибкость в оплате", "Бонус за быстрое решение"],
    "shopper":       ["Лучшая цена с обоснованием", "Всё включено без доплат", "Гарантия возврата"],
    "desperate":     ["Скажите что выход есть", "Начните прямо сейчас", "Помогите с первым шагом бесплатно"],
    "crying":        ["Просто выслушайте", "Скажите что всё будет хорошо", "Дайте время прийти в себя"],
    "grateful":      ["Покажите конкретный план", "Объясните что ожидать", "Дайте контакт юриста"],
    "overwhelmed":   ["Разбейте на маленькие шаги", "Один шаг за раз", "Напомните позже"],
    "returner":      ["Объясните что изменилось с прошлого раза", "Гарантия результата", "Другой подход"],
    "referred":      ["Подтвердите отзыв друга", "Покажите аналогичное дело", "Персональный менеджер"],
    "rushed":        ["Уложитесь в 3 минуты", "Конкретные цифры без воды", "Всё удалённо"],
    "lawyer_client": ["Покажите экспертизу на моём уровне", "Знание последних поправок", "Реестр ЕФРСБ"],
    "couple":        ["Успокойте обоих", "Покажите что это общее решение", "Выгода для двоих"],
}


# ══════════════════════════════════════════════════════════════════════
#  Age Ranges, Trust, Resistance — ALL 25 archetypes
# ══════════════════════════════════════════════════════════════════════

AGE_RANGES: dict[str, tuple[int, int]] = {
    "skeptic": (35, 60), "anxious": (25, 55), "passive": (35, 65),
    "avoidant": (28, 50), "paranoid": (35, 60), "ashamed": (25, 55),
    "aggressive": (30, 55), "hostile": (30, 55), "blamer": (35, 60),
    "sarcastic": (28, 50), "manipulator": (35, 55), "pragmatic": (30, 50),
    "delegator": (28, 50), "know_it_all": (30, 55), "negotiator": (30, 50),
    "shopper": (25, 50), "desperate": (25, 65), "crying": (25, 60),
    "grateful": (30, 65), "overwhelmed": (30, 60), "returner": (30, 55),
    "referred": (25, 55), "rushed": (28, 50), "lawyer_client": (30, 55),
    "couple": (25, 55),
}

AGE_ADJUST_BY_CATEGORY: dict[str, tuple[int, int]] = {
    "pensioner": (55, 75), "military": (25, 50),
    "it_office": (23, 45), "homemaker": (25, 55),
}

TRUST_BASE: dict[str, int] = {
    "skeptic": 2, "anxious": 4, "passive": 5, "avoidant": 3,
    "paranoid": 1, "ashamed": 4, "aggressive": 2, "hostile": 1,
    "blamer": 2, "sarcastic": 3, "manipulator": 3, "pragmatic": 4,
    "delegator": 5, "know_it_all": 2, "negotiator": 4, "shopper": 3,
    "desperate": 6, "crying": 5, "grateful": 7, "overwhelmed": 4,
    "returner": 3, "referred": 6, "rushed": 3, "lawyer_client": 2,
    "couple": 4,
}

RESISTANCE_BASE: dict[str, int] = {
    "skeptic": 7, "anxious": 4, "passive": 3, "avoidant": 5,
    "paranoid": 8, "ashamed": 4, "aggressive": 8, "hostile": 9,
    "blamer": 6, "sarcastic": 6, "manipulator": 8, "pragmatic": 6,
    "delegator": 3, "know_it_all": 7, "negotiator": 6, "shopper": 5,
    "desperate": 2, "crying": 3, "grateful": 2, "overwhelmed": 4,
    "returner": 6, "referred": 4, "rushed": 5, "lawyer_client": 7,
    "couple": 5,
}

TRUST_MODIFIER: dict[str, int] = {
    "cold_base": -2, "website_form": 1, "referral": 2,
    "social_media": 0, "repeat_call": 0, "incoming": 2,
    "partner": 1, "chatbot": 1, "webinar": 2, "churned": -1,
}


# ══════════════════════════════════════════════════════════════════════
#  Family Status Generation
# ══════════════════════════════════════════════════════════════════════

FAMILY_STATUS_WEIGHTS: dict[str, list[tuple[str, int]]] = {
    # age_group → [(status, weight)]
    "young":  [("single", 40), ("married", 35), ("divorced", 15), ("civil_union", 10)],
    "middle": [("married", 40), ("divorced", 25), ("single", 15), ("civil_union", 10), ("widowed", 10)],
    "senior": [("married", 35), ("divorced", 20), ("widowed", 25), ("single", 10), ("civil_union", 10)],
}


# ══════════════════════════════════════════════════════════════════════
#  Financial Data
# ══════════════════════════════════════════════════════════════════════

CREDITOR_BANKS = [
    "Сбербанк", "ВТБ", "Тинькофф", "Альфа-Банк", "Газпромбанк",
    "Россельхозбанк", "Совкомбанк", "Промсвязьбанк", "Райффайзен", "Открытие",
]

MFO_NAMES = [
    "Займер", "МигКредит", "Быстроденьги", "Монеза", "Веббанкир", "SmartCredit",
]

INCOME_RANGES: dict[str, tuple[int, int, str]] = {
    "budget":        (25_000, 55_000, "official"),
    "government":    (35_000, 80_000, "official"),
    "military":      (40_000, 90_000, "official"),
    "pensioner":     (12_000, 25_000, "official"),
    "entrepreneur":  (30_000, 200_000, "mixed"),
    "worker":        (25_000, 60_000, "official"),
    "it_office":     (60_000, 250_000, "mixed"),
    "trade_service": (20_000, 80_000, "gray"),
    "homemaker":     (0, 0, "none"),
    "special":       (30_000, 100_000, "official"),
}

EDUCATION_BY_CATEGORY: dict[str, list[str]] = {
    "budget": ["высшее"], "government": ["высшее", "два высших"],
    "military": ["средне-специальное", "высшее"],
    "pensioner": ["средне-специальное", "высшее", "среднее"],
    "entrepreneur": ["высшее", "средне-специальное", "неоконченное высшее"],
    "worker": ["средне-специальное", "среднее", "ПТУ"],
    "it_office": ["высшее", "неоконченное высшее"],
    "trade_service": ["средне-специальное", "среднее", "высшее"],
    "homemaker": ["средне-специальное", "высшее", "среднее"],
    "special": ["высшее", "средне-специальное"],
}

# DTI (Debt-To-Income) ranges by archetype — desperate clients have higher DTI
_DTI_RANGES: dict[str, tuple[float, float]] = {
    "desperate":    (1.5, 2.5),
    "crying":       (1.3, 2.2),
    "overwhelmed":  (1.4, 2.3),
    "anxious":      (1.0, 1.8),
    "ashamed":      (0.8, 1.6),
    "pragmatic":    (0.5, 1.0),
    "know_it_all":  (0.4, 0.9),
    "negotiator":   (0.5, 1.1),
    "sarcastic":    (0.6, 1.3),
    "skeptic":      (0.6, 1.4),
}
DTI_MIN = 0.5  # fallback
DTI_MAX = 2.0  # fallback


def _get_dti_range(archetype_code: str) -> tuple[float, float]:
    """Get DTI range for archetype. Falls back to global default."""
    return _DTI_RANGES.get(archetype_code, (DTI_MIN, DTI_MAX))


# ══════════════════════════════════════════════════════════════════════
#  Personality Profile Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class PersonalityProfile:
    """OCEAN + PAD + human_factors + backstory_events."""
    ocean: dict[str, float] = field(default_factory=dict)
    pad: dict[str, float] = field(default_factory=dict)
    human_factors: list[str] = field(default_factory=list)
    factor_intensities: dict[str, float] = field(default_factory=dict)
    backstory_events: list[str] = field(default_factory=list)


@dataclass
class GeneratedProfile:
    """Complete generated client profile."""
    full_name: str = ""
    age: int = 30
    gender: str = "male"
    city: str = ""
    city_income_mult: float = 1.0
    archetype_code: str = "skeptic"
    family_status: str = "single"
    children_count: int = 0
    children_ages: list[int] = field(default_factory=list)
    education: str = "среднее"
    total_debt: int = 500_000
    creditors: list[dict] = field(default_factory=list)
    income: int | None = None
    income_type: str = "official"
    dti_ratio: float = 0.0
    property_list: list[dict] = field(default_factory=list)
    fears: list[str] = field(default_factory=list)
    soft_spot: str = ""
    breaking_point: str = ""
    trust_level: int = 5
    resistance_level: int = 5
    personality: PersonalityProfile = field(default_factory=PersonalityProfile)
    backstory_text: str = ""
    lead_source: str = "cold_base"


# ══════════════════════════════════════════════════════════════════════
#  Core Generation Functions
# ══════════════════════════════════════════════════════════════════════

def generate_personality_profile(
    archetype_code: str,
    difficulty: int,
) -> PersonalityProfile:
    """Generate OCEAN, PAD, human_factors, backstory_events for archetype."""

    # 1) OCEAN with ±0.15 noise
    ocean_anchor = ARCHETYPE_OCEAN.get(archetype_code, ARCHETYPE_OCEAN["skeptic"])
    ocean = {}
    for dim, val in ocean_anchor.items():
        noised = val + random.uniform(-0.15, 0.15)
        ocean[dim] = round(max(0.0, min(1.0, noised)), 3)

    # 2) PAD with ±0.1 noise
    pad_anchor = ARCHETYPE_PAD.get(archetype_code, ARCHETYPE_PAD["skeptic"])
    pad = {}
    for dim, val in pad_anchor.items():
        noised = val + random.uniform(-0.1, 0.1)
        pad[dim] = round(max(-1.0, min(1.0, noised)), 3)

    # 3) Human factors by difficulty
    if difficulty <= 3:
        num_factors = 3
        intensity_range = (0.3, 0.6)
    elif difficulty <= 7:
        num_factors = random.randint(4, 5)
        intensity_range = (0.4, 0.7)
    else:
        num_factors = random.randint(6, 7)
        intensity_range = (0.6, 0.9)

    # Weight selection by archetype affinity
    weights = []
    for f in HUMAN_FACTORS:
        if archetype_code in f["archetype_affinity"]:
            weights.append(3.0)
        else:
            weights.append(1.0)

    chosen_factors = []
    chosen_indices = set()
    for _ in range(min(num_factors, len(HUMAN_FACTORS))):
        adjusted = [w if i not in chosen_indices else 0.0 for i, w in enumerate(weights)]
        total = sum(adjusted)
        if total == 0:
            break
        probs = [w / total for w in adjusted]
        idx = random.choices(range(len(HUMAN_FACTORS)), weights=probs, k=1)[0]
        chosen_indices.add(idx)
        chosen_factors.append(HUMAN_FACTORS[idx]["code"])

    intensities = {f: round(random.uniform(*intensity_range), 2) for f in chosen_factors}

    # 4) Backstory events (1-3 based on difficulty)
    num_events = 1 if difficulty <= 4 else (2 if difficulty <= 7 else 3)
    compatible = [e for e in BACKSTORY_EVENTS if archetype_code in e.compatible_archetypes]
    if not compatible:
        compatible = BACKSTORY_EVENTS[:5]
    events = random.sample(compatible, min(num_events, len(compatible)))
    event_codes = [e.code for e in events]

    return PersonalityProfile(
        ocean=ocean,
        pad=pad,
        human_factors=chosen_factors,
        factor_intensities=intensities,
        backstory_events=event_codes,
    )


def assign_human_factors(archetype_code: str, difficulty: int) -> list[dict]:
    """Standalone function returning human factors with intensities.

    Used by Game Director for Factor Activation Engine.
    """
    profile = generate_personality_profile(archetype_code, difficulty)
    return [
        {"code": f, "intensity": profile.factor_intensities.get(f, 0.5)}
        for f in profile.human_factors
    ]


# ══════════════════════════════════════════════════════════════════════
#  Identity Generation
# ══════════════════════════════════════════════════════════════════════

def _generate_name(gender: str) -> str:
    if gender == "female":
        return f"{random.choice(SURNAMES_FEMALE)} {random.choice(FEMALE_NAMES)}"
    return f"{random.choice(SURNAMES_MALE)} {random.choice(MALE_NAMES)}"


def _generate_age(archetype: str, profession_category: str | None) -> int:
    lo, hi = AGE_RANGES.get(archetype, (30, 55))
    if profession_category and profession_category in AGE_ADJUST_BY_CATEGORY:
        cat_lo, cat_hi = AGE_ADJUST_BY_CATEGORY[profession_category]
        lo, hi = max(lo, cat_lo), min(hi, cat_hi)
        if lo > hi:
            lo, hi = cat_lo, cat_hi
    return random.randint(lo, hi)


def _pick_city() -> dict:
    return random.choice(CITIES)


def _generate_family(age: int, archetype: str) -> tuple[str, int, list[int]]:
    """Generate family_status, children_count, children_ages."""
    if age < 30:
        group = "young"
    elif age < 50:
        group = "middle"
    else:
        group = "senior"

    statuses, weights = zip(*FAMILY_STATUS_WEIGHTS[group])
    family_status = random.choices(statuses, weights=weights, k=1)[0]

    # Children
    if family_status == "single" and age < 30:
        children = 0
    elif family_status in ("married", "divorced", "widowed", "civil_union"):
        if age < 28:
            children = random.choices([0, 1], weights=[60, 40], k=1)[0]
        elif age < 40:
            children = random.choices([0, 1, 2], weights=[15, 45, 40], k=1)[0]
        else:
            children = random.choices([0, 1, 2, 3], weights=[10, 30, 40, 20], k=1)[0]
    else:
        children = random.choices([0, 1], weights=[70, 30], k=1)[0]

    # Couple archetype: always has partner
    if archetype == "couple" and family_status == "single":
        family_status = "married"

    children_ages = sorted([
        random.randint(1, max(1, age - 20))
        for _ in range(children)
    ], reverse=True) if children > 0 else []

    return family_status, children, children_ages


# ══════════════════════════════════════════════════════════════════════
#  Financial Generation with DTI Validation
# ══════════════════════════════════════════════════════════════════════

def _generate_income(category: str, age: int, income_mult: float) -> tuple[int | None, str]:
    lo, hi, income_type = INCOME_RANGES.get(category, (25_000, 60_000, "official"))

    if lo == 0 and hi == 0:
        if random.random() < 0.3:
            return int(random.randint(10_000, 25_000) * income_mult), "gray"
        return None, "none"

    income = random.randint(lo, hi)
    income = round(income / 1_000) * 1_000

    if age > 45 and category in ("budget", "government"):
        income = int(income * random.uniform(1.05, 1.2))

    income = int(income * income_mult)
    return income, income_type


def _generate_creditors(total_debt: int) -> list[dict]:
    num = random.choices([1, 2, 3, 4, 5], weights=[10, 30, 30, 20, 10])[0]
    has_mfo = random.random() < 0.3 + (num * 0.1)

    banks = random.sample(CREDITOR_BANKS, min(num, len(CREDITOR_BANKS)))
    if has_mfo and num >= 2:
        num_mfo = random.randint(1, min(2, num - 1))
        banks = banks[:num - num_mfo]
        mfos = random.sample(MFO_NAMES, min(num_mfo, len(MFO_NAMES)))
        names = banks + mfos
    else:
        names = banks[:num]

    remaining = total_debt
    creditors = []
    for i, name in enumerate(names):
        if i == len(names) - 1:
            amount = remaining
        else:
            share = random.uniform(0.15, 0.50)
            amount = max(10_000, round(int(remaining * share) / 1_000) * 1_000)

        remaining -= amount
        if remaining < 0:
            amount += remaining
            remaining = 0
        creditors.append({"name": name, "amount": max(amount, 10_000)})

    return creditors


def _generate_debt_with_dti(
    profession_category: str,
    age: int,
    income: int | None,
    debt_min: int = 200_000,
    debt_max: int = 2_000_000,
    archetype_code: str = "",
) -> tuple[int, int | None]:
    """Generate debt ensuring DTI ratio is realistic per archetype.

    DTI ranges are archetype-specific (desperate=1.5-2.5, pragmatic=0.5-1.0).
    Returns (total_debt, adjusted_income).
    """
    dti_min, dti_max = _get_dti_range(archetype_code)
    total_debt = round(random.randint(debt_min, debt_max) / 10_000) * 10_000

    if income and income > 0:
        monthly_payment = total_debt / 36
        dti = monthly_payment / income

        if dti < dti_min:
            min_payment = income * dti_min
            total_debt = int(min_payment * 36)
            total_debt = round(total_debt / 10_000) * 10_000
        elif dti > dti_max:
            max_payment = income * dti_max
            total_debt = int(max_payment * 36)
            total_debt = round(total_debt / 10_000) * 10_000

    return total_debt, income


# ══════════════════════════════════════════════════════════════════════
#  Uniqueness Check (Redis-based)
# ══════════════════════════════════════════════════════════════════════

def _compute_profile_hash(
    archetype: str,
    profession_cat: str,
    factors: list[str],
    city: str,
    gender: str,
    age_decade: int,
) -> str:
    """Compute hash for uniqueness checking."""
    top3 = sorted(factors[:3])
    key = f"{archetype}:{profession_cat}:{':'.join(top3)}:{city}:{gender}:{age_decade}"
    return hashlib.md5(key.encode()).hexdigest()


async def _check_uniqueness(
    redis_client: Any,
    profile_hash: str,
    ttl_days: int = 30,
) -> bool:
    """Check if profile hash exists in Redis SET. Returns True if unique."""
    if redis_client is None:
        return True

    key = "hunter888:profile_hashes"
    exists = await redis_client.sismember(key, profile_hash)
    if exists:
        return False

    await redis_client.sadd(key, profile_hash)
    await redis_client.expire(key, ttl_days * 86400)
    return True


# ══════════════════════════════════════════════════════════════════════
#  Archetype Filtering by Manager Level
# ══════════════════════════════════════════════════════════════════════

def get_available_archetypes(manager_level: int) -> list[str]:
    """Return archetypes unlocked at this manager level."""
    return [
        code for code, min_level in ARCHETYPE_LEVEL_TIERS.items()
        if min_level <= manager_level
    ]


# ══════════════════════════════════════════════════════════════════════
#  LLM Backstory Generation
# ══════════════════════════════════════════════════════════════════════

LLM_BACKSTORY_PROMPT = """Создай краткую (3-4 предложения) жизненную историю клиента банкротства.

Имя: {name}
Возраст: {age} лет, город: {city}
Профессия: {profession}
Семья: {family}
Общий долг: {debt:,} руб ({creditors})
Жизненные обстоятельства: {events}
Характер: {traits}

Требования:
- Разговорный стиль, от третьего лица
- История должна быть связной
- Объясни КАК дошёл до долгов
- Не упоминай банкротство напрямую
- 3-4 предложения максимум"""


def generate_template_backstory(profile: GeneratedProfile) -> str:
    """Fallback шаблонная генерация если LLM недоступен."""
    parts = []

    parts.append(f"{profile.full_name}, {profile.age} лет, {profile.city}.")

    if profile.family_status == "married":
        child_text = f", {'есть дети' if profile.children_count > 0 else 'без детей'}"
        parts.append(f"В браке{child_text}.")
    elif profile.family_status == "divorced":
        parts.append("В разводе.")
    elif profile.family_status == "single":
        parts.append("Не в браке.")

    debt_k = profile.total_debt // 1000
    creditor_names = ", ".join([c["name"] for c in profile.creditors[:3]])
    parts.append(f"Общий долг {debt_k} тыс. руб. ({creditor_names}).")

    if profile.personality.backstory_events:
        event = BACKSTORY_EVENT_MAP.get(profile.personality.backstory_events[0])
        if event:
            parts.append(event.description_template.format(
                months_ago=random.randint(2, 12)
            ))

    return " ".join(parts)


async def generate_llm_backstory(
    profile: GeneratedProfile,
    llm_fn: Any = None,
) -> str:
    """Generate backstory via LLM with template fallback."""
    if llm_fn is None:
        return generate_template_backstory(profile)

    events_text = ", ".join([
        BACKSTORY_EVENT_MAP[e].name_ru
        for e in profile.personality.backstory_events
        if e in BACKSTORY_EVENT_MAP
    ])
    traits_text = ", ".join([
        HUMAN_FACTOR_MAP[f]["name_ru"]
        for f in profile.personality.human_factors
        if f in HUMAN_FACTOR_MAP
    ])

    creditor_names = ", ".join([c["name"] for c in profile.creditors[:3]])

    family_text = profile.family_status
    if profile.children_count > 0:
        family_text += f", {profile.children_count} детей"

    prompt = LLM_BACKSTORY_PROMPT.format(
        name=profile.full_name,
        age=profile.age,
        city=profile.city,
        profession="",  # filled from DB at runtime
        family=family_text,
        debt=profile.total_debt,
        creditors=creditor_names,
        events=events_text or "нет особых",
        traits=traits_text or "стандартные",
    )

    try:
        backstory = await llm_fn(prompt)
        return backstory.strip()
    except Exception as e:
        logger.warning("LLM backstory failed: %s, using template", e)
        return generate_template_backstory(profile)


# ══════════════════════════════════════════════════════════════════════
#  Main Generation Function
# ══════════════════════════════════════════════════════════════════════

async def generate_client(
    archetype_code: str,
    difficulty: int,
    profession_category: str = "worker",
    debt_min: int = 200_000,
    debt_max: int = 2_000_000,
    manager_level: int = 1,
    lead_source: str = "cold_base",
    redis_client: Any = None,
    llm_fn: Any = None,
) -> GeneratedProfile:
    """Generate a complete client profile.

    Args:
        archetype_code: One of 25 canonical archetype codes.
        difficulty: 1-10 effective difficulty.
        profession_category: From ProfessionCategory enum.
        debt_min/debt_max: Debt range from profession profile.
        manager_level: 1-20 for archetype filtering.
        lead_source: Lead source code.
        redis_client: Optional Redis for uniqueness checking.
        llm_fn: Optional async callable for backstory generation.

    Returns:
        GeneratedProfile with all fields populated.
    """

    # Validate archetype against manager level
    available = get_available_archetypes(manager_level)
    if archetype_code not in available:
        archetype_code = random.choice(available)
        logger.info("Archetype %s not unlocked at level %d, using %s",
                     archetype_code, manager_level, archetype_code)

    # 1) Identity
    gender = random.choice(["male", "female"])
    full_name = _generate_name(gender)
    age = _generate_age(archetype_code, profession_category)
    city_data = _pick_city()

    # 2) Family
    family_status, children_count, children_ages = _generate_family(age, archetype_code)

    # 3) Income (with regional multiplier)
    income, income_type = _generate_income(
        profession_category, age, city_data["income_mult"]
    )

    # 4) Debt with DTI validation (archetype-specific ranges)
    total_debt, income = _generate_debt_with_dti(
        profession_category, age, income, debt_min, debt_max,
        archetype_code=archetype_code,
    )
    creditors = _generate_creditors(total_debt)

    # 5) DTI ratio
    dti = 0.0
    if income and income > 0:
        dti = round((total_debt / 36) / income, 2)

    # 6) Personality profile
    personality = generate_personality_profile(archetype_code, difficulty)

    # 7) Fears, soft_spot, breaking_point
    archetype_fears = ARCHETYPE_FEARS.get(archetype_code, ARCHETYPE_FEARS["skeptic"])
    fears = random.sample(archetype_fears, min(random.randint(2, 4), len(archetype_fears)))

    soft_spots = ARCHETYPE_SOFT_SPOTS.get(archetype_code, ["Хочет решить проблему"])
    soft_spot = random.choice(soft_spots)
    if age >= 55 and random.random() < 0.4:
        soft_spot += ". Переживает за внуков."
    elif children_count > 0 and random.random() < 0.5:
        soft_spot += f". Боится за будущее {'ребёнка' if children_count == 1 else 'детей'}."

    breaking_points = ARCHETYPE_BREAKING_POINTS.get(archetype_code, ["Покажите результат"])
    breaking_point = random.choice(breaking_points)

    # 8) Trust & resistance (with contextual modifiers)
    from datetime import datetime
    hour = datetime.now().hour
    # Evening calls (18-21) get slight trust boost, early morning (7-9) slight penalty
    time_modifier = 1 if 18 <= hour <= 21 else (-1 if 7 <= hour <= 9 else 0)
    # Higher difficulty = lower baseline trust
    difficulty_trust_penalty = -1 if difficulty >= 8 else 0

    trust = max(1, min(10,
        TRUST_BASE.get(archetype_code, 3)
        + TRUST_MODIFIER.get(lead_source, 0)
        + time_modifier
        + difficulty_trust_penalty
    ))
    resistance_base = RESISTANCE_BASE.get(archetype_code, 5)
    resistance_mult = 0.8 + (difficulty / 10) * 0.4
    resistance = max(1, min(10, int(resistance_base * resistance_mult) + random.randint(-1, 1)))

    # 9) Education
    education = random.choice(EDUCATION_BY_CATEGORY.get(profession_category, ["среднее"]))

    profile = GeneratedProfile(
        full_name=full_name,
        age=age,
        gender=gender,
        city=city_data["name"],
        city_income_mult=city_data["income_mult"],
        archetype_code=archetype_code,
        family_status=family_status,
        children_count=children_count,
        children_ages=children_ages,
        education=education,
        total_debt=total_debt,
        creditors=creditors,
        income=income,
        income_type=income_type,
        dti_ratio=dti,
        fears=fears,
        soft_spot=soft_spot,
        breaking_point=breaking_point,
        trust_level=trust,
        resistance_level=resistance,
        personality=personality,
        lead_source=lead_source,
    )

    # 10) Uniqueness check (up to 5 retries)
    if redis_client:
        age_decade = (age // 10) * 10
        for attempt in range(5):
            h = _compute_profile_hash(
                archetype_code, profession_category,
                personality.human_factors, city_data["name"],
                gender, age_decade,
            )
            if await _check_uniqueness(redis_client, h):
                break
            # Regenerate varying elements
            city_data = _pick_city()
            profile.city = city_data["name"]
            profile.city_income_mult = city_data["income_mult"]
            gender = random.choice(["male", "female"])
            profile.gender = gender
            profile.full_name = _generate_name(gender)
            personality = generate_personality_profile(archetype_code, difficulty)
            profile.personality = personality
            if attempt == 4:
                logger.warning("Uniqueness check exhausted 5 retries for %s", archetype_code)

    # 11) Backstory
    profile.backstory_text = await generate_llm_backstory(profile, llm_fn)

    return profile


# ══════════════════════════════════════════════════════════════════════
#  Adapter functions (bridge GeneratedProfile → DB ClientProfile)
# ══════════════════════════════════════════════════════════════════════


async def generate_client_profile(
    *,
    session_id: uuid.UUID,
    scenario,
    character,
    difficulty: int = 5,
    db,
    custom_archetype: str | None = None,
    custom_profession: str | None = None,
    custom_lead_source: str | None = None,
):
    """Generate a full client profile and persist it to the database.

    This is the adapter that the WebSocket training handler calls.
    It calls generate_client() to get a GeneratedProfile dataclass,
    then creates a ClientProfile ORM row in the DB.

    Returns:
        ClientProfile ORM instance (persisted, flushed but not committed).
    """
    from app.models.roleplay import ClientProfile

    archetype_code = custom_archetype or (character.slug if character else "skeptic")
    profession_category = custom_profession or "worker"
    lead_source = custom_lead_source or "cold_base"

    gen = await generate_client(
        archetype_code=archetype_code,
        difficulty=difficulty,
        profession_category=profession_category,
        lead_source=lead_source,
    )

    profile = ClientProfile(
        session_id=session_id,
        full_name=gen.full_name,
        age=gen.age,
        gender=gen.gender,
        city=gen.city,
        archetype_code=gen.archetype_code,
        education_level=gen.education,
        total_debt=gen.total_debt,
        creditors=gen.creditors,
        income=gen.income,
        income_type=gen.income_type,
        fears=gen.fears,
        soft_spot=gen.soft_spot,
        breaking_point=gen.breaking_point,
        trust_level=gen.trust_level,
        resistance_level=gen.resistance_level,
        lead_source=gen.lead_source,
    )
    db.add(profile)
    await db.flush()

    return profile


def get_crm_card(profile) -> dict:
    """Build a CRM card dict from a ClientProfile or GeneratedProfile.

    This is the information shown to the manager in the left panel
    during training. Intentionally limited -- no hidden data.
    """
    creditors = getattr(profile, "creditors", []) or []
    creditor_names = [c.get("name", "Кредитор") if isinstance(c, dict) else str(c) for c in creditors[:5]]

    return {
        "name": getattr(profile, "full_name", "Клиент"),
        "age": getattr(profile, "age", 30),
        "city": getattr(profile, "city", ""),
        "total_debt": getattr(profile, "total_debt", 0),
        "creditors_count": len(creditors),
        "creditor_names": creditor_names,
        "income": getattr(profile, "income", None),
        "income_type": getattr(profile, "income_type", ""),
        "lead_source": getattr(profile, "lead_source", "cold_base"),
        "trust_level": getattr(profile, "trust_level", 5),
    }


def get_full_reveal_card(profile) -> dict:
    """Build a full reveal card for post-session results.

    Shows everything including hidden data that the manager
    did not see during the call (fears, soft spots, breaking point).
    """
    base = get_crm_card(profile)
    base.update({
        "fears": getattr(profile, "fears", []) or [],
        "soft_spot": getattr(profile, "soft_spot", ""),
        "breaking_point": getattr(profile, "breaking_point", ""),
        "resistance_level": getattr(profile, "resistance_level", 5),
        "archetype_code": getattr(profile, "archetype_code", ""),
        "gender": getattr(profile, "gender", ""),
    })
    return base
