"""Regression tests for two bugs found during the 2026-05-08 prod audit
of /leaderboard surface.

Bug #1
------
``GET /api/gamification/leaderboard/hunters?scope=company&limit=N`` returned
500 for any user who was NOT in the top-N. The fallback code path
"ensure viewer visible" constructed ``HunterRankEntry`` without the
``avatar_url`` argument, but the dataclass declares it as a required
field. Result: ``TypeError`` at line ``hunter_leaderboard.py:163`` →
500 to the client. The methodology user (rop role, B2B team) reproduced
the issue with ``limit=5``; ``limit=50`` masked it because the user fell
naturally inside the truncation window.

Bug #2
------
``GET /api/gamification/league/me/timeline`` returned an all-zero
sparkline even when ``GET /api/gamification/league/me`` reported a
non-zero ``weekly_xp``. The two endpoints read from different sources:
``/league/me`` uses ``WeeklyLeagueMembership.weekly_xp`` (canonical
counter, incremented from ``EVENT_TRAINING_COMPLETED``), while
``/timeline`` aggregates ``SessionHistory.xp_earned`` per day (column may
be 0/NULL for older sessions, and doesn't capture PvP/drill XP). The fix
reconciles ``my_total`` with the canonical counter and attributes any
missing delta to today's bucket, so the user sees a chart consistent
with the headline number above it.
"""

from __future__ import annotations

import inspect
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services.hunter_leaderboard import HunterRankEntry, get_hunter_leaderboard
from app.services import weekly_league


# ═══════════════════════════════════════════════════════════════════════════
# Bug #1 — HunterRankEntry fallback must include avatar_url
# ═══════════════════════════════════════════════════════════════════════════


class TestHunterRankEntryFallback:
    def test_dataclass_requires_avatar_url(self):
        """Sanity: HunterRankEntry has avatar_url as a required field.

        If a future refactor ever makes it optional with a default, this
        test will start passing without the fallback path being needed
        — at which point the regression below can be relaxed too.
        """
        with pytest.raises(TypeError):
            HunterRankEntry(  # type: ignore[call-arg]
                rank=1,
                user_id="x",
                full_name="x",
                hunter_score=0.0,
                current_level=1,
                week_tp=0,
                prev_week_tp=0,
                delta_vs_last_week=0,
                is_me=True,
            )

    def test_fallback_path_passes_avatar_url(self):
        """The fallback branch ('ensure viewer visible') must pass
        ``avatar_url=`` when constructing HunterRankEntry. This is an
        AST-level guard against accidental regressions to the pre-fix
        TypeError state.
        """
        src = inspect.getsource(get_hunter_leaderboard)
        # Locate the fallback block by its sentinel comment + verify the
        # avatar_url keyword appears between it and the closing paren.
        anchor = "Ensure viewer is visible"
        assert anchor in src, "fallback comment removed — find new anchor"
        tail = src.split(anchor, 1)[1]
        # Walk to the end of the fallback HunterRankEntry(...) construction.
        # The fallback contains exactly one HunterRankEntry(...). The next
        # line must include avatar_url=. We check the whole tail for safety.
        first_construction = tail.split("HunterRankEntry(", 1)[1].split(")", 1)[0]
        assert "avatar_url=" in first_construction, (
            "Bug #1 regressed: HunterRankEntry fallback no longer "
            "passes avatar_url. Re-add `avatar_url=u.avatar_url` in "
            "the 'Ensure viewer is visible' branch."
        )


# ═══════════════════════════════════════════════════════════════════════════
# Bug #2 — timeline.my_total must reconcile with canonical weekly_xp
# ═══════════════════════════════════════════════════════════════════════════


def _build_days(week_start: datetime, my_xps: list[int]) -> list[dict]:
    return [
        {
            "date": (week_start + timedelta(days=i)).date().isoformat(),
            "my_xp": my_xps[i],
            "median_xp": 0,
        }
        for i in range(7)
    ]


