"""Static invariants for the TZ-4 §10 conversation policy engine
(§13.2.1 forbidden list).

D5 made ``app.services.conversation_policy_engine`` the canonical
authority on the six §10.2 checks plus the system-prompt renderer.
Spec §13.2.1 explicitly forbids the legacy
``conversation_policy_prompt(mode)`` helper that hard-coded RU prompt
text — its removal is part of the D5 deliverable.

These tests fail the build the moment a future PR re-introduces the
removed function or imports the legacy facade for new code paths.
The fix is one of two:

  * Use ``conversation_policy_engine.render_prompt(mode=...)`` for
    prompt injection or
    ``conversation_policy_engine.audit_assistant_reply(...)`` for
    runtime audit; or
  * Get explicit TZ-4 §13.2.1 review approval and remove the file
    from the forbidden-list below.

Mirrors the AST-guard pattern from D2 (Attachment), D3 (MemoryPersona),
and D4 (knowledge_status).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parent.parent / "app"


# Modules allowed to define / re-export the engine surface. New
# producers go through the engine module instead of being added here.
ALLOWED_ENGINE_DEFINERS = {
    "app/services/conversation_policy_engine.py",
}

# The legacy facade module retains a deprecated `audit_assistant_reply`
# wrapper during the warn-only window. New imports of the legacy module
# are still flagged because D7 cutover removes it — so this set lists
# the modules that today legitimately still import from the legacy
# facade. Each entry is a tracked migration debt, not a permanent
# allow-list slot.
ALLOWED_LEGACY_FACADE_IMPORTERS: set[str] = set()


def _iter_python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def test_conversation_policy_prompt_is_removed_from_legacy_module():
    """§13.2.1 deletion: ``conversation_policy_prompt`` must not exist
    on ``app.services.conversation_policy``. The function was
    deleted in D5; this test catches a future revert.
    """
    from app.services import conversation_policy

    assert not hasattr(conversation_policy, "conversation_policy_prompt"), (
        "Legacy conversation_policy_prompt() is back. Per TZ-4 §13.2.1 "
        "this helper is forbidden — use "
        "conversation_policy_engine.render_prompt(mode=...) instead."
    )


def test_no_callers_of_removed_conversation_policy_prompt():
    """Sweep the source tree: nobody references ``conversation_policy_
    prompt`` by name. The string match is intentionally narrow (whole
    word) to avoid flagging the new ``render_prompt`` symbol or
    docstring text.
    """
    offenders: list[str] = []
    for file_path in _iter_python_files(APP_DIR):
        rel = file_path.relative_to(APP_DIR.parent).as_posix()
        if rel in ALLOWED_ENGINE_DEFINERS:
            continue
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            # Match `conversation_policy_prompt(...)` calls and
            # `from ... import conversation_policy_prompt` statements.
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "conversation_policy_prompt":
                    offenders.append(f"{rel}:{node.lineno} → call site")
                elif (
                    isinstance(func, ast.Attribute)
                    and func.attr == "conversation_policy_prompt"
                ):
                    offenders.append(f"{rel}:{node.lineno} → attribute access")
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "conversation_policy_prompt":
                        offenders.append(
                            f"{rel}:{node.lineno} → from-import of removed symbol"
                        )
    assert not offenders, (
        "Found references to the removed conversation_policy_prompt() "
        "helper. Use conversation_policy_engine.render_prompt instead:\n"
        + "\n".join(offenders)
    )


def test_audit_assistant_reply_callers_use_engine_module():
    """The deprecated facade at ``conversation_policy.audit_assistant_
    reply`` must not gain new callers — D7 cutover removes it. Every
    audit caller goes through ``conversation_policy_engine``.

    The :data:`ALLOWED_LEGACY_FACADE_IMPORTERS` set is the migration-
    debt allow-list; each entry tracks a specific module that hasn't
    moved yet. Adding a new entry requires explicit TZ-4 §13.2.1 review.
    """
    offenders: list[str] = []
    for file_path in _iter_python_files(APP_DIR):
        rel = file_path.relative_to(APP_DIR.parent).as_posix()
        if rel in ALLOWED_ENGINE_DEFINERS:
            continue
        if rel in ALLOWED_LEGACY_FACADE_IMPORTERS:
            continue
        if rel == "app/services/conversation_policy.py":
            # The facade module itself imports from the engine — that's
            # the whole point of the wrapper; skip it.
            continue
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            module = node.module or ""
            if module != "app.services.conversation_policy":
                continue
            for alias in node.names:
                if alias.name == "audit_assistant_reply":
                    offenders.append(
                        f"{rel}:{node.lineno} → "
                        "from app.services.conversation_policy import "
                        "audit_assistant_reply"
                    )
    assert not offenders, (
        "New caller of the deprecated conversation_policy.audit_assistant_reply "
        "facade. Import from conversation_policy_engine instead — the engine "
        "version supports the three persona-aware checks D5 added.\n"
        + "\n".join(offenders)
    )
