"""Morning Drill v2 — sequence of 3-5 micro-questions as a quick warm-up.

Replaces the chat-style DailyDrill UX on /home with a "quiz-like" sequence
where each question stands alone. User reads → answers in one short text
reply → moves to next. Total flow ≤ 1 minute.

2026-04-20 changes:
  * `POST /morning-drill/complete` — atomically persists the finished run
    so `daily_goals.py:daily_warmup` can count it.
  * `AnswerFeedback` now returns `law_article`, `why_it_matters` and
    `source_excerpt` so the UI can show a collapsible "почему так" block
    instead of a bare one-line hint (пользователи жаловались: «эталон без
    объяснения»).
  * Heuristic is otherwise unchanged — LLM grader is tracked separately.

Intentionally ISOLATED from `daily_drill.py` (which powers the old chat
drill with full LLM turn-taking + streak + XP). Keeping both live means we
don't break the streak/XP system while rolling out the new surface.
"""

from __future__ import annotations

import logging
import random
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models.morning_drill import MorningDrillSession
from app.models.progress import StreakFreeze
from app.models.rag import LegalKnowledgeChunk
from app.models.user import User
from app.utils.local_time import local_now, local_today

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/morning-drill", tags=["morning-drill"])


# ── Schemas ──────────────────────────────────────────────────────────────


class MorningQuestion(BaseModel):
    id: str                      # stable id for client-side iteration
    kind: str                    # "legal" | "sales"
    prompt: str                  # question text shown to user
    context: str | None = None   # optional short context under prompt
    hint: str | None = None      # one-line hint for the expected answer
    law_article: str | None = None   # for legal questions — reference article
    category: str | None = None      # eligibility / procedure / closing / …
    # 2026-04-20: multiple-choice mode. If `choices` is non-empty the UI
    # renders radio buttons instead of a textarea. `correct_choice_index`
    # is NOT sent to the client — we only reveal it after /submit.
    choices: list[str] | None = None


class MorningDrillResponse(BaseModel):
    session_id: str              # opaque id, client passes it to submit
    total_questions: int
    questions: list[MorningQuestion]


class AnswerSubmission(BaseModel):
    session_id: str
    question_id: str
    answer: str
    # 0-based index into the question's `choices`. When set, /submit treats
    # it as the authoritative signal and skips LLM grading. `answer` is
    # still kept for auditing (= the option's text as shown to the user).
    choice_index: int | None = None


class AnswerFeedback(BaseModel):
    question_id: str
    ok: bool                               # heuristic/LLM pass/fail
    hint: str | None = None                # ideal short answer ("Эталон")
    matched_keywords: list[str] = []
    is_last: bool = False
    # ── 2026-04-20: fields for the collapsible "почему так" UI block ──
    law_article: str | None = None         # "127-ФЗ ст. 213.4"
    why_it_matters: str | None = None      # 1-3 sentences of legal reasoning
    source_excerpt: str | None = None      # verbatim excerpt of the law / fact
    # ── 2026-04-20: LLM grader fields (navy.api / gpt-5.4). Null when the
    #    LLM was unavailable — the client falls back to the hint+keywords UI.
    ai_score: int | None = None            # 0..100 semantic score
    ai_feedback: str | None = None         # 1-2 sentence personalised nudge
    ai_covered: list[str] = []             # points that were raised well
    ai_missed: list[str] = []              # important points the user skipped
    ai_model: str | None = None            # e.g. "gpt-5.4"


class AnswerRecord(BaseModel):
    """One question's result, posted back in bulk by the client on completion."""

    question_id: str
    kind: str = "legal"
    answer: str = ""
    ok: bool = False
    matched_keywords: list[str] = Field(default_factory=list)


class CompleteRequest(BaseModel):
    session_id: str
    total_questions: int
    answers: list[AnswerRecord]


class CompleteResponse(BaseModel):
    saved: bool
    session_db_id: str
    correct_answers: int
    total_questions: int


