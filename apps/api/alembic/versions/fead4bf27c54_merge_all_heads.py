"""merge_all_heads

Revision ID: fead4bf27c54
Revises: 20260321_001, 701c6ddde3cf, e5f6a7b8c9d0
Create Date: 2026-03-21 05:39:25.506714

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fead4bf27c54'
down_revision: Union[str, None] = ('20260321_001', '701c6ddde3cf', 'e5f6a7b8c9d0')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
