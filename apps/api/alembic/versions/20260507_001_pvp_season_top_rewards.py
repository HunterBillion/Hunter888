"""Add top_rewards JSONB to pvp_seasons

Revision ID: 20260507_001
Revises: 20260504_002
Create Date: 2026-05-07

Adds a structured "top-N rewards" field to ``pvp_seasons`` so the
seasonal banner on /pvp can finally render meaningful headlines like
"Сезон до 31 мая · топ-1 = 100 AP". Previously the banner only had
``rewards`` (per-tier xp/badge) which doesn't map to "place 1, place 2,
place 3" framing the FE wants.

Schema (JSONB, nullable for backward compat):
    [
      {"rank": 1, "ap": 100, "badge": "champion-may-2026"},
      {"rank": 2, "ap": 60},
      {"rank": 3, "ap": 30},
      ...
    ]

Existing ``rewards`` (per-tier) stays as-is for the legacy
/pvp/leaderboard tier rewards UI. The two coexist intentionally: tier
rewards = "what every Diamond gets", top_rewards = "what the leaderboard
top-N earn extra".
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260507_001"
down_revision = "20260504_002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pvp_seasons",
        sa.Column(
            "top_rewards",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("pvp_seasons", "top_rewards")
