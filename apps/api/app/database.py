from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.app_debug,
    # Pool size: 4 gunicorn workers × ~8 concurrent requests each = 32 ideal.
    # pool_size is per-process, so 30 base + 15 burst = 45 max per worker.
    pool_size=30,
    max_overflow=15,
    pool_pre_ping=True,   # Detect stale connections after DB restart/network hiccup
    pool_recycle=1800,     # Recycle connections every 30min to prevent stale TCP
    pool_timeout=10,       # Fail fast if all connections are busy (don't hang for 30s default)
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
