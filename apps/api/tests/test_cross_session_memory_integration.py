"""PR-A integration tests: cross-session memory wired into the prompt.

These complement the existing ``test_cross_session_memory.py`` which
covers ``fetch_last_session_summary`` in isolation. The wiring layer
(``_build_system_prompt`` accepting ``client_history``) was the actual
breakage in production — the helper had been deployed for weeks but
its output was never reaching the LLM. These tests fail on the pre-fix
code (no ``client_history`` parameter / no injection block) and pass
after PR-A.

§4.1 CLAUDE.md compliance: the concurrent-fetch test below uses
``asyncio.gather`` rather than sequential awaits so a future regression
where Redis cache writes race with reads (e.g. someone "optimizes"
away the negative-cache tombstone) actually fails the test.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest

from app.services.llm import _build_system_prompt


def test_client_history_injected_into_system_prompt():
    """Summary string from cross_session_memory must reach the LLM
    verbatim under the «Прошлая встреча» header. Without this block
    the AI client cold-starts every session even when the manager is
    on the third call to the same CRM lead."""
    summary = "В прошлый звонок 2 дня назад менеджер ушёл с эмоцией HOSTILE, балл 42/100. Клиент бросил трубку."
    out = _build_system_prompt(
        character_prompt="Ты Сергей, директор.",
        guardrails="",
        emotion_state="cold",
        client_history=summary,
    )
    assert "## Прошлая встреча с этим менеджером" in out
    assert summary in out
    # Behavioural anchor — the section MUST tell the AI it remembers,
    # otherwise the LLM treats the summary as trivia and ignores it.
    assert "ты ПОМНИШЬ этот разговор" in out


def test_client_history_absent_when_none():
    """First contact (no prior session) must not leak the section
    header into the prompt — that header is the LLM's signal that
    history exists, and a stray header without content makes the AI
    invent fake recollections."""
    out = _build_system_prompt(
        character_prompt="Ты Сергей.",
        guardrails="",
        emotion_state="cold",
        client_history=None,
    )
    assert "## Прошлая встреча" not in out


def test_client_history_coexists_with_persona_facts():
    """Persona facts (TZ-4.5 PR 4) and client_history (PR-A) live in
    adjacent sections. Both must render when both are provided —
    they answer different questions ("что я знаю о менеджере" vs
    "что было в прошлый звонок") and the LLM uses them together."""
    facts = {"role_title": {"value": "директор по продажам", "source": "extractor"}}
    summary = "Прошлый раз 5 дней назад: ушёл хорошо, балл 78/100."
    out = _build_system_prompt(
        character_prompt="Ты Сергей.",
        guardrails="",
        emotion_state="cold",
        persona_facts=facts,
        client_history=summary,
    )
    # Persona facts section header (rendered by persona_slots)
    assert "ЧТО ТЫ УЖЕ ЗНАЕШЬ О СОБЕСЕДНИКЕ" in out
    # Cross-session memory section
    assert "## Прошлая встреча" in out
    assert summary in out
    # Order matters: facts come before history (facts shape identity,
    # history shapes greeting tone — identity should stabilize first).
    assert out.index("ЧТО ТЫ УЖЕ ЗНАЕШЬ") < out.index("Прошлая встреча")


def test_client_history_strips_surrounding_whitespace():
    """Cache may return summaries with trailing newlines from the
    renderer. Defensive strip keeps section formatting tight."""
    out = _build_system_prompt(
        character_prompt="x",
        guardrails="",
        emotion_state="cold",
        client_history="   \n\n  тест   \n",
    )
    assert "тест" in out
    # No double-blank between the header and the body.
    assert "## Прошлая встреча с этим менеджером\nтест" in out


@pytest.mark.asyncio
async def test_fetch_summary_no_race_under_parallel_load():
    """§4.1 CLAUDE.md regression fence — five parallel fetches of the
    SAME (user, real_client) pair must all return the same summary,
    not a mix of cache-hit and cache-miss results.

    Without the negative-cache tombstone, a fresh CRM client opened in
    five tabs simultaneously would hit the DB five times and a
    misordered Redis SET could leave one task seeing an empty cache
    value while the others see the real summary. Pre-emptive coverage
    so a future "skip the empty-string tombstone" optimization fails
    here loudly instead of silently degrading the feature.
    """
    from unittest.mock import AsyncMock, MagicMock

    from app.services import cross_session_memory as xsm

    # In-memory Redis stub so we can observe the real read/write order.
    storage: dict[str, str] = {}
    redis_stub = MagicMock()
    redis_stub.get = AsyncMock(side_effect=lambda k: storage.get(k))

    async def _set(k: str, v: str, ex: int | None = None) -> None:
        storage[k] = v

    redis_stub.set = AsyncMock(side_effect=_set)

    # Patch the DB read so all parallel branches converge on the same
    # synthetic prior session — the test's job is to verify cache
    # arbitration, not DB lookup correctness (covered elsewhere).
    user_id = uuid.uuid4()
    real_client_id = uuid.uuid4()

    fake_session = MagicMock()
    fake_session.ended_at = None
    fake_session.created_at = None
    fake_session.emotion_timeline = [{"state": "hostile"}]
    fake_session.scoring_details = {"judge": {"rationale_ru": "OK"}}
    fake_session.score_total = 50
    fake_session.terminal_outcome = "hangup"

    async def _fake_load(*args, **kwargs):
        await asyncio.sleep(0.01)  # simulate DB latency
        return fake_session

    db_stub = MagicMock()  # never touched once we patch _load_prior_session

    # Monkey-patch the loader so the test is hermetic.
    original_loader = xsm._load_prior_session
    xsm._load_prior_session = _fake_load
    try:
        results = await asyncio.gather(*[
            xsm.fetch_last_session_summary(
                db_stub,
                user_id=user_id,
                real_client_id=real_client_id,
                redis_client=redis_stub,
            )
            for _ in range(5)
        ])
    finally:
        xsm._load_prior_session = original_loader

    # All five calls must agree on the same non-empty summary. A race
    # would manifest as one of the results being None (saw an empty
    # tombstone written by a sibling) while the others see real text.
    assert all(r == results[0] for r in results), (
        f"race detected: {set(results)}"
    )
    assert results[0] is not None
    assert "HOSTILE" in results[0]


# ── PR-A.1 audit-fix tests (substance in summary) ───────────────────────


def test_render_summary_with_call_index_shows_leading_chip():
    """Lead-in must surface the call counter so the AI sees 'returning
    relationship' BEFORE the outcome line. Pre-fix summaries had no
    relationship signal — every contact looked first-ever."""
    from app.services.cross_session_memory import render_summary

    out = render_summary(
        completed_at=None,
        closing_emotion="cold",
        score_total=0,
        terminal_outcome="rejected",
        judge_rationale=None,
        call_index=4,
        total_completed=3,
    )
    assert "Это уже 4-й звонок" in out
    assert "всего завершённых: 3" in out


def test_render_summary_extracts_objections_from_messages():
    """Pre-fix the AI saw 'manager scored 0/100' but not WHY. Now the
    actual category of objection is surfaced so the next call's persona
    reacts contextually."""
    from app.services.cross_session_memory import render_summary

    msgs = [
        {"role": "user", "content": "Дорого. Где такие деньги взять?"},
        {"role": "assistant", "content": "У нас есть рассрочка"},
        {"role": "user", "content": "Мне нужно посоветоваться с мужем"},
    ]
    out = render_summary(
        completed_at=None,
        closing_emotion="cold",
        score_total=20,
        terminal_outcome="callback_scheduled",
        judge_rationale=None,
        messages=msgs,
    )
    assert "Клиент возражал по:" in out
    assert "цена/деньги" in out
    assert "нужно посоветоваться" in out


def test_render_summary_extracts_manager_promises():
    """Без этого AI на следующем звонке не может сказать «вы обещали
    смету — где она?». Это и есть ключевой WOW-эффект."""
    from app.services.cross_session_memory import render_summary

    msgs = [
        {"role": "user", "content": "А что мне делать?"},
        {"role": "assistant", "content": "Я отправлю вам смету на почту до конца дня"},
        {"role": "user", "content": "Хорошо, спасибо"},
        {"role": "assistant", "content": "Перезвоню вам завтра после трёх"},
    ]
    out = render_summary(
        completed_at=None,
        closing_emotion="curious",
        score_total=55,
        terminal_outcome="callback_scheduled",
        judge_rationale=None,
        messages=msgs,
    )
    assert "Менеджер обещал:" in out
    assert "отправлю" in out.lower()


def test_render_summary_inlines_persona_highlights():
    """Persona facts have a dedicated block in the system prompt, but
    the summary should still reference the highest-value ones (debt,
    income) so the AI's opening line can use them naturally."""
    from app.services.cross_session_memory import render_summary

    facts = {
        "total_debt": {"value": "1.2 млн", "source": "extractor"},
        "income": {"value": "60к", "source": "extractor"},
        "phone": {"value": "+79991234567", "source": "user"},  # not surfaced
    }
    out = render_summary(
        completed_at=None,
        closing_emotion="cold",
        score_total=10,
        terminal_outcome="rejected",
        judge_rationale=None,
        persona_facts=facts,
    )
    assert "Известные факты:" in out
    assert "1.2 млн" in out
    assert "+79991234567" not in out


def test_render_summary_handles_empty_extractor_inputs_gracefully():
    """Defensive: empty messages/facts/call_index=1 must NOT emit empty
    section headers like 'Клиент возражал по: .' which read as bugs to
    the LLM and degrade the prompt."""
    from app.services.cross_session_memory import render_summary

    out = render_summary(
        completed_at=None,
        closing_emotion="cold",
        score_total=0,
        terminal_outcome="rejected",
        judge_rationale=None,
        messages=[],
        persona_facts={},
        call_index=1,
        total_completed=0,
    )
    assert "Это уже" not in out
    assert "Клиент возражал по:" not in out
    assert "Менеджер обещал:" not in out
    assert "Известные факты:" not in out
