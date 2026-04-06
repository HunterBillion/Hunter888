"""Tests for the arena difficulty engine (services/arena_difficulty.py).

Covers rating tier boundaries, default profile for new users,
and court practice preference per tier. Uses mocked DB sessions.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.arena_difficulty import (
    DIFFICULTY_PROFILES,
    DEFAULT_PROFILE,
    get_arena_difficulty_profile,
    get_arena_rating_for_user,
)


# ---------------------------------------------------------------------------
# DIFFICULTY_PROFILES structure
# ---------------------------------------------------------------------------

class TestDifficultyProfiles:
    """Verify the static difficulty profile definitions."""

    def test_four_tiers_defined(self):
        assert len(DIFFICULTY_PROFILES) == 4

    def test_bronze_tier(self):
        max_r, diff_range, court, name = DIFFICULTY_PROFILES[0]
        assert max_r == 1400
        assert diff_range == (1, 3)
        assert court is False

    def test_silver_tier(self):
        max_r, diff_range, court, name = DIFFICULTY_PROFILES[1]
        assert max_r == 1600
        assert diff_range == (2, 4)
        assert court is False

    def test_gold_tier(self):
        max_r, diff_range, court, name = DIFFICULTY_PROFILES[2]
        assert max_r == 1800
        assert diff_range == (3, 5)
        assert court is True

    def test_platinum_tier(self):
        max_r, diff_range, court, name = DIFFICULTY_PROFILES[3]
        assert max_r == 9999
        assert diff_range == (4, 5)
        assert court is True

    def test_tiers_sorted_ascending(self):
        boundaries = [p[0] for p in DIFFICULTY_PROFILES]
        assert boundaries == sorted(boundaries)


# ---------------------------------------------------------------------------
# DEFAULT_PROFILE
# ---------------------------------------------------------------------------

class TestDefaultProfile:
    """Default profile for users with no PvP history."""

    def test_default_difficulty_range(self):
        assert DEFAULT_PROFILE["difficulty_range"] == (1, 3)

    def test_default_no_court_practice(self):
        assert DEFAULT_PROFILE["prefer_court_practice"] is False

    def test_default_has_pvp_data_false(self):
        assert DEFAULT_PROFILE["has_pvp_data"] is False

    def test_default_rating_1500(self):
        assert DEFAULT_PROFILE["rating"] == 1500


# ---------------------------------------------------------------------------
# get_arena_difficulty_profile (async, mocked DB)
# ---------------------------------------------------------------------------

class TestGetArenaDifficultyProfile:
    """Test difficulty profile lookup with mocked DB."""

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        return db

    def _make_rating_record(self, rating: float, total_duels: int = 10):
        record = MagicMock()
        record.rating = rating
        record.total_duels = total_duels
        return record

    async def test_no_record_returns_default(self, mock_db):
        """User with no PvP record gets default profile."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = result_mock

        profile = await get_arena_difficulty_profile(uuid.uuid4(), mock_db)
        assert profile == DEFAULT_PROFILE

    async def test_zero_duels_returns_default(self, mock_db):
        """User with PvP record but 0 duels gets default profile."""
        record = self._make_rating_record(1500, total_duels=0)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = record
        mock_db.execute.return_value = result_mock

        profile = await get_arena_difficulty_profile(uuid.uuid4(), mock_db)
        assert profile == DEFAULT_PROFILE

    async def test_bronze_rating(self, mock_db):
        """Rating 1200 -> Bronze tier."""
        record = self._make_rating_record(1200)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = record
        mock_db.execute.return_value = result_mock

        profile = await get_arena_difficulty_profile(uuid.uuid4(), mock_db)
        assert profile["difficulty_range"] == (1, 3)
        assert profile["prefer_court_practice"] is False
        assert profile["has_pvp_data"] is True

    async def test_silver_rating(self, mock_db):
        """Rating 1500 -> Silver tier (1400 <= r < 1600)."""
        record = self._make_rating_record(1500)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = record
        mock_db.execute.return_value = result_mock

        profile = await get_arena_difficulty_profile(uuid.uuid4(), mock_db)
        assert profile["difficulty_range"] == (2, 4)

    async def test_gold_rating(self, mock_db):
        """Rating 1700 -> Gold tier (1600 <= r < 1800)."""
        record = self._make_rating_record(1700)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = record
        mock_db.execute.return_value = result_mock

        profile = await get_arena_difficulty_profile(uuid.uuid4(), mock_db)
        assert profile["difficulty_range"] == (3, 5)
        assert profile["prefer_court_practice"] is True

    async def test_platinum_rating(self, mock_db):
        """Rating 2000 -> Platinum+ tier (>= 1800)."""
        record = self._make_rating_record(2000)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = record
        mock_db.execute.return_value = result_mock

        profile = await get_arena_difficulty_profile(uuid.uuid4(), mock_db)
        assert profile["difficulty_range"] == (4, 5)
        assert profile["prefer_court_practice"] is True

    async def test_boundary_at_1400(self, mock_db):
        """Rating exactly 1400 falls into Silver."""
        record = self._make_rating_record(1400)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = record
        mock_db.execute.return_value = result_mock

        profile = await get_arena_difficulty_profile(uuid.uuid4(), mock_db)
        assert profile["difficulty_range"] == (2, 4)

    async def test_boundary_at_1399(self, mock_db):
        """Rating 1399 falls into Bronze."""
        record = self._make_rating_record(1399)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = record
        mock_db.execute.return_value = result_mock

        profile = await get_arena_difficulty_profile(uuid.uuid4(), mock_db)
        assert profile["difficulty_range"] == (1, 3)


# ---------------------------------------------------------------------------
# get_arena_rating_for_user (async, mocked DB)
# ---------------------------------------------------------------------------

class TestGetArenaRatingForUser:
    """Test rating summary lookup for dashboard."""

    async def test_no_record_returns_defaults(self):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute.return_value = result_mock

        summary = await get_arena_rating_for_user(uuid.uuid4(), db)
        assert summary["rating"] == 1500
        assert summary["rank_tier"] == "unranked"
        assert summary["wins"] == 0
        assert summary["placement_done"] is False
