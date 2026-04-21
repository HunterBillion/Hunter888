"""Tests for S2-02: Double XP Elimination.

Covers:
- EventBus emit callers moved into main transaction
- daily_drill.py SELECT FOR UPDATE for race condition prevention
- daily_goals.py race condition fix + timezone-aware timestamps
- RapidFireMatch idempotency guard
- GauntletRun idempotency guard
"""

import inspect
import re
from pathlib import Path

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# EventBus Emit — Same Transaction (Outbox Pattern Guarantee)
# ═══════════════════════════════════════════════════════════════════════════════


class TestEventBusSameTransaction:
    """Verify emit() is called within the main DB transaction, not a separate one."""

    def test_pvp_emit_not_in_separate_session(self):
        """ws/pvp.py must NOT create async_session() for event emission."""
        pvp_path = Path(__file__).resolve().parent.parent / "app" / "ws" / "pvp.py"
        content = pvp_path.read_text()

        # The old pattern: async with async_session() as ev_db: ... event_bus.emit(...db=ev_db...)
        # Should NOT exist anymore
        # Find all emit calls and check they DON'T use a variable named ev_db
        assert "ev_db" not in content, \
            "ws/pvp.py still uses separate ev_db session for event emission"

    def test_pvp_emit_uses_main_db(self):
        """PvP emit should use the main 'db' session, not a separate one."""
        pvp_path = Path(__file__).resolve().parent.parent / "app" / "ws" / "pvp.py"
        content = pvp_path.read_text()

        # Find the duel result emit block — should use db= (main session)
        # Look for EVENT_PVP_COMPLETED emit with db=db (not db=ev_db)
        pattern = r'event_bus\.emit\(GameEvent\([^)]*db=db'
        assert re.search(pattern, content), \
            "PvP EventBus.emit must use the main 'db' session parameter"

    def test_training_emit_not_in_separate_session(self):
        """Training scoring block must NOT use evt_db — must share db session."""
        train_path = Path(__file__).resolve().parent.parent / "app" / "ws" / "training.py"
        content = train_path.read_text()

        # The EVENT_TRAINING_COMPLETED emit must use db= not evt_db=
        # (evt_db is still used for standalone story events, which is fine)
        pattern = r'EVENT_TRAINING_COMPLETED[^}]*db=evt_db'
        assert not re.search(pattern, content), \
            "EVENT_TRAINING_COMPLETED must use main db session, not separate evt_db"

    def test_training_emit_in_same_transaction(self):
        """Training emit should be in the same db session as ManagerProgress update."""
        train_path = Path(__file__).resolve().parent.parent / "app" / "ws" / "training.py"
        content = train_path.read_text()

        # The emit should use db= (the main session, same txn as score + XP)
        pattern = r'event_bus\.emit\(GameEvent\([^)]*db=db'
        assert re.search(pattern, content), \
            "Training EventBus.emit must use db session (same txn as XP award)"

    def test_training_emit_before_commit(self):
        """emit() must happen BEFORE db.commit(), not after."""
        train_path = Path(__file__).resolve().parent.parent / "app" / "ws" / "training.py"
        content = train_path.read_text()

        # Find the emit and the commit — emit must come first for outbox atomicity
        emit_pos = content.find("event_bus.emit(GameEvent(")
        # Look for the commit that follows the ManagerProgress block
        commit_pos = content.find("await db.commit()", emit_pos) if emit_pos > 0 else -1
        assert emit_pos > 0, "event_bus.emit not found in training.py"
        assert commit_pos > 0, "db.commit() not found after event_bus.emit in training.py"
        assert emit_pos < commit_pos, \
            "event_bus.emit must come BEFORE db.commit() for outbox atomicity"

    def test_pvp_emit_before_commit(self):
        """emit() must happen BEFORE db.commit() in the duel completion block."""
        pvp_path = Path(__file__).resolve().parent.parent / "app" / "ws" / "pvp.py"
        content = pvp_path.read_text()

        # Find EVENT_PVP_COMPLETED and the subsequent db.commit()
        emit_pos = content.find("EVENT_PVP_COMPLETED")
        # After the emit block, look for the commit
        remaining = content[emit_pos:]
        commit_offset = remaining.find("await db.commit()")
        assert commit_offset > 0, "db.commit() not found after PvP emit"


# ═══════════════════════════════════════════════════════════════════════════════
# Daily Drill — Race Condition Prevention
# ═══════════════════════════════════════════════════════════════════════════════


