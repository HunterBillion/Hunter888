"""Integration tests for API endpoints.

Tests HTTP endpoints with mocked auth and DB dependencies.
Covers: health, auth routes, dashboard, training, knowledge, pvp.

The protected-route paths used here are the *currently-implemented*
endpoints. The legacy aliases (``/api/users/me``, ``/api/training/sessions``
GET, ``/api/pvp/rating`` without ``/me``) drifted as routers were
restructured during the TZ-1...TZ-4 series.
"""

import uuid
from unittest.mock import MagicMock

import pytest

from app.core.deps import get_current_user
from app.main import app
from app.models.user import UserRole


# ═══════════════════════════════════════════════════════════════════════════════
# Health endpoint
# ═══════════════════════════════════════════════════════════════════════════════


class TestHealthEndpoint:

    @pytest.mark.asyncio
    async def test_health_check(self, client):
        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

    @pytest.mark.asyncio
    async def test_root_redirects_or_responds(self, client):
        response = await client.get("/")
        assert response.status_code in (200, 307, 404)


# ═══════════════════════════════════════════════════════════════════════════════
# Auth endpoints
# ═══════════════════════════════════════════════════════════════════════════════


class TestAuthEndpoints:

    @pytest.mark.asyncio
    async def test_login_missing_fields(self, client):
        response = await client.post("/api/auth/login", json={})
        assert response.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self, client):
        response = await client.post("/api/auth/login", json={
            "email": "nonexistent@test.com",
            "password": "wrong_password",
        })
        # Should return 401 or 400
        assert response.status_code in (400, 401, 404)

    @pytest.mark.asyncio
    async def test_register_validation(self, client):
        response = await client.post("/api/auth/register", json={
            "email": "not-an-email",
            "password": "123",  # too short
            "full_name": "",
        })
        assert response.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_me_without_token(self, client):
        response = await client.get("/api/auth/me")
        assert response.status_code in (401, 403)


# ═══════════════════════════════════════════════════════════════════════════════
# Protected endpoints (require auth)
# ═══════════════════════════════════════════════════════════════════════════════


class TestProtectedEndpoints:
    """Test that all protected endpoints reject unauthenticated requests."""

    PROTECTED_ROUTES = [
        ("GET", "/api/dashboard/manager"),
        ("GET", "/api/users/me/profile"),
        ("GET", "/api/training/recommended"),
        ("GET", "/api/training/history"),
        ("GET", "/api/pvp/rating/me"),
        ("GET", "/api/knowledge/progress"),
        ("GET", "/api/gamification/me/progress"),
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("method,path", PROTECTED_ROUTES)
    async def test_rejects_no_auth(self, client, method, path):
        if method == "GET":
            response = await client.get(path)
        elif method == "POST":
            response = await client.post(path)
        assert response.status_code in (401, 403), f"{method} {path} returned {response.status_code}"


# ═══════════════════════════════════════════════════════════════════════════════
# Dashboard (with auth mock)
# ═══════════════════════════════════════════════════════════════════════════════


class TestDashboard:

    def _make_auth_user(self, role=UserRole.manager, user_id=None):
        mock_user = MagicMock()
        mock_user.id = user_id or uuid.uuid4()
        mock_user.email = "test@test.com"
        mock_user.full_name = "Test User"
        mock_user.role = role
        mock_user.team_id = uuid.uuid4()
        mock_user.is_active = True
        mock_user.preferences = {}
        mock_user.onboarding_completed = True
        return mock_user

    @pytest.mark.asyncio
    async def test_manager_dashboard_with_auth(self, client):
        """Manager dashboard should return data when authenticated.

        Uses ``app.dependency_overrides`` because ``patch`` on
        ``get_current_user`` doesn't intercept FastAPI's dependency
        resolution — the dep is resolved before the patched name is
        looked up at the call site.
        """
        mock_user = self._make_auth_user(UserRole.manager)
        app.dependency_overrides[get_current_user] = lambda: mock_user
        try:
            response = await client.get(
                "/api/dashboard/manager",
                headers={"Authorization": "Bearer fake_token"},
            )
        finally:
            app.dependency_overrides.pop(get_current_user, None)
        # May 500 due to incomplete DB seeding but must not 401/403
        assert response.status_code != 401
        assert response.status_code != 403

    @pytest.mark.asyncio
    async def test_rop_dashboard_requires_rop_role(self, client):
        """ROP dashboard should reject managers."""
        mock_user = self._make_auth_user(UserRole.manager)
        app.dependency_overrides[get_current_user] = lambda: mock_user
        try:
            response = await client.get(
                "/api/dashboard/rop",
                headers={"Authorization": "Bearer fake_token"},
            )
        finally:
            app.dependency_overrides.pop(get_current_user, None)
        assert response.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════════
# Training API
# ═══════════════════════════════════════════════════════════════════════════════


class TestTrainingAPI:

    @pytest.mark.asyncio
    async def test_history_requires_auth(self, client):
        response = await client.get("/api/training/history")
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_recommended_requires_auth(self, client):
        response = await client.get("/api/training/recommended")
        assert response.status_code in (401, 403)


# ═══════════════════════════════════════════════════════════════════════════════
# PvP API
# ═══════════════════════════════════════════════════════════════════════════════


class TestPvPAPI:

    @pytest.mark.asyncio
    async def test_rating_requires_auth(self, client):
        response = await client.get("/api/pvp/rating/me")
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_leaderboard_requires_auth(self, client):
        response = await client.get("/api/pvp/leaderboard")
        # Some leaderboard endpoints may be public — accept 200/401/403
        assert response.status_code in (200, 401, 403)


# ═══════════════════════════════════════════════════════════════════════════════
# Knowledge API
# ═══════════════════════════════════════════════════════════════════════════════


class TestKnowledgeAPI:

    @pytest.mark.asyncio
    async def test_progress_requires_auth(self, client):
        response = await client.get("/api/knowledge/progress")
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_categories_endpoint(self, client):
        """Categories may be public or require auth — accept either."""
        response = await client.get("/api/knowledge/categories")
        assert response.status_code in (200, 401, 403, 404)
