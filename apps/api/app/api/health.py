"""Health check and monitoring endpoints."""

import time

import redis.asyncio as aioredis
from fastapi import APIRouter
from sqlalchemy import text

from app.config import settings
from app.database import async_session

router = APIRouter()


@router.get("/monitoring/health")
async def health_check():
    """Full health check: verify DB and Redis connectivity."""
    checks = {}
    overall = "ok"

    # Check PostgreSQL
    try:
        async with async_session() as db:
            result = await db.execute(text("SELECT 1"))
            result.scalar()
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {type(e).__name__}"
        overall = "degraded"

    # Check Redis
    try:
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        try:
            await r.ping()
            checks["redis"] = "ok"
        finally:
            await r.aclose()
    except Exception as e:
        checks["redis"] = f"error: {type(e).__name__}"
        overall = "degraded"

    return {
        "status": overall,
        "service": "ai-trainer-api",
        "version": "0.1.0",
        "checks": checks,
        "timestamp": time.time(),
    }


@router.get("/monitoring/metrics")
async def prometheus_metrics():
    """Basic Prometheus-compatible metrics endpoint.

    Returns key application metrics in Prometheus text exposition format.
    """
    from app.database import engine

    pool = engine.pool
    lines = [
        "# HELP db_pool_size Current database connection pool size",
        "# TYPE db_pool_size gauge",
        f"db_pool_size {pool.size()}",
        "# HELP db_pool_checked_in Number of idle connections in pool",
        "# TYPE db_pool_checked_in gauge",
        f"db_pool_checked_in {pool.checkedin()}",
        "# HELP db_pool_checked_out Number of active connections from pool",
        "# TYPE db_pool_checked_out gauge",
        f"db_pool_checked_out {pool.checkedout()}",
        "# HELP db_pool_overflow Number of overflow connections",
        "# TYPE db_pool_overflow gauge",
        f"db_pool_overflow {pool.overflow()}",
        "# HELP app_info Application version info",
        "# TYPE app_info gauge",
        'app_info{version="0.1.0",env="' + settings.app_env + '"} 1',
    ]

    from fastapi.responses import PlainTextResponse

    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain")