class WarmupStreakResponse(BaseModel):
    """Warm-up streak + freeze inventory for the current user.

    Streak counting rules (daily-warmup):
      * completed today         → streak unchanged (active)
      * completed yesterday     → streak = N, waiting for today
      * gap of 1 day + freeze   → streak unchanged, freeze spent (informational)
      * gap ≥ 2 days            → streak broken to 0
    This endpoint is READ-ONLY — actual freeze consumption happens when the
    user completes today's warm-up after a 1-day gap (see /complete).
    """

    current_streak: int
    longest_streak: int
    completed_today: bool
    last_completed_on: str | None     # ISO date (YYYY-MM-DD)
    # Freeze inventory (from existing StreakFreeze service).
    unused_freezes: int
    can_purchase: bool
    cost_ap: int
    max_per_month: int
    purchased_this_month: int


# ── Curated fallback sales-oriented questions ────────────────────────────


_SALES_POOL: list[dict[str, Any]] = [
    {
        "prompt": "Клиент говорит: «Это мошенники, не хочу слушать». Как снимете возражение за ОДНУ реплику?",
        "category": "objection",
        "hint": "Признать эмоцию + социальное доказательство + конкретика (ФЗ, кейсы).",
        "why": (
            "Возражение «мошенники» — эмоциональное, а не рациональное. Сначала признание "
            "эмоции снимает защиту, затем социальное доказательство (сколько людей прошли) "
            "переводит в рациональное русло."
        ),
    },
    {
        "prompt": "Клиент уходит в «я подумаю». Какой ваш заключительный вопрос, который фиксирует шаг?",
        "category": "closing",
        "hint": "Альтернативный выбор: «Запишу вас на консультацию в четверг в 14:00 или пятницу в 11:00?»",
        "why": (
            "«Я подумаю» обычно означает «я уйду и не вернусь». Альтернативный выбор не даёт "
            "уйти в неопределённость: клиент выбирает из двух конкретных опций, обе означают «да»."
        ),
    },
    {
        "prompt": "Вы позвонили холодно. Ваши первые 2 предложения — дословно.",
        "category": "opening",
        "hint": "Имя+компания → причина звонка → короткий релевантный хук → вопрос-разрешение.",
        "why": (
            "У холодного звонка — 8 секунд до отказа. Структура: кто, зачем, почему вам "
            "интересно, можно ли 1 минуту. Без вопроса-разрешения клиент кладёт трубку."
        ),
    },
    {
        "prompt": "Клиент спрашивает «Сколько стоит?» на первой минуте. Как отвечаете, не называя цену?",
        "category": "qualification",
        "hint": "Перенаправить: «Цена зависит от долга и активов. Можно 2 уточняющих вопроса?»",
        "why": (
            "Цена без контекста = либо «дорого», либо «дёшево», и клиент уходит. Квалификация "
            "до цены создаёт восприятие ценности и даёт точные вводные для финального оффера."
        ),
    },
    {
        "prompt": "Клиент молчит 5 секунд после вашего предложения. Что делаете?",
        "category": "rapport",
        "hint": "Не заполнять молчание → мягкий контакт: «Вижу, что это важный шаг. Что важно обдумать?»",
        "why": (
            "Молчание = клиент думает. Если заполнить его продающей речью — собьёте процесс "
            "принятия решения. Открытый вопрос возвращает диалог без давления."
        ),
    },
    {
        "prompt": "«У меня долг 800 000, зарплата 60 000. Подхожу под банкротство?» — одна строка ответа.",
        "category": "qualification",
        "hint": "Да, физлицо с долгом >500к и признаками неплатёжеспособности подходит под ст. 213.4.",
        "why": (
            "Порог 500 000 ₽ — обязанность подать при просрочке от 3 мес (ст. 213.4 п. 1 127-ФЗ). "
            "Зарплата 60к при долге 800к = признаки неплатёжеспособности — право на подачу также есть."
        ),
    },
]

# Fast lookup by prompt text (sales pool is tiny — O(n) is fine, but we'd
# rather not recompute the match every submit).
_SALES_BY_PROMPT: dict[str, dict[str, Any]] = {t["prompt"]: t for t in _SALES_POOL}


# ── Composition helpers ──────────────────────────────────────────────────


