"""Knowledge quiz service — AI examiner and PvP judge for 127-ФЗ.

Two modes:
1. AI Examiner — charismatic AI asks questions, evaluates answers using RAG
2. PvP Judge — strict AI evaluates answers from 2-4 competing players

Uses Gemini 2.5 Flash (same LLM chain as training) with specialized prompts.
"""

import json
import logging
import random
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
from app.services.rag_legal import retrieve_legal_context, RAGContext, RetrievalConfig, blitz_pool

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
    # V2 fields
    chunk_id: uuid.UUID | None = None  # Source chunk for session dedup
    blitz_answer: str | None = None  # Pre-built answer for zero-LLM blitz eval
    generation_strategy: str = "llm"  # "blitz_pool" | "template" | "llm" | "fallback"


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
    used_chunk_ids: set[uuid.UUID] | None = None,
) -> QuizQuestion:
    """Generate a quiz question using tiered strategy chain.

    Strategy 1 (blitz): BlitzQuestionPool — zero LLM, instant (<5ms)
    Strategy 2 (any): question_templates from RAG chunk — zero LLM (<50ms)
    Strategy 3 (free_dialog/themed): LLM generation with RAG context (2-5s)
    Strategy 4: RAG fact → template fallback
    Strategy 5: Hardcoded last resort
    """
    exclude_ids = list(used_chunk_ids) if used_chunk_ids else None

    # ── Strategy 1: BlitzQuestionPool (blitz mode only) ───────────────────────
    if mode == QuizMode.blitz and blitz_pool.loaded:
        diff_range = (max(1, difficulty - 1), min(5, difficulty + 1))
        item = blitz_pool.get_question(
            category=category,
            difficulty_range=diff_range,
            exclude_ids=used_chunk_ids,
        )
        if item:
            return QuizQuestion(
                question_text=item["question"],
                category=item["category"],
                difficulty=item["difficulty"],
                expected_article=item["article"],
                question_number=question_number,
                total_questions=total_questions,
                chunk_id=item["chunk_id"],
                blitz_answer=item["answer"],
                generation_strategy="blitz_pool",
            )

    # ── Build RAG retrieval config ────────────────────────────────────────────
    diff_range = None
    if mode == QuizMode.themed:
        diff_range = themed_difficulty_range(question_number, total_questions)
    else:
        diff_range = (max(1, difficulty - 1), min(5, difficulty + 1))

    config = RetrievalConfig(
        top_k=5,
        category=category,
        difficulty_range=diff_range,
        exclude_chunk_ids=exclude_ids,
        prefer_court_practice=(difficulty >= 4),
        mode=mode.value,
    )

    if category:
        search_query = f"вопрос по теме {category} федеральный закон 127-фз банкротство"
    elif user_weak_areas:
        search_query = f"вопрос по темам {', '.join(user_weak_areas[:3])} 127-фз"
    else:
        search_query = "вопрос по 127-фз банкротство физических лиц"

    rag_context = await retrieve_legal_context(search_query, db, config=config)

    # ── Strategy 2: question_templates from RAG chunk ─────────────────────────
    if rag_context.has_results:
        for result in rag_context.results:
            templates = result.question_templates
            if templates:
                # Filter: match difficulty, exclude previously used questions
                available = [
                    t for t in templates
                    if abs(t.get("difficulty", 3) - difficulty) <= 1
                    and t.get("text", "") not in (previous_questions or [])
                ]
                if available:
                    tmpl = random.choice(available)
                    return QuizQuestion(
                        question_text=tmpl["text"],
                        category=result.category,
                        difficulty=tmpl.get("difficulty", difficulty),
                        expected_article=result.law_article,
                        rag_context=rag_context,
                        question_number=question_number,
                        total_questions=total_questions,
                        chunk_id=result.chunk_id,
                        blitz_answer=result.blitz_answer,
                        generation_strategy="template",
                    )

    # ── Strategy 3: LLM generation with RAG context ──────────────────────────
    context_str = rag_context.to_prompt_context() if rag_context.has_results else ""
    previous_str = ""
    if previous_questions:
        previous_str = "\n\nУже заданные вопросы (НЕ ПОВТОРЯЙ):\n" + "\n".join(
            f"- {q}" for q in previous_questions[-5:]
        )

    messages = [{
        "role": "user",
        "content": (
            f"Сгенерируй один вопрос для проверки знаний по 127-ФЗ.\n"
            f"Сложность: {difficulty}/5\n"
            f"{'Категория: ' + category if category else 'Любая категория'}\n"
            f"Вопрос номер {question_number} из {total_questions}\n"
            f"\n{context_str}{previous_str}\n\n"
            f"Ответь СТРОГО в формате JSON с type='question'."
        ),
    }]

    try:
        result = await generate_response(
            system_prompt=AI_EXAMINER_PROMPT,
            messages=messages,
            emotion_state="curious",
        )
        parsed = _parse_json_response(result.content)
        if parsed and parsed.get("type") == "question":
            chunk_id = rag_context.results[0].chunk_id if rag_context.has_results else None
            return QuizQuestion(
                question_text=parsed.get("question_text", result.content),
                category=parsed.get("category", category or "general"),
                difficulty=parsed.get("difficulty", difficulty),
                expected_article=parsed.get("article_reference"),
                rag_context=rag_context,
                question_number=question_number,
                total_questions=total_questions,
                chunk_id=chunk_id,
                generation_strategy="llm",
            )
    except LLMError as e:
        logger.error("LLM failed to generate question: %s", e)

    # ── Strategy 4: RAG fact-based fallback ───────────────────────────────────
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
            chunk_id=top.chunk_id,
            generation_strategy="fallback",
        )

    # ── Strategy 5: Hardcoded last resort ─────────────────────────────────────
    return QuizQuestion(
        question_text="Каков минимальный размер задолженности для подачи заявления о банкротстве физического лица?",
        category="eligibility",
        difficulty=1,
        expected_article="127-ФЗ ст. 213.3",
        question_number=question_number,
        total_questions=total_questions,
        generation_strategy="hardcoded",
    )


