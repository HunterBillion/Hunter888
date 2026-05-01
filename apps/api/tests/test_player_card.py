"""Tests for the ``_player_card`` helper in ws/pvp.py (Content→Arena PR-1).

The helper builds a stable display-card dict that's embedded in
``match.found``, ``duel.brief``, and ``duel.result`` payloads so the
frontend (Phase 9) can render the arena scene (tier-themed background,
fighter cards, victory screen) without a follow-up REST call.

Contract being locked in:
* {id, name, tier, avatar_url} — exactly four keys, all stable types.
* For BOT_ID returns the synthetic ``{tier="ai", name="AI Бот"}`` card
  unconditionally (no DB lookup).
* For a missing User row returns safe placeholders so callers never
  have to handle None — keeps payloads bit-shaped.
* Tier comes from ``PvPRating.rank_tier`` enum value, falling back to
  ``"unranked"`` when the rating row is absent.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def fake_db():
    """A minimal AsyncSession stub: only ``execute`` is called by the helper."""
    db = MagicMock()
    db.execute = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_player_card_for_bot_returns_synthetic_card(fake_db):
    """BOT_ID is a sentinel — no DB query, deterministic card."""
    from app.ws.pvp import BOT_ID, _player_card

    card = await _player_card(fake_db, BOT_ID)

    assert card == {
        "id": str(BOT_ID),
        "name": "AI Бот",
        "tier": "ai",
        "avatar_url": None,
    }
    fake_db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_player_card_for_human_with_rating(fake_db):
    """Standard happy path: User + PvPRating both present."""
    from app.models.pvp import PvPRankTier
    from app.ws.pvp import _player_card

    user_id = uuid.uuid4()

    user_row = MagicMock(full_name="Vasya Pupkin", avatar_url="https://x/y.png")
    rating_row = MagicMock(rank_tier=PvPRankTier.gold_2)

    user_result = MagicMock()
    user_result.scalar_one_or_none = MagicMock(return_value=user_row)
    rating_result = MagicMock()
    rating_result.scalar_one_or_none = MagicMock(return_value=rating_row)

    fake_db.execute.side_effect = [user_result, rating_result]

    card = await _player_card(fake_db, user_id)

    assert card == {
        "id": str(user_id),
        "name": "Vasya Pupkin",
        "tier": "gold_2",
        "avatar_url": "https://x/y.png",
    }


@pytest.mark.asyncio
async def test_player_card_with_missing_rating_falls_back_to_unranked(fake_db):
    """User exists but no PvPRating row yet (fresh account) → unranked."""
    from app.ws.pvp import _player_card

    user_id = uuid.uuid4()
    user_row = MagicMock(full_name="Newbie", avatar_url=None)

    user_result = MagicMock()
    user_result.scalar_one_or_none = MagicMock(return_value=user_row)
    rating_result = MagicMock()
    rating_result.scalar_one_or_none = MagicMock(return_value=None)

    fake_db.execute.side_effect = [user_result, rating_result]

    card = await _player_card(fake_db, user_id)

    assert card["tier"] == "unranked"
    assert card["name"] == "Newbie"
    assert card["avatar_url"] is None


@pytest.mark.asyncio
async def test_player_card_with_missing_user_returns_placeholders(fake_db):
    """User row absent (deleted account, race) → safe placeholders, no None."""
    from app.ws.pvp import _player_card

    user_id = uuid.uuid4()

    user_result = MagicMock()
    user_result.scalar_one_or_none = MagicMock(return_value=None)
    rating_result = MagicMock()
    rating_result.scalar_one_or_none = MagicMock(return_value=None)

    fake_db.execute.side_effect = [user_result, rating_result]

    card = await _player_card(fake_db, user_id)

    assert card["id"] == str(user_id)
    assert card["name"] == "Неизвестно"
    assert card["tier"] == "unranked"
    assert card["avatar_url"] is None


@pytest.mark.asyncio
async def test_player_card_keys_are_stable_set(fake_db):
    """Frontend Phase 9 destructures these exact 4 keys — lock the shape."""
    from app.ws.pvp import BOT_ID, _player_card

    card = await _player_card(fake_db, BOT_ID)
    assert set(card.keys()) == {"id", "name", "tier", "avatar_url"}


@pytest.mark.asyncio
async def test_match_found_payload_includes_you_and_opponent(fake_db):
    """``match.found`` legacy fields preserved AND ``you``/``opponent`` added."""
    from app.ws.pvp import _match_found_payload

    p1 = uuid.uuid4()
    p2 = uuid.uuid4()
    match = {
        "duel_id": uuid.uuid4(),
        "player1_id": p1,
        "player2_id": p2,
        "player1_rating": 1500.0,
        "player2_rating": 1480.0,
        "difficulty": "medium",
    }

    # Patch the inner helper so we don't need to set up DB rows for both players.
    with patch(
        "app.ws.pvp._player_card",
        side_effect=[
            {"id": str(p1), "name": "P1", "tier": "silver_1", "avatar_url": None},
            {"id": str(p2), "name": "P2", "tier": "gold_3", "avatar_url": None},
        ],
    ):
        payload = await _match_found_payload(match, p1, fake_db)

    # Legacy fields preserved (FE that doesn't read new fields keeps working)
    assert payload["duel_id"] == str(match["duel_id"])
    assert payload["opponent_rating"] == 1480.0
    assert payload["difficulty"] == "medium"
    assert payload["is_pve"] is False
    # New fields available for FE Phase 9
    assert payload["you"]["name"] == "P1"
    assert payload["you"]["tier"] == "silver_1"
    assert payload["opponent"]["name"] == "P2"
    assert payload["opponent"]["tier"] == "gold_3"
