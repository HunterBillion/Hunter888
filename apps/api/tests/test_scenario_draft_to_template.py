"""TZ-5 — draft → ScenarioTemplate conversion tests.

The conversion happens at two layers:

  * :func:`scenario_extractor.draft_payload_to_template_fields` -- a pure
    function that maps the dataclass to ScenarioTemplate kwargs. Unit
    tests cover the field mapping + the "imported templates start in
    ``status='draft'``" invariant (TZ-5 §3.2 step 4).

  * The ROP API endpoint ``POST /scenarios/drafts/{id}/create-scenario``
    builds the template + a v1 ScenarioVersion (status='draft') and
    flips the source draft's ``status`` to ``converted``. End-to-end DB
    coverage of that flow lives in the API integration tests; this file
    pins the field-mapping contract and the AST-friendly invariants.
"""
from __future__ import annotations

import pytest

from app.services.scenario_extractor import (
    ScenarioDraftPayload,
    ScenarioStep,
    draft_payload_to_template_fields,
)


def _payload(**overrides) -> ScenarioDraftPayload:
    base = dict(
        title_suggested="Холодный звонок по списку",
        summary="Памятка ROP по холодному обзвону.",
        archetype_hint=None,
        steps=[
            ScenarioStep(order=1, name="Приветствие", description="Поздороваться"),
            ScenarioStep(order=2, name="Квалификация", description="Задать 3 вопроса"),
        ],
        expected_objections=["дорого", "подумаю"],
        success_criteria=["встреча в календаре"],
        quotes_from_source=["Поздороваться"],
        confidence=0.72,
    )
    base.update(overrides)
    return ScenarioDraftPayload(**base)


def test_imported_template_lands_in_draft_status():
    """TZ-5 §3.2 step 4: status='draft' so the runtime resolver never sees
    a half-baked imported template."""
    fields = draft_payload_to_template_fields(_payload(), fallback_code="imported_x")
    assert fields["status"] == "draft"


def test_template_name_uses_extracted_title():
    fields = draft_payload_to_template_fields(_payload(), fallback_code="imported_x")
    assert fields["name"] == "Холодный звонок по списку"


def test_template_falls_back_to_code_when_title_empty():
    fields = draft_payload_to_template_fields(
        _payload(title_suggested=""), fallback_code="imported_xyz"
    )
    assert fields["name"] == "imported_xyz"


def test_steps_become_stages_with_required_shape():
    """The ScenarioTemplate.stages JSONB column has a stable shape that
    the runtime resolver depends on. Every imported stage must include
    the keys the existing scenario_engine looks for."""
    fields = draft_payload_to_template_fields(_payload(), fallback_code="imported_x")
    stages = fields["stages"]
    assert len(stages) == 2
    for stage in stages:
        assert {
            "order",
            "name",
            "description",
            "manager_goals",
            "manager_mistakes",
            "expected_emotion_range",
            "duration_min",
            "duration_max",
            "required",
        }.issubset(stage.keys())


def test_template_uses_imported_group_name():
    """Imported templates land in a separate group so ROP can filter
    them in the editor."""
    fields = draft_payload_to_template_fields(_payload(), fallback_code="imported_x")
    assert fields["group_name"] == "imported"


def test_runtime_required_fields_have_neutral_defaults():
    """Imported templates must not crash the runtime resolver because of
    missing fields the LLM didn't extract. Defaults are explicitly empty
    so ROP knows they need editing before publish."""
    fields = draft_payload_to_template_fields(_payload(), fallback_code="imported_x")
    assert fields["archetype_weights"] == {}
    assert fields["lead_sources"] == []
    assert fields["recommended_chains"] == []
    assert fields["trap_pool_categories"] == []
    assert fields["scoring_modifiers"] == []


def test_empty_steps_produces_empty_stages():
    """A degenerate "no steps" payload still yields a valid template
    (stages=[] is allowed by the schema; ROP fills in manually)."""
    fields = draft_payload_to_template_fields(
        _payload(steps=[]), fallback_code="imported_x"
    )
    assert fields["stages"] == []


def test_to_jsonable_persists_full_payload_shape():
    """The dataclass round-trips through JSONB persistence. This is the
    contract the FE consumes via /scenarios/drafts/{id}."""
    blob = _payload().to_jsonable()
    assert blob["confidence"] == pytest.approx(0.72)
    assert len(blob["steps"]) == 2
    assert blob["steps"][0]["name"] == "Приветствие"
    assert blob["expected_objections"] == ["дорого", "подумаю"]
