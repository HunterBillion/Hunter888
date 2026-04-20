"""Presentation layer — wraps bare question text into personality-themed framing.

Two personalities per user request (2026-04-18):
  - professor ("Профессор Кодексов") — academic casus framing
  - detective ("Арбитражный Следопыт") — noir investigation framing

No third personality per user decision.

wrap_question() returns the FULL text shown to the user in the chat bubble.
The raw `question_text` from the quiz generator becomes the "payload"; the
presentation adds:
  - beat header (e.g. "ДЕНЬ 3: ПРОВЕРКА ДОКУМЕНТОВ")
  - case anchor (debtor name + one-line reminder)
  - personality-specific hook line

Intentionally avoids emojis per user feedback "эмодзи разные, много артефактов".
Uses minimal text-only accents: ▸ ▶ ● ─ │.
"""

from __future__ import annotations

from typing import Literal

from app.services.quiz_v2.beats import StoryBeat, beat_progress
from app.services.quiz_v2.cases import QuizCase
from app.services.quiz_v2.ramp import QuestionType

Personality = Literal["professor", "detective", "blitz"]


def _beat_header(beat: StoryBeat, position: int, beat_len: int) -> str:
    return f"{beat.ru_label.upper()}  {position}/{beat_len}"


def _case_anchor(case: QuizCase, personality: Personality) -> str:
    """One-line reminder of who the debtor is + key fact."""
    if personality == "detective":
        return (
            f"{case.debtor_name}, {case.debtor_age}. "
            f"Долг — {case.debt_amount_human()}. "
            f"Кредиторы: {case.creditors_summary()}."
        )
    # professor
    return (
        f"Должник: {case.debtor_name} ({case.debtor_age} лет). "
        f"Общая сумма требований — {case.debt_amount_human()}."
    )


def wrap_question(
    *,
    question_text: str,
    case: QuizCase | None,
    beat: StoryBeat | None,
    question_number: int,
    total_questions: int,
    personality: Personality,
    question_type: QuestionType | None = None,
) -> str:
    """Turn a bare question into personality-framed chat text.

    If case is None (e.g. blitz mode) returns the question as-is with a
    minimal header. Otherwise builds a 2-3 block narrative frame.
    """
    # Blitz / no-case path — keep it tight
    if case is None or personality == "blitz":
        return f"[{question_number}/{total_questions}]  {question_text}"

    # Beat info
    if beat is None:
        beat_line = ""
    else:
        _beat, pos, length = beat_progress(question_number, total_questions)
        beat_line = _beat_header(_beat, pos, length)

    anchor = _case_anchor(case, personality)

    if personality == "detective":
        # Noir framing
        hook = _detective_hook(case, beat, question_number)
        blocks = [
            f"▶ ДЕЛО-{case.case_id}  │  {beat_line}" if beat_line else f"▶ ДЕЛО-{case.case_id}",
            hook,
            anchor,
            f"─────",
            question_text,
            f"─────",
            "▸ Что у нас по этому пункту?",
        ]
        return "\n".join(b for b in blocks if b)

    # Professor — academic
    hook = _professor_hook(case, beat, question_type)
    blocks = [
        f"КАЗУС №{case.case_id}  │  {beat_line}" if beat_line else f"КАЗУС №{case.case_id}",
        hook,
        anchor,
        f"─────",
        f"Вопрос: {question_text}",
    ]
    return "\n".join(b for b in blocks if b)


def _detective_hook(case: QuizCase, beat: StoryBeat | None, question_number: int) -> str:
    """One-line mood-setter for the detective personality."""
    if question_number == 1:
        return f"В кабинете сумрачно. {case.debtor_name} сидит напротив. На столе — {case.trigger_event}."
    if beat == StoryBeat.intake:
        return "Папка дела раскрыта. Первые заявления."
    if beat == StoryBeat.documents:
        return "Разбираем бумаги. Что-то не сходится."
    if beat == StoryBeat.obstacles:
        if case.complicating_factors:
            return f"Осложнение: {case.complicating_factors[0]}."
        return "Кредиторы готовят возражения."
    if beat == StoryBeat.property_fate:
        return "Переходим к судьбе имущества."
    if beat == StoryBeat.outcome:
        return "Дело идёт к финалу. Последние ходы."
    return "Следующий штрих в картине."


def _professor_hook(case: QuizCase, beat: StoryBeat | None, question_type: QuestionType | None) -> str:
    """Academic intro for the professor personality."""
    if beat == StoryBeat.intake:
        return "Рассмотрим условия возбуждения производства."
    if beat == StoryBeat.documents:
        return "Разберём документальное сопровождение."
    if beat == StoryBeat.obstacles:
        return "Обратимся к процедурным осложнениям."
    if beat == StoryBeat.property_fate:
        return "Теперь — к режиму имущества должника."
    if beat == StoryBeat.outcome:
        return "Анализируем возможный исход."
    if question_type == QuestionType.strategic:
        return "Стратегический выбор в этой ситуации."
    return "Продолжим разбор казуса."


def build_case_intro(case: QuizCase, personality: Personality) -> str:
    """Full-screen intro card text shown BEFORE question #1.

    Used by WS handler to emit case.intro event. Paired with TTS audio
    on the frontend so user sees + hears the case before they start.
    """
    if personality == "detective":
        return (
            f"▶ НОВОЕ ДЕЛО — {case.case_id}\n\n"
            f"{case.debtor_name}. {case.debtor_age} лет. {case.debtor_occupation}.\n"
            f"Долг: {case.debt_amount_human()}. Кредиторы: {', '.join(case.creditors)}.\n"
            f"Триггер: {case.trigger_event}.\n\n"
            f"{case.narrative_hook}\n\n"
            f"Берёшь дело?"
        )
    # professor
    factors = ""
    if case.complicating_factors:
        factors = "\nОсложняющие обстоятельства:\n" + "\n".join(
            f"  • {f}" for f in case.complicating_factors
        )
    return (
        f"КАЗУС №{case.case_id}\n\n"
        f"Фигурант: {case.debtor_name}, {case.debtor_age} лет, {case.debtor_occupation}.\n"
        f"Совокупный долг: {case.debt_amount_human()}.\n"
        f"Кредиторы: {', '.join(case.creditors)}.\n"
        f"Повод: {case.trigger_event}.{factors}\n\n"
        f"Задача: {case.narrative_hook}"
    )
