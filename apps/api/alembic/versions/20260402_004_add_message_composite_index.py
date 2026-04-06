"""Add composite index on messages (session_id, sequence_number).

This index speeds up the most common query pattern: fetching all messages
for a training session in order. Without it, PostgreSQL performs a seq scan
on session_id index then sorts by sequence_number.

Revision ID: 20260402_004
Revises: 20260402_003
Create Date: 2026-04-02
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers
revision: str = "20260402_004"
down_revision: Union[str, None] = "20260402_003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_messages_session_seq",
        "messages",
        ["session_id", "sequence_number"],
    )


def downgrade() -> None:
    op.drop_index("ix_messages_session_seq", table_name="messages")
