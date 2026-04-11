"""add wiki_page embedding vector for semantic search

Revision ID: 20260410_001
Revises: fead4bf27c54
Create Date: 2026-04-10

Phase 2: Wiki becomes third RAG source via pgvector embeddings.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260410_001"
down_revision: Union[str, None] = "20260409_002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "wiki_pages",
        sa.Column("embedding", sa.dialects.postgresql.ARRAY(sa.Float), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("wiki_pages", "embedding")
