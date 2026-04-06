"""Tests for health check endpoints.

Mocks the database session to test health endpoint responses
without a real PostgreSQL connection.
"""

from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# Health endpoint tests with mocked DB
# ---------------------------------------------------------------------------

class TestHealthEndpoints:
    """Test /api/health and /api/monitoring/health endpoints."""

    @pytest.fixture
    async def client(self):
        """Create test client with mocked lifespan to avoid real DB/Redis."""
        from contextlib import asynccontextmanager
        from fastapi import FastAPI

        from app.api.health import router as health_router

        # Create a minimal app with just the health router
        @asynccontextmanager
        async def noop_lifespan(app):
            yield

        test_app = FastAPI(lifespan=noop_lifespan)
        test_app.include_router(health_router, prefix="/api")

        async with AsyncClient(
            transport=ASGITransport(app=test_app),
            base_url="http://test",
        ) as ac:
            yield ac

    @patch("app.api.health.async_session")
    async def test_health_returns_200(self, mock_session_factory, client):
        """GET /api/health returns 200 with status ok."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_db.execute.return_value = mock_result

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = mock_cm

        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    @patch("app.api.health.async_session")
    async def test_monitoring_health_returns_200(self, mock_session_factory, client):
        """GET /api/monitoring/health returns 200 with status ok."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_db.execute.return_value = mock_result

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = mock_cm

        response = await client.get("/api/monitoring/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    @patch("app.api.health.async_session")
    async def test_health_degraded_on_db_error(self, mock_session_factory, client):
        """GET /api/health returns degraded when DB is down."""
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(side_effect=Exception("DB connection failed"))
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = mock_cm

        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"

    @patch("app.api.health.async_session")
    async def test_health_alias_calls_public(self, mock_session_factory, client):
        """GET /api/health is an alias for /api/monitoring/health."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_db.execute.return_value = mock_result

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = mock_cm

        r1 = await client.get("/api/health")
        r2 = await client.get("/api/monitoring/health")
        assert r1.json() == r2.json()
