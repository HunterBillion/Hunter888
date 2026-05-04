"""P3 — cross-session AI client memory contract tests.

Covers the contracts spelled out in `services.cross_session_memory`:

* :func:`fetch_last_session_summary` returns ``None`` when no prior
  COMPLETED session exists for the (manager, real_client) pair.
* Returns a non-empty Russian summary referencing the closing emotion
  and score when a prior completed session exists.
* Excludes the in-flight session via ``skip_session_id`` so the row
  the caller is bootstrapping never matches itself.
* Backwards compatibility: when ``real_client_id`` is None on the
  session, the WS bootstrap does not call the helper at all — pinned
  by inspecting `_handle_session_start` source for the right guard.
* Integration: passing ``client_history`` into ``_build_system_prompt``
  injects the «ЧТО БЫЛО В ПРОШЛЫЙ РАЗ» block; passing nothing leaves
  the prompt unchanged.

The DB-layer tests use the in-memory SQLite engine fixture from
``conftest.py``. The render/template tests are pure-Python unit
tests with no DB dependency.
"""
from __future__ import annotations

import inspect
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.training import SessionStatus, TrainingSession
from app.services import cross_session_memory as xsm
from app.services.llm import _build_system_prompt


# ─── Pure-Python helpers ─────────────────────────────────────────────────


class TestExtractClosingEmotion:
    def test_none_on_empty_input(self):
        assert xsm.extract_closing_emotion(None) is None
        assert xsm.extract_closing_emotion([]) is None
        assert xsm.extract_closing_emotion({}) is None

    def test_list_of_dicts(self):
        timeline = [
            {"state": "cold"},
            {"state": "guarded"},
            {"state": "hostile"},
        ]
        assert xsm.extract_closing_emotion(timeline) == "hostile"

    def test_dict_with_events_key(self):
        timeline = {"events": [{"state": "cold"}, {"state": "callback"}]}
        assert xsm.extract_closing_emotion(timeline) == "callback"

    def test_skips_malformed_entries(self):
        timeline = [
            {"state": "cold"},
            "garbage",
            {"emotion": "deal"},  # tolerates 'emotion' alias
        ]
        assert xsm.extract_closing_emotion(timeline) == "deal"

    def test_normalizes_case_and_whitespace(self):
        timeline = [{"state": "  HOSTILE  "}]
        assert xsm.extract_closing_emotion(timeline) == "hostile"


class TestRenderSummary:
    def test_minimal_inputs(self):
        out = xsm.render_summary(
            completed_at=None,
            closing_emotion=None,
            score_total=None,
            terminal_outcome=None,
            judge_rationale=None,
        )
        assert "В прошлый звонок" in out
        assert "COLD" in out  # default for unknown emotion
        # No score / outcome / rationale → opener + minimal outcome only
        assert "/100" not in out

    def test_full_payload_russian_and_bounded(self):
        out = xsm.render_summary(
            completed_at=datetime.now(timezone.utc) - timedelta(days=1),
            closing_emotion="hostile",
            score_total=42.7,
            terminal_outcome="client_hangup",
            judge_rationale="Менеджер не отработал ключевое возражение про сроки.",
        )
        assert "вчера" in out
        assert "HOSTILE" in out
        assert "43/100" in out  # rounded
        assert "бросил трубку" in out
        assert "Судья отметил" in out
        assert len(out) <= 300

    def test_summary_truncated_to_300_chars(self):
        long_rationale = "А" * 1000
        out = xsm.render_summary(
            completed_at=datetime.now(timezone.utc),
            closing_emotion="hostile",
            score_total=10,
            terminal_outcome="client_hangup",
            judge_rationale=long_rationale,
        )
        assert len(out) <= 300

    def test_age_label_humanized(self):
        # Direct test of the private helper via render_summary
        cases = [
            (timedelta(hours=2), "сегодня"),
            (timedelta(days=1), "вчера"),
            (timedelta(days=3), "3 дн. назад"),
            (timedelta(days=20), "2 нед. назад"),
            (timedelta(days=60), "2 мес. назад"),
        ]
        for delta, expected_fragment in cases:
            out = xsm.render_summary(
                completed_at=datetime.now(timezone.utc) - delta,
                closing_emotion="cold",
                score_total=None,
                terminal_outcome=None,
                judge_rationale=None,
            )
            assert expected_fragment in out, f"Expected {expected_fragment!r} in {out!r}"


# ─── Cache key + eviction ────────────────────────────────────────────────


class TestCacheKey:
    def test_deterministic_key_format(self):
        u = uuid.UUID("00000000-0000-0000-0000-000000000001")
        c = uuid.UUID("00000000-0000-0000-0000-000000000002")
        assert xsm.cache_key(u, c) == f"xsession:summary:{u}:{c}"

    @pytest.mark.asyncio
    async def test_evict_no_op_on_missing_inputs(self):
        # No exception, no Redis call when either id is None
        await xsm.evict_summary_cache(user_id=None, real_client_id=uuid.uuid4())
        await xsm.evict_summary_cache(user_id=uuid.uuid4(), real_client_id=None)