class TestDailyDrillRaceCondition:
    """Verify SELECT FOR UPDATE prevents concurrent drill double-XP."""

    def test_drill_uses_for_update(self):
        """complete_drill must use .with_for_update() on ManagerProgress query."""
        source = inspect.getsource(__import__(
            "app.services.daily_drill", fromlist=["complete_drill"]
        ).complete_drill)
        assert "with_for_update()" in source, \
            "complete_drill must use SELECT FOR UPDATE to prevent race conditions"

    def test_drill_has_idempotency_check(self):
        """complete_drill must check last_drill_date before awarding XP."""
        source = inspect.getsource(__import__(
            "app.services.daily_drill", fromlist=["complete_drill"]
        ).complete_drill)
        assert "last_drill_date" in source, \
            "Must check last_drill_date for idempotency"
        assert "xp_earned=0" in source, \
            "Must return 0 XP if already completed today"

    def test_drill_uses_utc_timezone(self):
        """complete_drill must use timezone-aware UTC timestamps."""
        source = inspect.getsource(__import__(
            "app.services.daily_drill", fromlist=["complete_drill"]
        ).complete_drill)
        assert "timezone.utc" in source or "datetime.now(timezone.utc)" in source, \
            "Must use timezone-aware UTC"
        assert "datetime.utcnow()" not in source, \
            "Must NOT use deprecated datetime.utcnow()"


# ═══════════════════════════════════════════════════════════════════════════════
# Daily Goals — Race Condition + Timezone Fix
# ═══════════════════════════════════════════════════════════════════════════════


class TestDailyGoalsRaceCondition:
    """Verify goal XP award dedup and timezone fixes."""

    def test_award_goal_xp_uses_for_update(self):
        """award_goal_xp must use SELECT FOR UPDATE on dedup check."""
        source = inspect.getsource(__import__(
            "app.services.daily_goals", fromlist=["award_goal_xp"]
        ).award_goal_xp)
        assert "with_for_update()" in source, \
            "award_goal_xp must use FOR UPDATE to prevent TOCTOU race"

    def test_start_of_today_uses_utc(self):
        """_start_of_today must use timezone-aware UTC."""
        mod = __import__("app.services.daily_goals", fromlist=["_start_of_today"])
        source = inspect.getsource(mod._start_of_today)
        assert "datetime.utcnow()" not in source, \
            "_start_of_today must NOT use deprecated utcnow()"
        assert "timezone.utc" in source, \
            "_start_of_today must use timezone.utc"

    def test_start_of_week_uses_utc(self):
        """_start_of_week must use timezone-aware UTC."""
        mod = __import__("app.services.daily_goals", fromlist=["_start_of_week"])
        source = inspect.getsource(mod._start_of_week)
        assert "datetime.utcnow()" not in source, \
            "_start_of_week must NOT use deprecated utcnow()"
        assert "timezone.utc" in source, \
            "_start_of_week must use timezone.utc"

    def test_start_of_today_returns_tz_aware(self):
        """_start_of_today must return timezone-aware datetime."""
        from app.services.daily_goals import _start_of_today
        result = _start_of_today()
        assert result.tzinfo is not None, \
            "_start_of_today must return timezone-aware datetime"

    def test_start_of_week_returns_tz_aware(self):
        """_start_of_week must return timezone-aware datetime."""
        from app.services.daily_goals import _start_of_week
        result = _start_of_week()
        assert result.tzinfo is not None, \
            "_start_of_week must return timezone-aware datetime"


# ═══════════════════════════════════════════════════════════════════════════════
# RapidFire + Gauntlet — Idempotency Guards
# ═══════════════════════════════════════════════════════════════════════════════


class TestRapidFireIdempotency:
    """Verify RapidFireMatch cannot be completed twice."""

    def test_rapid_fire_uses_for_update(self):
        """RapidFire completion must SELECT FOR UPDATE."""
        pvp_path = Path(__file__).resolve().parent.parent / "app" / "ws" / "pvp.py"
        content = pvp_path.read_text()

        # Find the RapidFireMatch SELECT query — should have with_for_update
        rapid_section = content[content.find("RapidFireMatch"):]
        assert "with_for_update()" in rapid_section, \
            "RapidFireMatch completion must use SELECT FOR UPDATE"

    def test_rapid_fire_checks_completed_at(self):
        """RapidFire must check completed_at before processing."""
        pvp_path = Path(__file__).resolve().parent.parent / "app" / "ws" / "pvp.py"
        content = pvp_path.read_text()

        # Must check if already completed
        assert "already_completed" in content or "match.completed_at is not None" in content, \
            "RapidFireMatch must guard against double completion"


class TestGauntletIdempotency:
    """Verify GauntletRun cannot be completed twice."""

    def test_gauntlet_uses_for_update(self):
        """Gauntlet final result must SELECT FOR UPDATE."""
        pvp_path = Path(__file__).resolve().parent.parent / "app" / "ws" / "pvp.py"
        content = pvp_path.read_text()

        # Find the GauntletRun final result section
        # It should have with_for_update after the "Final result" comment
        final_pos = content.find("# ── Final result ──")
        assert final_pos > 0
        final_section = content[final_pos:final_pos + 500]
        assert "with_for_update()" in final_section, \
            "GauntletRun final result must use SELECT FOR UPDATE"

    def test_gauntlet_checks_is_completed(self):
        """Gauntlet must check is_completed before processing."""
        pvp_path = Path(__file__).resolve().parent.parent / "app" / "ws" / "pvp.py"
        content = pvp_path.read_text()

        final_pos = content.find("# ── Final result ──")
        final_section = content[final_pos:final_pos + 500]
        assert "run.is_completed" in final_section, \
            "GauntletRun must check is_completed to prevent double processing"
