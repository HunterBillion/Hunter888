"""Static invariants that guard the unified client domain (TZ-1 §10.3).

These tests grep the source tree for patterns that would break the canonical
event log: raw ``ClientInteraction(...)`` construction outside the allowed
helpers, DomainEvent emission without an idempotency key on hot paths, etc.

If a new PR introduces a CRM write path that skips ``client_domain.py``, the
invariant tests below turn red so the reviewer is forced to decide: route the
write through the canonical helper, or add the module to the allow-list
(which requires reading TZ §10.3).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


APP_DIR = Path(__file__).resolve().parent.parent / "app"


# Modules allowed to write ClientInteraction directly. All new producers MUST
# go through ``app.services.client_domain`` helpers instead of adding
# themselves to this list without TZ §10.3 review.
ALLOWED_CLIENT_INTERACTION_WRITERS = {
    # Canonical helper that every other module calls.
    "app/services/client_domain.py",
    # Repair path that rebuilds projections from historical data.
    "app/services/client_domain_repair.py",
    # Projector owns the materialization contract.
    "app/services/crm_timeline_projector.py",
}


def _iter_python_files(root: Path) -> list[Path]:
    return sorted(
        p
        for p in root.rglob("*.py")
        if "__pycache__" not in p.parts
    )


def _file_constructs(path: Path, class_name: str) -> list[int]:
    """Return the line numbers where a ``<class_name>(...)`` call appears."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        pytest.fail(f"{path} has a syntax error")
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == class_name:
            lines.append(node.lineno)
        elif isinstance(func, ast.Attribute) and func.attr == class_name:
            lines.append(node.lineno)
    return lines


def test_client_interaction_writes_are_gated_through_client_domain():
    """Only the canonical helper + projector may construct ``ClientInteraction``.

    If this fails, route the new write through
    ``app.services.client_domain.create_crm_interaction_with_event`` instead
    of instantiating the row directly. Adding the offending file to
    ALLOWED_CLIENT_INTERACTION_WRITERS is only appropriate after a TZ §10.3
    design review.
    """
    offenders: list[str] = []
    for file_path in _iter_python_files(APP_DIR):
        rel = file_path.relative_to(APP_DIR.parent).as_posix()
        if rel in ALLOWED_CLIENT_INTERACTION_WRITERS:
            continue
        lines = _file_constructs(file_path, "ClientInteraction")
        if lines:
            offenders.append(f"{rel}: {lines}")
    assert not offenders, (
        "Raw ClientInteraction(...) construction found outside allowed "
        "writers. Route the write through client_domain helpers:\n"
        + "\n".join(offenders)
    )


def test_domain_event_table_kept_in_canonical_module():
    """``DomainEvent`` must only be *constructed* inside the canonical helper
    and its test/repair peers. Raw writes elsewhere would bypass the
    idempotency contract.
    """
    allowed = {
        "app/services/client_domain.py",
        "app/services/client_domain_repair.py",
    }
    offenders: list[str] = []
    for file_path in _iter_python_files(APP_DIR):
        rel = file_path.relative_to(APP_DIR.parent).as_posix()
        if rel in allowed:
            continue
        # Allow ``isinstance(x, DomainEvent)`` and ``select(DomainEvent)``
        # — we only care about ``DomainEvent(lead_client_id=...)`` calls with
        # keyword args that look like record construction.
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name != "DomainEvent":
                continue
            if any(isinstance(k, ast.keyword) and k.arg == "lead_client_id" for k in node.keywords):
                offenders.append(f"{rel}:{node.lineno}")
    assert not offenders, (
        "Raw DomainEvent(lead_client_id=...) construction found outside "
        "client_domain/client_domain_repair. Use "
        "client_domain.emit_domain_event instead:\n" + "\n".join(offenders)
    )


def test_projection_metadata_keys_are_stable():
    """Frontend types rely on ``domain_event_id``/``schema_version``/
    ``projection_name``/``projection_version`` keys. Make sure the projector
    still produces them — if this breaks, update
    apps/web/src/types/index.ts first.
    """
    from app.services.crm_timeline_projector import (
        PROJECTION_NAME,
        PROJECTION_VERSION,
        interaction_metadata_patch,
    )
    from app.models.domain_event import DomainEvent
    import uuid as _uuid

    event = DomainEvent(
        id=_uuid.uuid4(),
        lead_client_id=_uuid.uuid4(),
        event_type="crm.interaction_logged",
        actor_type="user",
        source="test",
        payload_json={},
        idempotency_key="x",
        schema_version=1,
    )
    patch = interaction_metadata_patch(event)
    assert set(patch.keys()) >= {
        "domain_event_id",
        "schema_version",
        "projection_name",
        "projection_version",
    }
    assert patch["projection_name"] == PROJECTION_NAME
    assert patch["projection_version"] == PROJECTION_VERSION
