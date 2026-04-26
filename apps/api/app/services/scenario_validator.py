"""TZ-3 §9.2 — scenario semantic validator.

Pure-function validator that checks a ScenarioTemplate is publishable.
Returns a structured ValidationReport which the publisher writes into
``ScenarioVersion.validation_report`` for audit + UI display.

Per §9.3 the validator NEVER auto-fixes a problem — every issue is
recorded in the report. The publisher decides whether to abort
(any error-level issue) or proceed (warnings only).

Stage shape rules come straight from §9.2.1:

    | order              | int       | required, 1..N continuous unique
    | name               | str       | required, ≤80 chars
    | description        | str       | required, ≤500 chars
    | manager_goals      | list[str] | required, 1..5 items
    | client_state       | str       | optional
    | traps              | list[uuid]| optional, must reference existing rows
    | min_duration_secs  | int       | optional
    | success_criteria   | dict      | optional

Any future shape change bumps `schema_version` on the version row;
this validator stays keyed on `schema_version=1` until then.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from typing import Any


# ── Public types ────────────────────────────────────────────────────────────


class IssueSeverity(str, enum.Enum):
    """ERROR blocks publish. WARNING is recorded but allows publish."""

    error = "error"
    warning = "warning"


@dataclass
class ValidationIssue:
    code: str  # short identifier — frontend may translate
    severity: IssueSeverity
    message: str  # Russian, user-facing
    field: str | None = None  # dotted path: "stages[2].manager_goals"


@dataclass
class ValidationReport:
    schema_version: int
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == IssueSeverity.error for i in self.issues)

    def to_jsonb(self) -> dict[str, Any]:
        """Serialise into the JSONB shape stored in
        ``scenario_versions.validation_report``."""
        return {
            "schema_version": self.schema_version,
            "issues": [
                {
                    "code": i.code,
                    "severity": i.severity.value,
                    "message": i.message,
                    "field": i.field,
                }
                for i in self.issues
            ],
            "has_errors": self.has_errors,
        }


# ── Validator ───────────────────────────────────────────────────────────────


_DIFFICULTY_RANGE = range(1, 11)  # 1..10 inclusive
_DURATION_MIN = 1
_DURATION_MAX = 60  # minutes
_NAME_MAX = 80
_DESC_MAX = 500
_STAGE_DESC_MAX = 500
_GOALS_MIN = 1
_GOALS_MAX = 5

# Template-level required fields (post-rename to rop, see §6.1).
_REQUIRED_TEMPLATE_FIELDS = ("code", "name", "description")


def validate_template_for_publish(scenario, *, schema_version: int = 1) -> ValidationReport:
    """Run the full publish-time validator on a ScenarioTemplate.

    Caller passes the ORM row (or a mapping with the same keys). The
    function never mutates the input — it only inspects fields.
    """
    issues: list[ValidationIssue] = []

    # ── Top-level required fields ──
    for fname in _REQUIRED_TEMPLATE_FIELDS:
        value = _get(scenario, fname)
        if not _present(value):
            issues.append(ValidationIssue(
                code="template.required_field_missing",
                severity=IssueSeverity.error,
                message=f"Поле «{fname}» обязательно для публикации.",
                field=fname,
            ))

    # ── code shape ──
    code = _get(scenario, "code")
    if isinstance(code, str) and code:
        if not code.replace("_", "").replace("-", "").isalnum():
            issues.append(ValidationIssue(
                code="template.code_invalid_chars",
                severity=IssueSeverity.error,
                message=(
                    "Код сценария может содержать только латинские буквы, "
                    "цифры, '_' и '-'."
                ),
                field="code",
            ))

    # ── difficulty range ──
    difficulty = _get(scenario, "difficulty")
    if difficulty is not None and difficulty not in _DIFFICULTY_RANGE:
        issues.append(ValidationIssue(
            code="template.difficulty_out_of_range",
            severity=IssueSeverity.error,
            message="Сложность должна быть числом 1..10.",
            field="difficulty",
        ))

    # ── duration sanity ──
    typ = _get(scenario, "typical_duration_minutes")
    mx = _get(scenario, "max_duration_minutes")
    if typ is not None and not (_DURATION_MIN <= typ <= _DURATION_MAX):
        issues.append(ValidationIssue(
            code="template.typical_duration_out_of_range",
            severity=IssueSeverity.error,
            message=f"Типичная длительность должна быть {_DURATION_MIN}..{_DURATION_MAX} мин.",
            field="typical_duration_minutes",
        ))
    if mx is not None and not (_DURATION_MIN <= mx <= _DURATION_MAX):
        issues.append(ValidationIssue(
            code="template.max_duration_out_of_range",
            severity=IssueSeverity.error,
            message=f"Максимальная длительность должна быть {_DURATION_MIN}..{_DURATION_MAX} мин.",
            field="max_duration_minutes",
        ))
    if typ is not None and mx is not None and typ > mx:
        issues.append(ValidationIssue(
            code="template.typical_exceeds_max",
            severity=IssueSeverity.error,
            message="Типичная длительность не может превышать максимальную.",
            field="typical_duration_minutes",
        ))

    # ── stages (the largest validation surface) ──
    stages = _get(scenario, "stages") or []
    if not isinstance(stages, list) or len(stages) == 0:
        issues.append(ValidationIssue(
            code="stages.empty",
            severity=IssueSeverity.error,
            message="У сценария должен быть хотя бы один этап.",
            field="stages",
        ))
    else:
        issues.extend(_validate_stages(stages))

    # ── archetype_weights sum ──
    weights = _get(scenario, "archetype_weights") or {}
    if isinstance(weights, dict) and weights:
        total = sum(float(v) for v in weights.values() if isinstance(v, (int, float)))
        if not (95.0 <= total <= 105.0):
            issues.append(ValidationIssue(
                code="archetype_weights.sum_out_of_range",
                severity=IssueSeverity.warning,
                message=(
                    f"Сумма весов архетипов = {total:.1f}; ожидается ≈100. "
                    "Это не блокирует публикацию, но runtime будет нормировать."
                ),
                field="archetype_weights",
            ))

    return ValidationReport(schema_version=schema_version, issues=issues)


# ── Stages ──────────────────────────────────────────────────────────────────


def _validate_stages(stages: list[Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    seen_orders: set[int] = set()

    for idx, stage in enumerate(stages):
        path = f"stages[{idx}]"

        if not isinstance(stage, dict):
            issues.append(ValidationIssue(
                code="stage.not_a_dict",
                severity=IssueSeverity.error,
                message=f"Этап {idx + 1} должен быть объектом.",
                field=path,
            ))
            continue

        # order: required int
        order = stage.get("order")
        if not isinstance(order, int):
            issues.append(ValidationIssue(
                code="stage.order_missing",
                severity=IssueSeverity.error,
                message=f"У этапа {idx + 1} должно быть поле order (целое число).",
                field=f"{path}.order",
            ))
        else:
            if order in seen_orders:
                issues.append(ValidationIssue(
                    code="stage.order_duplicate",
                    severity=IssueSeverity.error,
                    message=f"Порядковый номер {order} повторяется в этапах.",
                    field=f"{path}.order",
                ))
            seen_orders.add(order)

        # name: required str ≤80
        name = stage.get("name")
        if not isinstance(name, str) or not name.strip():
            issues.append(ValidationIssue(
                code="stage.name_missing",
                severity=IssueSeverity.error,
                message=f"У этапа {idx + 1} не задано имя.",
                field=f"{path}.name",
            ))
        elif len(name) > _NAME_MAX:
            issues.append(ValidationIssue(
                code="stage.name_too_long",
                severity=IssueSeverity.error,
                message=f"Имя этапа {idx + 1} длиннее {_NAME_MAX} символов.",
                field=f"{path}.name",
            ))

        # description: required str ≤500
        desc = stage.get("description")
        if not isinstance(desc, str) or not desc.strip():
            issues.append(ValidationIssue(
                code="stage.description_missing",
                severity=IssueSeverity.error,
                message=f"У этапа {idx + 1} не задано описание.",
                field=f"{path}.description",
            ))
        elif len(desc) > _STAGE_DESC_MAX:
            issues.append(ValidationIssue(
                code="stage.description_too_long",
                severity=IssueSeverity.error,
                message=f"Описание этапа {idx + 1} длиннее {_STAGE_DESC_MAX} символов.",
                field=f"{path}.description",
            ))

        # manager_goals: required list of str, 1..5
        goals = stage.get("manager_goals")
        if not isinstance(goals, list) or not goals:
            issues.append(ValidationIssue(
                code="stage.manager_goals_missing",
                severity=IssueSeverity.error,
                message=f"У этапа {idx + 1} должно быть {_GOALS_MIN}..{_GOALS_MAX} целей менеджера.",
                field=f"{path}.manager_goals",
            ))
        elif len(goals) > _GOALS_MAX:
            issues.append(ValidationIssue(
                code="stage.manager_goals_too_many",
                severity=IssueSeverity.error,
                message=f"У этапа {idx + 1} больше {_GOALS_MAX} целей.",
                field=f"{path}.manager_goals",
            ))
        elif any(not isinstance(g, str) or not g.strip() for g in goals):
            issues.append(ValidationIssue(
                code="stage.manager_goals_invalid_item",
                severity=IssueSeverity.error,
                message=f"Цели этапа {idx + 1} должны быть непустыми строками.",
                field=f"{path}.manager_goals",
            ))

        # traps: optional list of uuid-strings
        traps = stage.get("traps")
        if traps is not None:
            if not isinstance(traps, list):
                issues.append(ValidationIssue(
                    code="stage.traps_not_a_list",
                    severity=IssueSeverity.error,
                    message=f"Поле traps этапа {idx + 1} должно быть списком.",
                    field=f"{path}.traps",
                ))
            else:
                for t_idx, t in enumerate(traps):
                    try:
                        uuid.UUID(str(t))
                    except (ValueError, TypeError):
                        issues.append(ValidationIssue(
                            code="stage.trap_id_invalid",
                            severity=IssueSeverity.error,
                            message=(
                                f"Trap[{t_idx}] этапа {idx + 1} не похож на UUID. "
                                "Существование trap-id в БД проверяется отдельно "
                                "(см. scenario_publisher)."
                            ),
                            field=f"{path}.traps[{t_idx}]",
                        ))

    # order continuity check (1..N without gaps)
    if seen_orders:
        expected = set(range(1, len(stages) + 1))
        if seen_orders != expected:
            issues.append(ValidationIssue(
                code="stages.order_not_continuous",
                severity=IssueSeverity.error,
                message=(
                    f"Порядковые номера этапов должны идти 1..{len(stages)} "
                    f"без пропусков. Найдено: {sorted(seen_orders)}."
                ),
                field="stages",
            ))

    return issues


# ── Helpers ─────────────────────────────────────────────────────────────────


def _get(scenario: Any, name: str) -> Any:
    """Read attr from ORM row OR from dict (helps unit tests)."""
    if isinstance(scenario, dict):
        return scenario.get(name)
    return getattr(scenario, name, None)


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


__all__ = [
    "IssueSeverity",
    "ValidationIssue",
    "ValidationReport",
    "validate_template_for_publish",
]
