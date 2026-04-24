"""Contract test (TZ-1 §16.2): REST and WS training-end paths converge.

Both ``apps/api/app/api/training.py`` (REST end-session) and
``apps/api/app/ws/training.py`` (WS end-session) MUST produce the same
``training.real_case_logged`` DomainEvent for the same training session —
same ``idempotency_key``, same ``aggregate_id``, same event payload shape.
If the two paths ever drift, this test turns red before it matters in prod.
"""

from __future__ import annotations

import ast
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"
REST_TRAINING_PATH = APP_DIR / "api" / "training.py"
WS_TRAINING_PATH = APP_DIR / "ws" / "training.py"


def _call_kwargs_by_name(source: str, fn_name: str) -> list[dict[str, str]]:
    """Return keyword-argument snippets for every call to ``fn_name``.

    Values are rendered back as source segments so we can compare shapes
    without evaluating expressions.
    """
    tree = ast.parse(source)
    results: list[dict[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = None
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name != fn_name:
            continue
        kwargs: dict[str, str] = {}
        for kw in node.keywords:
            if kw.arg is None:
                continue
            kwargs[kw.arg] = ast.unparse(kw.value)
        results.append(kwargs)
    return results


def test_rest_and_ws_emit_training_real_case_with_same_shape():
    rest_source = REST_TRAINING_PATH.read_text(encoding="utf-8")
    ws_source = WS_TRAINING_PATH.read_text(encoding="utf-8")

    rest_calls = _call_kwargs_by_name(rest_source, "log_training_real_case_summary")
    ws_calls = _call_kwargs_by_name(ws_source, "log_training_real_case_summary")

    assert len(rest_calls) >= 1, "REST path must emit training.real_case_logged"
    assert len(ws_calls) >= 1, "WS path must emit training.real_case_logged"

    rest_kw = rest_calls[0]
    ws_kw = ws_calls[0]

    # The argument SET must match — if one path forgets an argument, dedup
    # breaks because the idempotency key is the same but the payload differs.
    assert set(rest_kw.keys()) == set(ws_kw.keys()), (
        "log_training_real_case_summary kwargs diverged between REST and WS:\n"
        f"REST: {sorted(rest_kw.keys())}\n"
        f"WS:   {sorted(ws_kw.keys())}"
    )

    # Both MUST pass `session=session` and `manager_id=...` expressions.
    assert rest_kw.get("session") == "session" and ws_kw.get("session") == "session"
    assert "manager_id" in rest_kw and "manager_id" in ws_kw
    assert "source" in rest_kw and "source" in ws_kw
    # The source labels are informational but must be DIFFERENT so we can
    # see in telemetry which transport produced the event.
    assert rest_kw["source"] != ws_kw["source"]


def test_both_training_endings_call_ensure_followup():
    """``ensure_followup_for_session`` is the reminder-dual-write entry
    point. Both paths must wire it so ``crm.reminder_created`` fires.
    """
    rest = REST_TRAINING_PATH.read_text(encoding="utf-8")
    ws = WS_TRAINING_PATH.read_text(encoding="utf-8")
    assert "ensure_followup_for_session" in rest, (
        "REST training-end forgot ensure_followup_for_session"
    )
    assert "ensure_followup_for_session" in ws, "WS training-end forgot ensure_followup_for_session"
