"""Tests for S3-01 (Team Challenge Persistence) and S3-02 (XP Daily Soft Cap).

Covers:
- S3-01a: TeamChallenge model exists with correct columns
- S3-01b: TeamChallengeProgress model with unique constraint
- S3-01c: Service uses DB, not in-memory dict
- S3-01d: Migration creates correct tables
- S3-01e: Cancel uses FOR UPDATE
- S3-01f: Winner bonus XP uses FOR UPDATE
- S3-01g: Duplicate challenge guard
- S3-02a: compute_effective_xp tier logic
- S3-02b: Exempt sources bypass cap
- S3-02c: Redis key format
- S3-02d: Integration in manager_progress
- S3-02e: Integration in arena_xp
- S3-02f: API endpoint exists
"""

import inspect
import uuid

import pytest


# ═══════════════════════════════════════════════════════════════════════════
# S3-01: Team Challenge Persistence
# ═══════════════════════════════════════════════════════════════════════════


class TestS301aTeamChallengeModel:
    """Verify TeamChallenge SQLAlchemy model."""

    def test_model_exists(self):
        from app.models.team_challenge import TeamChallenge
        assert TeamChallenge.__tablename__ == "team_challenges"

    def test_columns(self):
        from app.models.team_challenge import TeamChallenge
        cols = {c.name for c in TeamChallenge.__table__.columns}
        required = {
            "id", "created_by", "team_a_id", "team_b_id",
            "challenge_type", "status", "scenario_code", "bonus_xp",
            "deadline", "winner_team_id", "metadata_json",
            "created_at", "updated_at",
        }
        assert required.issubset(cols), f"Missing columns: {required - cols}"

    def test_foreign_keys(self):
        from app.models.team_challenge import TeamChallenge
        fks = set()
        for c in TeamChallenge.__table__.columns:
            for fk in c.foreign_keys:
                fks.add(fk.target_fullname)
        assert "users.id" in fks
        assert "teams.id" in fks

    def test_status_enum(self):
        from app.models.team_challenge import ChallengeStatus
        assert "active" in [s.value for s in ChallengeStatus]
        assert "completed" in [s.value for s in ChallengeStatus]
        assert "cancelled" in [s.value for s in ChallengeStatus]

    def test_challenge_type_enum(self):
        from app.models.team_challenge import ChallengeType
        assert "score_avg" in [t.value for t in ChallengeType]


class TestS301bProgressModel:
    """Verify TeamChallengeProgress model."""

    def test_model_exists(self):
        from app.models.team_challenge import TeamChallengeProgress
        assert TeamChallengeProgress.__tablename__ == "team_challenge_progress"

    def test_unique_constraint(self):
        from app.models.team_challenge import TeamChallengeProgress
        constraints = TeamChallengeProgress.__table__.constraints
        unique_names = [c.name for c in constraints if hasattr(c, 'name')]
        assert "uq_challenge_team" in unique_names

    def test_columns(self):
        from app.models.team_challenge import TeamChallengeProgress
        cols = {c.name for c in TeamChallengeProgress.__table__.columns}
        assert "completed_sessions" in cols
        assert "avg_score" in cols
        assert "total_members" in cols


class TestS301cServiceUsesDB:
    """Verify service no longer uses in-memory dict."""

    def test_no_challenges_dict(self):
        from app.services import team_challenge
        source = inspect.getsource(team_challenge)
        assert "_challenges: dict" not in source, \
            "In-memory _challenges dict should be removed"
        assert "_challenges[" not in source, \
            "Dict access pattern should be gone"

    def test_create_uses_db_model(self):
        from app.services.team_challenge import create_challenge
        source = inspect.getsource(create_challenge)
        assert "TeamChallenge(" in source, "Should create DB model instance"
        assert "db.add(" in source

    def test_cancel_uses_for_update(self):
        from app.services.team_challenge import cancel_challenge
        source = inspect.getsource(cancel_challenge)
        assert "with_for_update" in source, \
            "Cancel should lock row with FOR UPDATE"

    def test_get_active_uses_db(self):
        from app.services.team_challenge import get_active_challenges
        source = inspect.getsource(get_active_challenges)
        assert "select(TeamChallenge)" in source
        assert "scalars" in source

    def test_on_session_complete_hook_exists(self):
        from app.services.team_challenge import on_session_complete
        sig = inspect.signature(on_session_complete)
        assert "user_id" in sig.parameters
        assert "db" in sig.parameters

    def test_expire_overdue_exists(self):
        from app.services.team_challenge import expire_overdue_challenges
        sig = inspect.signature(expire_overdue_challenges)
        assert "db" in sig.parameters

    def test_winner_bonus_uses_for_update(self):
        from app.services.team_challenge import _apply_winner_bonus
        source = inspect.getsource(_apply_winner_bonus)
        assert "with_for_update" in source, \
            "Winner bonus XP must use FOR UPDATE"

    def test_duplicate_challenge_guard(self):
        from app.services.team_challenge import create_challenge
        source = inspect.getsource(create_challenge)
        assert "Active challenge already exists" in source, \
            "Should prevent duplicate active challenges"


class TestS301dMigration:
    """Verify migration creates correct tables."""

    @staticmethod
    def _read_migration() -> str:
        import pathlib
        p = pathlib.Path(__file__).parent.parent / "alembic" / "versions" / "20260414_004_team_challenge_persistence.py"
        return p.read_text()

    def test_migration_exists(self):
        source = self._read_migration()
        assert "def upgrade" in source
        assert "def downgrade" in source

    def test_creates_team_challenges_table(self):
        source = self._read_migration()
        assert '"team_challenges"' in source

    def test_creates_progress_table(self):
        source = self._read_migration()
        assert '"team_challenge_progress"' in source

    def test_creates_indexes(self):
        source = self._read_migration()
        assert "ix_team_challenges_teams" in source
        assert "ix_team_challenges_status_deadline" in source
        assert "uq_challenge_team" in source


