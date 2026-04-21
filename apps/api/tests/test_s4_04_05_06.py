"""
Tests for S4-04, S4-05, S4-06 security/robustness tasks.

S4-04: catch_up_manager — silent failure when all params at minimum
S4-05: archetype_blender — deterministic random with session_id
S4-06: navigator — bounds check for empty QUOTES
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timezone


# ═══════════════════════════════════════════════════════════════════════════════
# S4-04: catch_up_manager — already_at_minimum is NOT silent
# ═══════════════════════════════════════════════════════════════════════════════

class TestS404SoftenCondition:
    """_soften_condition returns None when already at min; caller records it."""

    def _make_manager(self):
        from app.services.catch_up_manager import CatchUpManager
        return CatchUpManager(db=MagicMock())

    def test_soften_returns_dict_when_reducible(self):
        mgr = self._make_manager()
        result = mgr._soften_condition({"count": 5, "min_score": 60})
        assert result is not None
        assert result["count"] == 4
        assert result["min_score"] == 55

    def test_soften_returns_none_when_all_at_minimum(self):
        mgr = self._make_manager()
        # All values already at their minimums
        result = mgr._soften_condition({"count": 1, "min_score": 40})
        assert result is None

    def test_soften_partial_reduction(self):
        """Only reducible params change; at-minimum params stay."""
        mgr = self._make_manager()
        result = mgr._soften_condition({"count": 1, "min_score": 50})
        assert result is not None
        assert result["count"] == 1  # already at min, unchanged
        assert result["min_score"] == 45  # reduced

    def test_soften_unknown_params_ignored(self):
        """Params not in REDUCTION_RULES are preserved but don't trigger change."""
        mgr = self._make_manager()
        result = mgr._soften_condition({"type": "score_threshold", "count": 1})
        # count at min, type not in rules → nothing changed
        assert result is None

    def test_soften_empty_condition(self):
        mgr = self._make_manager()
        result = mgr._soften_condition({})
        assert result is None


class TestS404CheckAndApplyNotSilent:
    """check_and_apply emits 'already_at_minimum' action instead of skipping."""

    @pytest.mark.asyncio
    async def test_already_at_minimum_produces_action(self):
        from app.services.catch_up_manager import CatchUpManager
        from datetime import timedelta

        db = AsyncMock()
        mgr = CatchUpManager(db=db)

        # Mock a checkpoint stuck 15 days, already at minimum
        ucp = MagicMock()
        ucp.user_id = "user-1"
        ucp.is_completed = False
        ucp.is_softened = False
        ucp.updated_at = datetime.now(timezone.utc) - timedelta(days=15)
        ucp.created_at = ucp.updated_at
        ucp.progress = {}

        cp_def = MagicMock()
        cp_def.code = "cp_test"
        cp_def.condition = {"count": 1, "min_score": 40}  # all at min

        mock_result = MagicMock()
        mock_result.all.return_value = [(ucp, cp_def)]
        db.execute = AsyncMock(return_value=mock_result)

        actions = await mgr.check_and_apply("user-1")

        assert len(actions) == 1
        assert actions[0]["action"] == "already_at_minimum"
        assert actions[0]["stage"] == 2
        assert actions[0]["softened"] is None
        assert actions[0]["code"] == "cp_test"

    @pytest.mark.asyncio
    async def test_softened_action_still_works(self):
        from app.services.catch_up_manager import CatchUpManager
        from datetime import timedelta

        db = AsyncMock()
        mgr = CatchUpManager(db=db)

        ucp = MagicMock()
        ucp.user_id = "user-1"
        ucp.is_completed = False
        ucp.is_softened = False
        ucp.updated_at = datetime.now(timezone.utc) - timedelta(days=15)
        ucp.created_at = ucp.updated_at
        ucp.progress = {}

        cp_def = MagicMock()
        cp_def.code = "cp_test"
        cp_def.condition = {"count": 5, "min_score": 60}  # reducible

        mock_result = MagicMock()
        mock_result.all.return_value = [(ucp, cp_def)]
        db.execute = AsyncMock(return_value=mock_result)

        actions = await mgr.check_and_apply("user-1")

        assert len(actions) == 1
        assert actions[0]["action"] == "softened"
        assert actions[0]["softened"]["count"] == 4


# ═══════════════════════════════════════════════════════════════════════════════
# S4-05: archetype_blender — deterministic random
# ═══════════════════════════════════════════════════════════════════════════════

