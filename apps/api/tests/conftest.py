"""Shared fixtures for Hunter888 test suite.

Provides:
  - Async test client (ASGI transport, no real server)
  - In-memory SQLite database (aiosqlite) for isolation
  - Factory fixtures for User, Team, TrainingSession, etc.
  - Auth helpers (JWT tokens, authenticated client)
  - Redis mock
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool

# ─── Postgres → SQLite type shims ──────────────────────────────────────────
# Models reference Postgres-only types (JSONB / ARRAY / UUID). Tests run
# against in-memory SQLite, which can't compile those. Register dialect
# overrides BEFORE app.main is imported so create_all() emits SQLite-safe
# DDL — JSON for JSONB/ARRAY, CHAR(36) for UUID.

@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):  # noqa: ARG001
    return "JSON"


@compiles(PG_ARRAY, "sqlite")
def _compile_array_sqlite(type_, compiler, **kw):  # noqa: ARG001
    return "JSON"


@compiles(PG_UUID, "sqlite")
def _compile_uuid_sqlite(type_, compiler, **kw):  # noqa: ARG001
    return "CHAR(36)"


from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════════
# Database fixtures — in-memory SQLite for fast isolation
# ═══════════════════════════════════════════════════════════════════════════════

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def _strip_pg_casts_from_defaults(metadata) -> None:
    """Rewrite ``'<lit>'::jsonb`` server_defaults to plain SQL literals.

    Models declare ``server_default=text("'{}'::jsonb")`` for Postgres.
    SQLite doesn't know the ``::jsonb`` cast and rejects the DDL with
    a syntax error. We strip the cast in-place on the metadata so
    ``create_all`` emits ``DEFAULT '{}'`` — same effective value, just
    untyped, which SQLite stores in a JSON column without complaint.
    """
    import re
    from sqlalchemy import text as _sa_text
    from sqlalchemy.sql.elements import TextClause

    cast_re = re.compile(r"::\s*(jsonb|json|uuid|text|integer|boolean|timestamp(?:tz)?)", re.IGNORECASE)
    for table in metadata.tables.values():
        for col in table.columns:
            sd = col.server_default
            if sd is None:
                continue
            arg = getattr(sd, "arg", None)
            if isinstance(arg, TextClause):
                stripped = cast_re.sub("", str(arg))
                col.server_default.arg = _sa_text(stripped)


@pytest.fixture
async def db_engine():
    """Create a fresh in-memory SQLite engine for each test."""
    _strip_pg_casts_from_defaults(Base.metadata)
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    """Provide an async session bound to the test engine."""
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest.fixture
async def client(db_engine):
    """Async HTTP client with DB override (no real Postgres needed)."""
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# Auth helpers
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def make_token():
    """Factory fixture: create JWT access tokens for testing."""
    from app.core.security import create_access_token

    def _make(user_id: str | uuid.UUID | None = None, **extra) -> str:
        uid = str(user_id or uuid.uuid4())
        return create_access_token({"sub": uid, **extra})

    return _make


@pytest.fixture
def auth_headers(make_token):
    """Convenience fixture: returns Authorization headers for a random user."""
    token = make_token()
    return {"Authorization": f"Bearer {token}"}


# ═══════════════════════════════════════════════════════════════════════════════
# Factory fixtures — create test entities
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def user_factory():
    """Factory fixture: create User dicts for testing."""

    def _make(
        user_id: uuid.UUID | None = None,
        email: str | None = None,
        full_name: str = "Test Manager",
        role: str = "manager",
        team_id: uuid.UUID | None = None,
        is_active: bool = True,
    ) -> dict:
        uid = user_id or uuid.uuid4()
        return {
            "id": uid,
            "email": email or f"test_{uid.hex[:8]}@hunter888.test",
            "full_name": full_name,
            "role": role,
            "team_id": team_id,
            "is_active": is_active,
            "hashed_password": "$2b$12$test_hashed_password_placeholder",
        }

    return _make


@pytest.fixture
def chunk_factory():
    """Factory fixture: create LegalKnowledgeChunk-like dicts for testing."""

    def _make(
        chunk_id: uuid.UUID | None = None,
        category: str = "eligibility",
        fact_text: str = "Минимальный долг для банкротства — 500 000 руб.",
        law_article: str = "127-ФЗ ст. 213.3 п. 2",
        difficulty_level: int = 2,
        match_keywords: list | None = None,
        common_errors: list | None = None,
        tags: list | None = None,
        error_frequency: int = 5,
    ) -> dict:
        return {
            "id": chunk_id or uuid.uuid4(),
            "category": category,
            "fact_text": fact_text,
            "law_article": law_article,
            "difficulty_level": difficulty_level,
            "match_keywords": match_keywords or ["банкротство", "долг", "500"],
            "common_errors": common_errors or ["100 000 рублей", "300 000 рублей"],
            "correct_response_hint": "Порог — 500 тысяч рублей",
            "tags": tags or ["базовый", "порог"],
            "error_frequency": error_frequency,
            "is_active": True,
            "is_court_practice": False,
            "blitz_question": "Минимальный порог долга для банкротства ФЛ?",
            "blitz_answer": "500 000 рублей при просрочке от 3 месяцев",
        }

    return _make


# ═══════════════════════════════════════════════════════════════════════════════
# Redis mock
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_redis():
    """Mock Redis connection with basic get/set/setex support."""
    store = {}
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(side_effect=lambda k: store.get(k))
    redis_mock.set = AsyncMock(side_effect=lambda k, v: store.__setitem__(k, v))
    redis_mock.setex = AsyncMock(side_effect=lambda k, _ttl, v: store.__setitem__(k, v))
    redis_mock.delete = AsyncMock(side_effect=lambda k: store.pop(k, None))
    redis_mock.exists = AsyncMock(side_effect=lambda k: k in store)
    return redis_mock


@pytest.fixture
def mock_redis_pool(mock_redis):
    """Patch get_redis to return the mock."""
    with patch("app.core.redis_pool.get_redis", return_value=mock_redis):
        yield mock_redis


# ═══════════════════════════════════════════════════════════════════════════════
# Mock DB session (for unit tests that don't need full DB)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_db():
    """Lightweight mock AsyncSession for unit tests."""
    db = AsyncMock(spec=AsyncSession)
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    db.scalar = AsyncMock()
    db.get = AsyncMock()
    db.add = MagicMock()
    return db


# ═══════════════════════════════════════════════════════════════════════════════
# LLM mock (prevents real API calls during tests)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def mock_llm_calls():
    """Auto-mock all LLM API calls to prevent real network requests."""
    with patch("app.services.llm.generate_response", new_callable=AsyncMock, return_value="Mocked LLM response"):
        yield


@pytest.fixture(autouse=True)
def mock_embedding_calls():
    """Auto-mock Gemini embedding API to prevent real network requests."""
    fake_vec = [0.01] * 768
    with patch("app.services.rag_legal.get_embedding", new_callable=AsyncMock, return_value=fake_vec):
        yield
