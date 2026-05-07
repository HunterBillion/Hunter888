"""Create knowledge_answer_reports for user complaints about AI verdicts

Revision ID: 20260507_002
Revises: 20260507_001
Create Date: 2026-05-07

Adds the table backing PR-6 «Жалоба на ответ AI». A user clicks Flag
on a quiz verdict, the FE POSTs to /api/knowledge/answers/{id}/report,
the row lands here. Methodologist sees it inside KnowledgeReviewQueue
(Variant B — same widget, new ``source_kind=user_report`` filter).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260507_002"
down_revision = "20260507_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_answer_reports",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "answer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_answers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "reporter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("open", "accepted", "rejected", name="report_status"),
            nullable=False,
            server_default="open",
        ),
        sa.Column(
            "linked_chunk_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "reviewed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_knowledge_answer_reports_answer_id",
        "knowledge_answer_reports",
        ["answer_id"],
    )
    op.create_index(
        "ix_knowledge_answer_reports_reporter_id",
        "knowledge_answer_reports",
        ["reporter_id"],
    )
    op.create_index(
        "ix_knowledge_answer_reports_status",
        "knowledge_answer_reports",
        ["status"],
    )
    op.create_index(
        "ix_kareports_status_created",
        "knowledge_answer_reports",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_kareports_status_created", table_name="knowledge_answer_reports")
    op.drop_index("ix_knowledge_answer_reports_status", table_name="knowledge_answer_reports")
    op.drop_index("ix_knowledge_answer_reports_reporter_id", table_name="knowledge_answer_reports")
    op.drop_index("ix_knowledge_answer_reports_answer_id", table_name="knowledge_answer_reports")
    op.drop_table("knowledge_answer_reports")
    sa.Enum(name="report_status").drop(op.get_bind(), checkfirst=True)
