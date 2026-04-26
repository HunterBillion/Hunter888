"""Tests for S3-03 (Entitlement System).

Covers:
- S3-03a: UserSubscription model structure
- S3-03b: 4-tier plan limits
- S3-03c: Role-based exemptions (seed accounts → Master)
- S3-03d: Feature checks (session, PvP, RAG, boolean features)
- S3-03e: Migration creates table + seeds
- S3-03f: API endpoints registered
- S3-03g: Plan comparison for pricing page
- S3-03h: Diag v9 — ManagerProgress FOR UPDATE fix
"""

import inspect
import uuid

import pytest


# ═══════════════════════════════════════════════════════════════════════════
# S3-03a: UserSubscription Model
# ═══════════════════════════════════════════════════════════════════════════


class TestS303aModel:
    def test_model_exists(self):
        from app.models.subscription import UserSubscription
        assert UserSubscription.__tablename__ == "user_subscriptions"

    def test_columns(self):
        from app.models.subscription import UserSubscription
        cols = {c.name for c in UserSubscription.__table__.columns}
        required = {
            "id", "user_id", "plan_type", "started_at", "expires_at",
            "payment_id", "payment_provider", "metadata_json",
            "created_at", "updated_at",
        }
        assert required.issubset(cols), f"Missing: {required - cols}"

    def test_user_id_unique(self):
        from app.models.subscription import UserSubscription
        user_id_col = UserSubscription.__table__.c.user_id
        assert user_id_col.unique, "user_id must be unique (one subscription per user)"

    def test_plan_type_enum(self):
        from app.models.subscription import PlanType
        values = [p.value for p in PlanType]
        assert "scout" in values
        assert "ranger" in values
        assert "hunter" in values
        assert "master" in values

    def test_model_registered(self):
        from app.models import UserSubscription
        assert UserSubscription.__tablename__ == "user_subscriptions"


# ═══════════════════════════════════════════════════════════════════════════
# S3-03b: 4-Tier Plan Limits
# ═══════════════════════════════════════════════════════════════════════════


class TestS303bPlanLimits:
    def test_scout_limits(self):
        from app.services.entitlement import PlanType, PLAN_LIMITS
        s = PLAN_LIMITS[PlanType.scout]
        assert s.sessions_per_day == 3
        assert s.pvp_matches_per_day == 2
        assert s.rag_queries_per_day == 5
        assert s.ai_coach is False
        assert s.team_challenge is False

    def test_ranger_limits(self):
        from app.services.entitlement import PlanType, PLAN_LIMITS
        r = PLAN_LIMITS[PlanType.ranger]
        assert r.sessions_per_day == 10
        assert r.pvp_matches_per_day == 10
        assert r.rag_queries_per_day == 50
        assert r.ai_coach is True
        assert r.team_challenge is False

    def test_hunter_limits(self):
        from app.services.entitlement import PlanType, PLAN_LIMITS
        h = PLAN_LIMITS[PlanType.hunter]
        assert h.sessions_per_day == -1
        assert h.pvp_matches_per_day == -1
        assert h.rag_queries_per_day == 500
        assert h.team_challenge is True
        assert h.export_reports is True

    def test_master_limits(self):
        from app.services.entitlement import PlanType, PLAN_LIMITS
        m = PLAN_LIMITS[PlanType.master]
        assert m.sessions_per_day == -1
        assert m.pvp_matches_per_day == -1
        assert m.rag_queries_per_day == -1
        assert m.voice_cloning is True
        assert m.team_management is True
        assert m.llm_priority.value == "dedicated"

    def test_four_plans_exist(self):
        from app.services.entitlement import PlanType, PLAN_LIMITS
        assert len(PLAN_LIMITS) == 4


# ═══════════════════════════════════════════════════════════════════════════
# S3-03c: Role-Based Exemptions
# ═══════════════════════════════════════════════════════════════════════════


