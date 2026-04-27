"""Static invariants for the TZ-4 §10 conversation policy engine
(§13.2.1 forbidden list).

D5 made ``app.services.conversation_policy_engine`` the canonical
authority on the six §10.2 checks plus the system-prompt renderer.
Spec §13.2.1 explicitly forbids the legacy
``conversation_policy_prompt(mode)`` helper that hard-coded RU prompt
text; D7 finishes the cutover by deleting the deprecated facade
module ``app.services.conversation_policy`` entirely.

These tests fail the build the moment a future PR re-introduces the
removed function or the removed module. The fix is one of two:

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


def _iter_python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def test_legacy_conversation_policy_module_is_removed():
    """D7 §22 cutover: the deprecated ``app.services.conversation_policy``
    facade is deleted entirely. A revert that re-creates the module
    should fail this test.
    """
    legacy_path = APP_DIR / "services" / "conversation_policy.py"
    assert not legacy_path.exists(), (
        f"Legacy module {legacy_path.relative_to(APP_DIR.parent)} is back. "
        "Per TZ-4 §13.2.1 / §22 D7 cutover this facade is removed — "
        "import from conversation_policy_engine instead."
    )

    # Module-level import should also fail at runtime, regardless of
    # whether the file is present in some leftover branch.
    with pytest.raises(ModuleNotFoundError):
        __import__("app.services.conversation_policy")


def test_no_callers_of_removed_conversation_policy_prompt():
    """Sweep the source tree: nobody references the removed
    ``conversation_policy_prompt`` symbol by name. The string match is
    intentionally narrow (whole word) to avoid flagging the new
    ``render_prompt`` symbol or docstring text.
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


def test_no_imports_of_removed_legacy_module():
    """No file imports from the removed ``app.services.conversation_policy``
    module. Ensures D7's deletion is permanent.
    """
    offenders: list[str] = []
    for file_path in _iter_python_files(APP_DIR):
        rel = file_path.relative_to(APP_DIR.parent).as_posix()
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "app.services.conversation_policy":
                    offenders.append(
                        f"{rel}:{node.lineno} → from app.services.conversation_policy import …"
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "app.services.conversation_policy":
                        offenders.append(
                            f"{rel}:{node.lineno} → import app.services.conversation_policy"
                        )
    assert not offenders, (
        "Import of the removed legacy facade. Use "
        "conversation_policy_engine instead.\n" + "\n".join(offenders)
    )