def _compose_question_from_chunk(chunk: LegalKnowledgeChunk) -> MorningQuestion:
    """Build a quiz-style prompt from a curated legal fact."""
    prompt = chunk.blitz_question or f"Что говорит 127-ФЗ про следующее: {chunk.fact_text[:160]}?"
    hint = chunk.blitz_answer or chunk.correct_response_hint
    # Only ship `choices` when it's a well-formed list of 2-4 strings. We
    # deliberately DON'T send correct_choice_index — UI grades through
    # /submit, which re-checks it server-side.
    choices: list[str] | None = None
    if isinstance(chunk.choices, list) and 2 <= len(chunk.choices) <= 4:
        choices = [str(c) for c in chunk.choices if isinstance(c, (str, int, float))][:4]
        if len(choices) < 2:
            choices = None
    return MorningQuestion(
        id=str(chunk.id),
        kind="legal",
        prompt=prompt,
        context=chunk.fact_text[:240] if not chunk.blitz_question else None,
        hint=hint,
        law_article=chunk.law_article,
        category=chunk.category.value if chunk.category else None,
        choices=choices,
    )


def _compose_question_from_sales(tpl: dict[str, Any]) -> MorningQuestion:
    return MorningQuestion(
        id=f"sales::{uuid.uuid4().hex[:8]}",
        kind="sales",
        prompt=tpl["prompt"],
        context=None,
        hint=tpl.get("hint"),
        law_article=None,
        category=tpl.get("category"),
    )


# Client sends back `prompt` in answers on /complete when the question was
# sales (sales ids are ephemeral — `sales::<hex>` — so we can't rehydrate
# from DB). We don't currently force that; sales records are still saved
# verbatim into the answers JSONB blob.


# ── Handlers ─────────────────────────────────────────────────────────────