class TestS303cExemptions:
    def test_seed_accounts_listed(self):
        from app.services.entitlement import SEED_ACCOUNT_EMAILS
        assert "admin@trainer.local" in SEED_ACCOUNT_EMAILS
        assert "rop1@trainer.local" in SEED_ACCOUNT_EMAILS
        assert "manager1@trainer.local" in SEED_ACCOUNT_EMAILS
        assert len(SEED_ACCOUNT_EMAILS) == 8

    def test_elevated_roles(self):
        from app.services.entitlement import ELEVATED_ROLES
        assert "admin" in ELEVATED_ROLES
        assert "rop" in ELEVATED_ROLES
        # methodologist retired 2026-04-26 — must NOT be in ELEVATED_ROLES.
        # Ex-methodologist users were migrated to rop in alembic 20260426_002
        # and continue to receive Master via the rop entry.
        assert "methodologist" not in ELEVATED_ROLES
        assert "manager" not in ELEVATED_ROLES

    def test_resolve_plan_seed_account(self):
        from app.services.entitlement import _resolve_plan_for_user, PlanType
        from unittest.mock import MagicMock
        user = MagicMock()
        user.email = "admin@trainer.local"
        user.role.value = "admin"
        plan, is_seed = _resolve_plan_for_user(user, None)
        assert plan == PlanType.master
        assert is_seed is True

    def test_resolve_plan_rop_role(self):
        from app.services.entitlement import _resolve_plan_for_user, PlanType
        from unittest.mock import MagicMock
        user = MagicMock()
        user.email = "newrop@example.com"
        user.role.value = "rop"
        plan, is_seed = _resolve_plan_for_user(user, None)
        assert plan == PlanType.master
        assert is_seed is False

    def test_resolve_plan_manager_default(self):
        from app.services.entitlement import _resolve_plan_for_user, PlanType
        from unittest.mock import MagicMock
        user = MagicMock()
        user.email = "new@example.com"
        user.role.value = "manager"
        plan, is_seed = _resolve_plan_for_user(user, None)
        assert plan == PlanType.scout
        assert is_seed is False

    def test_resolve_plan_with_subscription(self):
        from app.services.entitlement import _resolve_plan_for_user, PlanType
        from unittest.mock import MagicMock
        from datetime import datetime, timezone, timedelta
        user = MagicMock()
        user.email = "paid@example.com"
        user.role.value = "manager"
        sub = MagicMock()
        sub.plan_type = "hunter"
        sub.expires_at = datetime.now(timezone.utc) + timedelta(days=30)
        plan, is_seed = _resolve_plan_for_user(user, sub)
        assert plan == PlanType.hunter


# ═══════════════════════════════════════════════════════════════════════════
# S3-03d: Feature Checks
# ═══════════════════════════════════════════════════════════════════════════


class TestS303dFeatureChecks:
    def test_session_limit_scout(self):
        from app.services.entitlement import (
            check_session_limit, EntitlementStatus, PlanType, PLAN_LIMITS,
        )
        ent = EntitlementStatus(
            plan=PlanType.scout, is_trial=True, trial_days_remaining=14,
            limits=PLAN_LIMITS[PlanType.scout], sessions_used_today=2,
            pvp_used_today=0, rag_used_today=0, is_seed_account=False,
            subscription_expires=None,
        )
        assert check_session_limit(ent) is True  # 2 < 3
        ent.sessions_used_today = 3
        assert check_session_limit(ent) is False  # 3 >= 3

    def test_session_limit_unlimited(self):
        from app.services.entitlement import (
            check_session_limit, EntitlementStatus, PlanType, PLAN_LIMITS,
        )
        ent = EntitlementStatus(
            plan=PlanType.hunter, is_trial=False, trial_days_remaining=0,
            limits=PLAN_LIMITS[PlanType.hunter], sessions_used_today=999,
            pvp_used_today=0, rag_used_today=0, is_seed_account=False,
            subscription_expires=None,
        )
        assert check_session_limit(ent) is True

    def test_pvp_limit(self):
        from app.services.entitlement import (
            check_pvp_limit, EntitlementStatus, PlanType, PLAN_LIMITS,
        )
        ent = EntitlementStatus(
            plan=PlanType.scout, is_trial=True, trial_days_remaining=14,
            limits=PLAN_LIMITS[PlanType.scout], sessions_used_today=0,
            pvp_used_today=2, rag_used_today=0, is_seed_account=False,
            subscription_expires=None,
        )
        assert check_pvp_limit(ent) is False  # 2 >= 2

    def test_rag_limit(self):
        from app.services.entitlement import (
            check_rag_limit, EntitlementStatus, PlanType, PLAN_LIMITS,
        )
        ent = EntitlementStatus(
            plan=PlanType.scout, is_trial=True, trial_days_remaining=14,
            limits=PLAN_LIMITS[PlanType.scout], sessions_used_today=0,
            pvp_used_today=0, rag_used_today=4, is_seed_account=False,
            subscription_expires=None,
        )
        assert check_rag_limit(ent) is True   # 4 < 5
        ent.rag_used_today = 5
        assert check_rag_limit(ent) is False

    def test_feature_check(self):
        from app.services.entitlement import (
            check_feature, EntitlementStatus, PlanType, PLAN_LIMITS,
        )
        scout_ent = EntitlementStatus(
            plan=PlanType.scout, is_trial=True, trial_days_remaining=14,
            limits=PLAN_LIMITS[PlanType.scout], sessions_used_today=0,
            pvp_used_today=0, rag_used_today=0, is_seed_account=False,
            subscription_expires=None,
        )
        assert check_feature(scout_ent, "ai_coach") is False
        assert check_feature(scout_ent, "team_challenge") is False

        master_ent = EntitlementStatus(
            plan=PlanType.master, is_trial=False, trial_days_remaining=0,
            limits=PLAN_LIMITS[PlanType.master], sessions_used_today=0,
            pvp_used_today=0, rag_used_today=0, is_seed_account=True,
            subscription_expires=None,
        )
        assert check_feature(master_ent, "ai_coach") is True
        assert check_feature(master_ent, "voice_cloning") is True
        assert check_feature(master_ent, "team_challenge") is True


