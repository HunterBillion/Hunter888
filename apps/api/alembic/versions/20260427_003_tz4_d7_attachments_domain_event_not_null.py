"""TZ-4 D7.3 — promote ``attachments.domain_event_id`` to NOT NULL

Revision ID: 20260427_003
Revises: 20260427_002
Create Date: 2026-04-27

D1 added the column nullable so the legacy backfill path could
land synthetic events for pre-existing attachment rows. D7.3 (this
migration) promotes the column to NOT NULL once two prerequisites
are met:

  1. ``attachment_pipeline.ingest_upload`` was refactored to the
     emit-first pattern: pre-generate the attachment uuid, emit
     the canonical event with that aggregate_id, INSERT the row
     with ``domain_event_id`` already set. Both writes are in the
     same savepoint so a dedup-race ``IntegrityError`` rolls back
     both — no orphan event in the canonical log.

  2. Production inventory at PR time confirmed zero orphan rows
     (``COUNT(*) FILTER (WHERE domain_event_id IS NULL)`` = 0).

The migration also re-runs a defensive repair INSERT/UPDATE pair
before the ALTER so dev / staging environments seeded with legacy
data don't fail mid-flight: any orphan with ``lead_client_id IS
NOT NULL`` gets a synthetic ``attachment.uploaded`` event linked
back. Rows that genuinely cannot be anchored (NULL lead) are
flagged with a hard error so the operator decides what to do —
hard-deleting silently is worse than failing loudly.

Re-runnability: the ALTER is a no-op if the column is already
NOT NULL (idempotent guard via ``information_schema``). The
repair INSERT is keyed on a stable idempotency key
(``attachment-backfill-d7:<id>``) so a re-run only touches
genuinely new orphans.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260427_003"
down_revision: Union[str, Sequence[str], None] = "20260427_002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_is_nullable(table: str, column: str) -> bool:
    bind = op.get_bind()
    row = bind.execute(
        sa.text(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = :table AND column_name = :column"
        ),
        {"table": table, "column": column},
    ).first()
    if row is None:
        return False
    return str(row[0]).upper() == "YES"


def upgrade() -> None:
    bind = op.get_bind()

    # Step 1 — defensive repair for any orphan rows with a lead
    # anchor. Mirrors the D1 backfill pattern but scoped to the
    # residual set still NULL at migration time. ``source`` is
    # tagged so the audit log can tell this batch apart from the
    # original D1 backfill.
    bind.execute(
        sa.text(
            """
            INSERT INTO domain_events (
                id, lead_client_id, event_type, aggregate_type, aggregate_id,
                session_id, source, actor_type, actor_id, occurred_at,
                payload_json, idempotency_key, correlation_id, schema_version
            )
            SELECT
                gen_random_uuid(),
                a.lead_client_id,
                'attachment.uploaded',
                'attachment',
                a.id,
                a.session_id,
                'backfill_d7_promote',
                'system',
                NULL,
                a.created_at,
                jsonb_build_object(
                    'attachment_id', a.id,
                    'sha256', a.sha256,
                    'filename', a.filename,
                    'backfilled_at', NOW(),
                    'reason', 'D7.3 NOT NULL promote — orphan repair'
                ),
                'attachment-backfill-d7:' || a.id::text,
                a.id::text,
                1
            FROM attachments a
            WHERE a.domain_event_id IS NULL
              AND a.lead_client_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM domain_events de
                  WHERE de.idempotency_key =
                      'attachment-backfill-d7:' || a.id::text
              )
            """
        )
    )

    bind.execute(
        sa.text(
            """
            UPDATE attachments
            SET domain_event_id = de.id
            FROM domain_events de
            WHERE attachments.domain_event_id IS NULL
              AND de.idempotency_key =
                  'attachment-backfill-d7:' || attachments.id::text
            """
        )
    )

    # Step 2 — sanity check: refuse to ALTER if any orphans
    # remain. The §12.1.1 backfill skip rule (NULL lead) is the
    # only legitimate orphan class — those need an operator
    # decision before NOT NULL is safe. Failing loudly keeps the
    # operator in the loop.
    remaining = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM attachments WHERE domain_event_id IS NULL"
        )
    ).scalar_one()
    if remaining and int(remaining) > 0:
        raise RuntimeError(
            "Cannot promote attachments.domain_event_id to NOT NULL: "
            f"{remaining} orphan rows remain (lead_client_id IS NULL). "
            "Hard-delete the orphans under operator supervision or "
            "rebind them to a fallback lead_client first."
        )

    # Step 3 — promote. Idempotent.
    if _column_is_nullable("attachments", "domain_event_id"):
        op.alter_column(
            "attachments",
            "domain_event_id",
            nullable=False,
            existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        )


def downgrade() -> None:
    if not _column_is_nullable("attachments", "domain_event_id"):
        op.alter_column(
            "attachments",
            "domain_event_id",
            nullable=True,
            existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        )
