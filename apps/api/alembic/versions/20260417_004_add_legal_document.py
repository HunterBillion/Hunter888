"""add legal_document table for hierarchical law + court practice corpus

Revision ID: 20260417_002
Revises: 20260417_001
Create Date: 2026-04-17

Hierarchical storage for:
  - Федеральные законы (127-ФЗ and potentially others) with chapters/articles/items
  - Судебная практика (ВС РФ + арбитражные суды)

Uses self-referential parent_id for tree structure. embedding_v2 is the shadow
column for gemini-embedding-001@768 RAG (lives side-by-side with legacy
legal_knowledge_chunks.embedding@768 from text-embedding-3-small).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = "20260417_004"
down_revision = "20260417_003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure pgvector exists (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "legal_document",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("legal_document.id", ondelete="CASCADE"), nullable=True),
        sa.Column("doc_type", sa.String(32), nullable=False, index=True),
        # doc_type ∈ {'law_fz', 'law_chapter', 'law_article', 'law_item',
        #             'court_case', 'court_paragraph'}
        sa.Column("doc_source", sa.String(64), nullable=False, index=True),
        # doc_source ∈ {'127-FZ', 'vsrf', 'arbitral_sudact', ...}
        sa.Column("source_url", sa.Text, nullable=True),
        sa.Column("number", sa.String(32), nullable=True, index=True),
        # For law: "1", "213.4", "I" (chapter); for cases: case number "А40-1234/2025"
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_hash", sa.String(16), nullable=False, index=True),
        sa.Column("metadata_json", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        # For law: {chapter_name, redaction_date}
        # For cases: {court, case_date, judges, region, parties, decision_type}
        sa.Column("token_count", sa.Integer, nullable=True),
        sa.Column("embedding_v2", Vector(768), nullable=True),
        sa.Column("embedding_model", sa.String(64), nullable=True),
        # e.g. "gemini-embedding-001@768"
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("retrieval_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Unique per (doc_source, doc_type, number, content_hash) — prevents duplicates
    # on re-ingestion while allowing the same article number under different laws.
    op.create_unique_constraint(
        "uq_legal_document_src_type_num_hash",
        "legal_document",
        ["doc_source", "doc_type", "number", "content_hash"],
    )

    # Indexes for common queries
    op.create_index("ix_legal_document_parent", "legal_document", ["parent_id"])
    op.create_index("ix_legal_document_src_type", "legal_document", ["doc_source", "doc_type"])

    # IVFFlat vector index on embedding_v2 for cosine similarity queries
    # lists=50 is a reasonable default for <50k rows; re-tune after full load.
    op.execute(
        "CREATE INDEX ix_legal_document_embedding_v2 ON legal_document "
        "USING ivfflat (embedding_v2 vector_cosine_ops) WITH (lists = 50)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_legal_document_embedding_v2")
    op.drop_index("ix_legal_document_src_type", table_name="legal_document")
    op.drop_index("ix_legal_document_parent", table_name="legal_document")
    op.drop_constraint("uq_legal_document_src_type_num_hash", "legal_document", type_="unique")
    op.drop_table("legal_document")
