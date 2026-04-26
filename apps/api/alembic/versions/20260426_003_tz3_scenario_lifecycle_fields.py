"""TZ-3 C1: scenario lifecycle fields on templates + versions.

Revision ID: 20260426_003
Revises: 20260426_002
Create Date: 2026-04-26

Phase 1 of TZ-3 (Constructor & ScenarioVersion Contracts). See
``docs/TZ-3_constructor_scenario_version_contracts.md`` §14.1 for the
full field table — this file implements that table verbatim.

Adds the lifecycle metadata that subsequent phases (C2 publisher,
C3 runtime resolver, C4 FE constructor) require:

  scenario_templates:
    + status                       VARCHAR(20) NOT NULL DEFAULT 'published'
                                   CHECK in {draft, published, archived}
    + draft_revision               INTEGER NOT NULL DEFAULT 0
    + current_published_version_id UUID NULL FK→scenario_versions(id) ON DELETE SET NULL

  scenario_versions:
    + schema_version               INTEGER NOT NULL DEFAULT 1
    + content_hash                 VARCHAR(64) NULL  (SET NOT NULL on the
                                                      backfilled rows in
                                                      this same migration)
    + validation_report            JSONB NOT NULL DEFAULT '{"backfilled":true,"issues":[]}'

Backfill
--------
* ``status`` and ``draft_revision`` get sane defaults via server_default —
  no UPDATE needed (matches §14.1 — existing templates are treated as
  ``published`` with revision ``0``).
* ``current_published_version_id`` is filled from the deterministic v1
  rows that migration ``20260423_002`` already minted (one v1
  ScenarioVersion per active template, deterministic UUID derived from
  template_id). The UPDATE uses the same MD5-on-template_id pattern as
  the source migration (lines 69-75 of 20260423_002) so both writes
  produce identical UUIDs and the FK resolves cleanly.
* ``schema_version`` defaults to 1 — every existing v1 row was authored
  before per-version schema versioning existed.
* ``content_hash`` is recomputed for every existing version row as the
  hex SHA256 of ``snapshot::text``. Deterministic and re-runnable.
  After backfill, the column is set NOT NULL — future versions are
  required to supply it (the publisher in PR C2 will compute it).
* ``validation_report`` defaults to ``{"backfilled":true,"issues":[]}``
  so the column shape is consistent (the field is always present, the
  flag tells consumers "this row was not validated by the new validator").

Indexes
-------
* ``ix_scenario_templates_status`` — needed by the publisher's
  "list active drafts" query.
* No new index on ``current_published_version_id`` — the column is
  consulted only by primary-key lookup on ``scenario_versions.id``,
  which already has the PK index.

Down migration
--------------
Reverses each ALTER. ``DROP COLUMN`` works in Postgres without locking
on a small pilot dataset (no production-scale concern at the current
~70 templates).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260426_003"
down_revision: Union[str, Sequence[str], None] = "20260426_002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Helpers ─────────────────────────────────────────────────────────────────


def _column_exists(table_name: str, column_name: str) -> bool:
    conn = op.get_bind()
    return bool(conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :table_name AND column_name = :column_name"
    ), {"table_name": table_name, "column_name": column_name}).fetchone())


def _constraint_exists(constraint_name: str) -> bool:
    conn = op.get_bind()
    return bool(conn.execute(sa.text(
        "SELECT 1 FROM information_schema.table_constraints "
        "WHERE constraint_name = :name"
    ), {"name": constraint_name}).fetchone())


def _index_exists(index_name: str) -> bool:
    conn = op.get_bind()
    return bool(conn.execute(sa.text(
        "SELECT 1 FROM pg_indexes WHERE indexname = :name"
    ), {"name": index_name}).fetchone())


# ── Upgrade ────────────────────────────────────────────────────────────────


def upgrade() -> None:
    # ── scenario_templates ─────────────────────────────────────────────
    if not _column_exists("scenario_templates", "status"):
        op.add_column(
            "scenario_templates",
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                server_default="published",
            ),
        )
    if not _constraint_exists("ck_scenario_templates_status_lattice"):
        op.create_check_constraint(
            "ck_scenario_templates_status_lattice",
            "scenario_templates",
            "status IN ('draft', 'published', 'archived')",
        )
    if not _index_exists("ix_scenario_templates_status"):
        op.create_index(
            "ix_scenario_templates_status",
            "scenario_templates",
            ["status"],
        )

    if not _column_exists("scenario_templates", "draft_revision"):
        op.add_column(
            "scenario_templates",
            sa.Column(
                "draft_revision",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )

    if not _column_exists("scenario_templates", "current_published_version_id"):
        op.add_column(
            "scenario_templates",
            sa.Column(
                "current_published_version_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
        )
        op.create_foreign_key(
            "fk_scenario_templates_current_published_version_id",
            "scenario_templates",
            "scenario_versions",
            ["current_published_version_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # Backfill current_published_version_id from the deterministic v1 rows
    # minted by migration 20260423_002 (lines 69-75). Must use the same
    # MD5-on-template_id hashing so the UUID matches what's already in
    # the scenario_versions table.
    op.execute(sa.text("""
        UPDATE scenario_templates st
        SET current_published_version_id = (
            substr(md5(st.id::text || ':scenario_version:v1'), 1, 8) || '-' ||
            substr(md5(st.id::text || ':scenario_version:v1'), 9, 4) || '-' ||
            substr(md5(st.id::text || ':scenario_version:v1'), 13, 4) || '-' ||
            substr(md5(st.id::text || ':scenario_version:v1'), 17, 4) || '-' ||
            substr(md5(st.id::text || ':scenario_version:v1'), 21, 12)
        )::uuid
        WHERE st.current_published_version_id IS NULL
          AND EXISTS (
            SELECT 1 FROM scenario_versions sv
            WHERE sv.template_id = st.id
              AND sv.version_number = 1
          )
    """))

    # ── scenario_versions ──────────────────────────────────────────────
    if not _column_exists("scenario_versions", "schema_version"):
        op.add_column(
            "scenario_versions",
            sa.Column(
                "schema_version",
                sa.Integer(),
                nullable=False,
                server_default="1",
            ),
        )

    if not _column_exists("scenario_versions", "validation_report"):
        # Two-step add: nullable + server_default '{}' (cannot use the
        # full literal here — sqlalchemy.text() parses `:key` inside the
        # JSON as a bind-parameter, which silently substitutes NULL and
        # crashes alembic with "invalid input syntax for type json"
        # — caught by CI on PR #50 attempt 1, see commit message).
        # Real default is set by the UPDATE below; column is then SET
        # NOT NULL so future inserts must supply a value.
        op.add_column(
            "scenario_versions",
            sa.Column(
                "validation_report",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )
        # Bind the JSON via a parameter so the parser doesn't trip on
        # `:true` inside the literal (caught by CI on PR #50 attempts
        # 1 and 2). asyncpg sends the value as a real bytea parameter,
        # bypassing JSON-in-SQL-literal entirely.
        op.execute(
            sa.text("""
                UPDATE scenario_versions
                SET validation_report = CAST(:report AS jsonb)
                WHERE validation_report IS NULL
                   OR validation_report = '{}'::jsonb
            """).bindparams(report='{"backfilled":true,"issues":[]}')
        )
        op.alter_column(
            "scenario_versions",
            "validation_report",
            existing_type=postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        )

    if not _column_exists("scenario_versions", "content_hash"):
        # Add nullable first → backfill → SET NOT NULL.
        op.add_column(
            "scenario_versions",
            sa.Column("content_hash", sa.String(length=64), nullable=True),
        )
        # Backfill strategy:
        #   * Try SHA256 via pgcrypto — content_hash is 64 hex chars wide,
        #     matches SHA256, and the future publisher writes SHA256 too.
        #   * If pgcrypto isn't installed (verified on prod 2026-04-26 it
        #     is NOT — both extensions list returned 0 rows), fall back
        #     to ``CREATE EXTENSION IF NOT EXISTS pgcrypto``. The trainer
        #     DB role owns the database and can install extensions on
        #     this single-tenant deployment.
        #   * Final fallback: MD5 zero-padded to 64 chars. Used only if
        #     extension creation also fails (e.g. read-only role).
        #     MD5 is cryptographically weak — but for backfill of
        #     historical rows where the content is already trusted, the
        #     hash is just a content-equality fingerprint, not a
        #     security boundary. New rows from PR C2 will always be
        #     SHA256 because the publisher checks the extension
        #     availability at startup.
        op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        op.execute(sa.text("""
            UPDATE scenario_versions
            SET content_hash = encode(digest(snapshot::text, 'sha256'), 'hex')
            WHERE content_hash IS NULL
        """))
        # Defensive: if any rows still have NULL (extension creation
        # silently no-op'd on a hardened DB), fall back to MD5-padded.
        op.execute(sa.text("""
            UPDATE scenario_versions
            SET content_hash = lpad(md5(snapshot::text), 64, '0')
            WHERE content_hash IS NULL
        """))
        # Now lock it down.
        op.alter_column(
            "scenario_versions",
            "content_hash",
            existing_type=sa.String(length=64),
            nullable=False,
        )


# ── Downgrade ──────────────────────────────────────────────────────────────


def downgrade() -> None:
    # scenario_versions
    if _column_exists("scenario_versions", "content_hash"):
        op.drop_column("scenario_versions", "content_hash")
    if _column_exists("scenario_versions", "validation_report"):
        op.drop_column("scenario_versions", "validation_report")
    if _column_exists("scenario_versions", "schema_version"):
        op.drop_column("scenario_versions", "schema_version")

    # scenario_templates
    if _column_exists("scenario_templates", "current_published_version_id"):
        op.drop_constraint(
            "fk_scenario_templates_current_published_version_id",
            "scenario_templates",
            type_="foreignkey",
        )
        op.drop_column("scenario_templates", "current_published_version_id")
    if _column_exists("scenario_templates", "draft_revision"):
        op.drop_column("scenario_templates", "draft_revision")
    if _index_exists("ix_scenario_templates_status"):
        op.drop_index("ix_scenario_templates_status", table_name="scenario_templates")
    if _constraint_exists("ck_scenario_templates_status_lattice"):
        op.drop_constraint(
            "ck_scenario_templates_status_lattice",
            "scenario_templates",
            type_="check",
        )
    if _column_exists("scenario_templates", "status"):
        op.drop_column("scenario_templates", "status")
