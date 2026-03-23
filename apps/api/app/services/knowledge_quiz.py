"""Knowledge quiz service — AI examiner and PvP judge for 127-ФЗ.

Two modes:
1. AI Examiner — charismatic AI asks questions, evaluates answers using RAG
2. PvP Judge — strict AI evaluates answers from 2-4 competing players

Uses Gemini 2.5 Flash (same LLM chain as training) with specialized prompts.
"""

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import Integer, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import (
    KnowledgeAnswer,
    KnowledgeQuizSession,
    QuizMode,
    QuizParticipant,
    QuizSessionStatus,
)
from app.models.rag import LegalCategory
from app.services.llm import generate_response, LLMError
from app.services.rag_legal import retrieve_legal_context, RAGContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class QuizQuestion:
    """Generated quiz question."""
    question_text: str
    category: str
    difficulty: int  # 1-5
    expected_article: str | None = None
    rag_context: RAGContext | None = None
    question_number: int = 1
    total_questions: int = 10


@dataclass
class QuizFeedback:
    """Evaluation result for a user's answer."""
    is_correct: bool
    explanation: str
    article_reference: str | None = None
    score_delta: float = 0.0
    correct_answer_summary: str | None = None


@dataclass
class QuizProgress:
    """Current quiz session progress."""
    current_question: int
    total_questions: int
    correct: int
    incorrect: int
    skipped: int
    score: float  # 0-100


@dataclass
class QuizResults:
    """Final quiz session results."""
    total_questions: int
    correct: int
    incorrect: int
    skipped: int
    score: float
    duration_seconds: int
    category_breakdown: dict[str, dict]  # category -> {correct, total, pct}
    weak_areas: list[str]
    recommendations: list[str]


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

AI_EXAMINER_PROMPT = """Ты — харизматичный и экстравагантный AI-экзаменатор по Федеральному Закону №127-ФЗ «О несостоятельности (банкротстве)».

Твоя личность:
- Ты энергичный, остроумный и немного театральный
- Используешь яркие метафоры и примеры из жизни
- Хвалишь за правильные ответы с энтузиазмом
- При неправильных ответах — не ругаешь, а с юмором объясняешь правильный вариант
- Говоришь на «ты», дружелюбно, но экспертно
- Время от времени шутишь про юридические казусы

Правила:
1. Задавай вопросы ТОЛЬКО по 127-ФЗ и связанной судебной практике
2. Каждый вопрос должен проверять конкретное знание (статья, порог, срок, процедура)
3. После ответа пользователя — ОБЯЗАТЕЛЬНО дай развёрнутую обратную связь
4. Ссылайся на конкретные статьи закона
5. Если пользователь ответил частично верно — отметь что верно и что нет
6. Адаптируй сложность: если отвечает хорошо — усложняй, плохо — упрощай

Формат ответа СТРОГО JSON:
{
  "type": "question" | "feedback" | "summary",
  "question_text": "текст вопроса (если type=question)",
  "category": "категория из: eligibility, procedure, property, consequences, costs, creditors, documents, timeline, court, rights",
  "difficulty": 1-5,
  "feedback_text": "текст обратной связи (если type=feedback)",
  "is_correct": true/false (если type=feedback),
  "explanation": "развёрнутое объяснение (если type=feedback)",
  "article_reference": "ссылка на статью закона",
  "correct_answer": "краткий правильный ответ (если type=feedback и is_correct=false)",
  "encouragement": "мотивирующая фраза"
}
"""

PVP_JUDGE_PROMPT = """Ты — строгий и справедливый AI-судья в дуэли знаний по 127-ФЗ «О несостоятельности (банкротстве)».

Правила:
1. Оценивай ответы ОБЪЕКТИВНО, без предвзятости к игрокам
2. Полностью правильный ответ со ссылкой на статью = максимальный балл
3. Частично верный ответ = пропорциональный балл
4. Неверный ответ = 0 баллов
5. Быстрый ответ получает бонус (если оба верны)
6. Объясняй правильный ответ после каждого раунда

Формат ответа СТРОГО JSON:
{
  "type": "round_result",
  "question_text": "вопрос, на который отвечали",
  "players": [
    {
      "user_id": "...",
      "answer": "текст ответа игрока",
      "score": 0-10,
      "is_correct": true/false,
      "comment": "комментарий к ответу"
    }
  ],
  "correct_answer": "полный правильный ответ",
  "article_reference": "ст. ...",
  "explanation": "развёрнутое объяснение"
}
"""


