"""add cascade_ids column to client_profiles

Fixes: column "cascade_ids" of relation "client_profiles" does not exist

Revision ID: 20260409_002
Revises: 20260409_001
Create Date: 2026-04-09
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260409_002"
down_revision: Union[str, None] = "57bdac9bac0d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE client_profiles
        ADD COLUMN IF NOT EXISTS cascade_ids JSONB DEFAULT '[]'::jsonb
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE client_profiles DROP COLUMN IF EXISTS cascade_ids")