@router.get("", response_model=MorningDrillResponse)
async def get_morning_drill(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MorningDrillResponse:
    """Return 3-5 sequential micro-questions for the morning warm-up.

    Composition:
      - 2-3 legal questions pulled from `legal_knowledge_chunks`, preferring
        chunks with precomputed `blitz_question`/`blitz_answer`.
      - 1-2 sales scenario questions from the curated pool above.
      - Shuffled so legal/sales are interleaved.
    """
    legal_rows = (
        await db.execute(
            select(LegalKnowledgeChunk)
            .where(
                LegalKnowledgeChunk.is_active.is_(True),
                LegalKnowledgeChunk.blitz_question.isnot(None),
            )
            .order_by(func.random())
            .limit(3)
        )
    ).scalars().all()
    if len(legal_rows) < 2:
        more = (
            await db.execute(
                select(LegalKnowledgeChunk)
                .where(LegalKnowledgeChunk.is_active.is_(True))
                .order_by(func.random())
                .limit(3)
            )
        ).scalars().all()
        legal_rows = list(legal_rows) + [r for r in more if r not in legal_rows]
        legal_rows = legal_rows[:3]

    legal_qs = [_compose_question_from_chunk(c) for c in legal_rows]
    sales_qs = [
        _compose_question_from_sales(tpl)
        for tpl in random.sample(_SALES_POOL, k=min(2, len(_SALES_POOL)))
    ]

    all_qs = legal_qs + sales_qs
    random.shuffle(all_qs)
    all_qs = all_qs[:5]

    return MorningDrillResponse(
        session_id=uuid.uuid4().hex,
        total_questions=len(all_qs),
        questions=all_qs,
    )


def _derive_why_from_chunk(chunk: LegalKnowledgeChunk) -> tuple[str | None, str | None]:
    """Build a short `why_it_matters` + `source_excerpt` for a legal answer.

    Keeps output bounded so the collapsible UI block doesn't overflow.
    """
    excerpt: str | None = None
    if chunk.source_article_full_text:
        excerpt = chunk.source_article_full_text[:500].strip()
    elif chunk.fact_text:
        excerpt = chunk.fact_text[:500].strip()

    why_parts: list[str] = []
    if chunk.fact_text:
        # Trim to ~240 chars, collapse internal whitespace.
        compact = re.sub(r"\s+", " ", chunk.fact_text).strip()
        why_parts.append(compact[:240] + ("…" if len(compact) > 240 else ""))
    if chunk.court_case_reference:
        why_parts.append(f"Судебная практика: {chunk.court_case_reference}")
    why = " ".join(why_parts) or None
    return why, excerpt


@router.post("/submit", response_model=AnswerFeedback)
async def submit_answer(
    body: AnswerSubmission,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AnswerFeedback:
    """Score the user's short answer with a cheap keyword-overlap heuristic.

    Returns the ideal short hint PLUS a longer `why_it_matters` + raw
    `source_excerpt` so the client can show a collapsible "почему так"
    block under the one-line "Эталон".

    Not a real quiz scorer — just gives the manager a quick "you covered the
    main ideas / you missed X" signal. Full scoring lives in training/quiz
    systems; this is 30-second warm-up.
    """
    question_id = body.question_id
    answer = body.answer.strip().lower()
    if not answer and body.choice_index is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty answer")

    hint_text: str | None = None
    expected_keywords: list[str] = []
    law_article: str | None = None
    why_it_matters: str | None = None
    source_excerpt: str | None = None

    # Legal question — real UUID, look up the chunk for rich feedback.
    is_legal = False
    try:
        legal_id = uuid.UUID(question_id)
        is_legal = True
    except ValueError:
        legal_id = None

    chunk_for_grader: LegalKnowledgeChunk | None = None
    if is_legal and legal_id is not None:
        chunk = (
            await db.execute(
                select(LegalKnowledgeChunk).where(LegalKnowledgeChunk.id == legal_id)
            )
        ).scalar_one_or_none()
        if chunk:
            chunk_for_grader = chunk
            hint_text = chunk.blitz_answer or chunk.correct_response_hint
            law_article = chunk.law_article
            why_it_matters, source_excerpt = _derive_why_from_chunk(chunk)
            if hint_text:
                # Extract keywords (3+ letter words, lowercased, dedup, max 8)
                words = re.findall(r"[а-яёa-z]{4,}", hint_text.lower())
                expected_keywords = list(dict.fromkeys(words))[:8]

            # ── 2026-04-20: multiple-choice shortcut. If the chunk has a
            # correct_choice_index AND the client sent choice_index, we
            # grade deterministically and skip the LLM entirely. This keeps
            # MC mode FAST (no network round-trip for objective questions).
            if (
                body.choice_index is not None
                and isinstance(chunk.choices, list)
                and chunk.correct_choice_index is not None
                and 0 <= body.choice_index < len(chunk.choices)
            ):
                mc_ok = body.choice_index == chunk.correct_choice_index
                mc_hint = hint_text or (
                    chunk.choices[chunk.correct_choice_index]
                    if 0 <= chunk.correct_choice_index < len(chunk.choices)
                    else None
                )
                return AnswerFeedback(
                    question_id=question_id,
                    ok=mc_ok,
                    hint=mc_hint,
                    matched_keywords=[],
                    is_last=False,
                    law_article=law_article,
                    why_it_matters=why_it_matters,
                    source_excerpt=source_excerpt,
                    ai_score=100 if mc_ok else 0,
                    ai_feedback=(
                        "Верно. Закрепим — смотри обоснование ниже." if mc_ok
                        else "Неверно. Правильный вариант — " + (
                            chunk.choices[chunk.correct_choice_index]
                            if 0 <= chunk.correct_choice_index < len(chunk.choices)
                            else "см. эталон"
                        )
                    ),
                    ai_covered=[] if not mc_ok else [mc_hint or "правильный выбор"],
                    ai_missed=[] if mc_ok else [mc_hint or "правильный выбор"],
                    ai_model="mc",
                )

    # Heuristic overlap for ok/not ok. For sales questions (no DB row) we
    # fall back to "did the user write something of substance" — the intent
    # is NOT to grade, just to flag empty/lazy answers.
    matched = [kw for kw in expected_keywords if kw in answer]
    heuristic_ok = bool(matched) if expected_keywords else len(answer) > 20

    # ── 2026-04-20: LLM grader (navy.api / gpt-5.4). Async call with a
    # 12s timeout + Redis cache — if it times out or fails, we silently
    # fall back to the heuristic above. Result OVERRIDES `ok` because the
    # semantic grade is much more trustworthy than keyword overlap.
    ai_grade: Any = None
    try:
        # Resolve the question text for the grader payload. For legal we
        # reuse the chunk fetched above — no extra DB round-trip.
        question_text = ""
        if chunk_for_grader is not None:
            question_text = (
                chunk_for_grader.blitz_question
                or f"Факт 127-ФЗ: {chunk_for_grader.fact_text[:200]}"
            )

        from app.services.warmup_grader import grade as llm_grade

        ai_grade = await llm_grade(
            question_id=question_id,
            question_text=question_text,
            user_answer=body.answer,
            hint=hint_text,
            law_article=law_article,
            kind="legal" if is_legal else "sales",
        )
    except Exception as e:  # defensive — grader must never break /submit
        logger.warning("warmup_grader failed: %s", e)
        ai_grade = None

    final_ok = ai_grade.ok if ai_grade is not None else heuristic_ok

    return AnswerFeedback(
        question_id=question_id,
        ok=final_ok,
        hint=hint_text,
        matched_keywords=matched,
        is_last=False,
        law_article=law_article,
        why_it_matters=why_it_matters,
        source_excerpt=source_excerpt,
        ai_score=ai_grade.score if ai_grade else None,
        ai_feedback=ai_grade.feedback if ai_grade else None,
        ai_covered=ai_grade.covered if ai_grade else [],
        ai_missed=ai_grade.missed if ai_grade else [],
        ai_model=ai_grade.model if ai_grade else None,
    )


async def _fetch_completed_dates(
    db: AsyncSession, user_id: uuid.UUID
) -> list:
    """Return distinct completion dates DESC (up to 2 years back).

    730 instead of 365 gives us a safety margin for power users and keeps
    longest_streak accurate past the 1-year mark. Cheap — composite
    (user_id, date) index turns this into a narrow range scan.
    """
    rows = await db.execute(
        select(func.distinct(MorningDrillSession.date))
        .where(
            MorningDrillSession.user_id == user_id,
            MorningDrillSession.completed_at.isnot(None),
        )
        .order_by(MorningDrillSession.date.desc())
        .limit(730)
    )
    return [r[0] for r in rows.all()]


def _compute_streak_readonly(all_dates: list, today_date) -> tuple[int, int]:
    """Pure function: current + longest streak, NO freeze consumption.

    Counts today as "in streak" if present OR if yesterday is present
    (today hasn't ended — no penalty for 'не сделал ещё'). Freeze
    consumption happens separately in /complete.
    """
    if not all_dates:
        return 0, 0
    date_set = set(all_dates)
    cursor = today_date
    if cursor not in date_set:
        cursor = cursor - timedelta(days=1)
    current = 0
    while cursor in date_set:
        current += 1
        cursor = cursor - timedelta(days=1)

    sorted_dates = sorted(all_dates)
    longest = 1
    run = 1
    for i in range(1, len(sorted_dates)):
        if (sorted_dates[i] - sorted_dates[i - 1]).days == 1:
            run += 1
        else:
            run = 1
        longest = max(longest, run)
    longest = max(longest, current)
    return current, longest


async def _consume_freeze_if_gap(
    db: AsyncSession,
    user_id: uuid.UUID,
    prev_last_date,
    today_date,
) -> bool:
    """Consume one StreakFreeze IFF today's completion is bridging exactly
    a 1-day gap (prev_last_date was 2 days ago). Returns True on consume.

    Called from /complete AFTER inserting the session row. Safe to call on
    every completion — no-op when there's no gap, gap is 0/1 day, or no
    unused freezes exist.

    Race safety: SELECT ... FOR UPDATE SKIP LOCKED on the freeze row so two
    concurrent completions can never both grab the same unused freeze.
    """
    if prev_last_date is None:
        return False
    gap = (today_date - prev_last_date).days
    if gap != 2:
        return False
    unused = (
        await db.execute(
            select(StreakFreeze)
            .where(
                StreakFreeze.user_id == user_id,
                StreakFreeze.used_at.is_(None),
            )
            .order_by(StreakFreeze.purchased_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
    ).scalar_one_or_none()
    if unused is None:
        return False
    unused.used_at = datetime.now(timezone.utc)
    await db.flush()
    logger.info("warmup streak freeze consumed: user=%s gap_days=%d", user_id, gap)
    return True


@router.get("/streak", response_model=WarmupStreakResponse)
async def get_warmup_streak(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WarmupStreakResponse:
    """Warm-up streak + freeze inventory for the /home badge. READ-ONLY."""
    from app.services.streak_freeze import get_freeze_status

    # 2026-04-20: use the local business timezone. With UTC a warm-up
    # completed at 00:30 Moscow would land on yesterday's date and the
    # streak would look broken.
    today_date = local_today()

    all_dates = await _fetch_completed_dates(db, user.id)
    current, longest = _compute_streak_readonly(all_dates, today_date)
    last_completed = all_dates[0] if all_dates else None

    freeze_info = await get_freeze_status(user.id, db)

    return WarmupStreakResponse(
        current_streak=current,
        longest_streak=longest,
        completed_today=(last_completed == today_date) if last_completed else False,
        last_completed_on=last_completed.isoformat() if last_completed else None,
        unused_freezes=freeze_info["unused_freezes"],
        can_purchase=freeze_info["can_purchase"],
        cost_ap=freeze_info["cost_ap"],
        max_per_month=freeze_info["max_per_month"],
        purchased_this_month=freeze_info["purchased_this_month"],
    )


@router.post("/complete", response_model=CompleteResponse)
async def complete_drill(
    body: CompleteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CompleteResponse:
    """Persist the completed warm-up so `daily_warmup` goal can count it.

    Idempotent-ish: if the user POSTs /complete twice with the same
    `session_id`, we write the row once and return the existing id. This
    protects against double-clicks on the final "Завершить" button.
    """
    # UTC for the wall-clock audit trail (started_at/completed_at), LOCAL
    # tz for the `date` key that streak + daily-goal logic groups by.
    now_utc = datetime.now(timezone.utc)
    today_local = local_today()

    # Dedup by (user_id, drill_session_id). Cheap because (user_id, date)
    # index makes this a narrow scan.
    existing = (
        await db.execute(
            select(MorningDrillSession).where(
                MorningDrillSession.user_id == user.id,
                MorningDrillSession.drill_session_id == body.session_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return CompleteResponse(
            saved=False,
            session_db_id=str(existing.id),
            correct_answers=existing.correct_answers,
            total_questions=existing.total_questions,
        )

    correct = sum(1 for a in body.answers if a.ok)

    # 2026-04-20: before inserting today's row, peek at the last completion
    # date so we can detect a 1-day gap and potentially consume a freeze.
    prev_last = (
        await db.execute(
            select(MorningDrillSession.date)
            .where(
                MorningDrillSession.user_id == user.id,
                MorningDrillSession.completed_at.isnot(None),
            )
            .order_by(MorningDrillSession.date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    row = MorningDrillSession(
        user_id=user.id,
        drill_session_id=body.session_id[:64],
        started_at=now_utc,
        completed_at=now_utc,
        total_questions=max(body.total_questions, len(body.answers)),
        correct_answers=correct,
        answers=[a.model_dump() for a in body.answers],
        date=today_local,
    )
    db.add(row)
    await db.flush()

    # Consume a freeze iff today bridges exactly a 1-day gap. Same
    # transaction as the insert so freeze + streak stay consistent.
    await _consume_freeze_if_gap(db, user.id, prev_last, today_local)

    # ── 2026-04-20: daily_warmup XP award ─────────────────────────────
    # check_goal_completions + award_goal_xp dedupe via GoalCompletionLog,
    # so a second call the same day is a no-op. Previously goals were only
    # checked by the training pipeline (event_bus) → warm-up never ticked.
    try:
        from app.services.daily_goals import (
            award_goal_xp,
            check_goal_completions,
        )
        newly_completed = await check_goal_completions(user.id, db)
        for goal in newly_completed:
            await award_goal_xp(user.id, goal, db)
    except Exception:
        # Never block /complete on XP bookkeeping — the warm-up row is
        # already persisted.
        logger.exception("morning_drill.complete: goal XP award failed")

    await db.commit()
    await db.refresh(row)

    logger.info(
        "morning_drill.complete user=%s correct=%d/%d date=%s",
        user.id,
        correct,
        row.total_questions,
        today_local.isoformat(),
    )

    return CompleteResponse(
        saved=True,
        session_db_id=str(row.id),
        correct_answers=correct,
        total_questions=row.total_questions,
    )