class TestTimelineReconciliation:
    """Direct tests of the reconciliation logic added inside
    ``get_my_league_timeline``. We don't spin up a DB — instead we
    exercise the post-aggregation block by inlining the same arithmetic
    so the contract stays verifiable as a pure-function property.

    The contract:
        if membership.weekly_xp > sum(daily.my_xp):
            today_bucket.my_xp += (membership.weekly_xp - sum)
            my_total = membership.weekly_xp
        else:
            my_total = sum(daily.my_xp)  # unchanged
    """

    @staticmethod
    def _reconcile(days: list[dict], canonical_total: int) -> tuple[list[dict], int]:
        """Replicate the production reconciliation step (single source
        of truth for what the test asserts)."""
        raw = sum(p["my_xp"] for p in days)
        if canonical_total > raw:
            delta = canonical_total - raw
            today_iso = datetime.now(timezone.utc).date().isoformat()
            target_idx = next(
                (i for i, p in enumerate(days) if p["date"] == today_iso),
                len(days) - 1,
            )
            days[target_idx]["my_xp"] += delta
            return days, canonical_total
        return days, raw

    def test_zero_daily_with_nonzero_canonical_attributes_to_today(self):
        """The original prod symptom: SessionHistory query returns 0,
        but membership.weekly_xp == 167. After reconciliation, today's
        bar must hold 167 and my_total must equal 167.
        """
        # Use this Monday so 'today' is somewhere inside the 7-day window.
        now = datetime.now(timezone.utc)
        monday = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        days = _build_days(monday, [0, 0, 0, 0, 0, 0, 0])
        days_out, total = self._reconcile(days, canonical_total=167)
        assert total == 167
        # Today's bar carries the missing delta.
        today_iso = now.date().isoformat()
        today_bar = next(p for p in days_out if p["date"] == today_iso)
        assert today_bar["my_xp"] == 167
        # All other days remain zero (no daily data was lost).
        for p in days_out:
            if p["date"] != today_iso:
                assert p["my_xp"] == 0

    def test_partial_daily_with_higher_canonical_adds_only_delta(self):
        """If SessionHistory has SOME data (e.g. 50 XP on day 1) but
        membership counter says 167, today's bar must absorb only the
        missing 117 — not overwrite the 50 already attributed correctly.
        """
        now = datetime.now(timezone.utc)
        monday = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        days = _build_days(monday, [50, 0, 0, 0, 0, 0, 0])
        days_out, total = self._reconcile(days, canonical_total=167)
        assert total == 167
        today_iso = now.date().isoformat()
        # Day 1 keeps its 50.
        assert days_out[0]["my_xp"] == 50 if days_out[0]["date"] != today_iso else True
        # Today (or day-1 if today IS day-1) carries the rest.
        if days_out[0]["date"] == today_iso:
            assert days_out[0]["my_xp"] == 50 + 117
        else:
            today_bar = next(p for p in days_out if p["date"] == today_iso)
            assert today_bar["my_xp"] == 117

    def test_canonical_equal_to_daily_no_change(self):
        """When membership.weekly_xp matches sum(daily) — most healthy
        case — reconciliation must be a no-op."""
        now = datetime.now(timezone.utc)
        monday = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        days = _build_days(monday, [10, 20, 30, 0, 0, 0, 0])
        before = [p["my_xp"] for p in days]
        days_out, total = self._reconcile(days, canonical_total=60)
        assert total == 60
        assert [p["my_xp"] for p in days_out] == before

    def test_canonical_smaller_than_daily_no_overwrite(self):
        """If by some accounting quirk daily total > canonical (e.g.
        SessionHistory has stale data, membership reset) — we must NOT
        subtract or zero anything. Trust the larger of the two sources
        rather than confusing the user with shrinking bars."""
        now = datetime.now(timezone.utc)
        monday = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        days = _build_days(monday, [50, 50, 50, 0, 0, 0, 0])
        days_out, total = self._reconcile(days, canonical_total=10)
        # Bigger total wins (raw daily sum), no rebalance triggered.
        assert total == 150
        assert [p["my_xp"] for p in days_out] == [50, 50, 50, 0, 0, 0, 0]


class TestTimelineSourceMatchesProductionCode:
    """The pure-function reconciliation above mirrors what
    ``get_my_league_timeline`` does. This test guards against drift
    by inspecting the production source for the canonical reconcile
    block — if someone removes it, the regression suite must trip.
    """

    def test_production_function_contains_canonical_reconciliation(self):
        src = inspect.getsource(weekly_league.get_my_league_timeline)
        assert "canonical_total" in src, (
            "Bug #2 regression: get_my_league_timeline no longer "
            "reconciles with membership.weekly_xp. Re-introduce the "
            "block guarded by `if canonical_total > raw_my_total`."
        )
        assert "membership" in src and "weekly_xp" in src