# ---------------------------------------------------------------------------
# Question generation
# ---------------------------------------------------------------------------

async def generate_question(
    db: AsyncSession,
    *,
    mode: QuizMode,
    category: str | None = None,
    difficulty: int = 3,
    question_number: int = 1,
    total_questions: int = 10,
    previous_questions: list[str] | None = None,
    user_weak_areas: list[str] | None = None,
) -> QuizQuestion:
    """Generate a quiz question using RAG + LLM.

    For themed mode: focuses on the specified category.
    For blitz: random categories, simpler questions.
    For free_dialog: adapts based on user's weak areas.
    """
    # Build a query to retrieve relevant legal context
    if category:
        search_query = f"вопрос по теме {category} федеральный закон 127-фз банкротство"
    elif user_weak_areas:
        search_query = f"вопрос по темам {', '.join(user_weak_areas[:3])} 127-фз"
    else:
        search_query = "вопрос по 127-фз банкротство физических лиц"

    # Retrieve RAG context for question generation
    try:
        rag_category = LegalCategory(category) if category else None
    except ValueError:
        rag_category = None

    rag_context = await retrieve_legal_context(
        search_query, db, top_k=5, prefer_embedding=True,
    )

    # Build prompt for question generation
    context_str = rag_context.to_prompt_context() if rag_context.has_results else ""

    previous_str = ""
    if previous_questions:
        previous_str = "\n\nУже заданные вопросы (НЕ ПОВТОРЯЙ):\n" + "\n".join(
            f"- {q}" for q in previous_questions[-5:]
        )

    messages = [
        {
            "role": "user",
            "content": (
                f"Сгенерируй один вопрос для проверки знаний по 127-ФЗ.\n"
                f"Сложность: {difficulty}/5\n"
                f"{'Категория: ' + category if category else 'Любая категория'}\n"
                f"Вопрос номер {question_number} из {total_questions}\n"
                f"\n{context_str}"
                f"{previous_str}\n\n"
                f"Ответь СТРОГО в формате JSON с type='question'."
            ),
        },
    ]

    try:
        result = await generate_response(
            system_prompt=AI_EXAMINER_PROMPT,
            messages=messages,
            emotion_state="curious",
        )

        parsed = _parse_json_response(result.content)
        if parsed and parsed.get("type") == "question":
            return QuizQuestion(
                question_text=parsed.get("question_text", result.content),
                category=parsed.get("category", category or "general"),
                difficulty=parsed.get("difficulty", difficulty),
                expected_article=parsed.get("article_reference"),
                rag_context=rag_context,
                question_number=question_number,
                total_questions=total_questions,
            )
    except LLMError as e:
        logger.error("LLM failed to generate question: %s", e)

    # Fallback: generate from RAG context directly
    if rag_context.has_results:
        top = rag_context.results[0]
        return QuizQuestion(
            question_text=f"Что вы знаете о следующем аспекте 127-ФЗ: {top.fact_text[:100]}...?",
            category=top.category,
            difficulty=difficulty,
            expected_article=top.law_article,
            rag_context=rag_context,
            question_number=question_number,
            total_questions=total_questions,
        )

    # Last resort fallback
    return QuizQuestion(
        question_text="Каков минимальный размер задолженности для подачи заявления о банкротстве физического лица?",
        category="eligibility",
        difficulty=1,
        expected_article="127-ФЗ ст. 213.3",
        question_number=question_number,
        total_questions=total_questions,
    )


# ---------------------------------------------------------------------------
# Answer evaluation
# ---------------------------------------------------------------------------