async def generate_question_with_arena_difficulty(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    mode: QuizMode,
    category: str | None = None,
    difficulty: int | None = None,
    question_number: int = 1,
    total_questions: int = 10,
    previous_questions: list[str] | None = None,
    user_weak_areas: list[str] | None = None,
) -> QuizQuestion:
    """Generate a question with difficulty adapted to user's Arena rating.

    Block 5 (Cross-Module): If difficulty is not explicitly set, the Arena
    difficulty engine determines the range based on PvP rating.
    """
    if difficulty is None:
        try:
            from app.services.arena_difficulty import get_arena_difficulty_profile

            profile = await get_arena_difficulty_profile(user_id, db)
            d_min, d_max = profile["difficulty_range"]
            difficulty = random.randint(d_min, d_max)
        except Exception:
            difficulty = 3  # Default fallback

    return await generate_question(
        db,
        mode=mode,
        category=category,
        difficulty=difficulty,
        question_number=question_number,
        total_questions=total_questions,
        previous_questions=previous_questions,
        user_weak_areas=user_weak_areas,
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
    """Evaluate a user's answer with anti-hallucination grounding.

    Pipeline:
    1. Blitz fast-path: if blitz_answer present → keyword match (no LLM)
    2. Pre-check: does answer match a known common_error? → instant incorrect
    3. LLM evaluation with RAG context injection
    4. Post-check: cross-verify LLM verdict against common_errors
       If LLM says "correct" but answer matches common_error → OVERRIDE
    5. No RAG context → return "cannot verify" (never guess)
    """
    difficulty = question.difficulty

    # ── Blitz fast-path (zero LLM) ───────────────────────────────────────────
    if question.blitz_answer and mode == QuizMode.blitz:
        is_correct = _blitz_keyword_match(user_answer, question.blitz_answer)
        return QuizFeedback(
            is_correct=is_correct,
            explanation=question.blitz_answer if not is_correct else "Верно!",
            article_reference=question.expected_article,
            score_delta=_score_delta(is_correct, difficulty),
            correct_answer_summary=question.blitz_answer if not is_correct else None,
        )

    # ── Retrieve fresh RAG context ───────────────────────────────────────────
    rag_context = await retrieve_legal_context(
        f"{question.question_text} {user_answer}", db, top_k=5
    )

    # ── Pre-check: instant common_error match ────────────────────────────────
    if rag_context.has_results:
        answer_lower = user_answer.lower()
        for result in rag_context.results[:3]:
            for err in result.common_errors:
                if isinstance(err, str) and err.lower() in answer_lower:
                    return QuizFeedback(
                        is_correct=False,
                        explanation=f"Это распространённая ошибка: «{err}». Правильно: {result.correct_response_hint or result.fact_text}",
                        article_reference=result.law_article,
                        score_delta=_score_delta(False, difficulty),
                        correct_answer_summary=result.correct_response_hint or result.fact_text,
                    )

    # ── LLM evaluation with RAG grounding ────────────────────────────────────
    context_str = rag_context.to_prompt_context() if rag_context.has_results else ""

    messages = [
        {"role": "assistant", "content": json.dumps({"type": "question", "question_text": question.question_text, "category": question.category}, ensure_ascii=False)},
        {"role": "user", "content": user_answer},
        {"role": "user", "content": (
            f"Оцени ответ пользователя на вопрос.\n\n"
            f"Правовой контекст для проверки:\n{context_str}\n\n"
            f"ВАЖНО: Оценивай СТРОГО по предоставленному контексту. "
            f"Если ответ совпадает с 'частыми ошибками' — это НЕВЕРНЫЙ ответ.\n\n"
            f"Ответь СТРОГО в формате JSON с type='feedback'."
        )},
    ]

    try:
        result = await generate_response(
            system_prompt=AI_EXAMINER_PROMPT,
            messages=messages,
            emotion_state="curious",
        )
        parsed = _parse_json_response(result.content)
        if parsed and parsed.get("type") == "feedback":
            llm_verdict = parsed.get("is_correct", False)

            # ── Post-check: anti-hallucination cross-verification ────────────
            final_verdict, override_reason = _cross_check_verdict(
                llm_verdict, user_answer, rag_context.results if rag_context.has_results else []
            )

            explanation = parsed.get("explanation", parsed.get("feedback_text", result.content))
            if override_reason:
                explanation = f"{override_reason} {explanation}"

            return QuizFeedback(
                is_correct=final_verdict,
                explanation=explanation,
                article_reference=parsed.get("article_reference"),
                score_delta=_score_delta(final_verdict, difficulty),
                correct_answer_summary=parsed.get("correct_answer") if not final_verdict else None,
            )
    except LLMError as e:
        logger.error("LLM failed to evaluate answer: %s", e)

    # ── Keyword fallback (no LLM available) ──────────────────────────────────
    if rag_context.has_results:
        top = rag_context.results[0]
        is_likely_correct = top.relevance_score >= 0.5
        return QuizFeedback(
            is_correct=is_likely_correct,
            explanation=f"{'Верно!' if is_likely_correct else 'Не совсем.'} По закону: {top.fact_text}",
            article_reference=top.law_article,
            score_delta=_score_delta(is_likely_correct, difficulty),
        )

    # ── No RAG context — cannot verify (anti-hallucination) ──────────────────
    return QuizFeedback(
        is_correct=False,
        explanation="Не удалось проверить ответ по базе знаний. Рекомендуем свериться с текстом ФЗ-127.",
        score_delta=0.0,
    )


def _cross_check_verdict(
    llm_verdict: bool, user_answer: str, rag_results: list,
) -> tuple[bool, str | None]:
    """Cross-check LLM verdict against known error patterns.

    If LLM says correct but answer matches a common_error → override to incorrect.
    """
    if not llm_verdict:
        return False, None

    answer_lower = user_answer.lower()
    for result in rag_results[:3]:
        for err in (result.common_errors or []):
            if isinstance(err, str) and len(err) > 5 and err.lower() in answer_lower:
                return False, f"Ваш ответ совпадает с частой ошибкой: «{err}»."
    return True, None


def _score_delta(is_correct: bool, difficulty: int) -> float:
    """Calculate score delta based on difficulty.

    Correct:  d1=+6, d2=+8, d3=+10, d4=+13, d5=+16
    Incorrect: d1=-1, d2=-1.5, d3=-2, d4=-2.5, d5=-3
    """
    if is_correct:
        return {1: 6.0, 2: 8.0, 3: 10.0, 4: 13.0, 5: 16.0}.get(difficulty, 10.0)
    return {1: -1.0, 2: -1.5, 3: -2.0, 4: -2.5, 5: -3.0}.get(difficulty, -2.0)


def _blitz_keyword_match(user_answer: str, expected: str) -> bool:
    """Fast keyword matching for blitz evaluation (no LLM).

    Extracts key numbers and terms, checks overlap.
    """
    import re as _re
    answer_lower = user_answer.lower().strip()
    expected_lower = expected.lower()

    # Extract and compare numbers
    answer_nums = set(_re.findall(r'\d+', answer_lower.replace(" ", "")))
    expected_nums = set(_re.findall(r'\d+', expected_lower.replace(" ", "")))
    if expected_nums:
        if len(answer_nums & expected_nums) / len(expected_nums) >= 0.5:
            return True

    # Keyword overlap
    stop = {"и", "в", "на", "по", "от", "с", "для", "при", "что", "это", "не", "а", "к", "о"}
    answer_words = set(answer_lower.split()) - stop
    expected_words = set(expected_lower.split()) - stop
    if expected_words:
        return len(answer_words & expected_words) / len(expected_words) >= 0.35

    return False


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

    # Fallback: keyword-based PvP evaluation (no LLM)
    # Use RAG context to do basic keyword matching per answer
    fallback_players = []
    for a in player_answers:
        ans_lower = (a.get("answer") or "").lower()
        is_correct = False
        score = 0
        comment = "Автоматическая оценка (базовая)"

        if rag_context.has_results:
            top = rag_context.results[0]
            # Check against common errors first
            for err in top.common_errors:
                if isinstance(err, str) and err.lower() in ans_lower:
                    is_correct = False
                    score = 0
                    comment = f"Совпадает с частой ошибкой"
                    break
            else:
                # Basic keyword overlap check
                keywords = [kw.lower() for kw in (getattr(top, 'match_keywords', None) or []) if kw]
                if keywords:
                    overlap = sum(1 for kw in keywords if kw in ans_lower)
                    if overlap >= len(keywords) * 0.3:
                        is_correct = True
                        score = 6
                        comment = "Частично верно (базовая проверка)"

        fallback_players.append({
            "user_id": a["user_id"],
            "answer": a.get("answer", ""),
            "score": score,
            "is_correct": is_correct,
            "comment": comment,
        })

    correct_answer = ""
    if rag_context.has_results:
        top = rag_context.results[0]
        correct_answer = top.correct_response_hint or top.fact_text[:200]

    return {
        "type": "round_result",
        "question_text": question.question_text,
        "players": fallback_players,
        "correct_answer": correct_answer or "Оценка временно недоступна",
        "explanation": "Оценка выполнена без AI-судьи (базовый режим)",
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
        # DOC_11: New modes
        QuizMode.rapid_blitz: 10,
        QuizMode.case_study: 7,
        QuizMode.debate: 7,
        QuizMode.mock_court: 10,
        QuizMode.article_deep_dive: 10,
        QuizMode.team_quiz: 10,
        QuizMode.daily_challenge: 10,
    }.get(mode, 10)


def get_time_limit_seconds(mode: QuizMode) -> int | None:
    """Get per-question time limit in seconds (None = no limit)."""
    return {
        QuizMode.free_dialog: None,
        QuizMode.blitz: 60,
        QuizMode.themed: None,
        QuizMode.pvp: 45,
        # DOC_11: New modes
        QuizMode.rapid_blitz: 30,
        QuizMode.case_study: None,
        QuizMode.debate: None,
        QuizMode.mock_court: None,
        QuizMode.article_deep_dive: 60,
        QuizMode.team_quiz: 45,
        QuizMode.daily_challenge: 60,
    }.get(mode)


# ---------------------------------------------------------------------------
# V2: Blitz speed bonus
# ---------------------------------------------------------------------------

def calculate_blitz_speed_bonus(response_time_ms: int) -> float:
    """Speed bonus for blitz mode based on answer time.

    < 15 sec: +2 points
    < 30 sec: +1 point
    >= 30 sec: 0
    """
    if response_time_ms < 15_000:
        return 2.0
    elif response_time_ms < 30_000:
        return 1.0
    return 0.0


# ---------------------------------------------------------------------------
# V2: Themed progressive difficulty
# ---------------------------------------------------------------------------

def themed_difficulty_range(question_number: int, total: int) -> tuple[int, int]:
    """Progressive difficulty for themed mode.

    Questions 1-5:  difficulty 1-2 (basic)
    Questions 6-10: difficulty 3-4 (medium)
    Questions 11-15: difficulty 4-5 (hard, court practice)
    """
    if total <= 0:
        return (1, 5)
    progress = question_number / total
    if progress <= 0.33:
        return (1, 2)
    elif progress <= 0.66:
        return (3, 4)
    else:
        return (4, 5)


# ---------------------------------------------------------------------------
# V2: Follow-up question generation
# ---------------------------------------------------------------------------

async def generate_follow_up(
    question: QuizQuestion,
    user_answer: str,
    is_correct: bool,
    personality_prompt: str | None = None,
) -> str | None:
    """Generate an optional follow-up question after every 3rd answer.

    Tries pre-built follow-ups from RAG chunk first, falls back to LLM.
    Only for free_dialog mode.
    """
    # Strategy 1: Use pre-built follow-up from RAG context
    if question.rag_context and question.rag_context.results:
        chunk = question.rag_context.results[0]
        follow_ups = chunk.follow_up_questions
        if follow_ups:
            return random.choice(follow_ups)

    # Strategy 2: Generate via LLM
    prompt = (
        f"На основе вопроса и ответа, задай УТОЧНЯЮЩИЙ вопрос.\n\n"
        f"Предыдущий вопрос: {question.question_text}\n"
        f"Ответ пользователя: {user_answer}\n"
        f"Оценка: {'Верно' if is_correct else 'Неверно'}\n"
        f"Статья: {question.expected_article or 'не указана'}\n\n"
        f"Правила:\n"
        f"1. Уточняющий вопрос должен УГЛУБЛЯТЬ тему, а не повторять\n"
        f"2. Тестировать ПОНИМАНИЕ, а не запоминание\n"
        f"3. Связать с практическим применением или судебной практикой\n"
        f"4. Формулировка: 'А знаете ли вы...' / 'Интересно, а как это связано с...'\n"
        f"5. Максимум 2 предложения\n\n"
        f"Ответь ТОЛЬКО текстом вопроса, без JSON."
    )

    try:
        result = await generate_response(
            system_prompt=personality_prompt or AI_EXAMINER_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            emotion_state="curious",
        )
        text = result.content.strip() if result else None
        if text and len(text) < 500:
            return text
    except (LLMError, Exception):
        pass

    return None


# ---------------------------------------------------------------------------
# V2: Guiding hints (not answers)
# ---------------------------------------------------------------------------

async def generate_guiding_hint(
    question: QuizQuestion,
    personality_name: str | None = None,
) -> str:
    """Generate a guiding hint that points to the relevant article without revealing the answer.

    Hints are styled based on the personality:
    - professor: "Обратите внимание на ст. 213.X..."
    - detective: "Улики ведут к ст. 213.X..."
    - showman: not used (hints blocked in blitz)
    """
    article = question.expected_article

    if article:
        if personality_name == "detective":
            hints = [
                f"Улики ведут к {article} — там ключ к разгадке!",
                f"Загляните в {article} — это ваша главная улика.",
                f"Следы преступления указывают на {article}...",
            ]
        else:
            hints = [
                f"Обратите внимание на {article} — там ключ к ответу.",
                f"Подсказка: ответ кроется в {article}.",
                f"Загляните в {article} — и истина откроется вам.",
            ]
        return random.choice(hints)

    # Fallback: use RAG context hint
    if question.rag_context and question.rag_context.results:
        chunk = question.rag_context.results[0]
        if chunk.correct_response_hint:
            words = chunk.correct_response_hint.split()
            if len(words) > 5:
                partial = " ".join(words[:5]) + "..."
                return f"Направление мысли: {partial}"

    return "Подсказка: внимательно перечитайте вопрос и подумайте о ключевых терминах ФЗ-127."


# ---------------------------------------------------------------------------
# V2: Enhanced answer evaluation with anti-hallucination
# ---------------------------------------------------------------------------

async def evaluate_answer_v2(
    db: AsyncSession,
    *,
    question: QuizQuestion,
    user_answer: str,
    mode: QuizMode = QuizMode.free_dialog,
    personality_prompt: str | None = None,
) -> QuizFeedback:
    """Enhanced answer evaluation with RAG grounding and anti-hallucination.

    Improvements over v1:
    1. Pre-check: fast match against common_errors (no LLM needed)
    2. Cross-check: LLM says correct but answer = known error → override
    3. Personality-styled feedback
    """
    # Get RAG context
    rag_context = question.rag_context
    if not rag_context or not rag_context.results:
        # Re-retrieve if missing
        rag_context = await retrieve_legal_context(
            question.question_text, db, top_k=3,
            config=RetrievalConfig(top_k=3),
        )

    if not rag_context.results:
        return QuizFeedback(
            is_correct=False,
            explanation="Не удалось проверить ответ по базе знаний. Попробуйте переформулировать.",
            score_delta=0.0,
        )

    chunk = rag_context.results[0]
    answer_lower = user_answer.lower().strip()

    # Pre-check: fast match against common errors
    for err in chunk.common_errors:
        if isinstance(err, str) and _text_overlap(answer_lower, err.lower()) > 0.6:
            return QuizFeedback(
                is_correct=False,
                explanation=f"Это распространённое заблуждение. Правильно: {chunk.correct_response_hint or chunk.fact_text}",
                article_reference=chunk.law_article,
                score_delta=0.0,
                correct_answer_summary=chunk.correct_response_hint or chunk.fact_text,
            )

    # LLM evaluation with RAG grounding
    context_str = rag_context.to_prompt_context()
    messages = [
        {"role": "assistant", "content": json.dumps(
            {"type": "question", "question_text": question.question_text, "category": question.category},
            ensure_ascii=False,
        )},
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
            system_prompt=personality_prompt or AI_EXAMINER_PROMPT,
            messages=messages,
            emotion_state="curious",
        )

        parsed = _parse_json_response(result.content)
        if parsed and parsed.get("type") == "feedback":
            is_correct = parsed.get("is_correct", False)

            # Cross-check: if LLM says correct but answer matches common error
            if is_correct:
                for err in chunk.common_errors:
                    if isinstance(err, str) and _text_overlap(answer_lower, err.lower()) > 0.5:
                        is_correct = False
                        break

            return QuizFeedback(
                is_correct=is_correct,
                explanation=parsed.get("explanation", parsed.get("feedback_text", result.content)),
                article_reference=parsed.get("article_reference") or chunk.law_article,
                score_delta=10.0 if is_correct else 0.0,
                correct_answer_summary=parsed.get("correct_answer") if not is_correct else None,
            )
    except (LLMError, Exception) as e:
        logger.error("LLM evaluation failed: %s", e)

    # Fallback: keyword-based evaluation
    return _keyword_based_evaluation(question, user_answer, chunk)


def _text_overlap(text_a: str, text_b: str) -> float:
    """Calculate word overlap ratio between two texts."""
    stop_words = {"и", "в", "на", "по", "от", "с", "для", "при", "что", "это", "не", "а", "но", "к", "о"}
    words_a = set(text_a.split()) - stop_words
    words_b = set(text_b.split()) - stop_words
    if not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_b)