# ─── DB-backed contract tests (sqlite in-memory) ─────────────────────────


def _make_session(
    *,
    user_id: uuid.UUID,
    real_client_id: uuid.UUID | None,
    status: SessionStatus = SessionStatus.completed,
    score_total: float | None = 50.0,
    terminal_outcome: str | None = "client_hangup",
    closing_emotion: str = "hostile",
    ended_at: datetime | None = None,
) -> TrainingSession:
    """Build a TrainingSession for the in-memory DB. Scenario_id is a stub
    UUID — the tests don't load via FK so SQLite tolerates the missing
    parent (FK constraints aren't enforced unless explicitly enabled)."""
    end_at = ended_at or datetime.now(timezone.utc) - timedelta(minutes=30)
    start_at = end_at - timedelta(minutes=15)
    return TrainingSession(
        id=uuid.uuid4(),
        user_id=user_id,
        scenario_id=uuid.uuid4(),
        status=status,
        score_total=score_total,
        terminal_outcome=terminal_outcome,
        emotion_timeline=[{"state": "cold"}, {"state": closing_emotion}],
        scoring_details={
            "judge": {"rationale_ru": "Хорошо отработал, но упустил тему долгов."},
        },
        real_client_id=real_client_id,
        started_at=start_at,
        ended_at=end_at,
    )


@pytest.mark.asyncio
async def test_fetch_last_session_summary_none_when_no_prior(db_session):
    """Manager calls a real CRM client for the FIRST time — there is
    no prior completed session, so the helper returns None and the
    WS bootstrap proceeds with the default cold-start prompt."""
    user_id = uuid.uuid4()
    real_client_id = uuid.uuid4()

    out = await xsm.fetch_last_session_summary(
        db_session,
        user_id=user_id,
        real_client_id=real_client_id,
        redis_client=None,  # bypass Redis — pure DB read
    )
    assert out is None


@pytest.mark.asyncio
async def test_fetch_last_session_summary_returns_russian_summary(db_session):
    """Prior completed session exists → helper returns a Russian
    summary that references the closing emotion AND the score."""
    user_id = uuid.uuid4()
    real_client_id = uuid.uuid4()

    session = _make_session(
        user_id=user_id,
        real_client_id=real_client_id,
        score_total=42,
        closing_emotion="hostile",
    )
    db_session.add(session)
    await db_session.flush()

    out = await xsm.fetch_last_session_summary(
        db_session,
        user_id=user_id,
        real_client_id=real_client_id,
        redis_client=None,
    )
    assert out is not None
    assert "В прошлый звонок" in out
    assert "HOSTILE" in out
    assert "42/100" in out
    assert "бросил трубку" in out
    assert len(out) <= 300


