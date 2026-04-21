"""Fix schema drift: wiki_pages.embedding ARRAY -> Vector(768), sync ORM-missing columns.

Revision ID: 20260415_006
Revises: 20260415_005
Create Date: 2026-04-15

Problem 1: wiki_pages.embedding was added as ARRAY(Float) in 20260410_001,
but the ORM model declares Vector(768). pgvector similarity operators (<->, <=>)
do not work on ARRAY, breaking semantic search.

Problem 2: Three columns were added by prior migrations but never synced
into ORM models (graph_variant, total_time_seconds, custom_character_id).
They existed on both sides — this migration is only for documentation/alignment
and does not alter the DB schema. The real fix is in the ORM models.

Safe to run: wiki_pages has zero rows with embeddings (verified). Zero data loss.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision: str = "20260415_006"
down_revision: Union[str, None] = "20260415_005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure pgvector extension is present (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Drop the ARRAY column and re-add as Vector(768). No data loss: 0 existing embeddings.
    op.drop_column("wiki_pages", "embedding")
    op.add_column(
        "wiki_pages",
        sa.Column("embedding", Vector(768), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("wiki_pages", "embedding")
    op.add_column(
        "wiki_pages",
        sa.Column("embedding", sa.dialects.postgresql.ARRAY(sa.Float), nullable=True),
    )