def _keyword_based_evaluation(
    question: QuizQuestion,
    user_answer: str,
    chunk,
) -> QuizFeedback:
    """Fallback evaluation without LLM using keyword matching."""
    answer_lower = user_answer.lower()

    # Check common errors first
    for err in (chunk.common_errors or []):
        if isinstance(err, str) and _text_overlap(answer_lower, err.lower()) > 0.5:
            return QuizFeedback(
                is_correct=False,
                explanation=f"Это частое заблуждение. {chunk.correct_response_hint or chunk.fact_text}",
                article_reference=chunk.law_article,
                score_delta=0.0,
                correct_answer_summary=chunk.correct_response_hint,
            )

    # Check keyword overlap with hint
    hint = (chunk.correct_response_hint or "").lower()
    if hint:
        overlap = _text_overlap(answer_lower, hint)
        if overlap >= 0.3:
            return QuizFeedback(
                is_correct=True,
                explanation=f"Верно! {chunk.correct_response_hint}",
                article_reference=chunk.law_article,
                score_delta=10.0,
            )

    return QuizFeedback(
        is_correct=False,
        explanation=f"Не совсем. {chunk.correct_response_hint or chunk.fact_text}",
        article_reference=chunk.law_article,
        score_delta=0.0,
        correct_answer_summary=chunk.correct_response_hint,
    )
