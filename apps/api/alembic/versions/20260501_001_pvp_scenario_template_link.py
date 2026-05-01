"""Content→Arena PR-2 — link PvPDuel rows to ScenarioTemplate / ScenarioVersion

Revision ID: 20260501_001
Revises: 20260429_002
Create Date: 2026-05-01

Background
----------

Today the arena (`ws/pvp.py::_load_duel_context`) picks a random row from the
legacy ``scenarios`` table — completely unaware of the TZ-3 publish flow that
governs ``scenario_templates`` / ``scenario_versions``. As a result, when a
ROP/admin imports a scenario via the methodology panel (TZ-5 PR-1, multi-route
classifier from PR-2), the resulting ``ScenarioTemplate`` exists but **never
shows up in any PvP/PvE duel** — the importer hits a dead end.

This migration adds two nullable FKs to ``pvp_duels``:

  * ``scenario_template_id``  → ``scenario_templates.id`` (ON DELETE SET NULL)
  * ``scenario_version_id``   → ``scenario_versions.id``  (ON DELETE SET NULL)

so a duel can carry the canonical content reference. PR-2 application code
will resolve the snapshot via ``scenario_runtime_resolver.resolve_for_runtime``
when ``scenario_version_id`` is set; legacy duels (both columns NULL) keep
working through the legacy ``scenarios`` table fallback in ``_load_duel_context``.

Why two columns and not just version_id
---------------------------------------

The version_id is what we *actually* render (immutable snapshot — TZ-3
invariant 4). The template_id is what we picked (mutable pointer to "current
published version"). Recording both lets analytics answer "how many duels were
on template X" without joining ``scenario_versions`` first, and detect drift
("template now points to v3 but this duel was on v2") cheaply.

Re-runnability
--------------

Idempotent column adds + idempotent FK constraints behind existence guards.
Both columns ``nullable=True`` with no backfill — existing duels stay NULL.
Indexes added so analytics queries can filter by template without a seq-scan.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260501_001"
down_revision: Union[str, Sequence[str], None] = "20260429_002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FK_TEMPLATE = "fk_pvp_duels_scenario_template_id"
FK_VERSION = "fk_pvp_duels_scenario_version_id"
IX_TEMPLATE = "ix_pvp_duels_scenario_template_id"
IX_VERSION = "ix_pvp_duels_scenario_version_id"


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


def _index_exists(name: str) -> bool:
    bind = op.get_bind()
    return (
        bind.execute(
            sa.text(
                "SELECT 1 FROM pg_indexes WHERE schemaname = current_schema() "
                "  AND indexname = :name LIMIT 1"
            ),
            {"name": name},
        ).scalar()
        is not None
    )


def upgrade() -> None:
    if not _column_exists("pvp_duels", "scenario_template_id"):
        op.add_column(
            "pvp_duels",
            sa.Column(
                "scenario_template_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
        )
    if not _index_exists(IX_TEMPLATE):
        op.create_index(IX_TEMPLATE, "pvp_duels", ["scenario_template_id"])
    if not _constraint_exists(FK_TEMPLATE):
        op.create_foreign_key(
            FK_TEMPLATE,
            "pvp_duels",
            "scenario_templates",
            ["scenario_template_id"],
            ["id"],
            ondelete="SET NULL",
        )

    if not _column_exists("pvp_duels", "scenario_version_id"):
        op.add_column(
            "pvp_duels",
            sa.Column(
                "scenario_version_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
        )
    if not _index_exists(IX_VERSION):
        op.create_index(IX_VERSION, "pvp_duels", ["scenario_version_id"])
    if not _constraint_exists(FK_VERSION):
        op.create_foreign_key(
            FK_VERSION,
            "pvp_duels",
            "scenario_versions",
            ["scenario_version_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    if _constraint_exists(FK_VERSION):
        op.drop_constraint(FK_VERSION, "pvp_duels", type_="foreignkey")
    if _index_exists(IX_VERSION):
        op.drop_index(IX_VERSION, table_name="pvp_duels")
    if _column_exists("pvp_duels", "scenario_version_id"):
        op.drop_column("pvp_duels", "scenario_version_id")

    if _constraint_exists(FK_TEMPLATE):
        op.drop_constraint(FK_TEMPLATE, "pvp_duels", type_="foreignkey")
    if _index_exists(IX_TEMPLATE):
        op.drop_index(IX_TEMPLATE, table_name="pvp_duels")
    if _column_exists("pvp_duels", "scenario_template_id"):
        op.drop_column("pvp_duels", "scenario_template_id")
