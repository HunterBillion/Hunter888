"""Drop ``users.arena_tutorial_completed_at`` — tutorial removed.

Revision ID: 20260503_002
Revises: 20260503_001
Create Date: 2026-05-03

The /pvp/tutorial flow was removed entirely (user feedback: layout
broken, slow Web Speech TTS, repeated every refresh). The column
``arena_tutorial_completed_at`` added by ``20260420_004_arena_tutorial_flag``
is no longer read or written.

Rollback adds the column back as nullable; any historical "completed"
timestamps are lost (acceptable — the flag is meaningless without the
flow that wrote it).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260503_002"
down_revision: Union[str, Sequence[str], None] = "20260503_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("users", "arena_tutorial_completed_at")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "arena_tutorial_completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
