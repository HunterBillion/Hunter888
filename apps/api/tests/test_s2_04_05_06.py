"""Tests for S2-04, S2-05, S2-06: Bracket Race Condition, Redis Atomicity, Scheduler Fixes.

Covers:
- S2-04: SELECT FOR UPDATE in bracket.py (_place_winner_in_next_round, complete_bracket_match)
- S2-05: Atomic Redis operations (emotion counter gates, embedding cache keys, adaptive CAS)
- S2-06: Scheduler lock TTL, placement_done reset, checkpoint ON CONFLICT
"""

import hashlib
import inspect
import re
from pathlib import Path

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# S2-04: Bracket Tournament Race Condition
# ═══════════════════════════════════════════════════════════════════════════════


class TestBracketRaceCondition:
    """Verify SELECT FOR UPDATE prevents concurrent bracket advancement."""

    def test_place_winner_uses_for_update(self):
        """_place_winner_in_next_round must lock the next_match row."""
        from app.services.bracket import _place_winner_in_next_round
        source = inspect.getsource(_place_winner_in_next_round)
        assert "with_for_update()" in source, \
            "_place_winner_in_next_round must use SELECT FOR UPDATE on next_match"

    def test_complete_bracket_match_uses_for_update(self):
        """complete_bracket_match must lock the match row."""
        from app.services.bracket import complete_bracket_match
        source = inspect.getsource(complete_bracket_match)
        assert "with_for_update()" in source, \
            "complete_bracket_match must use SELECT FOR UPDATE"

    def test_complete_bracket_match_not_uses_db_get(self):
        """complete_bracket_match must NOT use db.get() (doesn't support FOR UPDATE)."""
        from app.services.bracket import complete_bracket_match
        source = inspect.getsource(complete_bracket_match)
        assert "db.get(" not in source, \
            "Must use select().with_for_update() instead of db.get()"

    def test_place_winner_checks_status(self):
        """_place_winner_in_next_round must set winner for bye correctly."""
        from app.services.bracket import _place_winner_in_next_round
        source = inspect.getsource(_place_winner_in_next_round)
        assert "BracketMatchStatus.bye" in source
        assert "winner_id" in source


# ═══════════════════════════════════════════════════════════════════════════════
# S2-05a: Emotion Counter Gates — Atomic Lua Script
# ═══════════════════════════════════════════════════════════════════════════════


class TestEmotionCounterGateAtomic:
    """Verify counter gate uses atomic Lua script instead of GET+INCR."""

    def test_counter_gate_uses_lua(self):
        """Counter gate must use Redis eval() with Lua script."""
        emotion_path = Path(__file__).resolve().parent.parent / "app" / "services" / "emotion.py"
        content = emotion_path.read_text()

        # Must contain Lua script for atomic counter gate
        assert "redis.call('INCR'" in content, \
            "Counter gate must use Lua INCR for atomicity"
        assert "redis.call('DEL'" in content, \
            "Lua script must DEL counter when gate is passed"
        assert "redis.call('EXPIRE'" in content, \
            "Lua script must set EXPIRE on counter key"

    def test_no_separate_get_incr_pattern(self):
        """Counter gate must NOT have separate GET then INCR pattern."""
        emotion_path = Path(__file__).resolve().parent.parent / "app" / "services" / "emotion.py"
        content = emotion_path.read_text()

        # The old pattern: count = await redis.get(counter_key) followed by await redis.incr(counter_key)
        # Should not exist in the counter gate section
        counter_section_start = content.find("# Deduplicate and check for counter gates")
        counter_section_end = content.find("filtered_triggers.append(trigger)", counter_section_start)
        if counter_section_start > 0 and counter_section_end > 0:
            section = content[counter_section_start:counter_section_end]
            # Old non-atomic pattern should be gone
            assert "await redis.get(counter_key)" not in section, \
                "Counter gate must not use separate GET (use Lua script instead)"

    def test_lua_returns_gate_status(self):
        """Lua script must return 1 when gate is passed, 0 when not yet."""
        emotion_path = Path(__file__).resolve().parent.parent / "app" / "services" / "emotion.py"
        content = emotion_path.read_text()

        assert "return 1" in content and "return 0" in content, \
            "Lua script must return 1 (gate passed) or 0 (not yet)"


