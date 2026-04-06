"""Add RAG feedback loop: chunk_usage_logs table + chunk stats columns.

Revision ID: 20260401_001
Revises: fead4bf27c54
Create Date: 2026-04-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

# revision identifiers
revision: str = "20260401_001"
down_revision: Union[str, None] = "20260324_003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── New columns on legal_knowledge_chunks ─────────────────────────────
    op.add_column("legal_knowledge_chunks", sa.Column(
        "retrieval_count", sa.Integer(), nullable=False, server_default="0",
    ))
    op.add_column("legal_knowledge_chunks", sa.Column(
        "correct_answer_count", sa.Integer(), nullable=False, server_default="0",
    ))
    op.add_column("legal_knowledge_chunks", sa.Column(
        "incorrect_answer_count", sa.Integer(), nullable=False, server_default="0",
    ))
    op.add_column("legal_knowledge_chunks", sa.Column(
        "effectiveness_score", sa.Float(), nullable=True,
    ))
    op.add_column("legal_knowledge_chunks", sa.Column(
        "last_used_at", sa.DateTime(timezone=True), nullable=True,
    ))

    # ── New table: chunk_usage_logs ───────────────────────────────────────
    op.create_table(
        "chunk_usage_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("legal_knowledge_chunks.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("query_text", sa.Text(), nullable=True),
        sa.Column("retrieval_method", sa.String(20), nullable=True),
        sa.Column("relevance_score", sa.Float(), nullable=True),
        sa.Column("retrieval_rank", sa.Integer(), nullable=True),
        sa.Column("was_answered", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("answer_correct", sa.Boolean(), nullable=True),
        sa.Column("user_answer_excerpt", sa.String(500), nullable=True),
        sa.Column("score_delta", sa.Float(), nullable=True),
        sa.Column("discovered_error", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )

    # Indexes for common query patterns
    op.create_index("ix_chunk_usage_logs_chunk_id", "chunk_usage_logs", ["chunk_id"])
    op.create_index("ix_chunk_usage_logs_user_id", "chunk_usage_logs", ["user_id"])
    op.create_index("ix_chunk_usage_logs_source_type", "chunk_usage_logs", ["source_type"])
    op.create_index("ix_chunk_usage_logs_created_at", "chunk_usage_logs", ["created_at"])

    # GIN index on legal_knowledge_chunks.tags for @> containment queries
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_legal_knowledge_chunks_tags_gin "
        "ON legal_knowledge_chunks USING GIN (tags)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_legal_knowledge_chunks_tags_gin")
    op.drop_index("ix_chunk_usage_logs_created_at", table_name="chunk_usage_logs")
    op.drop_index("ix_chunk_usage_logs_source_type", table_name="chunk_usage_logs")
    op.drop_index("ix_chunk_usage_logs_user_id", table_name="chunk_usage_logs")
    op.drop_index("ix_chunk_usage_logs_chunk_id", table_name="chunk_usage_logs")
    op.drop_table("chunk_usage_logs")
    op.drop_column("legal_knowledge_chunks", "last_used_at")
    op.drop_column("legal_knowledge_chunks", "effectiveness_score")
    op.drop_column("legal_knowledge_chunks", "incorrect_answer_count")
    op.drop_column("legal_knowledge_chunks", "correct_answer_count")
    op.drop_column("legal_knowledge_chunks", "retrieval_count")
