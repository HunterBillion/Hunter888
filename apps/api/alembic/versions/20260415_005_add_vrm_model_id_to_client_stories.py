"""Add vrm_model_id to client_stories for avatar assignment.

Revision ID: 20260415_005
Revises: 20260415_004
Create Date: 2026-04-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260415_005"
down_revision: Union[str, None] = "20260415_004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "client_stories",
        sa.Column(
            "vrm_model_id",
            sa.String(100),
            nullable=True,
            comment="VRM model key from avatar_assignment, assigned at story creation",
        ),
    )


def downgrade() -> None:
    op.drop_column("client_stories", "vrm_model_id")
