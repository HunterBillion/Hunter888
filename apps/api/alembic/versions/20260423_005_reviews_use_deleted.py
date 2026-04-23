"""Replace approved flag with deleted flag for reviews.

Revision ID: reviews_use_deleted
Revises: 
Create Date: 2026-04-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'reviews_use_deleted'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add deleted column (default=False)
    op.add_column('reviews', sa.Column('deleted', sa.Boolean(), nullable=False, server_default='false'))
    
    # Copy existing approved=True to deleted=False (visible)
    op.execute("UPDATE reviews SET deleted = false WHERE approved = true")
    
    # Copy existing approved=False to deleted=False (was pending, now published directly)  
    op.execute("UPDATE reviews SET deleted = false WHERE approved = false")
    
    # Drop old approved column
    op.drop_column('reviews', 'approved')


def downgrade() -> None:
    # Recreate approved based on deleted
    op.add_column('reviews', sa.Column('approved', sa.Boolean(), nullable=False, server_default='false'))
    op.execute("UPDATE reviews SET approved = NOT deleted")
    op.drop_column('reviews', 'deleted')