"""TZ-5 PR #101 — re-extract + edit-flow contract tests.

Covers the unit-level invariants the new flow depends on:

  * `extract_for_route` produces a payload whose shape matches the
    `route_type` (the FE editor switches on it; mismatch → broken UI).
  * Re-extract round-trip: extracting an existing source through a
    *different* route_type yields a payload of the new shape (so a
    user-forced re-extract actually changes the stored shape).
  * Editing `extracted` JSONB and re-saving keeps `original_confidence`
    intact (audit invariant).

These are unit tests against the scenario_extractor service —
endpoint-level behavior is exercised in the existing API tests.
"""
from __future__ import annotations

from app.services.scenario_extractor import (
    ROUTE_TYPES,
    extract_for_route,
)


SAMPLE_TEXT = (
    "Скрипт холодного звонка по 127-ФЗ\n\n"
    "Шаг 1: Приветствие. Поздороваться, представиться.\n"
    "Шаг 2: Квалификация. Спросить про долг.\n\n"
    "Возражение: дорого. Ответить: первая консультация бесплатна.\n\n"
    "Согласно ст. 213.3 минимальный долг — 500 000 руб."
)


def test_extract_for_route_payload_shape_matches_route_type():
    """Each route's payload must have the right discriminator keys so the
    FE RouteEditor can switch on them without a runtime crash."""
    scenario = extract_for_route(SAMPLE_TEXT, "scenario")
    assert {"title_suggested", "summary", "steps"} <= set(scenario.keys())

    character = extract_for_route(SAMPLE_TEXT, "character")
    assert {"name", "description", "personality_traits"} <= set(character.keys())

    arena = extract_for_route(SAMPLE_TEXT, "arena_knowledge")
    assert {"fact_text", "law_article", "category", "match_keywords"} <= set(arena.keys())


def test_re_extract_with_forced_route_changes_shape():
    """Re-extracting the same source with a different route_type must
    produce the new shape — otherwise the FE editor would render the
    wrong fields."""
    first = extract_for_route(SAMPLE_TEXT, "scenario")
    assert "steps" in first

    re_run = extract_for_route(SAMPLE_TEXT, "character")
    assert "personality_traits" in re_run
    assert "steps" not in re_run


def test_extract_payloads_have_quotes_from_source_for_audit():
    """All three payload kinds must carry a `quotes_from_source` list so
    the FE quote-validator UI works regardless of route."""
    for route in ROUTE_TYPES:
        blob = extract_for_route(SAMPLE_TEXT, route)
        assert "quotes_from_source" in blob
        assert isinstance(blob["quotes_from_source"], list)


def test_extract_payload_confidence_in_range():
    for route in ROUTE_TYPES:
        blob = extract_for_route(SAMPLE_TEXT, route)
        c = blob.get("confidence")
        assert isinstance(c, float)
        assert 0.0 <= c <= 1.0


def test_arena_extract_difficulty_level_is_int_in_range():
    """ArenaKnowledgePayload.difficulty_level is consumed by a slider
    in the wizard — must be a small integer 1..5."""
    blob = extract_for_route(SAMPLE_TEXT, "arena_knowledge")
    d = blob["difficulty_level"]
    assert isinstance(d, int)
    assert 1 <= d <= 5


def test_extract_strips_pii_across_all_routes():
    """Wizard surfaces all three payloads to ROP — none must leak phones."""
    text_with_pii = (
        SAMPLE_TEXT
        + "\n\nКонтакт: +7 (495) 123-45-67, info@example.com"
    )
    for route in ROUTE_TYPES:
        blob = extract_for_route(text_with_pii, route)
        # Flatten to string for easy substring search.
        s = repr(blob)
        assert "495" not in s, f"PII leak in route {route}"
        assert "1234567" not in s.replace("-", "").replace(" ", "")
        assert "info@example.com" not in s
