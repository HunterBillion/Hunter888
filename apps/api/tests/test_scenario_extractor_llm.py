"""TZ-5 PR #102 — LLM extractor unit tests (mocked Claude responses).

Validates the LLM path of the input funnel:
  * `llm_classify_material` parses Haiku JSON → ClassificationResult
  * `llm_extract_for_route` parses Sonnet JSON → JSONB-ready dict
  * On API failure (no key, exception, malformed JSON) we fall back to
    the heuristic floor — callers never see an exception.
  * PII scrub still runs on outputs even when LLM did its own scrubbing.
  * Quote validator drops hallucinated cites and penalises confidence.
  * Kill-switch `TZ5_LLM_ENABLED=0` forces heuristic.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.scenario_extractor import (
    ClassificationResult,
    ROUTE_TYPES,
)
from app.services.scenario_extractor_llm import (
    _safe_json,
    _scrub_payload_dict,
    _truncate_for_llm,
    _validate_quotes_via_llm,
    llm_classify_material,
    llm_extract_for_route,
)


def _navy_response(text: str) -> SimpleNamespace:
    """Build the minimal OpenAI-compatible shape that
    `_get_local_client().chat.completions.create` returns: an object
    with `.choices[0].message.content`. Used by the navy proxy + the
    OpenAI SDK that wraps it.
    """
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
    )


def _navy_settings() -> SimpleNamespace:
    """Stub `settings` so `_llm_enabled` returns True (navy proxy
    configured) without touching the real env."""
    return SimpleNamespace(
        local_llm_enabled=True,
        local_llm_url="https://api.navy/v1",
        local_llm_api_key="sk-navy-test",
        tz5_classifier_model="gemini-3.1-pro-preview",
        tz5_extractor_model="gpt-5.4",
    )


def _navy_settings_no_key() -> SimpleNamespace:
    """`local_llm_enabled=False` → `_llm_enabled()` returns False →
    heuristic fallback path is taken."""
    return SimpleNamespace(
        local_llm_enabled=False,
        local_llm_url="",
        local_llm_api_key="",
        tz5_classifier_model="gemini-3.1-pro-preview",
        tz5_extractor_model="gpt-5.4",
    )



# ── Kill-switch + missing-key fallback ──────────────────────────────────


@pytest.mark.asyncio
async def test_llm_classify_falls_back_when_kill_switch_set(monkeypatch):
    """`TZ5_LLM_ENABLED=0` forces the heuristic regardless of API key."""
    monkeypatch.setenv("TZ5_LLM_ENABLED", "0")
    result = await llm_classify_material(
        "Шаг 1: Приветствие. Шаг 2: Квалификация."
    )
    assert isinstance(result, ClassificationResult)
    assert result.route_type in ROUTE_TYPES
    # Heuristic confidence caps at 0.55.
    assert result.confidence <= 0.55


@pytest.mark.asyncio
async def test_llm_classify_falls_back_when_no_api_key(monkeypatch):
    monkeypatch.setattr(
        "app.services.scenario_extractor_llm.settings",
        _navy_settings_no_key(),
    )
    result = await llm_classify_material("Шаг 1: Приветствие.")
    assert result.confidence <= 0.55


# ── Happy path: LLM classifier returns valid JSON ───────────────────────


@pytest.mark.asyncio
async def test_llm_classify_parses_haiku_response(monkeypatch):
    monkeypatch.setattr(
        "app.services.scenario_extractor_llm.settings",
        _navy_settings(),
    )
    monkeypatch.setenv("TZ5_LLM_ENABLED", "1")
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=AsyncMock(return_value=_navy_response(
            json.dumps({
                "route_type": "character",
                "confidence": 0.92,
                "reasoning": "описание типажа должника",
                "mixed_routes": [],
            })
    )))
    ))
    with patch(
        "app.services.llm._get_local_client",
        return_value=fake_client,
    ):
        result = await llm_classify_material("Клиент типа: агрессивный должник.")
    assert result.route_type == "character"
    assert result.confidence == 0.92
    assert "должник" in result.reasoning.lower()


@pytest.mark.asyncio
async def test_llm_classify_falls_back_on_malformed_json(monkeypatch):
    """LLM returned text but not JSON → heuristic fallback."""
    monkeypatch.setattr(
        "app.services.scenario_extractor_llm.settings",
        _navy_settings(),
    )
    monkeypatch.setenv("TZ5_LLM_ENABLED", "1")
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=AsyncMock(return_value=_navy_response("Sure, the route_type is character"))
    )))
    with patch(
        "app.services.llm._get_local_client",
        return_value=fake_client,
    ):
        result = await llm_classify_material("Шаг 1.")
    # Falls through to heuristic; route is whatever heuristic picks.
    assert result.route_type in ROUTE_TYPES


@pytest.mark.asyncio
async def test_llm_classify_falls_back_on_unknown_route_type(monkeypatch):
    """LLM returned a route_type that's not in ROUTE_TYPES → fallback."""
    monkeypatch.setattr(
        "app.services.scenario_extractor_llm.settings",
        _navy_settings(),
    )
    monkeypatch.setenv("TZ5_LLM_ENABLED", "1")
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=AsyncMock(return_value=_navy_response(
            json.dumps({"route_type": "garbage", "confidence": 0.9})
    )))
    ))
    with patch(
        "app.services.llm._get_local_client",
        return_value=fake_client,
    ):
        result = await llm_classify_material("Шаг 1.")
    assert result.route_type in ROUTE_TYPES