# ═══════════════════════════════════════════════════════════════════════════════
# S2-05b: Script Checker — Collision-Safe Cache Keys
# ═══════════════════════════════════════════════════════════════════════════════


class TestScriptCheckerCacheKeys:
    """Verify embedding cache uses hash-based keys, not truncated text."""

    def test_no_text_truncation_cache_key(self):
        """Cache key must NOT use text[:200] (collision risk)."""
        checker_path = Path(__file__).resolve().parent.parent / "app" / "services" / "script_checker.py"
        content = checker_path.read_text()

        assert "text[:200]" not in content, \
            "Cache key must not use text[:200] — collision risk"

    def test_uses_hash_for_cache_key(self):
        """Cache key must use hash of full text."""
        checker_path = Path(__file__).resolve().parent.parent / "app" / "services" / "script_checker.py"
        content = checker_path.read_text()

        assert "hashlib.sha256" in content, \
            "Must use hashlib.sha256 for collision-safe cache keys"
        assert "import hashlib" in content, \
            "Must import hashlib"

    def test_similarity_cache_key_uses_hash(self):
        """LLM similarity cache key must also use hash, not text[:80]."""
        checker_path = Path(__file__).resolve().parent.parent / "app" / "services" / "script_checker.py"
        content = checker_path.read_text()

        assert "text1[:80]" not in content, \
            "Similarity cache key must not use truncated text"

    def test_hash_collision_safety(self):
        """Verify different texts produce different cache keys."""
        text_a = "Добрый день, меня зовут Иван Петров, я из компании Финансовая Помощь."
        text_b = "Добрый день, меня зовут Иван Петров, я из компании Финансовая Защита."
        key_a = hashlib.sha256(text_a.encode()).hexdigest()
        key_b = hashlib.sha256(text_b.encode()).hexdigest()
        assert key_a != key_b, "Different texts must produce different hash keys"


# ═══════════════════════════════════════════════════════════════════════════════
# S2-05c: Adaptive Difficulty — CAS (WATCH/MULTI/EXEC)
# ═══════════════════════════════════════════════════════════════════════════════


class TestAdaptiveDifficultyCAS:
    """Verify adaptive difficulty uses CAS for state updates."""

    def test_atomic_process_method_exists(self):
        """IntraSessionAdapter must have _atomic_process method."""
        from app.services.adaptive_difficulty import IntraSessionAdapter
        assert hasattr(IntraSessionAdapter, "_atomic_process")
        assert inspect.iscoroutinefunction(IntraSessionAdapter._atomic_process)

    def test_process_reply_uses_atomic(self):
        """process_reply must attempt _atomic_process first."""
        from app.services.adaptive_difficulty import IntraSessionAdapter
        source = inspect.getsource(IntraSessionAdapter.process_reply)
        assert "_atomic_process" in source, \
            "process_reply must use _atomic_process for CAS safety"

    def test_atomic_process_uses_watch(self):
        """_atomic_process must use Redis WATCH for CAS."""
        from app.services.adaptive_difficulty import IntraSessionAdapter
        source = inspect.getsource(IntraSessionAdapter._atomic_process)
        assert "pipe.watch" in source, "Must use WATCH for optimistic locking"
        assert "pipe.multi()" in source, "Must use MULTI after modifications"

    def test_atomic_process_has_retry(self):
        """_atomic_process must retry on WatchError."""
        from app.services.adaptive_difficulty import IntraSessionAdapter
        source = inspect.getsource(IntraSessionAdapter._atomic_process)
        assert "for attempt in range" in source, "Must retry on CAS failure"


# ═══════════════════════════════════════════════════════════════════════════════
# S2-06a: Scheduler Lock TTL
# ═══════════════════════════════════════════════════════════════════════════════


