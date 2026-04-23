"""Add knowledge governance status.

Revision ID: 20260423_004
Revises: 20260423_003
Create Date: 2026-04-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260423_004"
down_revision: Union[str, Sequence[str], None] = "20260423_003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    conn = op.get_bind()
    return bool(conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :table_name AND column_name = :column_name"
    ), {"table_name": table_name, "column_name": column_name}).fetchone())


def upgrade() -> None:
    if not _column_exists("legal_knowledge_chunks", "knowledge_status"):
        op.add_column(
            "legal_knowledge_chunks",
            sa.Column("knowledge_status", sa.String(length=30), nullable=False, server_default="actual"),
        )
        op.create_index("ix_legal_knowledge_chunks_knowledge_status", "legal_knowledge_chunks", ["knowledge_status"])
    if not _column_exists("legal_knowledge_chunks", "status_reason"):
        op.add_column("legal_knowledge_chunks", sa.Column("status_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    if _column_exists("legal_knowledge_chunks", "status_reason"):
        op.drop_column("legal_knowledge_chunks", "status_reason")
    if _column_exists("legal_knowledge_chunks", "knowledge_status"):
        op.drop_index("ix_legal_knowledge_chunks_knowledge_status", table_name="legal_knowledge_chunks")
        op.drop_column("legal_knowledge_chunks", "knowledge_status")
