"""Static invariants for the TZ-4 §8 knowledge governance layer.

D4 made ``app.services.knowledge_review_policy`` the single sanctioned
writer of ``LegalKnowledgeChunk.knowledge_status``. Without an AST
guard, future PRs would drift — one inline
``chunk.knowledge_status = "outdated"`` and the §8.3.1 closed footgun
re-opens (auto-flipping a popular chunk to ``outdated`` silently
breaks every RAG retrieval that touches it).

These tests fail the build the moment a new producer skips the
service. The fix is one of two:

  * Route the new write through ``knowledge_review_policy.expire_overdue``
    or ``mark_reviewed`` (only legal paths); or
  * Get explicit TZ-4 §13.2.1 review approval and add the file to the
    allow-list below.

Mirrors the TZ-1 ``ClientInteraction``, TZ-4 D2 ``Attachment``, and
D3 ``MemoryPersona`` AST guard patterns.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parent.parent / "app"


# Modules allowed to mutate ``LegalKnowledgeChunk.knowledge_status``
# directly. Every new producer goes through the service helpers
# instead of being added here.
ALLOWED_KNOWLEDGE_STATUS_MUTATORS = {
    # Canonical service — TTL sweep + manual review.
    "app/services/knowledge_review_policy.py",
}


def _iter_python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _knowledge_status_assignments(path: Path) -> list[tuple[int, str]]:
    """Find ``<chunk>.knowledge_status = ...`` style writes.

    Heuristic: the LHS receiver is named ``chunk``, ``item``, ``row``
    or ``knowledge_chunk`` — the names used across the codebase. Adding
    a new receiver name should be a deliberate review choice.
    """
    candidate_names = {"chunk", "item", "row", "knowledge_chunk", "kc"}
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
            if target.attr != "knowledge_status":
                continue
            if (
                isinstance(target.value, ast.Name)
                and target.value.id in candidate_names
            ):
                hits.append((node.lineno, target.value.id))
    return hits


def _knowledge_status_bulk_updates(path: Path) -> list[int]:
    """Find ``update(LegalKnowledgeChunk).values(knowledge_status=...)``
    bulk update calls. These bypass the ORM but reach the same column."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    hits: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # Match `.values(knowledge_status=...)`
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "values"):
            continue
        for kw in node.keywords:
            if kw.arg == "knowledge_status":
                hits.append(node.lineno)
                break
    return hits


def test_knowledge_status_writes_are_gated_through_service():
    """Only ``knowledge_review_policy`` is allowed to write
    ``LegalKnowledgeChunk.knowledge_status``.

    If this fails, route the new write through
    ``app.services.knowledge_review_policy.mark_reviewed`` (manual
    transitions including ``outdated``) or rely on
    ``expire_overdue`` (TTL sweep, ``actual → needs_review`` only).
    Adding the offending file to
    :data:`ALLOWED_KNOWLEDGE_STATUS_MUTATORS` is only appropriate after
    a TZ-4 §13.2.1 design review.
    """
    offenders: list[str] = []
    for file_path in _iter_python_files(APP_DIR):
        rel = file_path.relative_to(APP_DIR.parent).as_posix()
        if rel in ALLOWED_KNOWLEDGE_STATUS_MUTATORS:
            continue
        for line, recv in _knowledge_status_assignments(file_path):
            offenders.append(f"{rel}:{line} → {recv}.knowledge_status = ...")
        for line in _knowledge_status_bulk_updates(file_path):
            offenders.append(f"{rel}:{line} → .values(knowledge_status=...)")
    assert not offenders, (
        "Direct knowledge_status mutation found outside the canonical "
        "service. Use knowledge_review_policy.mark_reviewed (manual) "
        "or .expire_overdue (TTL sweep, actual→needs_review only).\n"
        "Auto-flipping to 'outdated' is FORBIDDEN per TZ-4 §8.3.1.\n"
        + "\n".join(offenders)
    )


