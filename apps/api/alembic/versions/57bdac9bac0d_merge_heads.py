"""merge_heads

Revision ID: 57bdac9bac0d
Revises: 20260407_020, 20260409_001
Create Date: 2026-04-09 17:16:11.016364

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '57bdac9bac0d'
down_revision: Union[str, None] = ('20260407_020', '20260409_001')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
