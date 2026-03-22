"""merge heads

Revision ID: 701c6ddde3cf
Revises: 20260320_002, d4e5f6a7b8c9
Create Date: 2026-03-20 17:15:39.592752

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '701c6ddde3cf'
down_revision: Union[str, None] = ('20260320_002', 'd4e5f6a7b8c9')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
