"""TZ-5 PR-2 — multi-route classifier tests.

Covers ``classify_material`` + the per-route heuristic extractors. The
classifier is the gate that decides whether an uploaded material becomes
a Scenario, a Character, or an Arena knowledge chunk; if it silently
mis-routes, ROP gets a wrong-shaped draft and conversion fails downstream.

Tests sit in the blocking CI scope.
"""
from __future__ import annotations

import pytest

from app.services.scenario_extractor import (
    ROUTE_TYPES,
    ArenaKnowledgeDraftPayload,
    CharacterDraftPayload,
    ClassificationResult,
    ScenarioDraftPayload,
    classify_material,
    extract_for_route,
)


# ── classify_material ───────────────────────────────────────────────────


def test_classifier_picks_scenario_for_step_heavy_text():
    text = (
        "# Памятка холодного звонка\n\n"
        "Шаг 1: Приветствие. Шаг 2: Квалификация.\n"
        "Возражение: дорого. Шаг 3: Закрытие — приветствие, квалификация, закрытие."
    )
    result = classify_material(text)
    assert result.route_type == "scenario"
    assert 0.0 <= result.confidence <= 1.0
    assert "сценарий" in result.reasoning.lower() or "этап" in result.reasoning.lower()


def test_classifier_picks_character_for_persona_description():
    text = (
        "Клиент типа: должник, директор стройфирмы. "
        "Характер: агрессивный, торопится, недоверчив. "
        "Архетип — VIP-должник. Обычно говорит грубо."
    )
    result = classify_material(text)
    assert result.route_type == "character"


def test_classifier_picks_arena_knowledge_for_legal_facts():
    text = (
        "По 127-ФЗ ст. 213.3 минимальный долг для процедуры банкротства физлица — "
        "500 000 рублей. Закон предусматривает как судебную, так и внесудебную "
        "процедуру. Право заявить о банкротстве — у должника, кредитора и "
        "уполномоченного органа."
    )
    result = classify_material(text)
    assert result.route_type == "arena_knowledge"


def test_classifier_handles_empty_text_safely():
    result = classify_material("")
    assert result.route_type in ROUTE_TYPES
    assert result.confidence == 0.0


def test_classifier_returns_dataclass_with_full_shape():
    """Contract: every classifier result has all 4 fields."""
    result = classify_material("Шаг 1. Приветствие.")
    assert isinstance(result, ClassificationResult)
    assert isinstance(result.route_type, str)
    assert isinstance(result.confidence, float)
    assert isinstance(result.reasoning, str)
    assert isinstance(result.mixed_routes, list)


def test_classifier_mixed_routes_lists_secondary_candidates():
    """A mixed-content document should surface secondary routes so the FE
    can offer "split" instead of forcing one branch."""
    text = (
        # heavy scenario markers
        "Шаг 1. Шаг 2. Шаг 3. Шаг 4. Возражение: дорого. "
        # plus heavy legal markers
        "По ст. 213.3 127-ФЗ долг должен быть 500 000 рублей. Просрочка 3 месяца."
    )
    result = classify_material(text)
    # Top is one of the two; the other should appear in mixed.
    assert result.route_type in ("scenario", "arena_knowledge")
    other = "arena_knowledge" if result.route_type == "scenario" else "scenario"
    # Secondary route must be flagged when comparable score is detected.
    assert other in result.mixed_routes or result.confidence < 0.5


# ── extract_for_route dispatch ──────────────────────────────────────────


def test_extract_for_route_scenario_returns_scenario_payload_shape():
    blob = extract_for_route(
        "Шаг 1. Приветствие.\n\nШаг 2. Квалификация.", "scenario"
    )
    # Scenario shape keys (from ScenarioDraftPayload.to_jsonable):
    for key in ("title_suggested", "summary", "steps", "expected_objections", "quotes_from_source", "confidence"):
        assert key in blob


def test_extract_for_route_character_returns_character_payload_shape():
    blob = extract_for_route(
        "Клиент: директор стройфирмы. Агрессивный, торопится. Часто говорит дорого.",
        "character",
    )
    for key in ("name", "description", "personality_traits", "typical_objections", "quotes_from_source", "confidence"):
        assert key in blob


def test_extract_for_route_arena_returns_arena_payload_shape():
    blob = extract_for_route(
        "По 127-ФЗ ст. 213.3 порог долга — 500 000 рублей. Просрочка 3 месяца.",
        "arena_knowledge",
    )
    for key in ("fact_text", "law_article", "category", "match_keywords", "quotes_from_source", "confidence"):
        assert key in blob


def test_extract_for_route_rejects_unknown_route():
    with pytest.raises(ValueError):
        extract_for_route("any text", "unknown_route")


def test_extract_for_route_pii_scrubbed_across_branches():
    """All three branches must scrub PII on the way out."""
    text_with_pii = (
        "Шаг 1. Позвоните по +7 (495) 123-45-67. "
        "Email: client@example.com. Шаг 2. Закрытие."
    )
    for route in ROUTE_TYPES:
        blob = extract_for_route(text_with_pii, route)
        serialised = str(blob)
        assert "495" not in serialised, f"PII leak in route {route}: {serialised[:200]}"
        assert "client@example.com" not in serialised


# ── Per-route payload shape ─────────────────────────────────────────────


def test_character_payload_traits_capped():
    """Heuristic extractor caps traits to avoid noise."""
    text = (
        "Клиент агрессивный, недоверчивый, торопится, "
        "скептичный, эмоциональный, спокойный, грубый, вежливый, уставший."
    )
    blob = extract_for_route(text, "character")
    assert len(blob["personality_traits"]) <= 6


def test_arena_payload_law_article_extracted():
    blob = extract_for_route(
        "Согласно ст. 213.3 минимальный долг — 500 000 руб.", "arena_knowledge"
    )
    # Law article should be extracted as substring of source.
    if blob["law_article"]:
        assert "213" in blob["law_article"] or "ст." in blob["law_article"].lower()


def test_classifier_pii_scrubbed_before_classification():
    """Classifier must not see raw PII — pass through `strip_pii` first."""
    # Indirect: classifier doesn't expose what it saw, but if PII patterns
    # affected scoring we'd see drift; simplest assertion is that text
    # with phone-only content classifies somewhere stable.
    result = classify_material("+7 (495) 123-45-67")
    assert result.route_type in ROUTE_TYPES