class TestSchedulerLockTTL:
    """Verify scheduler lock TTL covers worst-case cycle duration."""

    def test_lock_ttl_covers_all_subtasks(self):
        """Lock TTL must be >= _TASK_TIMEOUT * num_subtasks."""
        sched_path = Path(__file__).resolve().parent.parent / "app" / "services" / "scheduler.py"
        content = sched_path.read_text()

        # Extract _TASK_TIMEOUT and _LOCK_TTL
        timeout_match = re.search(r'_TASK_TIMEOUT\s*=\s*(\d+)', content)
        lock_match = re.search(r'_LOCK_TTL\s*=\s*_TASK_TIMEOUT\s*\*\s*_NUM_SUBTASKS\s*\+\s*(\d+)', content)

        assert timeout_match, "_TASK_TIMEOUT must be defined"
        assert lock_match, "_LOCK_TTL must be _TASK_TIMEOUT * _NUM_SUBTASKS + buffer"

    def test_lock_not_interval_minus_10(self):
        """Lock TTL must NOT be CHECK_INTERVAL_MIN * 60 - 10 (old broken pattern)."""
        sched_path = Path(__file__).resolve().parent.parent / "app" / "services" / "scheduler.py"
        content = sched_path.read_text()

        assert "CHECK_INTERVAL_MIN * 60 - 10" not in content, \
            "Lock TTL must not be interval-based (too short for worst case)"


# ═══════════════════════════════════════════════════════════════════════════════
# S2-06b: placement_done Reset in Season
# ═══════════════════════════════════════════════════════════════════════════════


class TestPlacementDoneReset:
    """Verify PvP season reset clears placement_done."""

    def test_season_reset_clears_placement_done(self):
        """_check_seasonal_pvp_reset must set placement_done = False."""
        sched_path = Path(__file__).resolve().parent.parent / "app" / "services" / "scheduler.py"
        content = sched_path.read_text()

        # Find the seasonal reset section
        reset_pos = content.find("_check_seasonal_pvp_reset")
        assert reset_pos > 0
        reset_section = content[reset_pos:]

        assert "placement_done = False" in reset_section, \
            "Season reset must set placement_done = False on all ratings"

    def test_season_reset_clears_streak(self):
        """Season reset must also clear current_streak."""
        sched_path = Path(__file__).resolve().parent.parent / "app" / "services" / "scheduler.py"
        content = sched_path.read_text()

        reset_pos = content.find("_check_seasonal_pvp_reset")
        reset_section = content[reset_pos:]

        assert "current_streak = 0" in reset_section, \
            "Season reset must clear current_streak"


# ═══════════════════════════════════════════════════════════════════════════════
# S2-06c: Checkpoint Validator — ON CONFLICT DO NOTHING
# ═══════════════════════════════════════════════════════════════════════════════


class TestCheckpointGrandfatherIdempotency:
    """Verify checkpoint grandfathering uses INSERT ON CONFLICT."""

    def test_grandfather_uses_on_conflict(self):
        """grandfather_existing_user must use ON CONFLICT DO NOTHING."""
        from app.services.checkpoint_validator import CheckpointValidator
        source = inspect.getsource(CheckpointValidator.grandfather_existing_user)
        assert "on_conflict_do_nothing" in source, \
            "Must use INSERT ON CONFLICT DO NOTHING to prevent duplicate key errors"

    def test_grandfather_uses_pg_insert(self):
        """Must import and use PostgreSQL-specific insert for ON CONFLICT."""
        cp_path = Path(__file__).resolve().parent.parent / "app" / "services" / "checkpoint_validator.py"
        content = cp_path.read_text()
        assert "from sqlalchemy.dialects.postgresql import insert" in content or \
               "pg_insert" in content, \
            "Must use PostgreSQL dialect insert for ON CONFLICT support"

    def test_grandfather_no_select_then_insert(self):
        """grandfather must NOT use SELECT-then-INSERT pattern (TOCTOU race)."""
        from app.services.checkpoint_validator import CheckpointValidator
        source = inspect.getsource(CheckpointValidator.grandfather_existing_user)
        # Old pattern: select(UserCheckpoint).where(...) then self.db.add(...)
        assert "self.db.add(UserCheckpoint(" not in source, \
            "Must not use SELECT+INSERT pattern (use ON CONFLICT instead)"

    def test_grandfather_references_constraint_name(self):
        """ON CONFLICT must reference the correct unique constraint."""
        from app.services.checkpoint_validator import CheckpointValidator
        source = inspect.getsource(CheckpointValidator.grandfather_existing_user)
        assert "uq_user_checkpoint" in source, \
            "Must reference 'uq_user_checkpoint' constraint"
