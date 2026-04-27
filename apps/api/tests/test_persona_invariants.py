"""Static invariants for the TZ-4 persona memory layer (§9 / §13.2.1).

D3 made ``app.services.persona_memory`` the single sanctioned writer
of ``MemoryPersona`` and ``SessionPersonaSnapshot``. Without an AST
guard, future PRs would drift — one inline ``MemoryPersona(...)`` and
the §9.2 invariant 1 contract (immutable identity for the lifetime of
a session) quietly disappears.

These tests fail the build the moment a new producer skips the
service. The fix is one of two:

  * Route the new write through ``persona_memory.upsert_for_lead`` /
    ``persona_memory.capture_for_session`` / ``lock_slot``; or
  * Get explicit TZ-4 §13.2.1 review approval and add the file to the
    allow-list below.

Quietly weakening the allow-list in a PR review is the failure mode
the test exists to make impossible — same pattern as the TZ-1
``ClientInteraction`` and TZ-4 D2 ``Attachment`` AST guards.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parent.parent / "app"


# Modules allowed to construct MemoryPersona / SessionPersonaSnapshot
# directly. Every new producer goes through the service helpers instead
# of being added here.
ALLOWED_PERSONA_WRITERS = {
    # Canonical service — the only sanctioned producer.
    "app/services/persona_memory.py",
}


def _iter_python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _construct_call_lines(path: Path, class_name: str) -> list[int]:
    """Line numbers where ``<class_name>(...)`` is constructed.

    Covers both ``MemoryPersona(...)`` (direct import) and
    ``models.persona.MemoryPersona(...)`` (qualified).
    """
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


def test_memory_persona_writes_are_gated_through_service():
    """Only ``persona_memory`` is allowed to construct ``MemoryPersona``.

    If this fails, route the new write through
    ``app.services.persona_memory.upsert_for_lead`` instead of
    instantiating the row directly. Adding the offending file to
    :data:`ALLOWED_PERSONA_WRITERS` is only appropriate after a TZ-4
    §13.2.1 design review.
    """
    offenders: list[str] = []
    for file_path in _iter_python_files(APP_DIR):
        rel = file_path.relative_to(APP_DIR.parent).as_posix()
        if rel in ALLOWED_PERSONA_WRITERS:
            continue
        lines = _construct_call_lines(file_path, "MemoryPersona")
        if lines:
            offenders.append(f"{rel}: {lines}")
    assert not offenders, (
        "Direct MemoryPersona(...) construction found outside the "
        "canonical service. Use persona_memory.upsert_for_lead instead:\n"
        + "\n".join(offenders)
    )


def test_session_persona_snapshot_writes_are_gated_through_service():
    """Only ``persona_memory`` is allowed to construct
    ``SessionPersonaSnapshot``. The §9.2 invariant 1 ("identity frozen
    for the lifetime of a session") only holds when there's a single
    INSERT site and zero UPDATE sites for this row — both enforced here
    plus :func:`test_session_persona_snapshot_has_no_update_sites`.
    """
    offenders: list[str] = []
    for file_path in _iter_python_files(APP_DIR):
        rel = file_path.relative_to(APP_DIR.parent).as_posix()
        if rel in ALLOWED_PERSONA_WRITERS:
            continue
        lines = _construct_call_lines(file_path, "SessionPersonaSnapshot")
        if lines:
            offenders.append(f"{rel}: {lines}")
    assert not offenders, (
        "Direct SessionPersonaSnapshot(...) construction found outside "
        "the canonical service. Use persona_memory.capture_for_session "
        "instead:\n" + "\n".join(offenders)
    )


def _snapshot_attribute_assignments(path: Path) -> list[tuple[int, str]]:
    """Find ``snapshot.<identity_field> = ...`` style assignments.

    Heuristic: receiver named ``snapshot`` (matches the spec wording in
    §9.2) and the attribute being one of the immutable identity fields.
    The pipeline updates ``mutation_blocked_count`` via ``UPDATE`` rather
    than ORM mutation specifically to keep this guard clean.
    """
    immutable_fields = {
        "address_form",
        "full_name",
        "gender",
        "role_title",
        "tone",
        "captured_from",
        "persona_version",
        # session_id and lead_client_id are PK / FK — SQLAlchemy doesn't
        # allow re-assignment on a flushed row. Listing them anyway so a
        # future refactor can't sneak them through.
        "session_id",
        "lead_client_id",
    }
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Attribute):
                continue
            if target.attr not in immutable_fields:
                continue
            if isinstance(target.value, ast.Name) and target.value.id == "snapshot":
                hits.append((node.lineno, target.attr))
    return hits


def test_session_persona_snapshot_has_no_update_sites():
    """No code outside the service may write to a snapshot's identity
    fields after INSERT — that would defeat §9.2 invariant 1.

    Note: ``persona_memory.record_conflict_attempt`` updates the
    observability counter via raw SQL ``UPDATE`` rather than an ORM
    field write specifically to satisfy this guard.
    """
    offenders: list[str] = []
    for file_path in _iter_python_files(APP_DIR):
        rel = file_path.relative_to(APP_DIR.parent).as_posix()
        if rel in ALLOWED_PERSONA_WRITERS:
            continue
        for line, attr in _snapshot_attribute_assignments(file_path):
            offenders.append(f"{rel}:{line} → snapshot.{attr} = ...")
    assert not offenders, (
        "Mutation of an existing SessionPersonaSnapshot identity field "
        "found outside the canonical service. Snapshots are immutable "
        "for the lifetime of the session (TZ-4 §9.2 invariant 1):\n"
        + "\n".join(offenders)
    )