@pytest.mark.asyncio
async def test_llm_classify_falls_back_on_api_exception(monkeypatch):
    monkeypatch.setattr(
        "app.services.scenario_extractor_llm.settings",
        _navy_settings(),
    )
    monkeypatch.setenv("TZ5_LLM_ENABLED", "1")
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=AsyncMock(side_effect=RuntimeError("API down"))
    )))
    with patch(
        "app.services.llm._get_local_client",
        return_value=fake_client,
    ):
        result = await llm_classify_material("Шаг 1.")
    assert result.route_type in ROUTE_TYPES
    # Heuristic ceiling.
    assert result.confidence <= 0.55


# ── LLM extractor happy path ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_llm_extract_scenario_route_parses_sonnet_json(monkeypatch):
    monkeypatch.setattr(
        "app.services.scenario_extractor_llm.settings",
        _navy_settings(),
    )
    monkeypatch.setenv("TZ5_LLM_ENABLED", "1")
    source = (
        "Скрипт холодного звонка.\n\nШаг 1: Приветствие. "
        "Поздороваться, представиться."
    )
    sonnet_payload = {
        "title_suggested": "Холодный звонок",
        "summary": "Памятка по обзвону.",
        "archetype_hint": None,
        "steps": [
            {"order": 1, "name": "Приветствие", "description": "Поздороваться",
             "manager_goals": [], "expected_client_reaction": None}
        ],
        "expected_objections": ["дорого"],
        "success_criteria": ["встреча"],
        # One real quote (substring of source), one fabricated.
        "quotes_from_source": ["Поздороваться, представиться", "не было в исходнике"],
        "confidence": 0.85,
    }
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=AsyncMock(return_value=_navy_response(json.dumps(sonnet_payload)))
    )))
    with patch(
        "app.services.llm._get_local_client",
        return_value=fake_client,
    ):
        blob = await llm_extract_for_route(source, "scenario")
    # Quote validator drops the fake quote.
    assert "Поздороваться, представиться" in blob["quotes_from_source"]
    assert "не было в исходнике" not in blob["quotes_from_source"]
    # Confidence penalty for the dropped quote (0.5 * 0.5 = 0.25 max).
    assert blob["confidence"] < 0.85


@pytest.mark.asyncio
async def test_llm_extract_falls_back_on_missing_required_keys(monkeypatch):
    monkeypatch.setattr(
        "app.services.scenario_extractor_llm.settings",
        _navy_settings(),
    )
    monkeypatch.setenv("TZ5_LLM_ENABLED", "1")
    bad_payload = {"title_suggested": "X"}  # missing steps, quotes_from_source
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=AsyncMock(return_value=_navy_response(json.dumps(bad_payload)))
    )))
    with patch(
        "app.services.llm._get_local_client",
        return_value=fake_client,
    ):
        blob = await llm_extract_for_route("Шаг 1: Привет.", "scenario")
    # Heuristic returns a full shape — required keys present.
    assert "steps" in blob
    assert "quotes_from_source" in blob


