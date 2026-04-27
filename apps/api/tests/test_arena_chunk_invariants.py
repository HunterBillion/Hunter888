"""TZ-3 §16.4 / §19 risk #4 — AST guard against arena-chunk schema drift.

Mirrors the pattern from `test_client_domain_invariants.py`. Scans the
backend source for any LegalKnowledgeChunk(...) constructor or
setattr(chunk, "...", ...) using a kwarg name that is NOT a real ORM
column. If somebody re-introduces `title=` / `content=` /
`article_reference=` (the drift PR C5 just fixed), this test fires
**before** the bug ships to prod.

The allow-list is the canonical column set on
`apps/api/app/models/rag.py::LegalKnowledgeChunk` as of PR #54. Adding
a new column means updating the allow-list AND the Pydantic schema in
`apps/api/app/schemas/rop.py` — both intentional changes.

Why blocking: the previous deploy had `LegalKnowledgeChunk(title=...)`
in `create_chunk` for weeks and silently 500'd on every call (no
test coverage caught it because no test called the endpoint). This
guard makes the same bug class impossible to land again.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


# ── Allow-list of canonical column names (mirror of LegalKnowledgeChunk) ──

CANONICAL_CHUNK_COLUMNS: frozenset[str] = frozenset({
    # Identity
    "id",
    # Core content
    "category", "fact_text", "law_article",
    "common_errors", "match_keywords", "correct_response_hint",
    "error_frequency",
    # Difficulty / question generation
    "difficulty_level", "question_templates", "follow_up_questions",
    "related_chunk_ids",
    # Court practice
    "court_case_reference", "is_court_practice",
    # Blitz
    "blitz_question", "blitz_answer", "choices", "correct_choice_index",
    # Deep context
    "source_article_full_text",
    # Versioning / metadata
    "content_version", "knowledge_status", "status_reason",
    "last_verified_at", "embedding_model", "tags", "content_hash",
    "is_active",
    # Embeddings
    "embedding", "embedding_v2", "embedding_v2_model",
    # Stats
    "retrieval_count", "correct_answer_count", "incorrect_answer_count",
    "effectiveness_score", "last_used_at",
    # Timestamps
    "created_at", "updated_at",
    # TZ-4 D1 KnowledgeItem extension (alembic 20260427_001) — see
    # TZ-4 spec rev 2 §6.2.1. Added to allow-list so test_no_legal_
    # chunk_drift_kwargs_in_app_code accepts these column names when
    # D2/D4 services start writing them.
    "source_type", "title", "jurisdiction",
    "effective_from", "expires_at",
    "reviewed_by", "reviewed_at", "source_ref",
})


# Forbidden field names that have been seen as drift in the past.
# Keeping this explicit list separate from "anything not in the allow-
# list" gives a more actionable error message when the guard fires.
KNOWN_DRIFT_NAMES: frozenset[str] = frozenset({
    "title",            # was used as alias for `law_article`
    "content",          # was used as alias for `fact_text`
    "article_reference",  # was used as alias for `law_article`
})


# Files allowed to construct LegalKnowledgeChunk: the seed script (which
# is the source of truth for fixture rows), repair jobs, and the rop API
# handler that goes through the canonical Pydantic schema. Any other
# constructor site is a drift risk.
APP_DIR = Path(__file__).resolve().parent.parent / "app"


# ── AST visitors ────────────────────────────────────────────────────────────


class _ChunkConstructionVisitor(ast.NodeVisitor):
    """Find `LegalKnowledgeChunk(...)` calls and `setattr(x, "...", ...)`
    on objects that look like chunk variables."""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.violations: list[tuple[int, str, str]] = []  # (lineno, kwarg, snippet)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802 (ast API)
        # `LegalKnowledgeChunk(...)`
        is_chunk_ctor = (
            isinstance(node.func, ast.Name)
            and node.func.id == "LegalKnowledgeChunk"
        )
        if is_chunk_ctor:
            for kw in node.keywords:
                if kw.arg and kw.arg not in CANONICAL_CHUNK_COLUMNS:
                    self.violations.append((
                        node.lineno,
                        kw.arg,
                        f"LegalKnowledgeChunk({kw.arg}=…)",
                    ))

        # `setattr(chunk, "name", value)` — flag if "name" is not canonical
        if (
            isinstance(node.func, ast.Name)
            and node.func.id == "setattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            attr_name = node.args[1].value
            if attr_name in KNOWN_DRIFT_NAMES:
                self.violations.append((
                    node.lineno,
                    attr_name,
                    f'setattr(chunk, "{attr_name}", …)',
                ))

        self.generic_visit(node)


# ── The guard test ──────────────────────────────────────────────────────────


def _scan_file(file_path: Path) -> list[tuple[int, str, str]]:
    src = file_path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(file_path))
    v = _ChunkConstructionVisitor(file_path)
    v.visit(tree)
    return v.violations


def test_no_legal_chunk_drift_kwargs_in_app_code():
    """Scan every .py under apps/api/app/. Any LegalKnowledgeChunk(...)
    keyword that isn't a real ORM column → fail with a precise message
    pointing at the offender."""
    all_violations: list[str] = []
    for path in APP_DIR.rglob("*.py"):
        # Don't scan the model definition itself — it declares the columns.
        if path.name == "rag.py" and "models" in path.parts:
            continue
        for lineno, kwarg, snippet in _scan_file(path):
            rel = path.relative_to(APP_DIR.parent)
            all_violations.append(
                f"  {rel}:{lineno} — {snippet} (canonical name? "
                f"{'no' if kwarg in KNOWN_DRIFT_NAMES else 'unknown column'})"
            )

    if all_violations:
        pytest.fail(
            "LegalKnowledgeChunk drift detected. The following code "
            "passes a kwarg/setattr name that does NOT exist on the "
            "ORM model (apps/api/app/models/rag.py::LegalKnowledgeChunk):"
            f"\n\n{chr(10).join(all_violations)}\n\n"
            "Fix: route the write through "
            "apps/api/app/schemas/rop.py::ArenaChunk{Create,Update}Request "
            "and call .to_orm_kwargs() to translate aliases to canonical "
            "column names. See TZ-3 spec §12 / §14.5."
        )


# ── Sanity check on the allow-list itself ──────────────────────────────────


def test_canonical_column_list_matches_orm():
    """If somebody adds a column to LegalKnowledgeChunk but forgets to
    update the allow-list above, this test catches it. Guards against
    the inverse drift: false positives that block legit writes."""
    from app.models.rag import LegalKnowledgeChunk

    orm_columns = {c.name for c in LegalKnowledgeChunk.__table__.columns}
    missing_from_allowlist = orm_columns - CANONICAL_CHUNK_COLUMNS
    extra_in_allowlist = CANONICAL_CHUNK_COLUMNS - orm_columns

    assert not missing_from_allowlist, (
        "ORM has columns the allow-list doesn't know about — update "
        f"CANONICAL_CHUNK_COLUMNS in this file: {sorted(missing_from_allowlist)}"
    )
    assert not extra_in_allowlist, (
        "Allow-list has names that aren't real ORM columns — clean up: "
        f"{sorted(extra_in_allowlist)}"
    )
