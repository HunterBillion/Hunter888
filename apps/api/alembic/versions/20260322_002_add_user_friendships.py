"""Add user friendships for PvP social graph.

Revision ID: 20260322_002
Revises: 20260322_001
Create Date: 2026-03-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260322_002"
down_revision: Union[str, None] = "20260322_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS user_friendships (
            id UUID PRIMARY KEY,
            requester_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            addressee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            accepted_at TIMESTAMPTZ NULL,
            CONSTRAINT uq_user_friendships_pair UNIQUE (requester_id, addressee_id),
            CONSTRAINT ck_user_friendships_distinct CHECK (requester_id <> addressee_id),
            CONSTRAINT ck_user_friendships_status CHECK (status IN ('pending', 'accepted'))
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_user_friendships_requester_id ON user_friendships (requester_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_user_friendships_addressee_id ON user_friendships (addressee_id)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS user_friendships"))
