"""Add perfect_streak and best_perfect_streak to manager_progress.

Revision ID: 20260415_004
Revises: 20260415_003
Create Date: 2026-04-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260415_004"
down_revision: Union[str, None] = "20260415_003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("manager_progress", sa.Column("perfect_streak", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("manager_progress", sa.Column("best_perfect_streak", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("manager_progress", "best_perfect_streak")
    op.drop_column("manager_progress", "perfect_streak")
