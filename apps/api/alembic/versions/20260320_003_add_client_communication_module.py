"""add client communication module (Agent 7)

Revision ID: 20260320_003
Revises: 20260320_002_add_emotion_trap_tables
Create Date: 2026-03-20

Tables: real_clients, client_consents, client_interactions,
        client_notifications, manager_reminders, audit_log
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260320_003"
down_revision: Union[str, None] = "20260320_002"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # ── Enums ──────────────────────────────────────────────────────────────
    client_status = postgresql.ENUM(
        "new", "contacted", "interested", "consultation", "thinking",
        "consent_given", "contract_signed", "in_process", "paused",
        "completed", "lost", "consent_revoked",
        name="clientstatus", create_type=False,
    )
    consent_channel = postgresql.ENUM(
        "phone_call", "sms_link", "web_form", "whatsapp", "in_person", "email_link",
        name="consentchannel", create_type=False,
    )
    interaction_type = postgresql.ENUM(
        "outbound_call", "inbound_call", "sms_sent", "whatsapp_sent",
        "email_sent", "meeting", "status_change", "consent_event", "note", "system",
        name="interactiontype", create_type=False,
    )
    notification_channel = postgresql.ENUM(
        "in_app", "push", "sms", "whatsapp", "email",
        name="notificationchannel", create_type=False,
    )
    notification_status = postgresql.ENUM(
        "pending", "sent", "delivered", "read", "failed",
        name="notificationstatus", create_type=False,
    )

    # Create enums first
    client_status.create(op.get_bind(), checkfirst=True)
    consent_channel.create(op.get_bind(), checkfirst=True)
    interaction_type.create(op.get_bind(), checkfirst=True)
    notification_channel.create(op.get_bind(), checkfirst=True)
    notification_status.create(op.get_bind(), checkfirst=True)

    # ── real_clients ───────────────────────────────────────────────────────
    op.create_table(
        "real_clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("manager_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("status", client_status, server_default="new", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("debt_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("debt_details", postgresql.JSONB(), nullable=True),
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("next_contact_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lost_reason", sa.String(500), nullable=True),
        sa.Column("lost_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_status_change_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_real_clients_manager_id", "real_clients", ["manager_id"])
    op.create_index("ix_real_clients_status", "real_clients", ["status"])
    op.create_index("ix_real_clients_phone", "real_clients", ["phone"])
    op.create_index("ix_real_clients_is_active", "real_clients", ["is_active"])
    op.create_index("ix_real_clients_next_contact_at", "real_clients", ["next_contact_at"])
    op.create_index("ix_real_clients_last_status_change", "real_clients", ["last_status_change_at"])
    op.create_index("ix_real_clients_created_at", "real_clients", ["created_at"])

    # ── client_consents ────────────────────────────────────────────────────
    op.create_table(
        "client_consents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("real_clients.id"), nullable=False),
        sa.Column("consent_type", sa.String(50), nullable=False),
        sa.Column("channel", consent_channel, nullable=True),
        sa.Column("legal_text_version", sa.String(20), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(500), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("recorded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("evidence_url", sa.String(500), nullable=True),
        sa.Column("token", sa.String(128), unique=True, nullable=True),
        sa.Column("token_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_client_consents_client_id", "client_consents", ["client_id"])
    op.create_index("ix_client_consents_type", "client_consents", ["consent_type"])
    # Partial unique: один активный consent определённого типа
    op.execute(
        "CREATE UNIQUE INDEX uq_active_consent_per_type "
        "ON client_consents (client_id, consent_type) "
        "WHERE revoked_at IS NULL"
    )

    # ── client_interactions ────────────────────────────────────────────────
    op.create_table(
        "client_interactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("real_clients.id"), nullable=False),
        sa.Column("manager_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("interaction_type", interaction_type, nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("result", sa.String(200), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("old_status", sa.String(50), nullable=True),
        sa.Column("new_status", sa.String(50), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_client_interactions_client_id", "client_interactions", ["client_id"])
    op.create_index("ix_client_interactions_timeline", "client_interactions", ["client_id", "created_at"])
    op.create_index("ix_client_interactions_type", "client_interactions", ["interaction_type"])

    # ── client_notifications ───────────────────────────────────────────────
    op.create_table(
        "client_notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("recipient_type", sa.String(20), nullable=False),
        sa.Column("recipient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("real_clients.id"), nullable=True),
        sa.Column("channel", notification_channel, nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("template_id", sa.String(50), nullable=True),
        sa.Column("status", notification_status, server_default="pending", nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_reason", sa.String(500), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_notifications_recipient", "client_notifications", ["recipient_type", "recipient_id"])
    op.create_index("ix_notifications_status", "client_notifications", ["status", "created_at"])

    # ── manager_reminders ──────────────────────────────────────────────────
    op.create_table(
        "manager_reminders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("manager_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("real_clients.id"), nullable=False),
        sa.Column("remind_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("message", sa.String(500), nullable=True),
        sa.Column("is_completed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auto_generated", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_reminders_pending", "manager_reminders", ["manager_id", "is_completed", "remind_at"])

    # ── audit_log ──────────────────────────────────────────────────────────
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("actor_role", sa.String(20), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("old_values", postgresql.JSONB(), nullable=True),
        sa.Column("new_values", postgresql.JSONB(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_entity", "audit_log", ["entity_type", "entity_id"])
    op.create_index("ix_audit_actor", "audit_log", ["actor_id"])
    op.create_index("ix_audit_created", "audit_log", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("manager_reminders")
    op.drop_table("client_notifications")
    op.drop_table("client_interactions")
    # Drop partial index first
    op.execute("DROP INDEX IF EXISTS uq_active_consent_per_type")
    op.drop_table("client_consents")
    op.drop_table("real_clients")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS notificationstatus")
    op.execute("DROP TYPE IF EXISTS notificationchannel")
    op.execute("DROP TYPE IF EXISTS interactiontype")
    op.execute("DROP TYPE IF EXISTS consentchannel")
    op.execute("DROP TYPE IF EXISTS clientstatus")