@pytest.mark.asyncio
async def test_llm_extract_arena_payload_passes_through(monkeypatch):
    monkeypatch.setattr(
        "app.services.scenario_extractor_llm.settings",
        _navy_settings(),
    )
    monkeypatch.setenv("TZ5_LLM_ENABLED", "1")
    source = "По 127-ФЗ ст. 213.3 минимальный долг — 500 000 руб."
    arena_payload = {
        "fact_text": "Минимальный долг — 500 000 руб. по 127-ФЗ ст. 213.3.",
        "law_article": "127-ФЗ ст. 213.3",
        "category": "eligibility",
        "difficulty_level": 2,
        "match_keywords": ["банкротство", "долг", "500 тыс"],
        "common_errors": ["100 тысяч"],
        "correct_response_hint": "500 000 руб.",
        "quotes_from_source": ["500 000 руб."],
        "confidence": 0.9,
    }
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=AsyncMock(return_value=_navy_response(json.dumps(arena_payload)))
    )))
    with patch(
        "app.services.llm._get_local_client",
        return_value=fake_client,
    ):
        blob = await llm_extract_for_route(source, "arena_knowledge")
    assert blob["category"] == "eligibility"
    assert blob["difficulty_level"] == 2
    assert "500 000 руб." in blob["quotes_from_source"]


@pytest.mark.asyncio
async def test_llm_extract_pii_scrubbed_from_output(monkeypatch):
    """Even if LLM somehow synthesizes a phone-shaped string, the
    output PII scrub catches it before persistence."""
    monkeypatch.setattr(
        "app.services.scenario_extractor_llm.settings",
        _navy_settings(),
    )
    monkeypatch.setenv("TZ5_LLM_ENABLED", "1")
    payload = {
        "title_suggested": "Звонок на +7 (495) 123-45-67",
        "summary": "обзвон",
        "archetype_hint": None,
        "steps": [],
        "expected_objections": [],
        "success_criteria": [],
        "quotes_from_source": [],
        "confidence": 0.7,
    }
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=AsyncMock(return_value=_navy_response(json.dumps(payload)))
    )))
    with patch(
        "app.services.llm._get_local_client",
        return_value=fake_client,
    ):
        blob = await llm_extract_for_route("source", "scenario")
    # Phone digits must be masked.
    assert "495" not in blob["title_suggested"]
    assert "[ДАННЫЕ СКРЫТЫ]" in blob["title_suggested"]


# ── Helper functions ────────────────────────────────────────────────────


def test_safe_json_strips_code_fences():
    raw = '```json\n{"route_type": "scenario", "confidence": 0.9}\n```'
    parsed = _safe_json(raw)
    assert parsed == {"route_type": "scenario", "confidence": 0.9}


def test_safe_json_strips_prose_around_braces():
    raw = 'Sure, here is the JSON: {"x": 1} let me know if you need anything else'
    parsed = _safe_json(raw)
    assert parsed == {"x": 1}


def test_safe_json_returns_none_on_garbage():
    assert _safe_json("complete garbage no braces") is None
    assert _safe_json("") is None


def test_truncate_for_llm_keeps_short_text():
    assert _truncate_for_llm("short") == "short"


def test_truncate_for_llm_cuts_long_text_at_paragraph_boundary():
    long = "para1.\n\n" + ("x" * 5000) + "\n\npara3."
    out = _truncate_for_llm(long)
    assert len(out) <= 4000


@pytest.mark.asyncio
async def test_validate_quotes_drops_non_substring():
    source = "В исходнике есть фраза А и фраза Б."
    quotes = ["фраза А", "фраза А и фраза Б", "фраза В (выдумка)"]
    kept = await _validate_quotes_via_llm(quotes, source)
    assert "фраза А" in kept
    assert "фраза А и фраза Б" in kept
    assert "фраза В (выдумка)" not in kept


def test_scrub_payload_dict_walks_nested_strings():
    blob = {
        "title": "Звонок +7 (495) 123-45-67",
        "steps": [{"name": "контакт info@example.com", "goals": ["call +7 495 1234567"]}],
    }
    out = _scrub_payload_dict(blob, "scenario")
    blob_str = repr(out)
    assert "495" not in blob_str
    assert "info@example.com" not in blob_str
