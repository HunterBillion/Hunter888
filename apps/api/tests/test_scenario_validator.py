"""TZ-3 §9.2 / §9.2.1 — pure-function tests for scenario_validator.

No DB, no fixtures — the validator is a pure function over a dict
(or ORM row, but a dict is enough). Each test pins ONE rule from the
spec so a regression is unambiguous.
"""

from __future__ import annotations

import uuid

from app.services.scenario_validator import (
    IssueSeverity,
    validate_template_for_publish,
)


# Minimal "valid" template the tests start from — every test mutates one
# field to trigger one specific issue. Mirrors the §9.2.1 stage shape.
def _valid_template() -> dict:
    return {
        "code": "test_scenario",
        "name": "Тестовый сценарий",
        "description": "Описание для теста",
        "difficulty": 5,
        "typical_duration_minutes": 8,
        "max_duration_minutes": 15,
        "archetype_weights": {"skeptic": 50, "avoidant": 50},
        "stages": [
            {
                "order": 1,
                "name": "Приветствие",
                "description": "Установить контакт.",
                "manager_goals": ["Назвать себя"],
            },
            {
                "order": 2,
                "name": "Квалификация",
                "description": "Понять боль клиента.",
                "manager_goals": ["Узнать долг", "Узнать ситуацию"],
            },
        ],
    }


# ── Happy path ──────────────────────────────────────────────────────────────


def test_minimal_valid_template_passes():
    report = validate_template_for_publish(_valid_template())
    assert not report.has_errors
    # warning on archetype_weights sum is fine — sum is exactly 100
    assert report.schema_version == 1


# ── Required template fields ────────────────────────────────────────────────


def test_missing_code_is_error():
    t = _valid_template()
    t["code"] = ""
    report = validate_template_for_publish(t)
    assert report.has_errors
    codes = [i.code for i in report.issues]
    assert "template.required_field_missing" in codes


def test_invalid_code_chars():
    t = _valid_template()
    t["code"] = "invalid code with spaces"
    report = validate_template_for_publish(t)
    assert any(i.code == "template.code_invalid_chars" for i in report.issues)


# ── Difficulty / duration ───────────────────────────────────────────────────


def test_difficulty_out_of_range():
    t = _valid_template()
    t["difficulty"] = 11
    report = validate_template_for_publish(t)
    assert any(i.code == "template.difficulty_out_of_range" for i in report.issues)


def test_typical_exceeds_max_duration():
    t = _valid_template()
    t["typical_duration_minutes"] = 20
    t["max_duration_minutes"] = 15
    report = validate_template_for_publish(t)
    assert any(i.code == "template.typical_exceeds_max" for i in report.issues)


# ── Stage shape (§9.2.1) ────────────────────────────────────────────────────


def test_empty_stages_is_error():
    t = _valid_template()
    t["stages"] = []
    report = validate_template_for_publish(t)
    assert any(i.code == "stages.empty" for i in report.issues)


def test_stage_missing_required_fields():
    t = _valid_template()
    t["stages"] = [{"order": 1}]  # name/description/manager_goals all missing
    report = validate_template_for_publish(t)
    codes = {i.code for i in report.issues}
    assert "stage.name_missing" in codes
    assert "stage.description_missing" in codes
    assert "stage.manager_goals_missing" in codes


def test_stage_order_duplicate():
    t = _valid_template()
    t["stages"][1]["order"] = 1  # both stages now order=1
    report = validate_template_for_publish(t)
    assert any(i.code == "stage.order_duplicate" for i in report.issues)


def test_stage_order_not_continuous():
    t = _valid_template()
    t["stages"][1]["order"] = 5  # 1, 5 — gap
    report = validate_template_for_publish(t)
    assert any(i.code == "stages.order_not_continuous" for i in report.issues)


def test_stage_too_many_goals():
    t = _valid_template()
    t["stages"][0]["manager_goals"] = [f"goal {i}" for i in range(6)]  # 6 > 5
    report = validate_template_for_publish(t)
    assert any(i.code == "stage.manager_goals_too_many" for i in report.issues)


def test_stage_traps_must_be_uuid():
    t = _valid_template()
    t["stages"][0]["traps"] = ["not-a-uuid", str(uuid.uuid4())]
    report = validate_template_for_publish(t)
    assert any(i.code == "stage.trap_id_invalid" for i in report.issues)
    # The valid UUID (second item) must NOT trigger an error
    invalid_issues = [i for i in report.issues if i.code == "stage.trap_id_invalid"]
    assert all("traps[0]" in (i.field or "") for i in invalid_issues)


# ── Archetype weights (warning level only) ──────────────────────────────────


def test_archetype_weights_off_by_a_lot_is_warning_not_error():
    t = _valid_template()
    t["archetype_weights"] = {"skeptic": 200, "avoidant": 50}  # 250
    report = validate_template_for_publish(t)
    assert not report.has_errors
    warnings = [i for i in report.issues if i.severity == IssueSeverity.warning]
    assert any(w.code == "archetype_weights.sum_out_of_range" for w in warnings)


# ── Report shape ────────────────────────────────────────────────────────────


def test_report_serialises_to_jsonb_shape():
    """`validation_report` JSONB column round-trip — pin the shape so
    the FE can rely on it for highlighting failing fields."""
    report = validate_template_for_publish(_valid_template())
    blob = report.to_jsonb()
    assert blob["schema_version"] == 1
    assert "issues" in blob
    assert "has_errors" in blob
    if blob["issues"]:
        first = blob["issues"][0]
        assert {"code", "severity", "message"}.issubset(first.keys())