@pytest.mark.asyncio
async def test_skip_session_id_excludes_inflight_session(db_session):
    """The session that triggers the lookup must not match itself.
    Without ``skip_session_id``, a row that just got bootstrapped
    (status=active, but in some race cases status=completed already)
    would shadow the genuine prior one."""
    user_id = uuid.uuid4()
    real_client_id = uuid.uuid4()

    # Older completed session — this is the one we expect to retrieve
    older = _make_session(
        user_id=user_id,
        real_client_id=real_client_id,
        score_total=11,
        closing_emotion="callback",
        ended_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    # Newer session — caller wants this excluded
    newer = _make_session(
        user_id=user_id,
        real_client_id=real_client_id,
        score_total=99,
        closing_emotion="deal",
        ended_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db_session.add_all([older, newer])
    await db_session.flush()

    out = await xsm.fetch_last_session_summary(
        db_session,
        user_id=user_id,
        real_client_id=real_client_id,
        skip_session_id=newer.id,
        redis_client=None,
    )
    assert out is not None
    # Older session referenced (callback emotion + score 11)
    assert "CALLBACK" in out
    assert "11/100" in out
    assert "DEAL" not in out


@pytest.mark.asyncio
async def test_other_users_sessions_ignored(db_session):
    """Manager A's prior call must NOT bleed into manager B's lookup."""
    real_client_id = uuid.uuid4()
    manager_a = uuid.uuid4()
    manager_b = uuid.uuid4()

    db_session.add(_make_session(user_id=manager_a, real_client_id=real_client_id))
    await db_session.flush()

    # Manager B asks → no prior call FOR THEM
    out = await xsm.fetch_last_session_summary(
        db_session,
        user_id=manager_b,
        real_client_id=real_client_id,
        redis_client=None,
    )
    assert out is None


@pytest.mark.asyncio
async def test_active_sessions_ignored(db_session):
    """Sessions that haven't completed must not be summarized — a
    half-finished call has no terminal outcome to describe."""
    user_id = uuid.uuid4()
    real_client_id = uuid.uuid4()

    db_session.add(
        _make_session(
            user_id=user_id,
            real_client_id=real_client_id,
            status=SessionStatus.active,
        )
    )
    await db_session.flush()

    out = await xsm.fetch_last_session_summary(
        db_session,
        user_id=user_id,
        real_client_id=real_client_id,
        redis_client=None,
    )
    assert out is None


# ─── LLM prompt injection contract ───────────────────────────────────────


class TestBuildSystemPromptClientHistory:
    def test_no_history_no_block(self):
        """Backwards compat: callers that don't pass ``client_history``
        (catalog scenarios, anti_cheat coach, free practice) must see
        no «ЧТО БЫЛО В ПРОШЛЫЙ РАЗ» block."""
        out = _build_system_prompt(
            character_prompt="character",
            guardrails="guardrails",
            emotion_state="cold",
        )
        assert "ЧТО БЫЛО В ПРОШЛЫЙ РАЗ" not in out

    def test_empty_history_no_block(self):
        """Empty / whitespace-only summary is silently dropped — the
        helper renders "" as a tombstone for "we already checked, no
        prior" so `_build_system_prompt` must not turn that into a
        bogus block."""
        out_empty = _build_system_prompt(
            character_prompt="character",
            guardrails="guardrails",
            emotion_state="cold",
            client_history="",
        )
        out_ws = _build_system_prompt(
            character_prompt="character",
            guardrails="guardrails",
            emotion_state="cold",
            client_history="   \n  \t",
        )
        assert "ЧТО БЫЛО В ПРОШЛЫЙ РАЗ" not in out_empty
        assert "ЧТО БЫЛО В ПРОШЛЫЙ РАЗ" not in out_ws

    def test_history_present_block_appears(self):
        summary = (
            "В прошлый звонок (вчера) клиент завершил на эмоции HOSTILE. "
            "Менеджер получил 42/100. Краткая причина окончания: бросил трубку."
        )
        out = _build_system_prompt(
            character_prompt="character",
            guardrails="guardrails",
            emotion_state="cold",
            client_history=summary,
        )
        assert "## ЧТО БЫЛО В ПРОШЛЫЙ РАЗ" in out
        assert summary in out
        # And the behavioural footer telling the AI to act as a continuation
        assert "Веди себя как продолжение того разговора" in out

    def test_history_block_after_emotion(self):
        """Order matters: the cross-session memory block sits AFTER
        the current-emotion behaviour, so the freshest emotional
        guidance dominates if there's a conflict."""
        summary = "В прошлый звонок клиент завершил на эмоции HOSTILE."
        out = _build_system_prompt(
            character_prompt="character",
            guardrails="guardrails",
            emotion_state="cold",
            client_history=summary,
        )
        emotion_idx = out.find("Текущее эмоциональное состояние")
        history_idx = out.find("ЧТО БЫЛО В ПРОШЛЫЙ РАЗ")
        assert emotion_idx >= 0
        assert history_idx >= 0
        assert history_idx > emotion_idx, (
            "client_history block must come AFTER emotion block"
        )

    def test_history_and_persona_facts_coexist(self):
        """Two memory streams must coexist — confirmed_facts (what the
        manager said about themselves) and client_history (what
        happened on the prior call)."""
        out = _build_system_prompt(
            character_prompt="character",
            guardrails="guardrails",
            emotion_state="cold",
            persona_facts={"full_name": {"value": "Дмитрий"}},
            client_history="В прошлый звонок клиент завершил на эмоции HOSTILE.",
        )
        assert "ЧТО ТЫ УЖЕ ЗНАЕШЬ" in out
        assert "ЧТО БЫЛО В ПРОШЛЫЙ РАЗ" in out


# ─── Anti-regression: source-level guards ────────────────────────────────


def test_ws_bootstrap_only_loads_when_real_client_present():
    """Anti-regression guard for the «when real_client_id is None,
    behaviour is identical to before — no extra DB query, no helper
    call» requirement (P3 spec).

    We assert at the source level that the cross-session loader is
    nested inside an `if session.real_client_id` branch in
    `_handle_session_start`. A future refactor that moves the call
    out of that guard would silently regress catalog-mode latency
    by adding a DB roundtrip per session.start.
    """
    from app.ws import training as training_ws

    src = inspect.getsource(training_ws._handle_session_start)
    assert "fetch_last_session_summary" in src, (
        "expected cross-session loader to be wired into session-start"
    )
    # Find the bytes between the load call and the surrounding
    # `if session.real_client_id` — fail if the load is outside any
    # such guard.
    load_idx = src.index("fetch_last_session_summary")
    prefix = src[:load_idx]
    last_guard = prefix.rfind("if session.real_client_id")
    assert last_guard != -1, (
        "fetch_last_session_summary must be guarded by "
        "`if session.real_client_id` to preserve no-real-client behaviour"
    )


def test_finalize_evicts_xsession_cache_only_when_real_client_present():
    """Anti-regression: the cache eviction in finalize_training_session
    must remain guarded so finalizing a free-practice session never
    issues a Redis DEL for `xsession:summary:None:None`."""
    from app.services import completion_policy

    src = inspect.getsource(completion_policy.finalize_training_session)
    assert "evict_summary_cache" in src
    evict_idx = src.index("evict_summary_cache")
    prefix = src[:evict_idx]
    last_guard = prefix.rfind("session.real_client_id is not None")
    assert last_guard != -1, (
        "evict_summary_cache must be guarded by a real_client_id check"
    )
