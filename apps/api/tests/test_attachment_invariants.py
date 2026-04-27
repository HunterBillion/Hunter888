"""Static invariants that guard the TZ-4 attachment pipeline (§7 / §13.2.1).

The TZ-4 D2 PR established ``app.services.attachment_pipeline`` as the
single sanctioned writer of ``Attachment`` rows and of the four status
columns (``status``, ``ocr_status``, ``classification_status``,
``verification_status``). Without an AST guard, future PRs would drift —
one inline ``Attachment(...)`` and the dedup race contract from §7.2.6
quietly disappears.

These tests fail the build the moment a new producer skips the pipeline.
The fix is one of two:

  * Route the new write through ``attachment_pipeline.ingest_upload`` or
    one of the ``mark_*`` state-transition helpers; or
  * Get explicit TZ §13.2.1 review approval and add the file to the
    allow-list below.

Quietly weakening the allow-list in a PR review is the failure mode the
test exists to make impossible.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parent.parent / "app"


# Modules that are allowed to construct Attachment(...) directly. Every
# new producer goes through ``attachment_pipeline.ingest_upload`` instead
# of being added here.
ALLOWED_ATTACHMENT_WRITERS = {
    # Canonical pipeline — the only sanctioned producer.
    "app/services/attachment_pipeline.py",
}


# Modules allowed to mutate Attachment status columns directly. These are
# the state-transition helpers in the pipeline. Adding callers here means
# the AST guard would not catch a regression — instead, callers should
# invoke the appropriate ``mark_*`` helper from attachment_pipeline.
ALLOWED_ATTACHMENT_STATUS_MUTATORS = {
    "app/services/attachment_pipeline.py",
}


STATUS_COLUMNS = frozenset(
    {
        "status",
        "ocr_status",
        "classification_status",
        "verification_status",
    }
)


def _iter_python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _construct_call_lines(path: Path, class_name: str) -> list[int]:
    """Line numbers where ``<class_name>(...)`` is constructed.

    Returns the line of every ``ast.Call`` whose callee resolves to a name
    or attribute matching ``class_name`` — covers both ``Attachment(...)``
    (direct import) and ``models.client.Attachment(...)`` (qualified).
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


def _status_assignment_sites(path: Path) -> list[tuple[int, str]]:
    """Find ``<obj>.status = …`` style assignments where the LHS attribute
    is one of :data:`STATUS_COLUMNS`. We don't try to prove the LHS is an
    ``Attachment`` instance — false-positive cost is low (rename the
    column or use an unambiguous variable name) and the alternative
    (chasing types through SQLAlchemy mapped declarations) is fragile.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        # Plain `a.foo = ...`
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr in STATUS_COLUMNS:
                    if _looks_like_attachment(target.value):
                        hits.append((node.lineno, target.attr))
        # Augmented `a.foo += ...` — defensive, not currently used in code
        elif isinstance(node, ast.AugAssign):
            target = node.target
            if isinstance(target, ast.Attribute) and target.attr in STATUS_COLUMNS:
                if _looks_like_attachment(target.value):
                    hits.append((node.lineno, target.attr))
    return hits


def _looks_like_attachment(value: ast.expr) -> bool:
    """Heuristic: the LHS of a status assignment touches an Attachment if
    the receiver is named ``attachment``, ``att``, ``attach`` or
    ``new_attachment`` / ``existing_attachment``. The pipeline uses
    ``attachment``; the API layer used to use the same name. Adding a new
    receiver name should be a deliberate review choice — extend this list
    only after reading TZ-4 §13.2.1.
    """
    candidates = {"attachment", "att", "attach", "new_attachment", "existing_attachment"}
    if isinstance(value, ast.Name):
        return value.id in candidates
    return False


def test_attachment_writes_are_gated_through_pipeline():
    """Only ``attachment_pipeline`` is allowed to construct ``Attachment``.

    If this fails, route the new write through
    ``app.services.attachment_pipeline.ingest_upload`` instead of
    instantiating the row directly. Adding the offending file to
    :data:`ALLOWED_ATTACHMENT_WRITERS` is only appropriate after a
    TZ-4 §13.2.1 design review.
    """
    offenders: list[str] = []
    for file_path in _iter_python_files(APP_DIR):
        rel = file_path.relative_to(APP_DIR.parent).as_posix()
        if rel in ALLOWED_ATTACHMENT_WRITERS:
            continue
        lines = _construct_call_lines(file_path, "Attachment")
        if lines:
            offenders.append(f"{rel}: {lines}")
    assert not offenders, (
        "Direct Attachment(...) construction found outside the canonical "
        "pipeline. Use attachment_pipeline.ingest_upload instead:\n"
        + "\n".join(offenders)
    )


def test_attachment_status_columns_are_only_mutated_in_pipeline():
    """Direct writes to ``attachment.status`` / ``ocr_status`` /
    ``classification_status`` / ``verification_status`` are gated to the
    pipeline's ``mark_*`` helpers. This is the §7.2 #4 contract — every
    state transition emits a canonical event, which only happens when
    the helper is the writer.
    """
    offenders: list[str] = []
    for file_path in _iter_python_files(APP_DIR):
        rel = file_path.relative_to(APP_DIR.parent).as_posix()
        if rel in ALLOWED_ATTACHMENT_STATUS_MUTATORS:
            continue
        hits = _status_assignment_sites(file_path)
        for line, attr in hits:
            offenders.append(f"{rel}:{line} → attachment.{attr} = ...")
    assert not offenders, (
        "Direct attachment.<status> = ... assignment found outside the "
        "pipeline. Use the corresponding attachment_pipeline.mark_* "
        "helper so a canonical Domain Event is emitted (TZ-4 §7.2 #4):\n"
        + "\n".join(offenders)
    )
