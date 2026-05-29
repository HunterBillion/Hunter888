"""Race-resolution test for `submit_exam` (CLAUDE.md §4.1, §4.4).

Audit fix BUG#4 (2026-05-29): `submit_exam` previously loaded the attempt
with an unlocked `db.get(...)`. Two concurrent submits for the SAME attempt
both saw `status == "in_progress"`, both passed the guard, and both ran
`_issue_certificate` — which has no dedup and no unique constraint on
`(user_id, level)`. Result: **duplicate certificates** AND duplicate
"passed" Telegram notifications. The fix locks the row with
`SELECT ... FOR UPDATE` before the status guard, so the second submit blocks
until the first commits, then reads the terminal status and bails.

**Why this test needs real Postgres:** the symptom only materialises when
`FOR UPDATE` actually serialises two connections. The shared conftest uses
SQLite/StaticPool (single connection, `FOR UPDATE` is a no-op), where a
sequential test would pass on *pre-fix* code too — violating §4.6.1. CI
provides a real Postgres service (see `.github/workflows/ci.yml`); when only
SQLite is available (local default) the whole module skips.
"""
from __future__ import annotations

import asyncio
import os
import random
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.exam import Certificate, ExamAttempt
from app.models.user import User, UserRole
from app.services.exam_service import submit_exam

_DATABASE_URL = os.environ.get("DATABASE_URL", "")
_IS_PG = _DATABASE_URL.startswith("postgresql")

pytestmark = pytest.mark.skipif(
    not _IS_PG,
    reason="exam FOR UPDATE race needs real Postgres; SQLite can't lock "
    "(CI provides Postgres — see ci.yml)",
)


@pytest.fixture
async def pg_sessionmaker():
    """Async sessionmaker bound to the real Postgres from DATABASE_URL.

    Uses a connection pool so `asyncio.gather`-ed sessions get distinct
    connections — a prerequisite for the FOR UPDATE row lock to serialise
    them. Skips if the schema isn't migrated in the target DB.
    """
    engine = create_async_engine(_DATABASE_URL, pool_size=5, max_overflow=5)
    # Verify the schema exists (CI runs `alembic upgrade head` first). On a
    # fresh/unmigrated PG, skip rather than erroring with a cryptic ProgError.
    async with engine.connect() as conn:
        try:
            await conn.execute(text("SELECT 1 FROM exam_attempts LIMIT 1"))
        except Exception:  # noqa: BLE001 — any DB error here means "not ready"
            await engine.dispose()
            pytest.skip("exam_attempts not migrated in target Postgres")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_parallel_submit_issues_single_certificate(pg_sessionmaker):
    """Two genuinely-parallel submits for one attempt → exactly ONE
    certificate and ONE Telegram notification (BUG#4).

    Pre-fix (unlocked `db.get`) this produced TWO certificates and TWO
    notifications, so this assertion fails on pre-fix code — proving the
    test catches the regression (§4.6.1)."""
    user_id = uuid.uuid4()
    attempt_id = uuid.uuid4()
    # Unique chat id to satisfy the UNIQUE constraint on telegram_chat_id and
    # to trigger the TG-notification branch in submit_exam.
    chat_id = random.randint(1_000_000_000, 9_000_000_000_000)
    questions = [
        {"question": f"q{i}", "options": ["a", "b", "c", "d"], "correct": 0}
        for i in range(4)
    ]
    answers = [{"index": i, "selected": 0} for i in range(4)]  # all correct → pass

    # ── setup row state ──────────────────────────────────────────────────
    async with pg_sessionmaker() as s:
        s.add(User(
            id=user_id,
            email=f"exam_race_{user_id.hex[:10]}@test.local",
            hashed_password="$2b$12$placeholder",
            full_name="Race Tester",
            role=UserRole.manager,
            telegram_chat_id=chat_id,
        ))
        s.add(ExamAttempt(
            id=attempt_id,
            user_id=user_id,
            level=5,
            status="in_progress",
            total_questions=len(questions),
            pass_threshold=10.0,  # low → 100% score passes
            questions_data={"questions": questions},
            started_at=datetime.utcnow(),
        ))
        await s.commit()

    tg_mock = AsyncMock()

    async def _submit() -> dict:
        # Each task owns its session/connection and commits — so the winner
        # releases its FOR UPDATE lock and the loser can then read the
        # terminal status.
        async with pg_sessionmaker() as s:
            res = await submit_exam(attempt_id, answers, s)
            await s.commit()
            return res

    try:
        with patch(
            "app.services.exam_service.generate_certificate_pdf",
            new=AsyncMock(return_value="/tmp/cert.pdf"),
        ), patch(
            "app.services.telegram_bot.telegram_bot.send_exam_passed",
            new=tg_mock,
        ):
            # Genuinely parallel, not sequential awaits (CLAUDE.md §4.1).
            results = await asyncio.gather(_submit(), _submit())

        # ── assert: exactly one certificate exists for the attempt ──────
        async with pg_sessionmaker() as s:
            certs = (
                await s.execute(
                    select(Certificate).where(
                        Certificate.exam_attempt_id == attempt_id
                    )
                )
            ).scalars().all()
        assert len(certs) == 1, (
            f"{len(certs)} certificates issued — BUG#4 regression "
            "(FOR UPDATE lock failed to serialise concurrent submits)"
        )

        # Exactly one "passed" Telegram notification.
        assert tg_mock.await_count == 1, (
            f"send_exam_passed called {tg_mock.await_count}× — duplicate "
            "notification (BUG#4 regression)"
        )

        # One submit graded+issued; the other found the exam already finished.
        issued = [r for r in results if r.get("certificate_id")]
        closed = [r for r in results if r.get("error")]
        assert len(issued) == 1, f"expected 1 issuing submit, got {len(issued)}"
        assert len(closed) == 1, f"expected 1 'already finished' submit, got {len(closed)}"
    finally:
        # ── cleanup (best-effort) ───────────────────────────────────────
        async with pg_sessionmaker() as s:
            # Break the attempt→certificate FK before deleting either side.
            await s.execute(
                ExamAttempt.__table__.update()
                .where(ExamAttempt.id == attempt_id)
                .values(certificate_id=None)
            )
            await s.execute(
                delete(Certificate).where(Certificate.exam_attempt_id == attempt_id)
            )
            await s.execute(delete(ExamAttempt).where(ExamAttempt.id == attempt_id))
            await s.execute(delete(User).where(User.id == user_id))
            await s.commit()
