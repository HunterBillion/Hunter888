"""Centralized Redis connection pool for the entire application.

Every module that needs Redis MUST use `get_redis()` from this module
instead of calling `aioredis.from_url()` directly. Direct calls create
a new TCP connection per request — under load (~1000 users/day) this
exhausts Redis's connection limit and causes cascading failures.

Architecture:
┌──────────────────────────────────────────────────────────────────┐
│  get_redis()  →  shared ConnectionPool  →  Redis server         │
│                  (max 20 connections)                            │
│                                                                  │
│  Usage:                                                          │
│      from app.core.redis_pool import get_redis                   │
│      r = get_redis()             # instant — no IO               │
│      await r.get("my_key")       # uses pooled connection        │
│      # NO need to call r.aclose() — pool manages lifecycle       │
│                                                                  │
│  Lifecycle:                                                      │
│      close_redis_pool() — called once at app shutdown            │
└──────────────────────────────────────────────────────────────────┘
"""

import logging

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_pool: aioredis.ConnectionPool | None = None


def _ensure_pool() -> aioredis.ConnectionPool:
    """Lazily create a shared connection pool (thread-safe in async context)."""
    global _pool
    if _pool is None:
        _pool = aioredis.ConnectionPool.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=20,
            # Retry on transient connection errors
            retry_on_timeout=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        logger.info("Redis connection pool created (max_connections=20)")
    return _pool


def get_redis() -> aioredis.Redis:
    """Get a Redis client backed by the shared connection pool.

    This is the ONLY way to get a Redis connection in this app.
    Returns instantly (no IO) — actual connection is acquired on first command.
    Connections are automatically returned to the pool after each command.

    DO NOT call .aclose() on the returned client — the pool manages lifecycle.
    """
    return aioredis.Redis(connection_pool=_ensure_pool())


async def close_redis_pool() -> None:
    """Gracefully close the shared pool. Call once during app shutdown."""
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
        logger.info("Redis connection pool closed")


async def redis_health_check() -> bool:
    """Check if Redis is reachable. Used by health endpoints."""
    try:
        r = get_redis()
        await r.ping()
        return True
    except Exception:
        return False
