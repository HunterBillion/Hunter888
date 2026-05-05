"""PR-D regression tests for bot memory + state-machine determinism.

Without these, the random()-replaced injection logic and the regex fact
extractors could silently drift back to the "robot keeps repeating" /
"bot жёсткими прыжками меняет роль" failure modes.
"""

from __future__ import annotations

from app.services.pvp_bot_engine import (
    BotEmotionState,
    _extract_facts,
    _extract_questions,
)


# ─── Fact extractor ──────────────────────────────────────────────────────


def test_extract_facts_picks_article_refs():
    text = "Согласно ст. 213.4 необходимо подать заявление в течение 90 дней."
    facts = _extract_facts(text)
    assert any("213.4" in f for f in facts)
    assert any("90" in f and "дн" in f.lower() for f in facts)


def test_extract_facts_picks_paragraph_refs():
    text = "Смотрим статья 213.11 п. 2 — там про реструктуризацию."
    facts = _extract_facts(text)
    assert any("213.11" in f for f in facts)


def test_extract_facts_picks_money_thresholds():
    text = "Минимальный долг — 500 000 руб для подачи заявления."
    facts = _extract_facts(text)
    assert any("500" in f and "руб" in f.lower() for f in facts)


def test_extract_facts_returns_unique():
    text = "Ст. 213.4. И ещё раз ст. 213.4. И снова ст 213.4."
    facts = _extract_facts(text)
    # Should dedup the same article reference even if cited 3 times.
    article_facts = [f for f in facts if "213.4" in f]
    assert len(article_facts) == 1


def test_extract_facts_caps_at_max_n():
    text = "ст. 1, ст. 2, ст. 3, ст. 4, ст. 5"
    facts = _extract_facts(text, max_n=2)
    assert len(facts) == 2


def test_extract_facts_empty_on_chitchat():
    text = "Привет! Ну ок, понятно. Думаю, надо подумать."
    assert _extract_facts(text) == []


# ─── Question extractor ──────────────────────────────────────────────────


def test_extract_questions_finds_real_question():
    text = "Понял. А что будет с квартирой при банкротстве?"
    questions = _extract_questions(text)
    assert questions
    assert "квартир" in questions[0].lower()


def test_extract_questions_skips_too_short():
    # "Что?" — 4 chars, below 12-char threshold — noise.
    text = "Что? Не понял о чём вы говорите."
    questions = _extract_questions(text)
    assert all(len(q) >= 12 for q in questions)


def test_extract_questions_caps_at_max_n():
    text = "Вопрос один со ст. 213.4? Вопрос два про сроки? Третий вопрос про порядок?"
    questions = _extract_questions(text, max_n=2)
    assert len(questions) == 2


# ─── BotEmotionState memory fields ───────────────────────────────────────


def test_emotion_state_default_memory_lists_are_empty():
    s = BotEmotionState()
    assert s.said_facts == []
    assert s.asked_questions == []
    assert s.objections_count == 0
    assert s.legal_traps_played == 0


def test_emotion_state_memory_lists_are_per_instance():
    """Critical: ``field(default_factory=list)`` must isolate state per
    instance — sharing would leak memory across duels and is a classic
    Python dataclass pitfall."""
    a = BotEmotionState()
    b = BotEmotionState()
    a.said_facts.append("ст. 213.4")
    b.asked_questions.append("Что будет с квартирой?")
    assert a.said_facts == ["ст. 213.4"]
    assert a.asked_questions == []
    assert b.said_facts == []
    assert b.asked_questions == ["Что будет с квартирой?"]
