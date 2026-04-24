"""TZ-1 foundation: lead_clients, domain_events, CRM projection state.

Revision ID: 20260424_002
Revises: 20260424_001
Create Date: 2026-04-24
"""

from __future__ import annotations

import json
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260424_002"
down_revision: Union[str, Sequence[str], None] = "20260424_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    return sa.inspect(op.get_bind())


def _table_exists(table_name: str) -> bool:
    return _inspector().has_table(table_name)


def _column_exists(table_name: str, column_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return any(col["name"] == column_name for col in _inspector().get_columns(table_name))


def _index_exists(table_name: str, index_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return any(idx["name"] == index_name for idx in _inspector().get_indexes(table_name))


def _fk_exists(table_name: str, fk_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return any(fk.get("name") == fk_name for fk in _inspector().get_foreign_keys(table_name))


def upgrade() -> None:
    conn = op.get_bind()

    if not _table_exists("lead_clients"):
        op.create_table(
            "lead_clients",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True),
            sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("crm_card_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("lifecycle_stage", sa.String(length=40), nullable=False, server_default="new"),
            sa.Column("work_state", sa.String(length=40), nullable=False, server_default="active"),
            sa.Column("status_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("source_system", sa.String(length=50), nullable=True),
            sa.Column("source_ref", sa.String(length=120), nullable=True),
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    if not _index_exists("lead_clients", "ix_lead_clients_owner_stage"):
        op.create_index("ix_lead_clients_owner_stage", "lead_clients", ["owner_user_id", "lifecycle_stage"], unique=False)
    if not _index_exists("lead_clients", "ix_lead_clients_team_state"):
        op.create_index("ix_lead_clients_team_state", "lead_clients", ["team_id", "work_state"], unique=False)

    if not _table_exists("domain_events"):
        op.create_table(
            "domain_events",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("lead_client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lead_clients.id", ondelete="CASCADE"), nullable=False),
            sa.Column("event_type", sa.String(length=100), nullable=False),
            sa.Column("aggregate_type", sa.String(length=80), nullable=True),
            sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("call_attempt_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("actor_type", sa.String(length=30), nullable=False),
            sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("source", sa.String(length=30), nullable=False),
            sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("idempotency_key", sa.String(length=255), nullable=False),
            sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("causation_id", sa.String(length=120), nullable=True),
            sa.Column("correlation_id", sa.String(length=120), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("idempotency_key", name="uq_domain_events_idempotency_key"),
        )
    if not _index_exists("domain_events", "ix_domain_events_lead_occurred"):
        op.create_index("ix_domain_events_lead_occurred", "domain_events", ["lead_client_id", "occurred_at"], unique=False)
    if not _index_exists("domain_events", "ix_domain_events_type_occurred"):
        op.create_index("ix_domain_events_type_occurred", "domain_events", ["event_type", "occurred_at"], unique=False)
    if not _index_exists("domain_events", "ix_domain_events_correlation_id"):
        op.create_index("ix_domain_events_correlation_id", "domain_events", ["correlation_id"], unique=False)
    if not _index_exists("domain_events", "ix_domain_events_actor_id"):
        op.create_index("ix_domain_events_actor_id", "domain_events", ["actor_id"], unique=False)
    if not _index_exists("domain_events", "ix_domain_events_aggregate_id"):
        op.create_index("ix_domain_events_aggregate_id", "domain_events", ["aggregate_id"], unique=False)
    if not _index_exists("domain_events", "ix_domain_events_session_id"):
        op.create_index("ix_domain_events_session_id", "domain_events", ["session_id"], unique=False)

    if not _table_exists("crm_timeline_projection_state"):
        op.create_table(
            "crm_timeline_projection_state",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("domain_event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("domain_events.id", ondelete="CASCADE"), nullable=False),
            sa.Column("lead_client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lead_clients.id", ondelete="CASCADE"), nullable=False),
            sa.Column("interaction_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("client_interactions.id", ondelete="SET NULL"), nullable=True),
            sa.Column("projection_name", sa.String(length=60), nullable=False, server_default="crm_timeline"),
            sa.Column("projection_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="projected"),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("projected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("domain_event_id", name="uq_crm_timeline_projection_state_domain_event_id"),
        )
    if not _index_exists("crm_timeline_projection_state", "ix_crm_proj_lead_projected"):
        op.create_index("ix_crm_proj_lead_projected", "crm_timeline_projection_state", ["lead_client_id", "projected_at"], unique=False)
    if not _index_exists("crm_timeline_projection_state", "ix_crm_timeline_projection_state_interaction_id"):
        op.create_index("ix_crm_timeline_projection_state_interaction_id", "crm_timeline_projection_state", ["interaction_id"], unique=False)

    for table_name, fk_name in (
        ("real_clients", "fk_real_clients_lead_client_id"),
        ("client_interactions", "fk_client_interactions_lead_client_id"),
        ("attachments", "fk_attachments_lead_client_id"),
        ("training_sessions", "fk_training_sessions_lead_client_id"),
    ):
        if not _column_exists(table_name, "lead_client_id"):
            op.add_column(table_name, sa.Column("lead_client_id", postgresql.UUID(as_uuid=True), nullable=True))
        if not _fk_exists(table_name, fk_name):
            op.create_foreign_key(
                fk_name,
                source_table=table_name,
                referent_table="lead_clients",
                local_cols=["lead_client_id"],
                remote_cols=["id"],
                ondelete="SET NULL",
            )
        index_name = f"ix_{table_name}_lead_client_id"
        if not _index_exists(table_name, index_name):
            op.create_index(index_name, table_name, ["lead_client_id"], unique=False)

    conn.execute(sa.text(
        """
        INSERT INTO lead_clients (
            id, owner_user_id, team_id, lifecycle_stage, work_state, status_tags,
            source_system, source_ref
        )
        SELECT
            rc.id,
            rc.manager_id,
            u.team_id,
            CASE rc.status::text
                WHEN 'consent_given' THEN 'consent_received'
                WHEN 'in_process' THEN 'case_in_progress'
                WHEN 'paused' THEN 'case_in_progress'
                WHEN 'consent_revoked' THEN 'consent_received'
                ELSE rc.status::text
            END,
            CASE rc.status::text
                WHEN 'paused' THEN 'paused'
                WHEN 'consent_revoked' THEN 'consent_revoked'
                ELSE 'active'
            END,
            '[]'::jsonb,
            'real_clients',
            rc.id::text
        FROM real_clients rc
        LEFT JOIN users u ON u.id = rc.manager_id
        WHERE NOT EXISTS (
            SELECT 1 FROM lead_clients lc WHERE lc.id = rc.id
        )
        """
    ))

    conn.execute(sa.text(
        """
        UPDATE real_clients
        SET lead_client_id = id
        WHERE lead_client_id IS NULL
        """
    ))
    conn.execute(sa.text(
        """
        UPDATE client_interactions ci
        SET lead_client_id = rc.lead_client_id
        FROM real_clients rc
        WHERE ci.client_id = rc.id
          AND ci.lead_client_id IS NULL
        """
    ))
    conn.execute(sa.text(
        """
        UPDATE attachments a
        SET lead_client_id = rc.lead_client_id
        FROM real_clients rc
        WHERE a.client_id = rc.id
          AND a.lead_client_id IS NULL
        """
    ))
    conn.execute(sa.text(
        """
        UPDATE training_sessions ts
        SET lead_client_id = rc.lead_client_id
        FROM real_clients rc
        WHERE ts.real_client_id = rc.id
          AND ts.lead_client_id IS NULL
        """
    ))

    rows = conn.execute(sa.text(
        """
        SELECT
            ci.id AS interaction_id,
            ci.client_id,
            ci.lead_client_id,
            ci.manager_id,
            ci.interaction_type::text AS interaction_type,
            ci.content,
            ci.result,
            ci.duration_seconds,
            ci.old_status,
            ci.new_status,
            ci.metadata AS metadata_json,
            ci.created_at
        FROM client_interactions ci
        WHERE ci.lead_client_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM domain_events de
              WHERE de.idempotency_key = ('backfill:client_interaction:' || ci.id::text)
          )
        """
    )).mappings().all()

    if rows:
        domain_event_rows: list[dict] = []
        projection_rows: list[dict] = []
        metadata_updates: list[dict] = []
        for row in rows:
            domain_event_id = uuid.uuid4()
            event_type = {
                "status_change": "lead_client.lifecycle_changed",
                "consent_event": "consent.updated",
            }.get(row["interaction_type"], "crm.interaction_logged")
            payload = {
                "interaction_id": str(row["interaction_id"]),
                "client_id": str(row["client_id"]),
                "lead_client_id": str(row["lead_client_id"]),
                "interaction_type": row["interaction_type"],
                "content": row["content"],
                "result": row["result"],
                "duration_seconds": row["duration_seconds"],
                "old_status": row["old_status"],
                "new_status": row["new_status"],
                "metadata": row["metadata_json"] or None,
            }
            domain_event_rows.append({
                "id": domain_event_id,
                "lead_client_id": row["lead_client_id"],
                "event_type": event_type,
                "aggregate_type": "client_interaction",
                "aggregate_id": row["interaction_id"],
                "session_id": None,
                "call_attempt_id": None,
                "actor_type": "migration",
                "actor_id": row["manager_id"],
                "source": "migration",
                "occurred_at": row["created_at"],
                "payload_json": payload,
                "idempotency_key": f"backfill:client_interaction:{row['interaction_id']}",
                "schema_version": 1,
                "causation_id": None,
                "correlation_id": str(row["interaction_id"]),
                "created_at": row["created_at"],
            })
            projection_rows.append({
                "id": uuid.uuid4(),
                "domain_event_id": domain_event_id,
                "lead_client_id": row["lead_client_id"],
                "interaction_id": row["interaction_id"],
                "projection_name": "crm_timeline",
                "projection_version": 1,
                "status": "projected",
                "error": None,
                "projected_at": row["created_at"],
                "updated_at": row["created_at"],
            })
            metadata_updates.append({
                "interaction_id": str(row["interaction_id"]),
                "patch": json.dumps({
                    "domain_event_id": str(domain_event_id),
                    "schema_version": 1,
                    "projection_name": "crm_timeline",
                    "projection_version": 1,
                }),
            })

        domain_events_table = sa.table(
            "domain_events",
            sa.column("id", postgresql.UUID(as_uuid=True)),
            sa.column("lead_client_id", postgresql.UUID(as_uuid=True)),
            sa.column("event_type", sa.String()),
            sa.column("aggregate_type", sa.String()),
            sa.column("aggregate_id", postgresql.UUID(as_uuid=True)),
            sa.column("session_id", postgresql.UUID(as_uuid=True)),
            sa.column("call_attempt_id", postgresql.UUID(as_uuid=True)),
            sa.column("actor_type", sa.String()),
            sa.column("actor_id", postgresql.UUID(as_uuid=True)),
            sa.column("source", sa.String()),
            sa.column("occurred_at", sa.DateTime(timezone=True)),
            sa.column("payload_json", postgresql.JSONB(astext_type=sa.Text())),
            sa.column("idempotency_key", sa.String()),
            sa.column("schema_version", sa.Integer()),
            sa.column("causation_id", sa.String()),
            sa.column("correlation_id", sa.String()),
            sa.column("created_at", sa.DateTime(timezone=True)),
        )
        projection_table = sa.table(
            "crm_timeline_projection_state",
            sa.column("id", postgresql.UUID(as_uuid=True)),
            sa.column("domain_event_id", postgresql.UUID(as_uuid=True)),
            sa.column("lead_client_id", postgresql.UUID(as_uuid=True)),
            sa.column("interaction_id", postgresql.UUID(as_uuid=True)),
            sa.column("projection_name", sa.String()),
            sa.column("projection_version", sa.Integer()),
            sa.column("status", sa.String()),
            sa.column("error", sa.Text()),
            sa.column("projected_at", sa.DateTime(timezone=True)),
            sa.column("updated_at", sa.DateTime(timezone=True)),
        )
        conn.execute(sa.insert(domain_events_table), domain_event_rows)
        conn.execute(sa.insert(projection_table), projection_rows)
        for item in metadata_updates:
            conn.execute(
                sa.text(
                    """
                    UPDATE client_interactions
                    SET metadata = COALESCE(metadata, '{}'::jsonb) || CAST(:patch AS jsonb)
                    WHERE id = CAST(:interaction_id AS uuid)
                    """
                ),
                item,
            )


def downgrade() -> None:
    if _index_exists("training_sessions", "ix_training_sessions_lead_client_id"):
        op.drop_index("ix_training_sessions_lead_client_id", table_name="training_sessions")
    if _fk_exists("training_sessions", "fk_training_sessions_lead_client_id"):
        op.drop_constraint("fk_training_sessions_lead_client_id", "training_sessions", type_="foreignkey")
    if _column_exists("training_sessions", "lead_client_id"):
        op.drop_column("training_sessions", "lead_client_id")

    if _index_exists("attachments", "ix_attachments_lead_client_id"):
        op.drop_index("ix_attachments_lead_client_id", table_name="attachments")
    if _fk_exists("attachments", "fk_attachments_lead_client_id"):
        op.drop_constraint("fk_attachments_lead_client_id", "attachments", type_="foreignkey")
    if _column_exists("attachments", "lead_client_id"):
        op.drop_column("attachments", "lead_client_id")

    if _index_exists("client_interactions", "ix_client_interactions_lead_client_id"):
        op.drop_index("ix_client_interactions_lead_client_id", table_name="client_interactions")
    if _fk_exists("client_interactions", "fk_client_interactions_lead_client_id"):
        op.drop_constraint("fk_client_interactions_lead_client_id", "client_interactions", type_="foreignkey")
    if _column_exists("client_interactions", "lead_client_id"):
        op.drop_column("client_interactions", "lead_client_id")

    if _index_exists("real_clients", "ix_real_clients_lead_client_id"):
        op.drop_index("ix_real_clients_lead_client_id", table_name="real_clients")
    if _fk_exists("real_clients", "fk_real_clients_lead_client_id"):
        op.drop_constraint("fk_real_clients_lead_client_id", "real_clients", type_="foreignkey")
    if _column_exists("real_clients", "lead_client_id"):
        op.drop_column("real_clients", "lead_client_id")

    if _table_exists("crm_timeline_projection_state"):
        op.drop_table("crm_timeline_projection_state")
    if _table_exists("domain_events"):
        op.drop_table("domain_events")
    if _table_exists("lead_clients"):
        op.drop_table("lead_clients")
