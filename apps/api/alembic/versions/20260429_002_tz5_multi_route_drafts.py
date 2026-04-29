"""TZ-5 PR-2 — multi-route import drafts (scenario / character / arena_knowledge)

Revision ID: 20260429_002
Revises: 20260429_001
Create Date: 2026-04-29

Background
----------

PR-1 (`20260429_001`) shipped a single-route ``scenario_drafts`` table that
only ever produces a ``ScenarioTemplate``. Per product feedback, ROP/admin
uploads should be auto-classified into THREE branches:

  * ``scenario``         — turns into ``ScenarioTemplate`` (existing path)
  * ``character``        — turns into a custom_character (training builder)
  * ``arena_knowledge``  — turns into ``LegalKnowledgeChunk`` (RAG/quiz)

A single-table approach (``scenario_drafts``) is kept because the lifecycle
is identical across branches: extracting → ready → edited → converted/discarded
/failed. Only the target table changes. We add a discriminator column
``route_type`` and a target-pointer column ``target_id`` (UUID, polymorphic
— validated at the application layer per ``route_type``).

Re-runnability
--------------

Idempotent column adds via inspector check. ``route_type`` defaults to
``scenario`` for any pre-existing PR-1 rows so the new code paths see a
consistent value. Constraint added behind an existence guard.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260429_002"
down_revision: Union[str, Sequence[str], None] = "20260429_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CK_ROUTE_TYPE = "ck_scenario_drafts_route_type"
ROUTE_TYPES = ("scenario", "character", "arena_knowledge")


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    return (
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = current_schema() "
                "  AND table_name = :t AND column_name = :c LIMIT 1"
            ),
            {"t": table, "c": column},
        ).scalar()
        is not None
    )


def _constraint_exists(name: str) -> bool:
    bind = op.get_bind()
    return (
        bind.execute(
            sa.text("SELECT 1 FROM pg_constraint WHERE conname = :name LIMIT 1"),
            {"name": name},
        ).scalar()
        is not None
    )


def upgrade() -> None:
    bind = op.get_bind()

    # ── route_type discriminator ───────────────────────────────────────
    if not _column_exists("scenario_drafts", "route_type"):
        op.add_column(
            "scenario_drafts",
            sa.Column(
                "route_type",
                sa.String(length=30),
                nullable=False,
                server_default="scenario",
            ),
        )
        op.create_index(
            "ix_scenario_drafts_route_type",
            "scenario_drafts",
            ["route_type"],
        )

    # Backfill: existing PR-1 rows are all scenario-type.
    bind.execute(
        sa.text(
            "UPDATE scenario_drafts SET route_type = 'scenario' "
            "WHERE route_type IS NULL OR route_type = ''"
        )
    )

    # CHECK constraint so a typo at the app layer can't sneak in.
    if not _constraint_exists(CK_ROUTE_TYPE):
        op.create_check_constraint(
            CK_ROUTE_TYPE,
            "scenario_drafts",
            f"route_type IN {ROUTE_TYPES}",
        )

    # ── target_id polymorphic pointer ──────────────────────────────────
    # FK is intentionally NOT enforced at the SQL level because the target
    # table varies by route_type (scenario_templates / custom_characters /
    # legal_knowledge_chunks). Validated in app/api/rop.py before write.
    if not _column_exists("scenario_drafts", "target_id"):
        op.add_column(
            "scenario_drafts",
            sa.Column(
                "target_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
        )

    # ── original_confidence (audit invariant) ──────────────────────────
    # PR-1.1 audit fix C7 — keep the LLM's original confidence separate
    # from the editable column so an audit can detect "ROP raised the
    # confidence to publish a hallucinated draft".
    if not _column_exists("scenario_drafts", "original_confidence"):
        op.add_column(
            "scenario_drafts",
            sa.Column(
                "original_confidence",
                sa.Float(),
                nullable=True,
            ),
        )
        # Backfill: copy current confidence to original_confidence for
        # PR-1 rows that never had a separate "what the LLM thought"
        # column.
        bind.execute(
            sa.text(
                "UPDATE scenario_drafts "
                "SET original_confidence = confidence "
                "WHERE original_confidence IS NULL"
            )
        )


def downgrade() -> None:
    if _column_exists("scenario_drafts", "original_confidence"):
        op.drop_column("scenario_drafts", "original_confidence")
    if _column_exists("scenario_drafts", "target_id"):
        op.drop_column("scenario_drafts", "target_id")
    if _constraint_exists(CK_ROUTE_TYPE):
        op.drop_constraint(CK_ROUTE_TYPE, "scenario_drafts", type_="check")
    if _column_exists("scenario_drafts", "route_type"):
        op.drop_index("ix_scenario_drafts_route_type", table_name="scenario_drafts")
        op.drop_column("scenario_drafts", "route_type")
