"""Expand legal_knowledge_chunks for production RAG pipeline.

Adds:
- difficulty_level (1-5) for adaptive question selection
- question_templates (JSONB) for zero-LLM question generation
- follow_up_questions, related_chunk_ids for question chains
- court_case_reference, is_court_practice for judicial practice
- blitz_question, blitz_answer for zero-latency blitz mode
- source_article_full_text for deep evaluation context
- content_version, last_verified_at for versioning
- embedding_model for drift protection
- tags (JSONB) for flexible filtering
- content_hash (unique) for idempotent seed upserts
- updated_at for change tracking

Indexes:
- difficulty_level (B-tree) for difficulty-range queries
- is_court_practice (partial) for court practice boost
- tags (GIN) for JSONB containment queries
- content_hash (unique) for upsert dedup
- Recreates IVFFlat index with lists=18 (optimized for 300+ chunks)

Revision ID: 20260324_001
Revises: 20260323_002
Create Date: 2026-03-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision: str = "20260324_001"
down_revision: Union[str, None] = "20260323_002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "legal_knowledge_chunks"


def upgrade() -> None:
    # ── New columns ───────────────────────────────────────────────────────────

    # Difficulty & question generation
    op.add_column(TABLE, sa.Column("difficulty_level", sa.Integer(), server_default="3"))
    op.add_column(TABLE, sa.Column("question_templates", JSONB, nullable=True))
    op.add_column(TABLE, sa.Column("follow_up_questions", JSONB, nullable=True))
    op.add_column(TABLE, sa.Column("related_chunk_ids", JSONB, nullable=True))

    # Court practice
    op.add_column(TABLE, sa.Column("court_case_reference", sa.String(300), nullable=True))
    op.add_column(TABLE, sa.Column("is_court_practice", sa.Boolean(), server_default="false"))

    # Blitz mode
    op.add_column(TABLE, sa.Column("blitz_question", sa.Text(), nullable=True))
    op.add_column(TABLE, sa.Column("blitz_answer", sa.Text(), nullable=True))

    # Deep context
    op.add_column(TABLE, sa.Column("source_article_full_text", sa.Text(), nullable=True))

    # Versioning & metadata
    op.add_column(TABLE, sa.Column("content_version", sa.Integer(), server_default="1"))
    op.add_column(TABLE, sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(TABLE, sa.Column("embedding_model", sa.String(50), nullable=True))
    op.add_column(TABLE, sa.Column("tags", JSONB, nullable=True))
    op.add_column(TABLE, sa.Column("content_hash", sa.String(32), nullable=True))
    op.add_column(TABLE, sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))

    # ── Indexes ───────────────────────────────────────────────────────────────

    op.create_index("ix_legal_chunks_difficulty", TABLE, ["difficulty_level"])

    # Partial index: only court practice chunks (small, fast)
    op.execute(sa.text(
        f"CREATE INDEX ix_legal_chunks_court_practice ON {TABLE} (is_court_practice) "
        f"WHERE is_court_practice = true"
    ))

    # GIN index for JSONB tags containment queries (@>)
    op.execute(sa.text(
        f"CREATE INDEX ix_legal_chunks_tags ON {TABLE} USING gin (tags jsonb_path_ops)"
    ))

    # Unique constraint on content_hash for idempotent upserts
    op.create_unique_constraint("uq_legal_chunks_content_hash", TABLE, ["content_hash"])

    # Recreate IVFFlat index with optimized lists count for 300+ chunks
    op.execute(sa.text(
        f"DROP INDEX IF EXISTS ix_legal_chunks_embedding"
    ))
    op.execute(sa.text(
        f"CREATE INDEX ix_legal_chunks_embedding ON {TABLE} "
        f"USING ivfflat (embedding vector_cosine_ops) WITH (lists = 18)"
    ))

    # ── Backfill existing rows ────────────────────────────────────────────────

    # Set content_hash for existing chunks (md5 of fact_text + law_article)
    op.execute(sa.text(
        f"UPDATE {TABLE} SET "
        f"content_hash = md5(fact_text || '::' || law_article), "
        f"content_version = 1 "
        f"WHERE content_hash IS NULL"
    ))


def downgrade() -> None:
    op.drop_constraint("uq_legal_chunks_content_hash", TABLE, type_="unique")
    op.execute(sa.text(f"DROP INDEX IF EXISTS ix_legal_chunks_tags"))
    op.execute(sa.text(f"DROP INDEX IF EXISTS ix_legal_chunks_court_practice"))
    op.drop_index("ix_legal_chunks_difficulty", TABLE)

    # Recreate original IVFFlat index
    op.execute(sa.text(f"DROP INDEX IF EXISTS ix_legal_chunks_embedding"))
    op.execute(sa.text(
        f"CREATE INDEX ix_legal_chunks_embedding ON {TABLE} "
        f"USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10)"
    ))

    columns_to_drop = [
        "difficulty_level", "question_templates", "follow_up_questions",
        "related_chunk_ids", "court_case_reference", "is_court_practice",
        "blitz_question", "blitz_answer", "source_article_full_text",
        "content_version", "last_verified_at", "embedding_model",
        "tags", "content_hash", "updated_at",
    ]
    for col in columns_to_drop:
        op.drop_column(TABLE, col)
