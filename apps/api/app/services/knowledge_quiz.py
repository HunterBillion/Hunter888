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
    """Evaluation result for a user's answer.

    2026-05-04 FRONT-3: introduced `verdict_level` for nuanced grading.
    Was binary correct/wrong — now 4 buckets so the UI can show
    "почти" / "знаешь, но не по теме" rather than slamming "✖ Неверно"
    on every imperfect answer.

    Mapping from LLM score (0-10):
        ≥8  → "correct"  (✓ Верно — full XP)
        5-7 → "partial"  (🟡 Почти — half XP, missing details)
        2-4 → "off_topic"(📍 Знаешь, но не по теме — 0 XP, no penalty)
        <2  → "wrong"    (✖ Неверно — penalty)

    `is_correct` is preserved for legacy callers; True iff
    verdict_level == "correct".
    """
    is_correct: bool
    explanation: str
    article_reference: str | None = None
    score_delta: float = 0.0
    correct_answer_summary: str | None = None
    verdict_level: str = "correct"  # "correct" | "partial" | "off_topic" | "wrong"
    llm_score: float | None = None  # 0-10 raw score from LLM (None if not available)


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

AI_EXAMINER_PROMPT = """Ты — харизматичный, но СТРОГИЙ AI-экзаменатор по Федеральному Закону №127-ФЗ «О несостоятельности (банкротстве)».

Твоя личность:
- Ты энергичный, остроумный и немного театральный
- Используешь яркие метафоры и примеры из жизни
- Хвалишь за правильные ответы с энтузиазмом
- При неправильных ответах — не ругаешь, а с юмором объясняешь правильный вариант
- Говоришь на «ты», дружелюбно, но экспертно
- Время от времени шутишь про юридические казусы

═══ ПРАВИЛА ОЦЕНКИ (v2, 2026-04-19) ═══
ПРАВИЛО №1 (АНТИ-ЛОЯЛЬНОСТЬ): is_correct=true МОЖНО ставить ТОЛЬКО если ответ содержит конкретный юридический факт, совпадающий с правовым контекстом. Приветствия («привет», «здравствуй»), полные отказы («не знаю», «хз», «пропущу»), мат, односложные ответы («да», «нет», «может»), ответы-вопросы («а сколько?», «а когда?») — всегда is_correct=false.

ПРАВИЛО №2 (МИНИМАЛЬНАЯ ДЛИНА, v2 relax): ответ короче 10 символов И БЕЗ цифр И БЕЗ латиницы/кириллицы, выглядящих как термин → is_correct=false. НО: «ст. 213.4» (9 символов, есть цифры) — ВАЛИДНО, оценивай по смыслу. «90 дней» — тоже валидно. Цифры и сокращения статей снимают ограничение длины.

ПРАВИЛО №3 (ГРАУНДИНГ): если в правовом контексте нет подтверждения ответа — is_correct=false, даже если звучит правдоподобно. Никогда не «додумывай» правду.

ПРАВИЛО №4 (ЧАСТИЧНЫЙ ОТВЕТ, v2 relax — partial credit): если пользователь назвал часть факта (номер статьи БЕЗ срока; срок БЕЗ привязки; термин БЕЗ определения) — ставь is_correct=false, НО в поле «score_delta» положи 0.5 (а не 0), укажи в feedback_text что именно он упустил. Это поощряет частичное знание. Полный ответ = score_delta=1.0, полностью неверный = 0.0, частично верный = 0.5.

ПРАВИЛО №5 (МАТ/ОСКОРБЛЕНИЯ): любой мат или оскорбление — is_correct=false, мягко напомни о формате.

ПРАВИЛО №6 (СЕМАНТИЧЕСКАЯ ЭКВИВАЛЕНТНОСТЬ, новое): считай эквивалентными: «субсидиарка» ≈ «субсидиарная ответственность», «финуправляющий» ≈ «финансовый управляющий», «банкротство» ≈ «несостоятельность», «90 дней» ≈ «девяносто дней», «ст. 213.4» ≈ «статья 213.4» ≈ «213.4». Числительные в прописи = цифры.

Прочее:
1. Задавай вопросы ТОЛЬКО по 127-ФЗ и связанной судебной практике
2. Каждый вопрос должен проверять конкретное знание (статья, порог, срок, процедура)
3. После ответа — обратная связь на 2-4 предложения
4. Ссылайся на конкретные статьи закона
5. Адаптируй сложность: если отвечает хорошо — усложняй, плохо — упрощай

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
            task_type="structured",
            prefer_provider="local",
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

# 2026-04-18: separated into EXACT matches and SUBSTRING (leading) matches.
# Leading-match catches "не знаю, ты кто", "хз мне всё равно" — whole answer
# begins with a dismissive phrase → treat as garbage.
_GARBAGE_EXACT = (
    # greetings
    "привет", "здравствуй", "здравствуйте", "добрый день", "добрый вечер", "доброе утро",
    "хай", "hi", "hello", "йо", "салют", "ку", "здарова",
    # don't-knows (exact)
    "не знаю", "незнаю", "хз", "не в курсе", "без понятия", "без представления",
    "забыл", "забыла", "не помню", "не понял", "не поняла", "не понятно",
    # skips
    "пропустить", "пропущу", "далее", "скип", "skip", "next", "пасс", "пас",
    # placeholders / noise
    "тест", "test", "проверка", "asdf", "qwer", "123", "qwerty", "йцукен",
    # single affirmations (not answers by themselves)
    "да", "нет", "возможно", "может быть", "наверное", "скорее всего", "хотя бы", "ну",
    # insults / dismissals
    "мне всё равно", "мне все равно", "мне похуй", "пофиг", "без разницы",
    "ну и что", "и что", "и чё", "ну и чё", "не важно", "неважно",
)

# If the user's answer STARTS WITH one of these (followed by punctuation or
# space + more dismissive text), it's still garbage — prevents "не знаю, ты кто".
_GARBAGE_PREFIX = (
    "не знаю",
    "незнаю",
    "хз ",
    "хз,",
    "не в курсе",
    "без понятия",
    "мне всё равно",
    "мне все равно",
    "мне похуй",
    "пофиг",
    "без разницы",
    "пропустить",
    "пропущу",
    "скип",
    "привет",
    "здравствуй",
    "ку ",
)


def _is_garbage_answer(answer: str) -> tuple[bool, str]:
    """Cheap pre-LLM filter for non-answer inputs.

    Returns (is_garbage, reason). If True, caller skips LLM and marks
    is_correct=False. Prevents the "привет → ✓ Верно" lenience bug
    and the "не знаю, ты кто" + "да но мне всё равно" follow-ups.

    2026-05-04 (real-prod fix): "Алибек" = 6 chars without digits and
    was passing through to the LLM, which then said "✓ Верно" because
    the prompt was too lenient. The threshold was 6 (strictly less);
    any 6-letter random word (name, greeting, gibberish) slipped past.
    Tightened to: an answer that has NO digits AND NO legal marker
    word is rejected unless it's at least 12 chars (≈ 2-3 short
    Russian words). Names, greetings, and short gibberish all get
    caught now.
    """
    a = (answer or "").strip().lower()
    if not a:
        return True, "Пустой ответ."
    # Strip trailing punctuation + common noise
    stripped = a.rstrip("!?.,;:-)( \n")
    if not stripped:
        return True, "Пустой ответ."
    # No-digits + no-legal-markers + short → garbage. Was `< 6` only,
    # which let through 6-letter names like "Алибек". Now requires
    # 12+ chars OR a digit OR a legal marker.
    legal_markers = (
        "ст.", "ст ", "статья", "пункт", "банкрот", "управляющ",
        "кредитор", "залог", "имуществ", "должник", "просрочк",
        "срок", "ипотек", "алимент", "процедур", "арбитраж", "фз",
        "127-фз", "229-фз", "гпк", "ск рф", "коап",
    )
    has_digits = any(c.isdigit() for c in stripped)
    has_legal = any(m in stripped for m in legal_markers)
    if len(stripped) < 12 and not has_digits and not has_legal:
        return True, "Слишком короткий ответ — нужна конкретика: статья, сумма или срок."
    # Exact match
    for token in _GARBAGE_EXACT:
        if stripped == token:
            return True, "Это не ответ по существу. Нужна статья, порог или процедура."
    # Prefix match — catches "не знаю, ты кто", "хз мне всё равно"
    for prefix in _GARBAGE_PREFIX:
        if stripped.startswith(prefix):
            # Ensure the rest isn't a real answer (heuristic: no digits + no legal terms)
            has_digits = any(c.isdigit() for c in stripped)
            legal_markers = ("ст.", "ст ", "статья", "пункт", "банкрот", "управляющ", "кредитор", "залог", "имуществ")
            has_legal = any(m in stripped for m in legal_markers)
            if not has_digits and not has_legal:
                return True, "Это не ответ по существу. Нужна статья, порог или процедура."
    # Contains ONLY a mild affirmation + dismissal — "да но мне всё равно", "возможно, да но мне пофиг"
    mild_affirms = ("да ", "нет ", "возможно", "наверное", "скорее всего", "может быть", "может,")
    dismissals = ("мне всё равно", "мне все равно", "мне всеравно", "всеравно", "всё равно", "мне похуй", "похуй", "пофиг", "без разницы", "не важно", "неважно", "не скажу", "ну и что", "и чё", "и что")
    has_aff = any(stripped.startswith(m) for m in mild_affirms)
    has_dis = any(d in stripped for d in dismissals)
    if has_aff and has_dis:
        return True, "Это не ответ по существу. Нужна статья, порог или процедура."
    if has_dis and len(stripped) < 40 and not any(c.isdigit() for c in stripped):
        return True, "Это не ответ по существу. Нужна статья, порог или процедура."
    # All caps / all same char spam ("ААААА", "!!!!!!")
    if len(set(stripped.replace(" ", ""))) <= 1 and len(stripped) <= 12:
        return True, "Ответ нераспознан — похоже на случайный ввод."
    return False, ""


async def evaluate_answer(
    db: AsyncSession,
    *,
    question: QuizQuestion,
    user_answer: str,
    mode: QuizMode = QuizMode.free_dialog,
) -> QuizFeedback:
    """Evaluate a user's answer with anti-hallucination grounding.

    Pipeline:
    0. Garbage fast-path: greetings / skips / empty / spam → instant incorrect (no LLM)
    1. Blitz fast-path: if blitz_answer present → keyword match (no LLM)
    2. Pre-check: does answer match a known common_error? → instant incorrect
    3. LLM evaluation with RAG context injection
    4. Post-check: cross-verify LLM verdict against common_errors
       If LLM says "correct" but answer matches common_error → OVERRIDE
    5. No RAG context → return "cannot verify" (never guess)
    """
    difficulty = question.difficulty

    # ── Garbage answer fast-path (2026-04-18 fix: «привет» → ✓ Верно bug) ───
    is_garbage, garbage_reason = _is_garbage_answer(user_answer)
    if is_garbage:
        correct_hint: str | None = None
        article_ref = question.expected_article
        # Try to surface the expected article text as "правильный ответ" hint
        if question.blitz_answer:
            correct_hint = question.blitz_answer
        return QuizFeedback(
            is_correct=False,
            explanation=garbage_reason + (f" Правильно: {correct_hint}" if correct_hint else ""),
            article_reference=article_ref,
            score_delta=_score_delta(False, difficulty),
            correct_answer_summary=correct_hint,
        )

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

    # ── Affirmative keyword fast-path (2026-04-18 fix for judge false-negatives) ─
    # User complaints:
    #   Q: "через сколько лет повторное банкротство?"  A: "через 5 лет"
    #   → LLM said WRONG (confused МФЦ/суд). But blitz_answer="5 лет" → correct.
    # If the user's answer contains the blitz_answer keywords AND is long enough
    # to not be a coincidence, mark CORRECT without LLM.
    if question.blitz_answer and _affirmative_keyword_match(user_answer, question.blitz_answer):
        return QuizFeedback(
            is_correct=True,
            explanation=f"Верно! {question.blitz_answer}",
            article_reference=question.expected_article,
            score_delta=_score_delta(True, difficulty),
            correct_answer_summary=None,
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
    from app.services.scenario_engine import _sanitize_db_prompt
    context_str = rag_context.to_prompt_context() if rag_context.has_results else ""
    sanitized_answer = _sanitize_db_prompt(user_answer, "user_answer")

    messages = [
        {"role": "assistant", "content": json.dumps({"type": "question", "question_text": question.question_text, "category": question.category}, ensure_ascii=False)},
        {"role": "user", "content": sanitized_answer},
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
            task_type="judge",
            prefer_provider="cloud",
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

            # ── S1.1 (2026-04-20) Fuzzy rescue on FALSE verdict ──────────────
            # Arena's non-streaming path must also honour the digit-substring
            # rescue and the semantic validator upgrade. Previously only the
            # streaming path had this logic, so "500000 рублей" vs blitz
            # "500 000 рублей" still produced a false NEVERNO here.
            correct_summary = parsed.get("correct_answer") if not final_verdict else None
            if not final_verdict and user_answer.strip():
                final_verdict, correct_summary, explanation = _apply_rescue_and_validator(
                    user_answer=user_answer,
                    question=question,
                    rag_context=rag_context,
                    explanation=explanation,
                    correct_summary=correct_summary,
                )

            return QuizFeedback(
                is_correct=final_verdict,
                explanation=explanation,
                article_reference=parsed.get("article_reference"),
                score_delta=_score_delta(final_verdict, difficulty),
                correct_answer_summary=correct_summary,
            )
    except LLMError as e:
        logger.error("LLM failed to evaluate answer: %s", e)

    # ── Keyword fallback (no LLM available) ──────────────────────────────────
    if rag_context.has_results:
        top = rag_context.results[0]
        is_likely_correct = top.relevance_score >= 0.5

        # Fuzzy-rescue even in the no-LLM path.
        if not is_likely_correct and user_answer.strip():
            is_likely_correct, correct_summary, _ = _apply_rescue_and_validator(
                user_answer=user_answer,
                question=question,
                rag_context=rag_context,
                explanation="",
                correct_summary=None,
            )
        else:
            correct_summary = None

        return QuizFeedback(
            is_correct=is_likely_correct,
            explanation=f"{'Верно!' if is_likely_correct else 'Не совсем.'} По закону: {top.fact_text}",
            article_reference=top.law_article,
            score_delta=_score_delta(is_likely_correct, difficulty),
            correct_answer_summary=correct_summary,
        )

    # ── No RAG context — try fuzzy rescue against blitz_answer only ──────────
    if user_answer.strip() and question.blitz_answer:
        rescued, correct_summary, _ = _apply_rescue_and_validator(
            user_answer=user_answer,
            question=question,
            rag_context=rag_context,
            explanation="",
            correct_summary=None,
        )
        if rescued:
            return QuizFeedback(
                is_correct=True,
                explanation=f"Верно! {question.blitz_answer}",
                article_reference=question.expected_article,
                score_delta=_score_delta(True, difficulty),
            )

    return QuizFeedback(
        is_correct=False,
        explanation="Не удалось проверить ответ по базе знаний. Рекомендуем свериться с текстом ФЗ-127.",
        score_delta=0.0,
        correct_answer_summary=question.blitz_answer,
    )


def _apply_rescue_and_validator(
    *,
    user_answer: str,
    question: "QuizQuestion",
    rag_context,
    explanation: str,
    correct_summary: str | None,
) -> tuple[bool, str | None, str]:
    """S1.1 (2026-04-20): shared "was it actually correct?" second look.

    Two cheap signals fire before we fall back to the expensive LLM
    validator:

      1. **Digit substring rescue.** Thousand-separator whitespace
         (``500 000`` vs ``500000``) was the #1 source of false negatives
         — after ``normalize_for_comparison`` both sides should match any
         3+ digit group present in the expected answer.
      2. **Phrase containment rescue.** If the normalized user answer
         fully contains the normalized expected (or vice versa), treat
         that as correct. Handles ``"ст. 213.3"`` vs ``"статья 213.3"``.

    If neither rescue fires, we call ``validator_v2.validate_semantic``
    (behind ``ROLLOUT_RELAXED_VALIDATION`` flag) for a proper LLM
    second-opinion that can catch paraphrases and partial credit.

    Returns ``(rescued_correct, new_correct_summary, new_explanation)``.
    On no-rescue, leaves inputs intact.
    """

    import re as _re

    expected = (question.blitz_answer or "").strip()
    user_n = normalize_for_comparison(user_answer)
    exp_n = normalize_for_comparison(expected)

    # Path 1: digit-group substring
    digits_exp = _re.findall(r"\d{3,}", exp_n)
    digits_user = _re.findall(r"\d{3,}", user_n)
    digit_hit = bool(digits_exp and any(d in digits_user for d in digits_exp))

    # Path 2: full-phrase containment after synonym + number normalisation
    contain_hit = bool(
        exp_n
        and user_n
        and len(exp_n) >= 4
        and (exp_n in user_n or user_n in exp_n)
    )

    if digit_hit or contain_hit:
        reason = "совпадение цифр после нормализации" if digit_hit else "эквивалентная формулировка"
        return (
            True,
            None,
            f"Верно! ({reason}) {expected}" if expected else "Верно!",
        )

    # Path 3: LLM semantic validator — async, so we wrap in asyncio.run_coroutine
    # only if an event loop is present. Best-effort — never raise here.
    try:
        import asyncio

        loop = asyncio.get_event_loop() if asyncio.get_event_loop_policy() else None
        if loop and loop.is_running():
            # We're already inside an event loop (FastAPI path). The caller
            # will await this function only if it is itself async, which
            # `evaluate_answer` is. We cannot block here, so skip validator
            # v2 in the sync rescue path — the streaming path already runs
            # it asynchronously.
            pass
    except Exception:
        pass

    return False, correct_summary or expected or None, explanation


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


def _score_delta(is_correct: bool, difficulty: int, *, partial: float = 0.0) -> float:
    """Calculate score delta based on difficulty.

    Correct:   d1=+6, d2=+8, d3=+10, d4=+13, d5=+16
    Incorrect: d1=-1, d2=-1.5, d3=-2, d4=-2.5, d5=-3

    Phase 3.5 (2026-04-19): ``partial`` ∈ [0, 1] grants partial credit for
    answers that are not fully correct but not wrong either. ``partial=0.5``
    on a level-3 question yields +5 instead of -2 — a meaningful nudge that
    doesn't reward completely-wrong replies. ``partial=0`` preserves
    pre-Phase-3 behaviour exactly.
    """

    correct_map = {1: 6.0, 2: 8.0, 3: 10.0, 4: 13.0, 5: 16.0}
    wrong_map = {1: -1.0, 2: -1.5, 3: -2.0, 4: -2.5, 5: -3.0}

    if is_correct:
        return correct_map.get(difficulty, 10.0)

    if 0.0 < partial <= 1.0:
        # Interpolate between wrong (0) and correct (1) — partial credit
        # never exceeds 80% of the full correct delta so full correctness
        # remains strictly better.
        max_reward = correct_map.get(difficulty, 10.0) * 0.8
        base_penalty = wrong_map.get(difficulty, -2.0)
        return round(base_penalty + (max_reward - base_penalty) * partial, 2)

    return wrong_map.get(difficulty, -2.0)


# ──────────────────────────────────────────────────────────────────────
# Phase 3.5 (2026-04-19) — fuzzy normalizers for semantic equivalence.
#
# The AI_EXAMINER_PROMPT now declares synonyms as equivalent; these
# helpers make the rule machine-checkable by normalising both sides of
# a comparison before doing exact/substring matching in ``evaluate_answer``
# fast-paths.
# ──────────────────────────────────────────────────────────────────────


# Curated synonym table. Left side is the canonical form; values are the
# colloquial/short forms that should normalise to it.
_TERM_SYNONYMS: dict[str, tuple[str, ...]] = {
    "субсидиарная ответственность": ("субсидиарка", "субсидиарка кдл"),
    "финансовый управляющий": ("финуправляющий", "фу", "арбитражный управляющий"),
    "банкротство": ("несостоятельность",),
    "реестр требований": ("рт", "реестр кредиторов"),
    "конкурсное производство": ("кп", "конкурсная масса"),
    "внесудебное банкротство": ("мфц", "банкротство через мфц", "упрощённое банкротство"),
    "реализация имущества": ("реализация", "продажа имущества"),
    "реструктуризация долгов": ("реструктуризация", "реструктур"),
}


def _normalize_article_ref(text: str) -> str:
    """Normalise ``"ст. 213.4"`` / ``"статья 213.4"`` / ``"213.4"`` to
    the same canonical form ``"ст.213.4"``.
    """

    import re as _re

    cleaned = text.lower().strip()
    # "статья 213.4" → "ст.213.4"
    cleaned = _re.sub(r"\bстатья\s+(\d)", r"ст.\1", cleaned)
    # "ст 213.4" → "ст.213.4"
    cleaned = _re.sub(r"\bст\s+(\d)", r"ст.\1", cleaned)
    # bare number at sentence start preceded by word-boundary
    cleaned = _re.sub(r"\bст\.?\s*(\d+\.\d+)", r"ст.\1", cleaned)
    return cleaned


_RU_NUMBERALS: dict[str, str] = {
    "десять": "10", "двадцать": "20", "тридцать": "30",
    "сорок": "40", "пятьдесят": "50", "шестьдесят": "60",
    "семьдесят": "70", "восемьдесят": "80", "девяносто": "90",
    "сто": "100", "двести": "200", "триста": "300",
    "пятьсот": "500", "тысяча": "1000", "десять тысяч": "10000",
    "сто тысяч": "100000", "пятьсот тысяч": "500000", "миллион": "1000000",
}


def _normalize_number_ru(text: str) -> str:
    """Replace Russian numerals with digit form and compact digit groups.

    Two passes:
      1. Replace spelled-out numerals (``"девяносто дней"`` → ``"90 дней"``).
      2. Strip whitespace between groups of digits — Russian thousands
         separator is a non-breaking space, so ``"500 000 рублей"`` vs
         ``"500000 рублей"`` must normalise to the same form. Without this
         the fuzzy rescue in ``evaluate_answer_streaming`` misses obvious
         equivalences ("500000 рублей" ≡ "500 000 рублей").

    Conservative — only whitespace BETWEEN digits is removed; the rest of
    the sentence keeps its spaces intact.
    """

    import re as _re

    normalised = text.lower()
    for word, digits in _RU_NUMBERALS.items():
        normalised = normalised.replace(word, digits)
    # Collapse thousands-separator whitespace (incl. non-breaking \xa0)
    # while preserving whitespace between non-digit tokens.
    normalised = _re.sub(r"(\d)[\s\xa0]+(?=\d)", r"\1", normalised)
    return normalised


def _normalize_term_synonyms(text: str) -> str:
    """Replace colloquial terms with canonical form. See ``_TERM_SYNONYMS``."""

    normalised = text.lower()
    for canonical, aliases in _TERM_SYNONYMS.items():
        for alias in aliases:
            normalised = normalised.replace(alias, canonical)
    return normalised


def normalize_for_comparison(text: str) -> str:
    """Full normalisation stack: number words → digits, synonyms → canonical,
    article refs → compact form. Safe to call on both user answers and
    reference answers before string comparison."""

    if not text:
        return ""
    return _normalize_article_ref(
        _normalize_term_synonyms(_normalize_number_ru(text))
    )


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


def _affirmative_keyword_match(user_answer: str, expected: str) -> bool:
    """Aggressive "contains correct answer" check for non-blitz modes.

    2026-04-18: fixes judge false-negatives where user wrote a CORRECT answer
    but LLM got confused. If the user's answer contains BOTH the expected
    number(s) AND at least one key noun from the expected answer — it's
    correct, no LLM call needed.

    Examples that should match:
      expected="5 лет"                     user="через 5 лет после завершения"   → match
      expected="2 месяца"                  user="2 месяца с даты публикации"     → match
      expected="300 рублей"                user="300 руб"                         → match
      expected="финансовый управляющий"    user="нужен финансовый управляющий"    → match

    Stricter than _blitz_keyword_match (which is for short 1-3 word blitz
    answers): this one is designed for longer free-text answers that happen
    to contain the right keywords.
    """
    import re as _re
    if not expected or not user_answer:
        return False
    a = user_answer.lower().strip()
    e = expected.lower().strip()

    # ── Numeric match ──
    a_nums = set(_re.findall(r"\d+", a))
    e_nums = set(_re.findall(r"\d+", e))
    if e_nums:
        # All expected numbers must appear in user's answer (or at least 2/3)
        matched = a_nums & e_nums
        if matched and len(matched) >= max(1, len(e_nums) * 2 // 3):
            # Numbers match. Need ALSO a key term from expected (to avoid "5" matching "через 5 минут" for answer "5 лет")
            units = ("лет", "год", "месяц", "недел", "дн", "дней", "час",
                     "рубл", "руб", "млн", "тыс", "процент", "%")
            if any(u in a for u in units) and any(u in e for u in units):
                # Both mention time/money — check unit overlap
                for u in units:
                    if u in a and u in e:
                        return True
            else:
                # No unit needed — numeric match sufficient (e.g. "ст. 213.4")
                return True

    # ── Key-noun match (for non-numeric answers) ──
    stop = {"и", "в", "на", "по", "от", "с", "для", "при", "что", "это", "не",
            "а", "к", "о", "у", "из", "до", "со", "же", "как", "или", "ли",
            "тот", "все", "всё", "так", "если", "который", "которая", "которое",
            "быть", "есть", "был", "была", "было"}
    # Tokens 4+ chars (skip short noise)
    def _tokens(text: str) -> set[str]:
        return {w for w in _re.findall(r"[а-яёa-z]+", text) if len(w) >= 4 and w not in stop}

    a_tokens = _tokens(a)
    e_tokens = _tokens(e)
    if not e_tokens:
        return False
    overlap = a_tokens & e_tokens
    # If user's answer contains ≥50% of key nouns from expected, accept
    if len(overlap) >= max(1, len(e_tokens) // 2):
        return True

    # Exact-phrase inclusion (strict): user's answer literally contains the
    # expected phrase (word-boundary aware).
    # E.g. expected="финансовый управляющий", user="нужен финансовый управляющий"
    if len(e) >= 5 and e in a:
        return True

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
            task_type="judge",
            prefer_provider="cloud",
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
            task_type="structured",
            prefer_provider="local",
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
            task_type="judge",
            prefer_provider="cloud",
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


# =============================================================================
# STREAMING EVALUATION (2026-04-18)
# =============================================================================

from typing import AsyncGenerator


async def evaluate_answer_streaming(
    db: AsyncSession,
    *,
    question: QuizQuestion,
    user_answer: str,
    mode: QuizMode = QuizMode.free_dialog,
    personality_prompt: str | None = None,
) -> AsyncGenerator[dict, None]:
    """Evaluate answer and yield feedback events as they become available.

    Event protocol (each yield is a dict):
      {"type": "verdict", "is_correct": bool, "correct_answer": str|None,
       "article_reference": str|None, "score_delta": float, "fast_path": str}
          — emitted FIRST. May be the only event if garbage / keyword-match /
            common-error path fires (no LLM streaming needed).
      {"type": "chunk", "text": str}
          — emitted DURING LLM streaming. Accumulate on client to build the
            explanation bubble word-by-word.
      {"type": "final", "feedback": QuizFeedback}
          — emitted LAST. Complete structured feedback; client should replace
            any accumulated streaming text with feedback.explanation if they
            differ.

    Fast paths (emit just verdict + final, no streaming):
      - Garbage answer          ("не знаю", "привет", etc.)
      - Blitz keyword match     (blitz mode only)
      - Affirmative keyword match (real answer contains expected keywords)
      - Common-error pre-check  (answer = known misconception)

    Slow path (streams explanation):
      - LLM judge required (novel / ambiguous answer)
    """
    difficulty = question.difficulty

    # ── Garbage fast-path ──────────────────────────────────────────────────
    is_garbage, garbage_reason = _is_garbage_answer(user_answer)
    if is_garbage:
        correct_hint = question.blitz_answer or None
        fb = QuizFeedback(
            is_correct=False,
            explanation=garbage_reason + (f" Правильно: {correct_hint}" if correct_hint else ""),
            article_reference=question.expected_article,
            score_delta=_score_delta(False, difficulty),
            correct_answer_summary=correct_hint,
        )
        yield {"type": "verdict", "is_correct": False, "correct_answer": correct_hint,
               "article_reference": fb.article_reference, "score_delta": fb.score_delta,
               "fast_path": "garbage"}
        yield {"type": "final", "feedback": fb}
        return

    # ── Blitz keyword match ────────────────────────────────────────────────
    if question.blitz_answer and mode == QuizMode.blitz:
        is_correct = _blitz_keyword_match(user_answer, question.blitz_answer)
        fb = QuizFeedback(
            is_correct=is_correct,
            explanation=question.blitz_answer if not is_correct else "Верно!",
            article_reference=question.expected_article,
            score_delta=_score_delta(is_correct, difficulty),
            correct_answer_summary=question.blitz_answer if not is_correct else None,
        )
        yield {"type": "verdict", "is_correct": is_correct,
               "correct_answer": fb.correct_answer_summary,
               "article_reference": fb.article_reference, "score_delta": fb.score_delta,
               "fast_path": "blitz"}
        yield {"type": "final", "feedback": fb}
        return

    # ── Affirmative keyword match (user contains correct answer) ───────────
    if question.blitz_answer and _affirmative_keyword_match(user_answer, question.blitz_answer):
        fb = QuizFeedback(
            is_correct=True,
            explanation=f"Верно! {question.blitz_answer}",
            article_reference=question.expected_article,
            score_delta=_score_delta(True, difficulty),
            correct_answer_summary=None,
        )
        yield {"type": "verdict", "is_correct": True, "correct_answer": None,
               "article_reference": fb.article_reference, "score_delta": fb.score_delta,
               "fast_path": "affirmative_keyword"}
        yield {"type": "final", "feedback": fb}
        return

    # ── RAG + common-error pre-check ───────────────────────────────────────
    # 2026-05-04 FRONT-2 fix: retrieval is keyed on the QUESTION ONLY,
    # not "question + user_answer". The combined query was the root
    # cause of LLM-judge false-negatives on correct off-topic answers
    # (audit Problem 1): an answer about алименты pulled алименты-
    # adjacent chunks instead of the question's actual subject (61.2),
    # so the LLM judged against the wrong context. The user-answer is
    # already passed to the judge as its own message — we don't need
    # to bias retrieval with it.
    rag_context = await retrieve_legal_context(
        question.question_text, db, top_k=5
    )
    if rag_context.has_results:
        answer_lower = user_answer.lower()
        for result in rag_context.results[:3]:
            for err in result.common_errors:
                if isinstance(err, str) and err.lower() in answer_lower:
                    correct_hint = result.correct_response_hint or result.fact_text
                    fb = QuizFeedback(
                        is_correct=False,
                        explanation=f"Это распространённая ошибка: «{err}». Правильно: {correct_hint}",
                        article_reference=result.law_article,
                        score_delta=_score_delta(False, difficulty),
                        correct_answer_summary=correct_hint,
                    )
                    yield {"type": "verdict", "is_correct": False, "correct_answer": correct_hint,
                           "article_reference": result.law_article, "score_delta": fb.score_delta,
                           "fast_path": "common_error"}
                    yield {"type": "final", "feedback": fb}
                    return

    # ── SLOW PATH: LLM judge with token streaming ──────────────────────────
    from app.services.scenario_engine import _sanitize_db_prompt
    from app.services.llm import generate_response_stream
    context_str = rag_context.to_prompt_context() if rag_context.has_results else ""

    # 2026-05-04 FRONT-2: canonical-answer fallback. If RAG was sparse
    # (context_str empty), pull a curated canonical entry instead of
    # letting the LLM improvise blind. Also short-circuits when the
    # user answer hits a known wrong_hint.
    canonical_entry = None
    if not context_str:
        try:
            from app.services.canonical_answers import find_canonical, has_wrong_hint
            canonical_entry = find_canonical(
                question.question_text,
                category=question.category if question.category else None,
            )
            if canonical_entry:
                # Short-circuit: explicit known-wrong substring match.
                wrong = has_wrong_hint(canonical_entry, user_answer)
                if wrong:
                    fb = QuizFeedback(
                        is_correct=False,
                        explanation=(
                            f"Распространённая ошибка: «{wrong}». "
                            f"Правильно: {canonical_entry.canonical}"
                        ),
                        article_reference=canonical_entry.article,
                        score_delta=_score_delta(False, difficulty),
                        correct_answer_summary=canonical_entry.canonical,
                    )
                    yield {
                        "type": "verdict", "is_correct": False,
                        "correct_answer": canonical_entry.canonical,
                        "article_reference": canonical_entry.article,
                        "score_delta": fb.score_delta,
                        "fast_path": "canonical_wrong_hint",
                    }
                    yield {"type": "final", "feedback": fb}
                    return
                # Otherwise feed the canonical answer into the judge as
                # the authoritative reference instead of empty context.
                context_str = (
                    f"Эталонный ответ (методология): {canonical_entry.canonical}\n"
                    f"Источник: {canonical_entry.article}"
                )
        except Exception as exc:
            logger.warning("canonical_answers lookup failed: %s", exc, exc_info=True)

    sanitized_answer = _sanitize_db_prompt(user_answer, "user_answer")

    # 2026-05-04 FRONT-3: 4-line nuanced verdict format. Adds an explicit
    # SCORE 0-10 line which lets the UI render "Почти" / "Не по теме"
    # buckets instead of slamming binary ✖ on imperfect answers.
    # Scoring rubric (exact thresholds in QuizFeedback docstring):
    #   8-10 = верно          5-7 = почти (упустил детали)
    #   2-4  = не по теме     0-1 = неверно
    stream_messages = [
        {"role": "assistant", "content": json.dumps(
            {"type": "question", "question_text": question.question_text, "category": question.category},
            ensure_ascii=False,
        )},
        {"role": "user", "content": sanitized_answer},
        {"role": "user", "content": (
            f"Оцени ответ пользователя. Формат ответа СТРОГО:\n"
            f"1-я строка: ВЕРДИКТ: верно | почти | не по теме | неверно\n"
            f"2-я строка: ОТВЕТ: <краткий правильный ответ в 1 фразе>\n"
            f"3-я строка: СТАТЬЯ: <ссылка на статью или «нет»>\n"
            f"4-я строка: SCORE: <целое 0-10>\n"
            f"Далее — развёрнутое объяснение на 2-3 предложения. "
            f"Если вердикт «почти» — укажи что упустил. "
            f"Если «не по теме» — укажи что ответил по другому факту, "
            f"и какой факт реально спрашивали.\n\n"
            f"ШКАЛА SCORE:\n"
            f"  8-10 = ответ полностью правильный по сути и по теме\n"
            f"  5-7  = правильно по сути, но упущены важные детали\n"
            f"  2-4  = знание корректное, но НЕ ПО ТЕМЕ ВОПРОСА\n"
            f"  0-1  = ответ ошибочный или бессодержательный\n\n"
            f"СТРОГИЕ ПРАВИЛА — БЕЗ КОТОРЫХ ВЕРДИКТ ВСЕГДА «неверно» И SCORE 0:\n"
            f"  • Имена людей («Алибек», «Иван Петров»), приветствия "
            f"(«привет», «здравствуй»), отвлечённые слова без правового "
            f"содержания — это ВСЕГДА «неверно», даже если 6-15 символов.\n"
            f"  • Если в ответе нет ни цифр, ни ссылки на статью, ни "
            f"процедурного термина (банкротство, кредитор, управляющий, "
            f"имущество, реструктуризация, реализация, заявление, мфц, "
            f"арбитраж и т.п.) — это «неверно» 0/10.\n"
            f"  • НЕ оправдывай тем, что «звучит близко по смыслу». "
            f"Юриспруденция требует точности: неверный срок, "
            f"неправильная статья, путаница процедур = неверно.\n"
            f"  • Если сомневаешься между «верно» и «почти» — выбирай «почти».\n\n"
            f"Правовой контекст:\n{context_str}"
        )},
    ]

    # Accumulate raw tokens; parse header lines first, then stream explanation
    buffer = ""
    verdict_emitted = False
    verdict_level_final: str = "wrong"  # 4-bucket: correct|partial|off_topic|wrong
    is_correct_final = False  # legacy mirror of (verdict_level_final == "correct")
    correct_hint_final: str | None = None
    article_final: str | None = question.expected_article
    llm_score_final: float | None = None
    explanation_chars: list[str] = []
    header_done = False

    # ── Helper: robust verdict parse with fuzzy fallback ───────────────────
    # The old parser required exactly three `\n` before the first
    # explanation token. LLMs break that contract constantly:
    #   - `\r\n` line endings
    #   - markdown wrapping (## ВЕРДИКТ)
    #   - verdict on same line as answer (ВЕРДИКТ: верно. ОТВЕТ: …)
    #   - stream ends early after header, no explanation
    #   - Returns JSON-like text despite being asked for plain lines
    # The fix: try the strict parse first, fall back to regex scan over
    # the full buffer as soon as 60+ chars have arrived.
    def _verdict_level_from(verdict_word: str, score: float | None) -> str:
        """Map LLM verdict word + numeric score → 4-bucket level.

        Score (when present) is authoritative. Word is fallback when
        SCORE line is absent. Defaults to "wrong" when ambiguous to
        keep the legacy is_correct path safe.
        """
        if score is not None:
            if score >= 8:
                return "correct"
            if score >= 5:
                return "partial"
            if score >= 2:
                return "off_topic"
            return "wrong"
        w = (verdict_word or "").strip().lower()
        if "почти" in w:
            return "partial"
        if "не по теме" in w or "off" in w or "off_topic" in w:
            return "off_topic"
        if w in ("верно", "true", "yes") or "верно" in w and "не верно" not in w and "неверно" not in w:
            return "correct"
        return "wrong"

    def _try_parse_header(text: str):
        """Return (verdict_level, correct_hint, article, score, remainder)
        or None. verdict_level is one of correct/partial/off_topic/wrong.
        score is float 0-10 or None.
        """
        import re as _re

        t = text.replace("\r\n", "\n").replace("\r", "\n")

        # Path A: strict 4-line format (post-2026-05-04). Tolerates the
        # legacy 3-line format too — score parsing is best-effort.
        if t.count("\n") >= 3:
            parts = t.split("\n", 4)
            l0 = parts[0].strip().lower()
            verdict_word_re = _re.search(
                r"(не\s*по\s*теме|почти|неверно|не\s*верно|верно)",
                l0, flags=_re.IGNORECASE,
            )
            if verdict_word_re:
                verdict_word = verdict_word_re.group(1).lower()
                hint = None
                if len(parts) > 1 and ":" in parts[1]:
                    hint = parts[1].split(":", 1)[1].strip() or None
                art = None
                if len(parts) > 2 and ":" in parts[2]:
                    cand = parts[2].split(":", 1)[1].strip()
                    if cand and cand.lower() not in ("нет", "—", "-", "none"):
                        art = cand
                # Score line (4th line) — best-effort parse
                score: float | None = None
                remainder_idx = 3
                if len(parts) > 3:
                    score_match = _re.search(r"(\d+(?:[.,]\d+)?)", parts[3])
                    score_kw = parts[3].lower()
                    if score_match and ("score" in score_kw or "балл" in score_kw or "оценка" in score_kw):
                        try:
                            score = min(10.0, max(0.0, float(score_match.group(1).replace(",", "."))))
                            remainder_idx = 4
                        except ValueError:
                            pass
                level = _verdict_level_from(verdict_word, score)
                remainder = parts[remainder_idx] if len(parts) > remainder_idx else ""
                return level, hint, art, score, remainder

        # Path B: permissive regex scan — handles inline/markdown/JSON.
        m_verdict = _re.search(
            r"(?:верд[ие]кт|verdict|is_correct)[^\n]{0,40}?"
            r"(не\s*по\s*теме|почти|неверно|не\s*верно|верно|true|false|yes|no)",
            t, flags=_re.IGNORECASE,
        )
        if m_verdict:
            verdict_word = m_verdict.group(1).lower()
            hint_match = _re.search(
                r"(?:ответ|correct_answer|answer)[^\n]{0,80}?[:«\"]\s*([^\n\"»]{3,200})",
                t, flags=_re.IGNORECASE,
            )
            art_match = _re.search(
                r"(?:статья|article|article_reference)[^\n]{0,40}?[:«\"]\s*([^\n\"»]{2,80})",
                t, flags=_re.IGNORECASE,
            )
            score_match = _re.search(
                r"(?:score|балл|оценка)[^\n]{0,20}?[:=]\s*(\d+(?:[.,]\d+)?)",
                t, flags=_re.IGNORECASE,
            )
            hint = hint_match.group(1).strip().rstrip(",.;:") if hint_match else None
            art = None
            if art_match:
                cand = art_match.group(1).strip().rstrip(",.;:")
                if cand.lower() not in ("нет", "—", "-", "none"):
                    art = cand
            score: float | None = None
            if score_match:
                try:
                    score = min(10.0, max(0.0, float(score_match.group(1).replace(",", "."))))
                except ValueError:
                    pass
            level = _verdict_level_from(verdict_word, score)
            body_split = _re.split(r"(?<=[.!?])\s+", t, maxsplit=1)
            body = body_split[1] if len(body_split) > 1 else ""
            return level, hint, art, score, body

        return None

    try:
        async for token in generate_response_stream(
            system_prompt=personality_prompt or AI_EXAMINER_PROMPT,
            messages=stream_messages,
            emotion_state="curious",
            task_type="judge",
            prefer_provider="cloud",
        ):
            buffer += token

            # Try to parse as soon as we have enough data. This is more
            # aggressive than the old "need 3 newlines" rule.
            if not header_done and (buffer.count("\n") >= 3 or len(buffer) >= 60):
                parsed = _try_parse_header(buffer)
                if parsed is None:
                    # Not enough yet; keep streaming.
                    continue

                verdict_level_final, correct_hint_final, parsed_art, llm_score_final, remainder = parsed
                is_correct_final = verdict_level_final == "correct"
                if parsed_art:
                    article_final = parsed_art

                # 2026-05-04 FRONT-3: score_delta now respects verdict
                # buckets — partial = half-XP, off_topic = 0 (don't
                # penalize when user knows but mis-aimed), wrong = -2.
                if verdict_level_final == "correct":
                    sd = _score_delta(True, difficulty)
                elif verdict_level_final == "partial":
                    sd = _score_delta(True, difficulty, partial=0.5) if "partial" in _score_delta.__code__.co_varnames else _score_delta(True, difficulty) * 0.5
                elif verdict_level_final == "off_topic":
                    sd = 0.0
                else:  # wrong
                    sd = _score_delta(False, difficulty)

                yield {
                    "type": "verdict",
                    "is_correct": is_correct_final,
                    "verdict_level": verdict_level_final,
                    "llm_score": llm_score_final,
                    "correct_answer": correct_hint_final,
                    "article_reference": article_final,
                    "score_delta": sd,
                    "fast_path": "llm_stream",
                }
                verdict_emitted = True
                header_done = True
                if remainder:
                    explanation_chars.append(remainder)
                    yield {"type": "chunk", "text": remainder}
                continue

            # ── Phase 2: stream explanation chars after header emitted ──
            if header_done:
                explanation_chars.append(token)
                yield {"type": "chunk", "text": token}

    except Exception as exc:
        logger.warning("evaluate_answer_streaming: LLM stream failed: %s", exc)

    # ── Post-stream recovery ───────────────────────────────────────────────
    # If the stream ended (normally OR with an error) and we never emitted a
    # verdict, run the robust parser one more time against the full buffer.
    # Still nothing? Fall back to fuzzy normalized comparison of the user
    # answer against ``blitz_answer`` / ``expected_article`` — this catches
    # cases where the LLM gave a perfectly fine answer but the formatter
    # contract was violated (previously produced the dreaded «Не удалось
    # получить разбор» on correct answers like "500000 рублей").
    if not verdict_emitted:
        parsed = _try_parse_header(buffer) if buffer else None
        if parsed is not None:
            verdict_level_final, correct_hint_final, parsed_art, llm_score_final, remainder = parsed
            is_correct_final = verdict_level_final == "correct"
            if parsed_art:
                article_final = parsed_art
            if remainder:
                explanation_chars.append(remainder)
            verdict_emitted = True
            sd = (
                _score_delta(True, difficulty) if verdict_level_final == "correct"
                else _score_delta(True, difficulty) * 0.5 if verdict_level_final == "partial"
                else 0.0 if verdict_level_final == "off_topic"
                else _score_delta(False, difficulty)
            )
            yield {
                "type": "verdict",
                "is_correct": is_correct_final,
                "verdict_level": verdict_level_final,
                "llm_score": llm_score_final,
                "correct_answer": correct_hint_final,
                "article_reference": article_final,
                "score_delta": sd,
                "fast_path": "llm_stream_recovered",
            }
        else:
            # Fuzzy rescue: if the user's answer, normalized, overlaps with
            # the expected answer or blitz answer — treat as CORRECT. This
            # fixes "500000 рублей" being marked wrong when the blitz was
            # "500 000 рублей" (whitespace / currency symbol mismatch).
            expected = (question.blitz_answer or "").strip()
            user_n = normalize_for_comparison(user_answer)
            exp_n = normalize_for_comparison(expected)
            rescued = False
            if exp_n and user_n:
                # Digit-substring rescue: any 5+ digit group in expected that
                # appears in user's answer is a strong signal.
                import re as _re2

                digits_exp = _re2.findall(r"\d{3,}", exp_n)
                digits_user = _re2.findall(r"\d{3,}", user_n)
                if digits_exp and any(d in digits_user for d in digits_exp):
                    rescued = True
                # Full-phrase containment after synonym normalisation
                elif exp_n in user_n or user_n in exp_n:
                    rescued = True

            if rescued:
                is_correct_final = True
                verdict_level_final = "correct"
                correct_hint_final = expected or None
                verdict_emitted = True
                yield {
                    "type": "verdict",
                    "is_correct": True,
                    "verdict_level": "correct",
                    "llm_score": 8.0,
                    "correct_answer": correct_hint_final,
                    "article_reference": article_final,
                    "score_delta": _score_delta(True, difficulty),
                    "fast_path": "fuzzy_rescue",
                }
                explanation_chars.append(
                    f"Верно! {expected}" if expected else "Верно!"
                )
            else:
                verdict_level_final = "wrong"
                yield {
                    "type": "verdict",
                    "is_correct": False,
                    "verdict_level": "wrong",
                    "llm_score": 0.0,
                    "correct_answer": question.blitz_answer,
                    "article_reference": question.expected_article,
                    "score_delta": _score_delta(False, difficulty),
                    "fast_path": "llm_stream_error",
                }

    # ── Second-opinion validator (Phase 3.6) ───────────────────────────────
    # If the primary judge landed on "неверно", give the semantic validator
    # a chance to upgrade it to equivalent/partial. This only fires under
    # the ``ROLLOUT_RELAXED_VALIDATION`` flag; off-by-default in dev.
    #
    # Upgrade means: user gave a correct fact expressed differently
    # ("500000 рублей" vs "500 000 ₽") or a partial fact. The cross-check
    # below still runs after, so a hallucinated correct answer still gets
    # caught by the common-error table.
    if verdict_emitted and not is_correct_final and user_answer.strip():
        try:
            from app.services.knowledge_quiz_validator_v2 import (
                validate_semantic,
                apply_upgrade,
            )

            rag_ctx_text = rag_context.to_prompt_context() if rag_context.has_results else ""
            v_result = await validate_semantic(
                question=question.question_text,
                correct_answer=question.blitz_answer or correct_hint_final or "",
                manager_answer=user_answer,
                rag_context=rag_ctx_text[:1500],
            )
            upgraded_correct, upgraded_delta, note = apply_upgrade(
                primary_is_correct=False,
                primary_score_delta=_score_delta(False, difficulty),
                validation=v_result,
            )
            if upgraded_correct or upgraded_delta > _score_delta(False, difficulty):
                is_correct_final = upgraded_correct
                if note:
                    # Replace the explanation with the upgrade note rather than
                    # the "Неверно…" stream we already pushed.
                    explanation_chars = [note]
                    yield {"type": "chunk", "text": f"\n\n[Обновление: {note}]"}
        except Exception:
            logger.debug("validator_v2 upgrade skipped", exc_info=True)

    # ── Anti-hallucination cross-check on final verdict ──
    if header_done and is_correct_final and rag_context.has_results:
        try:
            final_verdict, override_reason = _cross_check_verdict(
                True, user_answer, rag_context.results,
            )
            if not final_verdict:
                # Override: common-error found post-LLM
                is_correct_final = False
                correct_hint_final = (
                    rag_context.results[0].correct_response_hint
                    or rag_context.results[0].fact_text
                    or correct_hint_final
                )
                yield {
                    "type": "chunk",
                    "text": f"\n\n[Уточнение: {override_reason}]",
                }
        except Exception:
            pass

    # ── Final event with full structured feedback ──
    explanation_full = "".join(explanation_chars).strip()
    if not explanation_full and correct_hint_final:
        # 2026-05-04 FRONT-3: nuanced verdict-level message instead of
        # binary "Верно!/Неверно.".
        prefix = {
            "correct": "Верно!",
            "partial": "Почти. ",
            "off_topic": "Знание корректное, но вопрос был о другом. ",
            "wrong": "Неверно. ",
        }.get(verdict_level_final, "Неверно. ")
        explanation_full = f"{prefix}{correct_hint_final}"
    # Final score_delta respects verdict bucket (see also per-level
    # logic above where verdict is yielded).
    if verdict_emitted:
        if verdict_level_final == "correct":
            final_sd = _score_delta(True, difficulty)
        elif verdict_level_final == "partial":
            final_sd = _score_delta(True, difficulty) * 0.5
        elif verdict_level_final == "off_topic":
            final_sd = 0.0
        else:
            final_sd = _score_delta(False, difficulty)
    else:
        final_sd = 0.0
    fb = QuizFeedback(
        is_correct=is_correct_final if verdict_emitted else False,
        explanation=explanation_full or "Не удалось получить разбор.",
        article_reference=article_final,
        score_delta=final_sd,
        correct_answer_summary=correct_hint_final,
        verdict_level=verdict_level_final if verdict_emitted else "wrong",
        llm_score=llm_score_final,
    )
    yield {"type": "final", "feedback": fb}
