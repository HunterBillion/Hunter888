"""Add CRM/client attachments.

Revision ID: 20260423_003
Revises: 20260423_002
Create Date: 2026-04-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260423_003"
down_revision: Union[str, Sequence[str], None] = "20260423_002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    return bool(conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_name = :table_name"
    ), {"table_name": table_name}).fetchone())


def upgrade() -> None:
    if not _table_exists("attachments"):
        op.create_table(
            "attachments",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("interaction_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("content_type", sa.String(length=120), nullable=True),
            sa.Column("file_size", sa.Integer(), nullable=False),
            sa.Column("sha256", sa.String(length=64), nullable=False),
            sa.Column("storage_path", sa.String(length=1000), nullable=False),
            sa.Column("public_url", sa.String(length=1000), nullable=True),
            sa.Column("document_type", sa.String(length=80), nullable=True),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="received"),
            sa.Column("ocr_status", sa.String(length=30), nullable=False, server_default="not_required"),
            sa.Column("classification_status", sa.String(length=30), nullable=False, server_default="pending"),
            sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["client_id"], ["real_clients.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["session_id"], ["training_sessions.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["interaction_id"], ["client_interactions.id"], ondelete="SET NULL"),
        )
        op.create_index("ix_attachments_uploaded_by", "attachments", ["uploaded_by"])
        op.create_index("ix_attachments_client_id", "attachments", ["client_id"])
        op.create_index("ix_attachments_session_id", "attachments", ["session_id"])
        op.create_index("ix_attachments_message_id", "attachments", ["message_id"])
        op.create_index("ix_attachments_interaction_id", "attachments", ["interaction_id"])
        op.create_index("ix_attachments_sha256", "attachments", ["sha256"])
        op.create_index("ix_attachments_document_type", "attachments", ["document_type"])
        op.create_index("ix_attachments_status", "attachments", ["status"])
        op.create_index("ix_attachments_created_at", "attachments", ["created_at"])
        op.create_index("ix_attachments_client_created", "attachments", ["client_id", "created_at"])
        op.create_index("ix_attachments_session_created", "attachments", ["session_id", "created_at"])
        op.create_index("ix_attachments_client_sha", "attachments", ["client_id", "sha256"])


def downgrade() -> None:
    if _table_exists("attachments"):
        op.drop_index("ix_attachments_client_sha", table_name="attachments")
        op.drop_index("ix_attachments_session_created", table_name="attachments")
        op.drop_index("ix_attachments_client_created", table_name="attachments")
        op.drop_index("ix_attachments_created_at", table_name="attachments")
        op.drop_index("ix_attachments_status", table_name="attachments")
        op.drop_index("ix_attachments_document_type", table_name="attachments")
        op.drop_index("ix_attachments_sha256", table_name="attachments")
        op.drop_index("ix_attachments_interaction_id", table_name="attachments")
        op.drop_index("ix_attachments_message_id", table_name="attachments")
        op.drop_index("ix_attachments_session_id", table_name="attachments")
        op.drop_index("ix_attachments_client_id", table_name="attachments")
        op.drop_index("ix_attachments_uploaded_by", table_name="attachments")
        op.drop_table("attachments")
