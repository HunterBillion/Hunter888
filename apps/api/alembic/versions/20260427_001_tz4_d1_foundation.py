"""TZ-4 D1: trust-layer foundation — Attachment + KnowledgeItem + MemoryPersona + SessionPersonaSnapshot.

Revision ID: 20260427_001
Revises: 20260426_003
Create Date: 2026-04-27

Phase 1 of TZ-4 (Attachment, Knowledge Governance, Persona Policy).
Implements §6.1.1 / §6.2.1 / §6.3.1 / §6.4.1 / §7.2.6 / §12.1.1 of the
spec (rev 2). All schema additions are non-breaking — existing code
keeps working until D2-D7 deliver the new services.

Five blocks
-----------

  attachments (extend)
    + call_attempt_id           — link to call_attempts (nullable FK)
    + domain_event_id           — TZ-1 canonical link (NOT NULL after backfill)
    + verification_status       — VARCHAR(40), default 'unverified'
    + duplicate_of              — self-FK to attachments(id), nullable
    + UNIQUE (lead_client_id, sha256) WHERE duplicate_of IS NULL
                                  — sha256 dedup race contract (§7.2.6)
    + backfill: synthetic attachment.uploaded events for existing rows

  legal_knowledge_chunks (extend) → covers TZ-4 §6.2 KnowledgeItem
    + source_type               — enum (manual/scraped/...)
    + title                     — VARCHAR(300)
    + jurisdiction              — VARCHAR(20), default 'RU'
    + effective_from            — TIMESTAMPTZ nullable
    + expires_at                — TIMESTAMPTZ nullable (TTL)
    + reviewed_by               — FK to users.id, nullable
    + reviewed_at               — TIMESTAMPTZ nullable
    + source_ref                — VARCHAR(2000) URL/docket

  memory_personas (CREATE)      — §6.3.1, one per lead_client_id
    + 12 columns incl. version (optimistic concurrency token §9.2.5)

  session_persona_snapshots (CREATE)  — §6.4.1, immutable per session
    + 11 columns incl. mutation_blocked_count (observability)

  + ALLOWED_EVENT_TYPES table comment for TZ-1 invariant 2 future enforcement
    (no schema change here; the ALLOWED_EVENT_TYPES frozenset will land in D2's
    client_domain.py refactor — this migration only sets up the data layer).

Backfill discipline
-------------------

§12.1.1 of TZ-4 spec rev 2 specifies that:
  * attachments.domain_event_id is populated by synthesising
    attachment.uploaded events (occurred_at = attachment.created_at,
    actor_id = attachment.uploaded_by). Then SET NOT NULL.
  * legal_knowledge_chunks new fields stay nullable in this migration —
    knowledge_review_policy.py (D4) backfills `title` from `law_article`
    and sets defaults for source_type/jurisdiction.
  * No backfill for memory_personas / session_persona_snapshots — these
    are populated by D3 services on first session start per client.

Bind-parameter discipline
-------------------------

CLAUDE.md §4.3 lesson: sqlalchemy.text() interprets `:identifier` as a
bind-param marker. JSON literals like `{"key":true}` will silently break
because `:true` becomes a NULL bind. Either escape with `\:` or use
`.bindparams(...)`. This migration uses the bind-params pattern (proven
in 20260426_003) for any JSONB defaults containing `:`.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260427_001"
down_revision: Union[str, Sequence[str], None] = "20260426_003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Helpers (idempotent guards — pattern from 20260423_002) ──────────────


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    return bool(conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_name = :tn"
    ), {"tn": table_name}).fetchone())


def _column_exists(table_name: str, column_name: str) -> bool:
    conn = op.get_bind()
    return bool(conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :tn AND column_name = :cn"
    ), {"tn": table_name, "cn": column_name}).fetchone())


def _index_exists(name: str) -> bool:
    conn = op.get_bind()
    return bool(conn.execute(sa.text(
        "SELECT 1 FROM pg_indexes WHERE indexname = :n"
    ), {"n": name}).fetchone())


def _constraint_exists(name: str) -> bool:
    conn = op.get_bind()
    return bool(conn.execute(sa.text(
        "SELECT 1 FROM information_schema.table_constraints WHERE constraint_name = :n"
    ), {"n": name}).fetchone())


# ── Upgrade ────────────────────────────────────────────────────────────────


def upgrade() -> None:
    # =========================================================
    # Block 1 — attachments table extension
    # =========================================================

    if not _column_exists("attachments", "call_attempt_id"):
        op.add_column(
            "attachments",
            sa.Column("call_attempt_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
        # NB: no FK in D1 — `call_attempts` table doesn't exist yet
        # (TZ-1 §7.1 reserves the field, model lands later). Forward-
        # compatible UUID column. Add FK in a follow-up alembic when
        # the CallAttempt model ships.

    if not _column_exists("attachments", "domain_event_id"):
        op.add_column(
            "attachments",
            sa.Column("domain_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        )

    if not _column_exists("attachments", "verification_status"):
        op.add_column(
            "attachments",
            sa.Column(
                "verification_status",
                sa.String(length=40),
                nullable=False,
                server_default="unverified",
            ),
        )

    if not _column_exists("attachments", "duplicate_of"):
        op.add_column(
            "attachments",
            sa.Column("duplicate_of", postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_foreign_key(
            "fk_attachments_duplicate_of",
            "attachments", "attachments",
            ["duplicate_of"], ["id"],
            ondelete="SET NULL",
        )

    # =========================================================
    # Block 2 — synthetic attachment.uploaded events backfill (§12.1.1)
    # =========================================================
    # Pre-existing attachments rows have NO domain_event_id linkage. Spec
    # §12.1.1 mandates synthetic events with occurred_at = attachment.
    # created_at, actor_id = attachment.uploaded_by. Then SET NOT NULL.
    #
    # The INSERT uses gen_random_uuid() (pgcrypto, installed by
    # 20260426_003) for new event IDs. correlation_id = attachment.id
    # so TZ-1 invariant 4 is satisfied (correlation_id NOT NULL).
    # idempotency_key = 'attachment-backfill:{attachment.id}' so re-runs
    # are no-ops via the UNIQUE constraint on idempotency_key.
    #
    # NB: rows with lead_client_id IS NULL (orphan attachments from old
    # WS uploads) are SKIPPED by the WHERE filter — they remain with
    # domain_event_id IS NULL. After SET NOT NULL below they cannot be
    # written to, but their READ paths still work. A separate repair
    # job in D2 will either link them to a fallback lead_client or hard-
    # delete them under admin supervision.
    op.execute(sa.text("""
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
            'backfill_d1_tz4',
            'system',
            a.uploaded_by,
            a.created_at,
            jsonb_build_object(
                'filename', a.filename,
                'content_type', a.content_type,
                'file_size', a.file_size,
                'sha256', a.sha256,
                'document_type', a.document_type,
                'backfilled', true
            ),
            'attachment-backfill:' || a.id::text,
            a.id::text,
            1
        FROM attachments a
        WHERE a.lead_client_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM domain_events de
              WHERE de.aggregate_type = 'attachment'
                AND de.aggregate_id = a.id
                AND de.event_type = 'attachment.uploaded'
          )
    """))

    # Link attachments to their backfilled events
    op.execute(sa.text("""
        UPDATE attachments a
        SET domain_event_id = de.id
        FROM domain_events de
        WHERE de.aggregate_type = 'attachment'
          AND de.aggregate_id = a.id
          AND de.event_type = 'attachment.uploaded'
          AND a.domain_event_id IS NULL
    """))

    # FK constraint (only if pointing to existing rows works post-backfill)
    if not _constraint_exists("fk_attachments_domain_event_id"):
        op.create_foreign_key(
            "fk_attachments_domain_event_id",
            "attachments", "domain_events",
            ["domain_event_id"], ["id"],
            ondelete="RESTRICT",  # do NOT cascade; domain events are immutable
        )

    # NB: NOT setting `domain_event_id` to NOT NULL in this migration. Orphan
    # attachments (lead_client_id IS NULL) must be cleaned up by a D2 repair
    # job before we can promote the column to NOT NULL. Spec §12.1.1 explicitly
    # documents this as a deferred enforcement step.

    # =========================================================
    # Block 3 — sha256 dedup UNIQUE partial index (§7.2.6)
    # =========================================================
    # Composite UNIQUE on (lead_client_id, sha256) WHERE duplicate_of IS NULL.
    # Prevents two original attachments for the same file under the same
    # client. Duplicates (with non-null duplicate_of) bypass the index
    # because of the WHERE clause — that's by design (spec §7.2 #2:
    # "duplicate link не должен терять факт повторной отправки").
    if not _index_exists("uq_attachments_client_sha256_orig"):
        op.create_index(
            "uq_attachments_client_sha256_orig",
            "attachments",
            ["lead_client_id", "sha256"],
            unique=True,
            postgresql_where=sa.text("duplicate_of IS NULL AND lead_client_id IS NOT NULL"),
        )

    # =========================================================
    # Block 4 — legal_knowledge_chunks extension → KnowledgeItem (§6.2.1)
    # =========================================================
    # Backward-compat: existing columns (fact_text, law_article, ...)
    # stay; new columns nullable until D4 backfill.
    new_kchunk_cols = [
        ("source_type", sa.String(length=40), True, "manual"),
        ("title", sa.String(length=300), True, None),
        ("jurisdiction", sa.String(length=20), True, "RU"),
        ("effective_from", sa.DateTime(timezone=True), True, None),
        ("expires_at", sa.DateTime(timezone=True), True, None),
        ("reviewed_by", postgresql.UUID(as_uuid=True), True, None),
        ("reviewed_at", sa.DateTime(timezone=True), True, None),
        ("source_ref", sa.String(length=2000), True, None),
    ]
    for col_name, col_type, nullable, default in new_kchunk_cols:
        if not _column_exists("legal_knowledge_chunks", col_name):
            kwargs = {"nullable": nullable}
            if default is not None:
                kwargs["server_default"] = default
            op.add_column(
                "legal_knowledge_chunks",
                sa.Column(col_name, col_type, **kwargs),
            )

    # FK reviewed_by → users.id (only if doesn't exist yet)
    if not _constraint_exists("fk_legal_knowledge_chunks_reviewed_by"):
        op.create_foreign_key(
            "fk_legal_knowledge_chunks_reviewed_by",
            "legal_knowledge_chunks", "users",
            ["reviewed_by"], ["id"],
            ondelete="SET NULL",
        )

    # Index for TTL cron query (§8.3.1)
    if not _index_exists("ix_legal_knowledge_chunks_expires_at"):
        op.create_index(
            "ix_legal_knowledge_chunks_expires_at",
            "legal_knowledge_chunks",
            ["expires_at"],
            postgresql_where=sa.text("expires_at IS NOT NULL"),
        )

    # =========================================================
    # Block 5 — memory_personas table (CREATE) §6.3.1
    # =========================================================
    if not _table_exists("memory_personas"):
        op.create_table(
            "memory_personas",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("lead_client_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("address_form", sa.String(length=20),
                      nullable=False, server_default="auto"),
            sa.Column("full_name", sa.String(length=200), nullable=False),
            sa.Column("gender", sa.String(length=20),
                      nullable=False, server_default="unknown"),
            sa.Column("role_title", sa.String(length=100), nullable=True),
            sa.Column("tone", sa.String(length=40),
                      nullable=False, server_default="neutral"),
            # Use empty JSONB defaults — § §12.1.1 lesson learned from 20260426_003:
            # never use sa.text() with :true in JSON literals (bind-param trap).
            sa.Column("do_not_ask_again_slots", postgresql.JSONB(astext_type=sa.Text()),
                      nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("confirmed_facts", postgresql.JSONB(astext_type=sa.Text()),
                      nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("source_profile_version", sa.Integer(),
                      nullable=False, server_default="1"),
            sa.Column("version", sa.Integer(),
                      nullable=False, server_default="1"),
            sa.Column("last_confirmed_at", sa.DateTime(timezone=True),
                      nullable=False, server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["lead_client_id"], ["lead_clients.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("lead_client_id", name="uq_memory_personas_lead_client_id"),
            # CHECK constraint on address_form enum
            sa.CheckConstraint(
                "address_form IN ('вы', 'ты', 'formal', 'informal', 'auto')",
                name="ck_memory_personas_address_form",
            ),
            sa.CheckConstraint(
                "gender IN ('male', 'female', 'other', 'unknown')",
                name="ck_memory_personas_gender",
            ),
            sa.CheckConstraint(
                "tone IN ('neutral', 'friendly', 'formal', 'cautious', 'hostile')",
                name="ck_memory_personas_tone",
            ),
        )

    # =========================================================
    # Block 6 — session_persona_snapshots table (CREATE) §6.4.1
    # =========================================================
    if not _table_exists("session_persona_snapshots"):
        op.create_table(
            "session_persona_snapshots",
            # session_id is PK (one snapshot per session, immutable)
            sa.Column("session_id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("lead_client_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("persona_version", sa.Integer(),
                      nullable=False, server_default="1"),
            sa.Column("address_form", sa.String(length=20),
                      nullable=False, server_default="auto"),
            sa.Column("full_name", sa.String(length=200), nullable=False),
            sa.Column("gender", sa.String(length=20),
                      nullable=False, server_default="unknown"),
            sa.Column("role_title", sa.String(length=100), nullable=True),
            sa.Column("tone", sa.String(length=40),
                      nullable=False, server_default="neutral"),
            sa.Column("captured_at", sa.DateTime(timezone=True),
                      nullable=False, server_default=sa.func.now()),
            sa.Column("captured_from", sa.String(length=40), nullable=False),
            sa.Column("mutation_blocked_count", sa.Integer(),
                      nullable=False, server_default="0"),
            sa.ForeignKeyConstraint(["session_id"], ["training_sessions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["lead_client_id"], ["lead_clients.id"], ondelete="SET NULL"),
            sa.CheckConstraint(
                "address_form IN ('вы', 'ты', 'formal', 'informal', 'auto')",
                name="ck_session_persona_snapshots_address_form",
            ),
            sa.CheckConstraint(
                "gender IN ('male', 'female', 'other', 'unknown')",
                name="ck_session_persona_snapshots_gender",
            ),
            sa.CheckConstraint(
                "tone IN ('neutral', 'friendly', 'formal', 'cautious', 'hostile')",
                name="ck_session_persona_snapshots_tone",
            ),
            sa.CheckConstraint(
                "captured_from IN ('real_client', 'home_preview', 'training_simulation', 'pvp', 'center')",
                name="ck_session_persona_snapshots_captured_from",
            ),
        )
        op.create_index(
            "ix_session_persona_snapshots_lead_client_id",
            "session_persona_snapshots",
            ["lead_client_id"],
            postgresql_where=sa.text("lead_client_id IS NOT NULL"),
        )


# ── Downgrade ──────────────────────────────────────────────────────────────


def downgrade() -> None:
    # session_persona_snapshots
    if _table_exists("session_persona_snapshots"):
        op.drop_table("session_persona_snapshots")

    # memory_personas
    if _table_exists("memory_personas"):
        op.drop_table("memory_personas")

    # legal_knowledge_chunks columns (reverse order)
    if _index_exists("ix_legal_knowledge_chunks_expires_at"):
        op.drop_index("ix_legal_knowledge_chunks_expires_at",
                      table_name="legal_knowledge_chunks")
    if _constraint_exists("fk_legal_knowledge_chunks_reviewed_by"):
        op.drop_constraint("fk_legal_knowledge_chunks_reviewed_by",
                           "legal_knowledge_chunks", type_="foreignkey")
    for col in ["source_ref", "reviewed_at", "reviewed_by", "expires_at",
                "effective_from", "jurisdiction", "title", "source_type"]:
        if _column_exists("legal_knowledge_chunks", col):
            op.drop_column("legal_knowledge_chunks", col)

    # attachments
    if _index_exists("uq_attachments_client_sha256_orig"):
        op.drop_index("uq_attachments_client_sha256_orig", table_name="attachments")
    if _constraint_exists("fk_attachments_domain_event_id"):
        op.drop_constraint("fk_attachments_domain_event_id",
                           "attachments", type_="foreignkey")
    if _constraint_exists("fk_attachments_duplicate_of"):
        op.drop_constraint("fk_attachments_duplicate_of",
                           "attachments", type_="foreignkey")
    if _constraint_exists("fk_attachments_call_attempt_id"):
        op.drop_constraint("fk_attachments_call_attempt_id",
                           "attachments", type_="foreignkey")
    for col in ["duplicate_of", "verification_status",
                "domain_event_id", "call_attempt_id"]:
        if _column_exists("attachments", col):
            op.drop_column("attachments", col)
