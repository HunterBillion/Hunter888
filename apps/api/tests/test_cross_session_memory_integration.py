"""PR-A integration tests: cross-session memory wired into the prompt.

These complement the existing ``test_cross_session_memory.py`` which
covers ``fetch_last_session_summary`` in isolation. The wiring layer
(``_build_system_prompt`` accepting ``client_history``) was the actual
breakage in production — the helper had been deployed for weeks but
its output was never reaching the LLM. These tests fail on the pre-fix
code (no ``client_history`` parameter / no injection block) and pass
after PR-A.
"""
from __future__ import annotations

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