async def evaluate_answer(
    db: AsyncSession,
    *,
    question: QuizQuestion,
    user_answer: str,
    mode: QuizMode = QuizMode.free_dialog,
) -> QuizFeedback:
    """Evaluate a user's answer using RAG + LLM.

    1. Retrieve relevant legal facts via RAG
    2. Ask LLM to evaluate correctness based on RAG context
    3. Return structured feedback
    """
    # Retrieve fresh RAG context for the answer
    rag_context = await retrieve_legal_context(
        f"{question.question_text} {user_answer}", db, top_k=5
    )
    context_str = rag_context.to_prompt_context() if rag_context.has_results else ""

    messages = [
        {"role": "assistant", "content": json.dumps({"type": "question", "question_text": question.question_text, "category": question.category}, ensure_ascii=False)},
        {"role": "user", "content": user_answer},
        {
            "role": "user",
            "content": (
                f"Оцени ответ пользователя на вопрос.\n\n"
                f"Правовой контекст для проверки:\n{context_str}\n\n"
                f"Ответь СТРОГО в формате JSON с type='feedback'."
            ),
        },
    ]

    try:
        result = await generate_response(
            system_prompt=AI_EXAMINER_PROMPT,
            messages=messages,
            emotion_state="curious",
        )

        parsed = _parse_json_response(result.content)
        if parsed and parsed.get("type") == "feedback":
            is_correct = parsed.get("is_correct", False)
            return QuizFeedback(
                is_correct=is_correct,
                explanation=parsed.get("explanation", parsed.get("feedback_text", result.content)),
                article_reference=parsed.get("article_reference"),
                score_delta=10.0 if is_correct else 0.0,
                correct_answer_summary=parsed.get("correct_answer") if not is_correct else None,
            )
    except LLMError as e:
        logger.error("LLM failed to evaluate answer: %s", e)

    # Fallback: use RAG keyword matching
    if rag_context.has_results:
        top = rag_context.results[0]
        answer_lower = user_answer.lower()

        # Check if answer contains error patterns
        for err in top.common_errors:
            if isinstance(err, str) and err.lower() in answer_lower:
                return QuizFeedback(
                    is_correct=False,
                    explanation=f"К сожалению, это распространённая ошибка. Правильно: {top.fact_text}",
                    article_reference=top.law_article,
                    score_delta=0.0,
                    correct_answer_summary=top.fact_text,
                )

        # Simple heuristic: if answer overlaps significantly with fact text
        is_likely_correct = top.relevance_score >= 0.5
        return QuizFeedback(
            is_correct=is_likely_correct,
            explanation=f"{'Верно!' if is_likely_correct else 'Не совсем.'} По закону: {top.fact_text}",
            article_reference=top.law_article,
            score_delta=10.0 if is_likely_correct else 0.0,
        )

    return QuizFeedback(
        is_correct=False,
        explanation="Не удалось проверить ответ. Попробуйте переформулировать.",
        score_delta=0.0,
    )


# ---------------------------------------------------------------------------
# PvP round evaluation
# ---------------------------------------------------------------------------

async def evaluate_pvp_round(
    db: AsyncSession,
    *,
    question: QuizQuestion,
    player_answers: list[dict],  # [{"user_id": str, "answer": str, "response_time_ms": int}]
) -> dict:
    """Evaluate a PvP round — multiple players answer the same question.

    Returns per-player scores with AI judge commentary.
    """
    rag_context = await retrieve_legal_context(
        question.question_text, db, top_k=5
    )
    context_str = rag_context.to_prompt_context() if rag_context.has_results else ""

    answers_str = "\n".join(
        f"Игрок {i+1} (user_id={a['user_id']}): «{a['answer']}» (время: {a.get('response_time_ms', 0)}мс)"
        for i, a in enumerate(player_answers)
    )

    messages = [
        {
            "role": "user",
            "content": (
                f"Вопрос: {question.question_text}\n\n"
                f"Правовой контекст:\n{context_str}\n\n"
                f"Ответы игроков:\n{answers_str}\n\n"
                f"Оцени каждый ответ. Ответь СТРОГО в формате JSON с type='round_result'."
            ),
        },
    ]

    try:
        result = await generate_response(
            system_prompt=PVP_JUDGE_PROMPT,
            messages=messages,
            emotion_state="cold",
        )

        parsed = _parse_json_response(result.content)
        if parsed and parsed.get("type") == "round_result":
            return parsed
    except LLMError as e:
        logger.error("LLM failed to evaluate PvP round: %s", e)

    # Fallback: simple evaluation
    return {
        "type": "round_result",
        "question_text": question.question_text,
        "players": [
            {
                "user_id": a["user_id"],
                "answer": a["answer"],
                "score": 5,
                "is_correct": True,
                "comment": "Автоматическая оценка недоступна",
            }
            for a in player_answers
        ],
        "correct_answer": "Оценка временно недоступна",
        "explanation": "Автоматическая оценка по RAG не удалась",
    }


