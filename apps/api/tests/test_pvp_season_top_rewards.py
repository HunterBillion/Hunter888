"""Regression tests for PvPSeason.top_rewards (added 2026-05-07).

The /pvp slim hero banner needs structured "top-N rewards" data to render
"Сезон до 31 мая · топ-1 = 100 AP". Existing `rewards` JSONB stores
per-tier rewards (diamond/platinum/gold), which doesn't model rank-based
prizes. New `top_rewards` JSONB stores a list of {rank, ap, badge?}.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


@pytest.mark.asyncio
async def test_pvp_season_persists_top_rewards(db_session):
    from app.models.pvp import PvPSeason

    s = PvPSeason(
        name="Test Season",
        start_date=datetime.now(timezone.utc),
        end_date=datetime.now(timezone.utc) + timedelta(days=30),
        is_active=True,
        rewards={"diamond": {"xp": 500}},
        top_rewards=[
            {"rank": 1, "ap": 100, "badge": "champion-test"},
            {"rank": 2, "ap": 60},
            {"rank": 3, "ap": 30},
        ],
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)

    assert isinstance(s.top_rewards, list)
    assert len(s.top_rewards) == 3
    assert s.top_rewards[0]["rank"] == 1
    assert s.top_rewards[0]["ap"] == 100
    assert s.top_rewards[0]["badge"] == "champion-test"
    assert "badge" not in s.top_rewards[2] or s.top_rewards[2]["badge"] is None


@pytest.mark.asyncio
async def test_pvp_season_top_rewards_nullable(db_session):
    """Backward compat: legacy seasons may not have top_rewards yet."""
    from app.models.pvp import PvPSeason

    s = PvPSeason(
        name="Legacy Season",
        start_date=datetime.now(timezone.utc),
        end_date=datetime.now(timezone.utc) + timedelta(days=30),
        is_active=True,
        rewards={"diamond": {"xp": 500}},
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    assert s.top_rewards is None


def test_season_response_schema_serialises_top_rewards():
    """Pydantic schema accepts None and a list-of-dict."""
    from app.schemas.pvp import SeasonResponse

    payload = {
        "id": "11111111-2222-3333-4444-555555555555",
        "name": "Schema test",
        "start_date": datetime.now(timezone.utc).isoformat(),
        "end_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        "is_active": True,
        "rewards": None,
        "top_rewards": [
            {"rank": 1, "ap": 100, "badge": "x"},
            {"rank": 2, "ap": 60},
        ],
    }
    parsed = SeasonResponse(**payload)
    assert parsed.top_rewards is not None
    assert len(parsed.top_rewards) == 2
    assert parsed.top_rewards[0].rank == 1
    assert parsed.top_rewards[1].badge is None

    # And backward-compat: omit top_rewards entirely
    payload.pop("top_rewards")
    parsed2 = SeasonResponse(**payload)
    assert parsed2.top_rewards is None