class TestS405BlendPadDeterministic:
    """blend_pad with session_id produces reproducible noise."""

    def test_same_session_id_same_result(self):
        from app.services.archetype_blender import blend_pad

        pad_a = {"P": 0.5, "A": 0.3, "D": 0.7}
        pad_b = {"P": 0.2, "A": 0.6, "D": 0.4}

        r1 = blend_pad(pad_a, pad_b, session_id="session-abc-123")
        r2 = blend_pad(pad_a, pad_b, session_id="session-abc-123")
        assert r1 == r2

    def test_different_session_id_different_result(self):
        from app.services.archetype_blender import blend_pad

        pad_a = {"P": 0.5, "A": 0.3, "D": 0.7}
        pad_b = {"P": 0.2, "A": 0.6, "D": 0.4}

        r1 = blend_pad(pad_a, pad_b, session_id="session-1")
        r2 = blend_pad(pad_a, pad_b, session_id="session-2")
        # Highly unlikely to be equal with different seeds
        assert r1 != r2

    def test_no_session_id_still_works(self):
        """Without session_id, blend_pad still returns valid PAD dict."""
        from app.services.archetype_blender import blend_pad

        pad_a = {"P": 0.5, "A": 0.3, "D": 0.7}
        pad_b = {"P": 0.2, "A": 0.6, "D": 0.4}

        result = blend_pad(pad_a, pad_b)
        assert "P" in result and "A" in result and "D" in result


class TestS405ShiftingArchetypeDeterministic:
    """ShiftingArchetype with session_id produces reproducible pool and shifts."""

    def test_same_session_id_same_pool(self):
        from app.services.archetype_blender import ShiftingArchetype

        sa1 = ShiftingArchetype(difficulty=10, session_id="sess-xyz")
        sa2 = ShiftingArchetype(difficulty=10, session_id="sess-xyz")
        assert sa1.pool == sa2.pool
        assert sa1.shift_interval == sa2.shift_interval

    def test_different_session_id_different_pool(self):
        from app.services.archetype_blender import ShiftingArchetype

        sa1 = ShiftingArchetype(difficulty=10, session_id="sess-1")
        sa2 = ShiftingArchetype(difficulty=10, session_id="sess-2")
        # Pools are shuffled differently — very unlikely to match
        assert sa1.pool != sa2.pool or sa1.shift_interval != sa2.shift_interval

    def test_no_session_id_non_deterministic(self):
        """Without session_id, each instance gets its own unseeded RNG."""
        from app.services.archetype_blender import ShiftingArchetype

        sa = ShiftingArchetype(difficulty=10)
        assert len(sa.pool) >= 5
        assert sa.shift_interval in (3, 4)

    def test_check_shift_deterministic(self):
        from app.services.archetype_blender import ShiftingArchetype

        sa1 = ShiftingArchetype(difficulty=10, session_id="sess-shift")
        sa2 = ShiftingArchetype(difficulty=10, session_id="sess-shift")

        shifts1 = [sa1.check_shift() for _ in range(10)]
        shifts2 = [sa2.check_shift() for _ in range(10)]
        assert shifts1 == shifts2


# ═══════════════════════════════════════════════════════════════════════════════
# S4-06: navigator — bounds check
# ═══════════════════════════════════════════════════════════════════════════════

class TestS406NavigatorBoundsCheck:
    """get_navigator_response handles empty QUOTES without crash."""

    def test_normal_response_has_quote(self):
        from app.services.navigator import get_navigator_response

        now = datetime(2025, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
        resp = get_navigator_response(now)
        assert "text" in resp
        assert "author" in resp
        assert resp["total"] > 0

    def test_empty_quotes_returns_fallback(self):
        from app.services import navigator

        with patch.object(navigator, "QUOTES", []), \
             patch.object(navigator, "TOTAL_QUOTES", 0):
            now = datetime(2025, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
            resp = navigator.get_navigator_response(now)

            assert resp["total"] == 0
            assert resp["text"] == "Двигайся вперёд."
            assert resp["slot"] == 1  # hour 10 // 6

    def test_quote_index_zero_on_empty(self):
        from app.services import navigator

        with patch.object(navigator, "TOTAL_QUOTES", 0):
            idx = navigator.get_current_quote_index(
                datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            )
            assert idx == 0

    def test_quote_index_wraps_correctly(self):
        from app.services.navigator import get_current_quote_index, TOTAL_QUOTES

        # Different times should give different indices within bounds
        for hour in (0, 6, 12, 18):
            now = datetime(2025, 6, 15, hour, 0, 0, tzinfo=timezone.utc)
            idx = get_current_quote_index(now)
            assert 0 <= idx < TOTAL_QUOTES

    def test_response_fields_complete(self):
        from app.services.navigator import get_navigator_response

        now = datetime(2025, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
        resp = get_navigator_response(now)
        required = ["index", "total", "text", "author", "source",
                     "category", "category_label", "slot",
                     "next_change_at", "seconds_remaining"]
        for field in required:
            assert field in resp, f"Missing field: {field}"