# ---------------------------------------------------------------------------
# Session management helpers
# ---------------------------------------------------------------------------

async def get_user_weak_areas(
    user_id: uuid.UUID,
    db: AsyncSession,
    limit: int = 5,
) -> list[str]:
    """Get user's weak categories based on incorrect answers history."""
    result = await db.execute(
        select(
            KnowledgeAnswer.question_category,
            func.count().label("wrong_count"),
        )
        .where(
            KnowledgeAnswer.user_id == user_id,
            KnowledgeAnswer.is_correct.is_(False),
        )
        .group_by(KnowledgeAnswer.question_category)
        .order_by(func.count().desc())
        .limit(limit)
    )
    return [row.question_category for row in result]


async def get_category_progress(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> list[dict]:
    """Get user's progress per category."""
    categories = [c.value for c in LegalCategory]
    progress = []

    for cat in categories:
        result = await db.execute(
            select(
                func.count().label("total"),
                func.sum(func.cast(KnowledgeAnswer.is_correct, Integer)).label("correct"),
            )
            .where(
                KnowledgeAnswer.user_id == user_id,
                KnowledgeAnswer.question_category == cat,
            )
        )
        row = result.first()
        total = row.total if row else 0
        correct = row.correct if row and row.correct else 0

        progress.append({
            "category": cat,
            "total_answers": total,
            "correct_answers": correct,
            "mastery_pct": round(correct / total * 100, 1) if total > 0 else 0.0,
        })

    return progress


async def calculate_quiz_results(
    session: KnowledgeQuizSession,
    db: AsyncSession,
) -> QuizResults:
    """Calculate final quiz results with category breakdown."""
    answers_result = await db.execute(
        select(KnowledgeAnswer)
        .where(KnowledgeAnswer.session_id == session.id)
        .order_by(KnowledgeAnswer.question_number)
    )
    answers = answers_result.scalars().all()

    # Category breakdown
    cat_stats: dict[str, dict] = {}
    for a in answers:
        cat = a.question_category
        if cat not in cat_stats:
            cat_stats[cat] = {"correct": 0, "total": 0}
        cat_stats[cat]["total"] += 1
        if a.is_correct:
            cat_stats[cat]["correct"] += 1

    for cat in cat_stats:
        cat_stats[cat]["pct"] = round(
            cat_stats[cat]["correct"] / cat_stats[cat]["total"] * 100, 1
        ) if cat_stats[cat]["total"] > 0 else 0.0

    # Weak areas (below 50% accuracy)
    weak = [cat for cat, stats in cat_stats.items() if stats["pct"] < 50.0]

    # Duration
    duration = 0
    if session.started_at and session.ended_at:
        duration = int((session.ended_at - session.started_at).total_seconds())

    total = len(answers)
    correct = sum(1 for a in answers if a.is_correct)
    incorrect = sum(1 for a in answers if not a.is_correct)
    skipped = session.skipped or 0

    return QuizResults(
        total_questions=total,
        correct=correct,
        incorrect=incorrect,
        skipped=skipped,
        score=round(correct / total * 100, 1) if total > 0 else 0.0,
        duration_seconds=duration,
        category_breakdown=cat_stats,
        weak_areas=weak,
        recommendations=[
            f"Обратите внимание на раздел «{w}»" for w in weak[:3]
        ] if weak else ["Отличная подготовка! Попробуйте режим блиц для ускорения."],
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json_response(text: str) -> dict | None:
    """Extract JSON from LLM response (handles markdown code blocks)."""
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from ```json ... ``` blocks
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding first { ... } block
    start = text.find('{')
    if start >= 0:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i+1])
                    except json.JSONDecodeError:
                        pass
                    break

    return None


def get_total_questions(mode: QuizMode) -> int:
    """Get default number of questions for a quiz mode."""
    return {
        QuizMode.free_dialog: 10,
        QuizMode.blitz: 20,
        QuizMode.themed: 15,
        QuizMode.pvp: 10,
    }.get(mode, 10)


def get_time_limit_seconds(mode: QuizMode) -> int | None:
    """Get per-question time limit in seconds (None = no limit)."""
    return {
        QuizMode.free_dialog: None,
        QuizMode.blitz: 60,
        QuizMode.themed: None,
        QuizMode.pvp: 45,
    }.get(mode)
