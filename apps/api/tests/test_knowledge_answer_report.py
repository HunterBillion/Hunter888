"""PR-6 tests: user-filed reports about AI quiz verdicts (Variant B).

Covers:
  1. POST /knowledge/answers/{id}/report — happy path, idempotent on
     repeat for same (answer, reporter), 403 for non-owner, 404 for
     missing answer.
  2. GET /admin/knowledge/queue — filter source=user_report returns
     reports with surrounding context; source=ttl excludes them; default
     source=all returns merged list.
  3. POST /admin/knowledge/reports/{id}/resolve — accept/reject
     transitions, 409 on double-resolve.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest


@pytest.fixture
async def authed_client_factory(client, db_session, user_factory):
    """Build (client, user) pair with role override."""
    from app.core.deps import get_current_user, require_role
    from app.main import app
    from app.models.user import User, UserRole

    created: list[User] = []

    async def _make(role: str = "manager"):
        u = User(**user_factory(email=f"{role}-{uuid.uuid4().hex[:6]}@trainer.local"))
        u.role = UserRole(role) if hasattr(UserRole, role) else UserRole.manager
        if role == "admin":
            u.role = UserRole.admin
        elif role == "rop":
            u.role = UserRole.rop
        db_session.add(u)
        await db_session.commit()
        created.append(u)

        async def _override():
            return u
        app.dependency_overrides[get_current_user] = _override

        # require_role uses get_current_user under the hood — same override fits.
        # For role-gated endpoints, also override require_role factory result.
        return u

    csrf = "test-csrf-token"
    client.headers.update({
        "Authorization": "Bearer test",
        "X-CSRF-Token": csrf,
    })
    client.cookies.set("csrf_token", csrf)
    yield _make
    app.dependency_overrides.pop(get_current_user, None)


# ── helpers ─────────────────────────────────────────────────────────────

async def _seed_session_with_answer(db, user_id, *, explanation: str = "AI says X"):
    from app.models.knowledge import (
        KnowledgeAnswer,
        KnowledgeQuizSession,
        QuizMode,
        QuizSessionStatus,
    )

    s = KnowledgeQuizSession(
        user_id=user_id,
        mode=QuizMode.free_dialog,
        category="eligibility",
        difficulty=5,
        max_players=1,
        total_questions=10,
        status=QuizSessionStatus.completed,
    )
    db.add(s)
    await db.flush()

    a = KnowledgeAnswer(
        session_id=s.id,
        user_id=user_id,
        question_number=1,
        question_text="Когда возможна реализация имущества?",
        question_category="property",
        user_answer="Я думаю что после введения процедуры",
        is_correct=True,
        explanation=explanation,
        rag_chunks_used=[str(uuid.uuid4()), str(uuid.uuid4())],
    )
    db.add(a)
    await db.commit()
    return s, a


# ── 1. POST /knowledge/answers/{id}/report ──────────────────────────────


@pytest.mark.asyncio
async def test_report_endpoint_happy_path(authed_client_factory, client, db_session):
    user = await authed_client_factory("manager")
    _, ans = await _seed_session_with_answer(db_session, user.id)

    resp = await client.post(
        f"/api/knowledge/answers/{ans.id}/report",
        json={"reason": "Это не закон, а мнение AI."},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["answer_id"] == str(ans.id)
    assert body["reporter_id"] == str(user.id)
    assert body["status"] == "open"
    assert body["reason"] == "Это не закон, а мнение AI."
    assert isinstance(body["linked_chunk_ids"], list)
    assert len(body["linked_chunk_ids"]) == 2


@pytest.mark.asyncio
async def test_report_endpoint_is_idempotent(authed_client_factory, client, db_session):
    user = await authed_client_factory("manager")
    _, ans = await _seed_session_with_answer(db_session, user.id)

    r1 = await client.post(
        f"/api/knowledge/answers/{ans.id}/report",
        json={"reason": "first reason"},
    )
    r2 = await client.post(
        f"/api/knowledge/answers/{ans.id}/report",
        json={"reason": "second reason — should be ignored"},
    )
    assert r1.status_code == r2.status_code == 201
    # Same id, original reason preserved.
    assert r1.json()["id"] == r2.json()["id"]
    assert r2.json()["reason"] == "first reason"


@pytest.mark.asyncio
async def test_report_endpoint_404_for_missing_answer(authed_client_factory, client):
    await authed_client_factory("manager")
    resp = await client.post(
        f"/api/knowledge/answers/{uuid.uuid4()}/report",
        json={"reason": "missing"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_report_endpoint_403_for_other_user_answer(
    authed_client_factory, client, db_session, user_factory,
):
    from app.models.user import User

    other = User(**user_factory(email="owner@trainer.local"))
    db_session.add(other)
    await db_session.commit()
    _, ans = await _seed_session_with_answer(db_session, other.id)

    # Different user makes the call.
    await authed_client_factory("manager")  # default "me"
    resp = await client.post(
        f"/api/knowledge/answers/{ans.id}/report",
        json={"reason": "не моё, но пожалуюсь"},
    )
    assert resp.status_code == 403


# ── 2. GET /admin/knowledge/queue ───────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_queue_user_report_filter_returns_reports(
    authed_client_factory, client, db_session,
):
    # Seed: regular user files a report
    me = await authed_client_factory("manager")
    _, ans = await _seed_session_with_answer(db_session, me.id, explanation="AI text body")
    r = await client.post(
        f"/api/knowledge/answers/{ans.id}/report",
        json={"reason": "Не та статья закона"},
    )
    assert r.status_code == 201

    # Switch identity to admin and query the queue
    await authed_client_factory("admin")
    resp = await client.get("/api/admin/knowledge/queue?source=user_report")
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) >= 1
    item = next(i for i in items if i["report_id"] == r.json()["id"])
    assert item["source_kind"] == "user_report"
    assert item["report_reason"] == "Не та статья закона"
    assert item["answer_id"] == str(ans.id)
    assert item["answer_explanation"] == "AI text body"


@pytest.mark.asyncio
async def test_admin_queue_ttl_filter_excludes_user_reports(
    authed_client_factory, client, db_session,
):
    me = await authed_client_factory("manager")
    _, ans = await _seed_session_with_answer(db_session, me.id)
    await client.post(
        f"/api/knowledge/answers/{ans.id}/report",
        json={"reason": "X"},
    )

    await authed_client_factory("admin")
    # `source=ttl` mocks empty review queue path (no real chunks expired)
    with patch("app.services.knowledge_review_policy.list_review_queue", return_value=[]):
        resp = await client.get("/api/admin/knowledge/queue?source=ttl")
    assert resp.status_code == 200
    items = resp.json()
    assert all(it["source_kind"] != "user_report" for it in items)


# ── 3. POST /admin/knowledge/reports/{id}/resolve ───────────────────────


@pytest.mark.asyncio
async def test_resolve_report_accepted(
    authed_client_factory, client, db_session,
):
    me = await authed_client_factory("manager")
    _, ans = await _seed_session_with_answer(db_session, me.id)
    r = await client.post(
        f"/api/knowledge/answers/{ans.id}/report",
        json={"reason": "wrong law"},
    )
    rid = r.json()["id"]

    admin = await authed_client_factory("admin")
    resp = await client.post(
        f"/api/admin/knowledge/reports/{rid}/resolve",
        json={"decision": "accepted", "note": "agreed, chunk needs update"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "accepted"
    assert body["reviewed_by"] == str(admin.id)
    # And a second resolve must 409
    resp2 = await client.post(
        f"/api/admin/knowledge/reports/{rid}/resolve",
        json={"decision": "rejected"},
    )
    assert resp2.status_code == 409
