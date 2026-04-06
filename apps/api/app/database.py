from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.app_debug,
    # Pool size: 4 gunicorn workers × ~15 concurrent requests each at 500-600 DAU peak.
    # Each training session can hold 2-3 connections briefly (message save + scoring + emotion).
    # pool_size is per-process: 50 base + 20 burst = 70 max per worker.
    # PostgreSQL max_connections should be >= 4 × 70 + 20 admin = 300.
    pool_size=50,
    max_overflow=20,
    pool_pre_ping=True,   # Detect stale connections after DB restart/network hiccup
    pool_recycle=1800,     # Recycle connections every 30min to prevent stale TCP
    pool_timeout=30,       # Queue up to 30s for a connection (was 10 — too aggressive, causes cascading failures)
    connect_args={
        "timeout": 10,                              # TCP connect timeout
        "server_settings": {
            "statement_timeout": "30000",            # 30s max per SQL statement (prevents runaway queries)
            "lock_timeout": "10000",                 # 10s max waiting for row locks
        },
    },
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