# ═══════════════════════════════════════════════════════════════════════════
# S3-03e: Migration
# ═══════════════════════════════════════════════════════════════════════════


class TestS303eMigration:
    @staticmethod
    def _read_migration() -> str:
        import pathlib
        p = pathlib.Path(__file__).parent.parent / "alembic" / "versions" / "20260414_005_user_subscriptions.py"
        return p.read_text()

    def test_migration_exists(self):
        source = self._read_migration()
        assert "def upgrade" in source
        assert "def downgrade" in source

    def test_creates_table(self):
        source = self._read_migration()
        assert '"user_subscriptions"' in source

    def test_seeds_master_for_existing(self):
        source = self._read_migration()
        assert "admin@trainer.local" in source
        assert "'master'" in source
        assert "ON CONFLICT" in source

    def test_index_on_plan_expires(self):
        source = self._read_migration()
        assert "ix_user_subscriptions_plan_expires" in source


# ═══════════════════════════════════════════════════════════════════════════
# S3-03f: API Endpoints
# ═══════════════════════════════════════════════════════════════════════════


class TestS303fAPI:
    def test_subscription_router_registered(self):
        import pathlib
        source = pathlib.Path(__file__).parent.parent / "app" / "api" / "router.py"
        content = source.read_text()
        assert "subscription_router" in content
        assert "/subscription" in content

    def test_get_endpoint(self):
        import pathlib
        source = pathlib.Path(__file__).parent.parent / "app" / "api" / "subscription.py"
        content = source.read_text()
        assert '@router.get("")' in content
        assert "get_entitlement" in content

    def test_plans_endpoint(self):
        import pathlib
        source = pathlib.Path(__file__).parent.parent / "app" / "api" / "subscription.py"
        content = source.read_text()
        assert '"/plans"' in content
        assert "get_plan_comparison" in content

    def test_upgrade_endpoint(self):
        import pathlib
        source = pathlib.Path(__file__).parent.parent / "app" / "api" / "subscription.py"
        content = source.read_text()
        assert '"/upgrade"' in content
        assert "UpgradeRequest" in content


# ═══════════════════════════════════════════════════════════════════════════
# S3-03g: Plan Comparison
# ═══════════════════════════════════════════════════════════════════════════


class TestS303gPlanComparison:
    def test_returns_4_plans(self):
        from app.services.entitlement import get_plan_comparison
        plans = get_plan_comparison()
        assert len(plans) == 4
        ids = [p["id"] for p in plans]
        assert "scout" in ids
        assert "ranger" in ids
        assert "hunter" in ids
        assert "master" in ids

    def test_plan_has_required_fields(self):
        from app.services.entitlement import get_plan_comparison
        plans = get_plan_comparison()
        for p in plans:
            assert "name" in p
            assert "sessions_per_day" in p
            assert "pvp_matches_per_day" in p
            assert "analytics" in p
            assert "llm_priority" in p


# ═══════════════════════════════════════════════════════════════════════════
# S3-03h: Diag v9 — ManagerProgress FOR UPDATE Fix
# ═══════════════════════════════════════════════════════════════════════════


class TestS303hDiagFix:
    def test_get_or_create_profile_has_lock_param(self):
        from app.services.manager_progress import ManagerProgressService
        sig = inspect.signature(ManagerProgressService.get_or_create_profile)
        assert "lock" in sig.parameters

    def test_update_after_session_uses_lock(self):
        from app.services.manager_progress import ManagerProgressService
        source = inspect.getsource(ManagerProgressService.update_after_session)
        assert "lock=True" in source, \
            "update_after_session must use locked profile fetch"

    def test_get_or_create_has_for_update(self):
        from app.services.manager_progress import ManagerProgressService
        source = inspect.getsource(ManagerProgressService.get_or_create_profile)
        assert "with_for_update" in source

    def test_expire_overdue_in_scheduler(self):
        import pathlib
        source = pathlib.Path(__file__).parent.parent / "app" / "services" / "scheduler.py"
        content = source.read_text()
        assert "expire_overdue_challenges" in content, \
            "Scheduler must call expire_overdue_challenges"


# ═══════════════════════════════════════════════════════════════════════════
# S3-03i: Dependency injection checks
# ═══════════════════════════════════════════════════════════════════════════


class TestS303iDeps:
    def test_check_pvp_limit_exists(self):
        import pathlib
        source = pathlib.Path(__file__).parent.parent / "app" / "core" / "deps.py"
        content = source.read_text()
        assert "check_pvp_limit" in content

    def test_check_rag_limit_exists(self):
        import pathlib
        source = pathlib.Path(__file__).parent.parent / "app" / "core" / "deps.py"
        content = source.read_text()
        assert "check_rag_limit" in content
