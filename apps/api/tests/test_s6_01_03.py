"""
Tests for architectural specs 6.1 (Outbox Pattern) and 6.3 (Entitlement System).

6.1: OutboxEvent — aggregate_id + idempotency_key columns
6.3: Entitlement — Redis cache layer, invalidation
"""

import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ═══════════════════════════════════════════════════════════════════════════════
# 6.1: Outbox Pattern — aggregate_id, idempotency_key
# ═══════════════════════════════════════════════════════════════════════════════

class TestOutboxEventModel:
    """OutboxEvent has aggregate_id and idempotency_key per spec 6.1."""

    def test_has_aggregate_id(self):
        from app.models.outbox import OutboxEvent
        assert hasattr(OutboxEvent, "aggregate_id")

    def test_has_idempotency_key(self):
        from app.models.outbox import OutboxEvent
        assert hasattr(OutboxEvent, "idempotency_key")

    def test_aggregate_id_nullable(self):
        from app.models.outbox import OutboxEvent
        col = OutboxEvent.__table__.columns["aggregate_id"]
        assert col.nullable is True

    def test_aggregate_id_indexed(self):
        from app.models.outbox import OutboxEvent
        col = OutboxEvent.__table__.columns["aggregate_id"]
        assert col.index is True

    def test_idempotency_key_unique(self):
        from app.models.outbox import OutboxEvent
        col = OutboxEvent.__table__.columns["idempotency_key"]
        assert col.unique is True

    def test_idempotency_key_length(self):
        from app.models.outbox import OutboxEvent
        col = OutboxEvent.__table__.columns["idempotency_key"]
        assert col.type.length == 128

    def test_existing_columns_preserved(self):
        """Original columns are still present."""
        from app.models.outbox import OutboxEvent
        table_cols = {c.name for c in OutboxEvent.__table__.columns}
        expected = {
            "id", "event_type", "user_id", "payload", "status",
            "attempts", "max_attempts", "last_error", "next_retry_at",
            "created_at", "processed_at",
            "aggregate_id", "idempotency_key",
        }
        assert expected.issubset(table_cols)

    def test_pending_retry_index_exists(self):
        """Composite index on (status, next_retry_at) still exists."""
        from app.models.outbox import OutboxEvent
        index_names = {idx.name for idx in OutboxEvent.__table__.indexes}
        assert "idx_outbox_pending_retry" in index_names

    def test_outbox_status_enum(self):
        from app.models.outbox import OutboxStatus
        assert OutboxStatus.pending == "pending"
        assert OutboxStatus.failed == "failed"


# ═══════════════════════════════════════════════════════════════════════════════
# 6.3: Entitlement System — Redis cache layer
# ═══════════════════════════════════════════════════════════════════════════════

class TestEntitlementCache:
    """Entitlement Redis cache functions exist and have correct TTL."""

    def test_cache_ttl_constant(self):
        from app.services.entitlement import ENTITLEMENT_CACHE_TTL
        assert ENTITLEMENT_CACHE_TTL == 300  # 5 minutes

    def test_cache_functions_exist(self):
        from app.services.entitlement import (
            _get_cached_plan,
            _set_cached_plan,
            invalidate_entitlement_cache,
        )
        import asyncio
        assert asyncio.iscoroutinefunction(_get_cached_plan)
        assert asyncio.iscoroutinefunction(_set_cached_plan)
        assert asyncio.iscoroutinefunction(invalidate_entitlement_cache)

    @pytest.mark.asyncio
    async def test_get_cached_plan_returns_none_on_miss(self):
        """Cache miss returns None (Redis returns None)."""
        from app.services.entitlement import _get_cached_plan

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with patch("app.core.redis_pool.get_redis", return_value=mock_redis):
            result = await _get_cached_plan(uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_get_cached_plan_returns_plan_on_hit(self):
        """Cache hit returns PlanType."""
        from app.services.entitlement import _get_cached_plan, PlanType

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=b"ranger")

        with patch("app.core.redis_pool.get_redis", return_value=mock_redis):
            result = await _get_cached_plan(uuid.uuid4())
        assert result == PlanType.ranger

    @pytest.mark.asyncio
    async def test_set_cached_plan_uses_ttl(self):
        """Cache set uses correct TTL."""
        from app.services.entitlement import _set_cached_plan, PlanType

        mock_redis = AsyncMock()
        uid = uuid.uuid4()

        with patch("app.core.redis_pool.get_redis", return_value=mock_redis):
            await _set_cached_plan(uid, PlanType.hunter)

        mock_redis.set.assert_called_once_with(
            f"entitlement:{uid}", "hunter", ex=300
        )

    @pytest.mark.asyncio
    async def test_invalidate_cache(self):
        """invalidate_entitlement_cache deletes the key."""
        from app.services.entitlement import invalidate_entitlement_cache

        mock_redis = AsyncMock()
        uid = uuid.uuid4()

        with patch("app.core.redis_pool.get_redis", return_value=mock_redis):
            await invalidate_entitlement_cache(uid)

        mock_redis.delete.assert_called_once_with(f"entitlement:{uid}")

    @pytest.mark.asyncio
    async def test_cache_error_returns_none_gracefully(self):
        """Redis failure in cache read returns None, doesn't crash."""
        from app.services.entitlement import _get_cached_plan

        with patch("app.core.redis_pool.get_redis", side_effect=Exception("Redis down")):
            result = await _get_cached_plan(uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_set_error_silent(self):
        """Redis failure in cache write is silent."""
        from app.services.entitlement import _set_cached_plan, PlanType

        with patch("app.core.redis_pool.get_redis", side_effect=Exception("Redis down")):
            # Should not raise
            await _set_cached_plan(uuid.uuid4(), PlanType.scout)


class TestEntitlementPlanResolution:
    """Plan resolution logic and plan comparison."""

    def test_plan_comparison_has_is_free(self):
        """get_plan_comparison includes is_free flag."""
        from app.services.entitlement import get_plan_comparison
        plans = get_plan_comparison()
        scout = next(p for p in plans if p["id"] == "scout")
        assert scout["is_free"] is True
        ranger = next(p for p in plans if p["id"] == "ranger")
        assert ranger["is_free"] is False

    def test_scout_name_is_free(self):
        """Scout plan name is 'Бесплатный'."""
        from app.services.entitlement import get_plan_comparison
        plans = get_plan_comparison()
        scout = next(p for p in plans if p["id"] == "scout")
        assert scout["name"] == "Бесплатный"

    def test_seed_accounts_defined(self):
        from app.services.entitlement import SEED_ACCOUNT_EMAILS
        assert "admin@trainer.local" in SEED_ACCOUNT_EMAILS
        assert len(SEED_ACCOUNT_EMAILS) >= 8

    def test_free_trial_days(self):
        from app.services.entitlement import FREE_TRIAL_DAYS
        assert FREE_TRIAL_DAYS == 14
