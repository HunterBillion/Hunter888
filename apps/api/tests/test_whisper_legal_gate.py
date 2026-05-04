"""Regression tests for the question-gate added to whisper_engine._check_legal.

Production session 2026-05-04 example 1 fired:
  «Алименты НЕ списываются при банкротстве»
…because the trainee mentioned «дет» in passing (matched the
``r"дет"`` keyword in the alimony trigger). The new gate requires the
client message to actually be ASKING something, with two exceptions:
manager-claim patterns ("100% списание", "бесплатно") still always fire
because those are misleading statements the coach must counter.
"""
from __future__ import annotations

import pytest

from app.services.whisper_engine import WhisperEngine


@pytest.fixture
def engine() -> WhisperEngine:
    return WhisperEngine(redis_client=None)


# ── MUST FIRE ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "client_message, must_contain",
    [
        # Real legal questions — all should fire.
        ("Что будет с квартирой при банкротстве?", "жильё"),
        ("Заберут ли мою машину?", "Автомобиль"),
        ("А алименты на ребёнка тоже спишут?", "Алименты"),
        ("Сколько длится процедура?", "6 месяцев"),
        ("Как банкротство повлияет на кредитную историю?", "кредитной истории"),
        ("Можно ли мне выехать за границу?", "выезд"),
        # Manager-claim patterns (always fire, no question gate).
        ("я гарантирую списание 100%", "100% списание"),
        ("это абсолютно бесплатно", "НЕ бесплатно"),
    ],
)
def test_must_fire(engine: WhisperEngine, client_message: str, must_contain: str) -> None:
    w = engine._check_legal(client_message, "qualification")
    assert w is not None, f"expected whisper for: {client_message!r}"
    assert must_contain.lower() in w.message.lower(), (
        f"whisper for {client_message!r} should mention {must_contain!r}, "
        f"got: {w.message!r}"
    )


# ── MUST NOT FIRE ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "client_message",
    [
        # The actual prod regression — 'дет' word in passing.
        "Привычка. Ничего такого.",  # no keyword at all
        "Не хочу сейчас в личное сильно уходить.",  # no keyword
        "Это все из-за блокировок инета у нас",  # no keyword
        # Keyword present but no question context — must NOT fire.
        "У меня есть дети, но это не важно.",
        "Машина у меня есть, и квартира есть, но об этом не сейчас.",
        "Зарплата у меня средняя, ничего особенного.",
        "Дом я унаследовал от отца.",
    ],
)
def test_must_not_fire(engine: WhisperEngine, client_message: str) -> None:
    w = engine._check_legal(client_message, "qualification")
    assert w is None, (
        f"unexpected whisper for {client_message!r}: {w and w.message!r}"
    )