class TestS301eModelRegistration:
    """Verify models are registered in __init__.py."""

    def test_team_challenge_importable(self):
        from app.models import TeamChallenge
        assert TeamChallenge.__tablename__ == "team_challenges"

    def test_progress_importable(self):
        from app.models import TeamChallengeProgress
        assert TeamChallengeProgress.__tablename__ == "team_challenge_progress"


# ═══════════════════════════════════════════════════════════════════════════
# S3-02: XP Daily Soft Cap
# ═══════════════════════════════════════════════════════════════════════════


class TestS302aComputeEffectiveXP:
    """Verify pure tier computation logic."""

    def test_tier1_full(self):
        from app.services.xp_daily_cap import compute_effective_xp
        # Under limit → 100%
        assert compute_effective_xp(100, 0) == 100
        assert compute_effective_xp(500, 500) == 500

    def test_tier1_boundary(self):
        from app.services.xp_daily_cap import compute_effective_xp, TIER_1_LIMIT
        # Exactly at tier 1 limit
        assert compute_effective_xp(TIER_1_LIMIT, 0) == TIER_1_LIMIT

    def test_tier2_half(self):
        from app.services.xp_daily_cap import compute_effective_xp, TIER_1_LIMIT
        # 200 XP over tier1 → 50% = 100
        result = compute_effective_xp(200, TIER_1_LIMIT)
        assert result == 100

    def test_tier3_quarter(self):
        from app.services.xp_daily_cap import compute_effective_xp, TIER_2_LIMIT
        # 400 XP in tier3 → 25% = 100
        result = compute_effective_xp(400, TIER_2_LIMIT)
        assert result == 100

    def test_cross_tier_boundary(self):
        from app.services.xp_daily_cap import compute_effective_xp, TIER_1_LIMIT
        # 1400 earned, award 200 → 100 at 100% + 100 at 50% = 100 + 50 = 150
        result = compute_effective_xp(200, TIER_1_LIMIT - 100)
        assert result == 100 + 50  # 100 from tier1 + 50% of 100 from tier2

    def test_zero_xp(self):
        from app.services.xp_daily_cap import compute_effective_xp
        assert compute_effective_xp(0, 500) == 0

    def test_negative_xp(self):
        from app.services.xp_daily_cap import compute_effective_xp
        assert compute_effective_xp(-10, 500) == 0

    def test_minimum_1_xp(self):
        from app.services.xp_daily_cap import compute_effective_xp, TIER_2_LIMIT
        # Even at tier3, positive XP should give at least 1
        result = compute_effective_xp(1, TIER_2_LIMIT)
        assert result >= 1


class TestS302bExemptSources:
    """Verify exempt sources configuration."""

    def test_achievement_exempt(self):
        from app.services.xp_daily_cap import EXEMPT_SOURCES
        assert "achievement" in EXEMPT_SOURCES

    def test_team_challenge_exempt(self):
        from app.services.xp_daily_cap import EXEMPT_SOURCES
        assert "team_challenge_win" in EXEMPT_SOURCES

    def test_training_not_exempt(self):
        from app.services.xp_daily_cap import EXEMPT_SOURCES
        assert "training_session" not in EXEMPT_SOURCES

    def test_arena_not_exempt(self):
        from app.services.xp_daily_cap import EXEMPT_SOURCES
        assert "arena_session" not in EXEMPT_SOURCES


class TestS302cRedisKeyFormat:
    """Verify Redis key structure."""

    def test_key_format(self):
        from app.services.xp_daily_cap import _redis_key
        uid = uuid.UUID("12345678-1234-1234-1234-123456789abc")
        key = _redis_key(uid, "2026-04-14")
        assert key == "xp:daily:12345678-1234-1234-1234-123456789abc:2026-04-14"

    def test_ttl_value(self):
        from app.services.xp_daily_cap import TTL_SECONDS
        assert TTL_SECONDS == 25 * 3600, "TTL should be 25 hours"


class TestS302dManagerProgressIntegration:
    """Verify daily cap is integrated into ManagerProgressService."""

    def test_update_after_session_uses_cap(self):
        from app.services.manager_progress import ManagerProgressService
        source = inspect.getsource(ManagerProgressService.update_after_session)
        assert "apply_daily_cap" in source, \
            "update_after_session should apply daily XP cap"
        assert "training_session" in source, \
            "Should pass 'training_session' as source"


class TestS302eArenaIntegration:
    """Verify daily cap is integrated into arena XP."""

    def test_arena_xp_uses_cap(self):
        from app.services.arena_xp import apply_arena_xp_to_progress
        source = inspect.getsource(apply_arena_xp_to_progress)
        assert "apply_daily_cap" in source, \
            "Arena XP should apply daily cap"
        assert "arena_session" in source


class TestS302fAPIEndpoint:
    """Verify the XP daily status endpoint exists."""

    def test_get_daily_xp_status_function(self):
        from app.services.xp_daily_cap import get_daily_xp_status
        sig = inspect.signature(get_daily_xp_status)
        assert "user_id" in sig.parameters

    def test_endpoint_registered(self):
        import ast
        import pathlib
        source = pathlib.Path(__file__).parent.parent / "app" / "api" / "gamification.py"
        content = source.read_text()
        assert '"/xp-daily"' in content, "GET /xp-daily endpoint should exist"
        assert "get_daily_xp_status" in content
