"""Index drift sync — bring DB indexes in line with model declarations.

Revision ID: 20260502_003
Revises: 20260502_002
Create Date: 2026-05-02

Why this exists
---------------

``alembic check`` against prod (audit 2026-05-02) reported 35+ index
operations needed to align the DB with the SQLAlchemy models. The
forward direction — model has, DB lacks — is the load-bearing half:
without these indexes TZ-8 team-scoping does seq-scans on
``lead_clients``, the admin timeline filters do seq-scans on
``domain_events``, etc. At pilot scale (7 clients, 13 events) this is
invisible; under any real ramp it will surface as p95 spikes.

The other direction (DB has indexes the models lack) is handled in
the same audit by adding the missing ``index=True`` /
``__table_args__`` declarations to the models — no DB drops here.
``pg_stat_user_indexes`` shows a couple of those legacy indexes have
real traffic (``ix_morning_drill_sessions_user_id`` 1445 scans,
``ix_pvp_duels_winner_id`` 1429 scans), so dropping them blindly
would have been the wrong call. Restoring them in the model is
zero-risk.

What this migration does
------------------------

1. Adds 12 missing single-column indexes that the models declared via
   ``index=True`` but that never made it into the DB. All are FK or
   filter-frequency columns that the query planner needs.

2. Promotes ``ix_persona_snapshots_session_id`` from non-unique to
   UNIQUE. The model has carried ``unique=True`` since
   ``20260425_001_add_persona_snapshots`` shipped — the index that
   landed back then was non-unique. Today (2026-05-02) the table has
   zero rows on prod, so the swap is free; later, when call mode
   resumes producing snapshots, the UNIQUE will protect the
   "one snapshot per session" invariant the service layer already
   enforces in code.

Idempotent
----------

Every operation is guarded by ``_index_exists`` so re-running on a
DB that's already been migrated (e.g. local Docker after testing)
is a no-op.

Reversibility
-------------

``downgrade()`` reverses each step: drops the 12 added indexes, and
swaps the UNIQUE persona snapshot index back to non-unique. None of
the upgrade ops touches data — just DDL — so downgrade is safe to run
on any DB state.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260502_003"
down_revision: Union[str, Sequence[str], None] = "20260502_002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Idempotent guards ─────────────────────────────────────────────────


def _index_exists(index_name: str) -> bool:
    conn = op.get_bind()
    return bool(
        conn.execute(
            sa.text("SELECT 1 FROM pg_indexes WHERE indexname = :n"),
            {"n": index_name},
        ).fetchone()
    )


# 12 single-column indexes the models declare but the DB lacks. Each
# entry: (index_name, table_name, column_name, unique). Order is not
# significant — every operation is independent.
_FORWARD_INDEXES: tuple[tuple[str, str, str, bool], ...] = (
    # lead_clients — TZ-8 team scoping + manager owner queries
    ("ix_lead_clients_team_id",         "lead_clients",                 "team_id",         False),
    ("ix_lead_clients_owner_user_id",   "lead_clients",                 "owner_user_id",   False),
    ("ix_lead_clients_lifecycle_stage", "lead_clients",                 "lifecycle_stage", False),
    ("ix_lead_clients_work_state",      "lead_clients",                 "work_state",      False),
    ("ix_lead_clients_crm_card_id",     "lead_clients",                 "crm_card_id",     False),
    ("ix_lead_clients_profile_id",      "lead_clients",                 "profile_id",      False),
    # domain_events — admin timeline event-type / per-client filters
    ("ix_domain_events_event_type",     "domain_events",                "event_type",      False),
    ("ix_domain_events_lead_client_id", "domain_events",                "lead_client_id",  False),
    # crm_timeline_projection_state — projector retry loop + admin status
    ("ix_crm_timeline_projection_state_lead_client_id",
                                        "crm_timeline_projection_state","lead_client_id",  False),
    ("ix_crm_timeline_projection_state_status",
                                        "crm_timeline_projection_state","status",          False),
    # attachments — TZ-4 D1 mandatory FK to domain_events
    ("ix_attachments_domain_event_id",  "attachments",                  "domain_event_id", False),
    # chunk_usage_logs — TZ-8 PR-D discriminator filter
    ("ix_chunk_usage_logs_chunk_kind",  "chunk_usage_logs",             "chunk_kind",      False),
)


def upgrade() -> None:
    # Step 1: add the 12 missing forward indexes.
    for index_name, table_name, column_name, unique in _FORWARD_INDEXES:
        if not _index_exists(index_name):
            op.create_index(index_name, table_name, [column_name], unique=unique)

    # Step 2: promote ``ix_persona_snapshots_session_id`` to UNIQUE.
    # The non-unique index that exists came from
    # ``20260425_001_add_persona_snapshots`` (where the column was
    # marked ``index=True`` *before* the model gained ``unique=True``).
    # We drop and recreate rather than ``ALTER INDEX`` because pg
    # doesn't support converting btree → unique-btree in place; the
    # accepted pattern is drop + create. Safe at pilot scale —
    # persona_snapshots is currently empty (audit 2026-05-02).
    if _index_exists("ix_persona_snapshots_session_id"):
        op.drop_index("ix_persona_snapshots_session_id", table_name="persona_snapshots")
    op.create_index(
        "ix_persona_snapshots_session_id",
        "persona_snapshots",
        ["session_id"],
        unique=True,
    )


def downgrade() -> None:
    # Reverse step 2 first — drop the unique, recreate non-unique.
    if _index_exists("ix_persona_snapshots_session_id"):
        op.drop_index("ix_persona_snapshots_session_id", table_name="persona_snapshots")
    op.create_index(
        "ix_persona_snapshots_session_id",
        "persona_snapshots",
        ["session_id"],
        unique=False,
    )

    # Then drop the 12 forward indexes — order doesn't matter.
    for index_name, table_name, _column_name, _unique in _FORWARD_INDEXES:
        if _index_exists(index_name):
            op.drop_index(index_name, table_name=table_name)
