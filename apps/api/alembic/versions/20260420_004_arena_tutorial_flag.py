"""Add arena_tutorial_completed_at flag to users.

Revision ID: 20260420_004
Revises: 20260420_003
Create Date: 2026-04-20

Phase C (2026-04-20). First-match tutorial — a scripted 3-round walkthrough
players see before their first real PvP match. We track completion per-user
so we can:
  • Gate the ``/pvp`` lobby with a "Новичок? Пройди тренировку" banner.
  • Show the button/overlay only once unless the user explicitly replays.

We specifically do NOT reuse ``users.onboarding_completed`` — that flag is
for the top-level account onboarding (profile fields, consent, role), and
Arena is a separate mode a user may discover later. Keeping them orthogonal
lets either flow be replayed without disturbing the other.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers
revision = "20260420_004"
down_revision = "20260420_003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "arena_tutorial_completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "arena_tutorial_completed_at")
