"""Exam service — question generation, scoring, certificate PDF.

Uses Navy API for intelligent question generation with legal chunk context.
Falls back to hardcoded questions if API unavailable.
"""
import logging
import os
import random
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.exam import Certificate, ExamAttempt

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────

EXAM_LEVELS = {5, 10, 15, 20}

# level -> (num_questions, pass_threshold_%, time_limit_seconds)
EXAM_CONFIG: dict[int, tuple[int, float, int]] = {
    5: (10, 70.0, 600),
    10: (15, 80.0, 900),
    15: (20, 85.0, 1200),
    20: (30, 90.0, 1800),
}


def needs_exam(level: int) -> bool:
    return level in EXAM_LEVELS


async def get_exam_status(user_id: uuid.UUID, level: int, db: AsyncSession) -> dict[str, Any]:
    """Check user's exam status for a given level."""
    result = await db.execute(
        select(ExamAttempt)
        .where(ExamAttempt.user_id == user_id, ExamAttempt.level == level)
        .order_by(ExamAttempt.started_at.desc())
        .limit(1)
    )
    attempt = result.scalar_one_or_none()

    if not attempt:
        return {"status": "not_started", "attempt_id": None}

    if attempt.status == "in_progress":
        elapsed = (datetime.utcnow() - attempt.started_at).total_seconds()
        config = EXAM_CONFIG.get(level, (10, 70.0, 600))
        time_limit = config[2]
        if elapsed > time_limit + 60:
            attempt.status = "failed"
            attempt.completed_at = datetime.utcnow()
            attempt.score = 0
            await db.flush()
            return {"status": "failed", "attempt_id": str(attempt.id), "score": 0}
        return {"status": "in_progress", "attempt_id": str(attempt.id)}

    if attempt.status == "passed":
        cert_result = await db.execute(
            select(Certificate)
            .where(Certificate.user_id == user_id, Certificate.level == level)
            .limit(1)
        )
        cert = cert_result.scalar_one_or_none()
        return {
            "status": "passed",
            "attempt_id": str(attempt.id),
            "score": attempt.score,
            "certificate_id": str(cert.id) if cert else None,
        }

    return {
        "status": "failed",
        "attempt_id": str(attempt.id),
        "score": attempt.score,
    }


async def create_exam(user_id: uuid.UUID, level: int, db: AsyncSession) -> ExamAttempt:
    """Create a new exam attempt with generated questions."""
    config = EXAM_CONFIG.get(level, (10, 70.0, 600))
    num_questions, threshold, time_limit = config

    questions = await _generate_exam_questions(level, num_questions, db)

    attempt = ExamAttempt(
        user_id=user_id,
        level=level,
        status="in_progress",
        total_questions=len(questions),
        pass_threshold=threshold,
        questions_data={"questions": questions, "time_limit": time_limit},
        started_at=datetime.utcnow(),
    )
    db.add(attempt)
    await db.flush()
    return attempt


async def submit_exam(
    attempt_id: uuid.UUID, answers: list[dict], db: AsyncSession
) -> dict[str, Any]:
    """Grade exam and issue certificate if passed."""
    attempt = await db.get(ExamAttempt, attempt_id)
    if not attempt:
        return {"error": "Экзамен не найден"}
    if attempt.status != "in_progress":
        return {"error": "Экзамен уже завершён"}

    questions = (attempt.questions_data or {}).get("questions", [])
    if not questions:
        return {"error": "Вопросы не найдены"}

    correct = 0
    details = []
    for ans in answers:
        idx = ans.get("index", -1)
        selected = ans.get("selected")
        if 0 <= idx < len(questions):
            q = questions[idx]
            is_correct = selected == q.get("correct")
            if is_correct:
                correct += 1
            details.append({
                "index": idx,
                "selected": selected,
                "correct": q.get("correct"),
                "is_correct": is_correct,
            })

    total = len(questions)
    score = (correct / total * 100) if total > 0 else 0
    passed = score >= attempt.pass_threshold

    attempt.correct_answers = correct
    attempt.score = round(score, 1)
    attempt.status = "passed" if passed else "failed"
    attempt.completed_at = datetime.utcnow()
    attempt.answers_data = {"answers": details}

    if attempt.started_at:
        attempt.duration_seconds = int(
            (attempt.completed_at - attempt.started_at).total_seconds()
        )

    result: dict[str, Any] = {
        "passed": passed,
        "score": round(score, 1),
        "correct": correct,
        "total": total,
        "threshold": attempt.pass_threshold,
        "details": details,
    }

    if passed:
        cert = await _issue_certificate(attempt, db)
        result["certificate_id"] = str(cert.id)
        result["serial_number"] = cert.serial_number

        # Send TG notifications
        try:
            from app.models.user import User
            user = await db.get(User, attempt.user_id)
            if user and user.telegram_chat_id:
                from app.services.telegram_bot import telegram_bot
                from scripts.seed_levels import get_level_name
                level_name = get_level_name(attempt.level)
                await telegram_bot.send_exam_passed(
                    chat_id=user.telegram_chat_id,
                    user_name=user.full_name or "бро",
                    level=attempt.level,
                    level_name=level_name,
                    score=score,
                    serial=cert.serial_number,
                )
        except Exception as e:
            logger.warning("TG exam passed notification failed: %s", e)
    else:
        # TG notification for failed exam
        try:
            from app.models.user import User
            user = await db.get(User, attempt.user_id)
            if user and user.telegram_chat_id:
                from app.services.telegram_bot import telegram_bot
                await telegram_bot.send_exam_failed(
                    chat_id=user.telegram_chat_id,
                    user_name=user.full_name or "бро",
                    level=attempt.level,
                    score=score,
                    threshold=attempt.pass_threshold,
                )
        except Exception as e:
            logger.warning("TG exam failed notification failed: %s", e)

    await db.flush()
    return result


# ── Question Generation ─────────────────────────────────────────────────

async def _generate_exam_questions(
    level: int, num_questions: int, db: AsyncSession
) -> list[dict]:
    """Generate exam questions using Navy API with legal chunk context."""
    if not settings.local_llm_enabled:
        return _generate_fallback_questions(level, num_questions)

    try:
        # Get legal knowledge chunks for context
        context_chunks = await _get_legal_context(level, db)
        return await _generate_via_navy(level, num_questions, context_chunks)
    except Exception as e:
        logger.warning("Navy API question generation failed: %s, using fallback", e)
        return _generate_fallback_questions(level, num_questions)


async def _get_legal_context(level: int, db: AsyncSession) -> list[str]:
    """Fetch relevant legal knowledge chunks for question context."""
    try:
        from app.models.rag import LegalKnowledgeChunk
        result = await db.execute(
            select(LegalKnowledgeChunk.body)
            .order_by(func.random())
            .limit(min(level * 2, 20))
        )
        return [row[0] for row in result.all() if row[0]]
    except Exception:
        return []


async def _generate_via_navy(
    level: int, num_questions: int, context_chunks: list[str]
) -> list[dict]:
    """Generate questions via Navy API."""
    import httpx

    context_text = "\n\n".join(context_chunks[:10]) if context_chunks else ""
    difficulty_map = {5: "базовый", 10: "средний", 15: "продвинутый", 20: "экспертный"}
    difficulty = difficulty_map.get(level, "средний")

    prompt = (
        f"Сгенерируй {num_questions} вопросов для экзамена уровня {level} "
        f"(сложность: {difficulty}) по теме взыскания задолженности и 127-ФЗ.\n\n"
        f"Формат каждого вопроса — JSON объект:\n"
        f'{{"question": "текст вопроса", "options": ["A", "B", "C", "D"], "correct": 0}}\n\n'
        f"correct — индекс правильного ответа (0-3).\n"
        f"Верни JSON массив из {num_questions} объектов, без markdown.\n"
    )
    if context_text:
        prompt += f"\nКонтекст для вопросов:\n{context_text[:3000]}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.local_llm_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.local_llm_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.local_llm_model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Ты генератор экзаменационных вопросов по взысканию задолженности "
                            "и банкротству физических лиц (127-ФЗ). Отвечай только JSON массивом."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 4000,
                "temperature": 0.7,
            },
        )
        data = resp.json()
        text = data["choices"][0]["message"]["content"].strip()

        # Parse JSON from response
        import json
        # Strip markdown code blocks if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        questions = json.loads(text)
        if not isinstance(questions, list):
            raise ValueError("Expected JSON array")

        # Validate and normalize
        valid = []
        for q in questions:
            if (
                isinstance(q, dict)
                and "question" in q
                and "options" in q
                and "correct" in q
                and isinstance(q["options"], list)
                and len(q["options"]) >= 2
                and isinstance(q["correct"], int)
                and 0 <= q["correct"] < len(q["options"])
            ):
                valid.append({
                    "question": str(q["question"]),
                    "options": [str(o) for o in q["options"][:4]],
                    "correct": q["correct"],
                })
        if len(valid) < num_questions // 2:
            raise ValueError(f"Only {len(valid)} valid questions generated")
        return valid[:num_questions]


def _generate_fallback_questions(level: int, num_questions: int) -> list[dict]:
    """Hardcoded bankruptcy law questions as fallback."""
    pool = [
        {
            "question": "Какой минимальный размер задолженности для подачи заявления о банкротстве физлица?",
            "options": ["300 000 руб.", "500 000 руб.", "1 000 000 руб.", "100 000 руб."],
            "correct": 1,
        },
        {
            "question": "Какой срок просрочки необходим для подачи заявления о банкротстве?",
            "options": ["1 месяц", "3 месяца", "6 месяцев", "12 месяцев"],
            "correct": 1,
        },
        {
            "question": "Кто может быть финансовым управляющим в деле о банкротстве?",
            "options": [
                "Любой юрист",
                "Член СРО арбитражных управляющих",
                "Сотрудник банка",
                "Судебный пристав",
            ],
            "correct": 1,
        },
        {
            "question": "Какой суд рассматривает дела о банкротстве физических лиц?",
            "options": [
                "Мировой суд",
                "Районный суд",
                "Арбитражный суд",
                "Верховный суд",
            ],
            "correct": 2,
        },
        {
            "question": "Что происходит с долгами после завершения процедуры банкротства?",
            "options": [
                "Списываются полностью",
                "Списываются частично",
                "Переходят наследникам",
                "Удваиваются",
            ],
            "correct": 0,
        },
        {
            "question": "Какие долги НЕ списываются при банкротстве?",
            "options": [
                "Кредитные долги",
                "Алименты",
                "Долги по ЖКХ",
                "Микрозаймы",
            ],
            "correct": 1,
        },
        {
            "question": "Сколько длится процедура реализации имущества?",
            "options": ["1 месяц", "3 месяца", "6 месяцев", "12 месяцев"],
            "correct": 2,
        },
        {
            "question": "Может ли должник выезжать за границу во время банкротства?",
            "options": [
                "Да, без ограничений",
                "Только с разрешения суда",
                "Нет, запрещено полностью",
                "Только в страны СНГ",
            ],
            "correct": 1,
        },
        {
            "question": "Какое имущество не подлежит реализации при банкротстве?",
            "options": [
                "Автомобиль",
                "Единственное жилье (без ипотеки)",
                "Вклады в банках",
                "Ценные бумаги",
            ],
            "correct": 1,
        },
        {
            "question": "Через сколько лет после банкротства можно повторно подать заявление?",
            "options": ["1 год", "3 года", "5 лет", "10 лет"],
            "correct": 2,
        },
        {
            "question": "Что такое реструктуризация долгов?",
            "options": [
                "Списание долгов",
                "План погашения долгов на новых условиях",
                "Передача долгов другому лицу",
                "Увеличение суммы долга",
            ],
            "correct": 1,
        },
        {
            "question": "Кто публикует сведения о банкротстве?",
            "options": [
                "Должник",
                "Кредитор",
                "Финансовый управляющий в ЕФРСБ",
                "Налоговая инспекция",
            ],
            "correct": 2,
        },
        {
            "question": "Какой размер вознаграждения финансового управляющего?",
            "options": [
                "10 000 руб.",
                "25 000 руб. за процедуру",
                "50 000 руб.",
                "100 000 руб.",
            ],
            "correct": 1,
        },
        {
            "question": "Может ли должник оспорить включение требования кредитора?",
            "options": [
                "Нет",
                "Да, через суд",
                "Только через прокуратуру",
                "Только с помощью адвоката",
            ],
            "correct": 1,
        },
        {
            "question": "Что такое мораторий на удовлетворение требований кредиторов?",
            "options": [
                "Запрет на новые займы",
                "Приостановка взыскания на время процедуры",
                "Увеличение процентной ставки",
                "Конфискация имущества",
            ],
            "correct": 1,
        },
        {
            "question": "Какой документ регулирует процедуру банкротства физлиц?",
            "options": [
                "Гражданский кодекс",
                "127-ФЗ «О несостоятельности (банкротстве)»",
                "Трудовой кодекс",
                "Налоговый кодекс",
            ],
            "correct": 1,
        },
        {
            "question": "Что должен указать должник при подаче на банкротство?",
            "options": [
                "Только сумму долга",
                "Список кредиторов и имущества",
                "Паспортные данные кредиторов",
                "Историю покупок за 10 лет",
            ],
            "correct": 1,
        },
        {
            "question": "Можно ли пройти внесудебное банкротство?",
            "options": [
                "Нет, только через суд",
                "Да, через МФЦ при долге 50 000 - 500 000 руб.",
                "Да, через нотариуса",
                "Да, через банк-кредитор",
            ],
            "correct": 1,
        },
        {
            "question": "Какое последствие банкротства для должника на 5 лет?",
            "options": [
                "Запрет на работу",
                "Обязанность сообщать о банкротстве при получении кредита",
                "Запрет на выезд из города",
                "Конфискация зарплаты",
            ],
            "correct": 1,
        },
        {
            "question": "Может ли кредитор подать заявление о банкротстве должника?",
            "options": [
                "Нет, только сам должник",
                "Да, при наличии судебного решения",
                "Только банк",
                "Только налоговая",
            ],
            "correct": 1,
        },
        {
            "question": "Что такое конкурсная масса?",
            "options": [
                "Общая сумма долгов",
                "Имущество должника для реализации",
                "Список кредиторов",
                "Судебные расходы",
            ],
            "correct": 1,
        },
        {
            "question": "Какой максимальный срок реструктуризации долгов?",
            "options": ["1 год", "2 года", "3 года", "5 лет"],
            "correct": 2,
        },
        {
            "question": "Можно ли сохранить ипотечное жилье при банкротстве?",
            "options": [
                "Да, всегда",
                "Нет, оно реализуется залоговым кредитором",
                "Только если долг менее 500 000",
                "Только с согласия банка",
            ],
            "correct": 1,
        },
        {
            "question": "Какие сделки могут быть оспорены при банкротстве?",
            "options": [
                "Любые за последний месяц",
                "Подозрительные сделки за 3 года до заявления",
                "Только дарение",
                "Никакие",
            ],
            "correct": 1,
        },
        {
            "question": "Что такое собрание кредиторов?",
            "options": [
                "Суд над должником",
                "Орган для принятия решений кредиторами",
                "Встреча должника с приставами",
                "Заседание арбитражного суда",
            ],
            "correct": 1,
        },
        {
            "question": "Какой первый этап процедуры банкротства физлица?",
            "options": [
                "Реализация имущества",
                "Реструктуризация долгов",
                "Мировое соглашение",
                "Конкурсное производство",
            ],
            "correct": 1,
        },
        {
            "question": "Что происходит с исполнительными производствами при банкротстве?",
            "options": [
                "Продолжаются",
                "Приостанавливаются",
                "Ускоряются",
                "Передаются в другой суд",
            ],
            "correct": 1,
        },
        {
            "question": "Может ли должник работать во время банкротства?",
            "options": [
                "Нет",
                "Да, но зарплата перечисляется управляющему",
                "Да, сохраняя прожиточный минимум",
                "Только неофициально",
            ],
            "correct": 2,
        },
        {
            "question": "Какой срок для включения требований в реестр кредиторов?",
            "options": [
                "1 месяц",
                "2 месяца с момента публикации",
                "6 месяцев",
                "Без ограничений",
            ],
            "correct": 1,
        },
        {
            "question": "Что такое мировое соглашение в деле о банкротстве?",
            "options": [
                "Решение суда",
                "Соглашение между должником и кредиторами о порядке погашения",
                "Отказ от долга",
                "Передача дела в другой суд",
            ],
            "correct": 1,
        },
    ]

    random.shuffle(pool)
    return pool[:num_questions]


# ── Certificate ─────────────────────────────────────────────────────────

async def _issue_certificate(attempt: ExamAttempt, db: AsyncSession) -> Certificate:
    """Issue a certificate for a passed exam."""
    from scripts.seed_levels import get_level_name

    level_name = get_level_name(attempt.level)
    serial = _generate_serial(attempt.level)

    cert = Certificate(
        user_id=attempt.user_id,
        exam_attempt_id=attempt.id,
        level=attempt.level,
        level_name=level_name,
        score=attempt.score or 0,
        serial_number=serial,
        issued_at=datetime.utcnow(),
    )
    db.add(cert)
    await db.flush()

    # Generate PDF
    try:
        cert.pdf_path = await generate_certificate_pdf(cert)
    except Exception as e:
        logger.warning("Certificate PDF generation failed: %s", e)

    attempt.certificate_id = cert.id
    await db.flush()
    return cert


def _generate_serial(level: int) -> str:
    """Generate unique certificate serial number."""
    import time
    ts = int(time.time())
    rand = random.randint(1000, 9999)
    return f"H888-L{level:02d}-{ts}-{rand}"


async def generate_certificate_pdf(cert: Certificate) -> str:
    """Generate a landscape A4 PDF certificate using fpdf2."""
    from fpdf import FPDF

    cert_dir = "/app/uploads/certificates"
    os.makedirs(cert_dir, exist_ok=True)

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()
    pdf.set_auto_page_break(auto=False)

    # Background — dark blue
    pdf.set_fill_color(20, 30, 70)
    pdf.rect(0, 0, 297, 210, "F")

    # Gold border
    pdf.set_draw_color(218, 165, 32)
    pdf.set_line_width(2)
    pdf.rect(10, 10, 277, 190)
    pdf.set_line_width(0.5)
    pdf.rect(14, 14, 269, 182)

    # Title
    pdf.set_font("Helvetica", "B", 36)
    pdf.set_text_color(218, 165, 32)
    pdf.set_xy(0, 30)
    pdf.cell(297, 15, "CERTIFICATE", align="C")

    # Subtitle
    pdf.set_font("Helvetica", "", 16)
    pdf.set_text_color(200, 200, 220)
    pdf.set_xy(0, 48)
    pdf.cell(297, 10, "Hunter888 Training Platform", align="C")

    # Divider
    pdf.set_draw_color(218, 165, 32)
    pdf.set_line_width(0.5)
    pdf.line(80, 62, 217, 62)

    # Level info
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(0, 70)
    level_text = f"Level {cert.level}"
    pdf.cell(297, 12, level_text, align="C")

    pdf.set_font("Helvetica", "", 16)
    pdf.set_text_color(180, 190, 220)
    pdf.set_xy(0, 84)
    pdf.cell(297, 10, cert.level_name, align="C")

    # Score
    pdf.set_font("Helvetica", "B", 28)
    pdf.set_text_color(100, 220, 100)
    pdf.set_xy(0, 102)
    pdf.cell(297, 14, f"{cert.score:.1f}%", align="C")

    pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(160, 170, 200)
    pdf.set_xy(0, 118)
    pdf.cell(297, 8, "Examination Score", align="C")

    # Divider
    pdf.line(80, 132, 217, 132)

    # Serial
    pdf.set_font("Courier", "", 11)
    pdf.set_text_color(160, 170, 200)
    pdf.set_xy(0, 140)
    pdf.cell(297, 8, f"Serial: {cert.serial_number}", align="C")

    # Date
    issued = cert.issued_at.strftime("%d.%m.%Y") if cert.issued_at else ""
    pdf.set_font("Helvetica", "", 11)
    pdf.set_xy(0, 150)
    pdf.cell(297, 8, f"Issued: {issued}", align="C")

    # Footer
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(120, 130, 160)
    pdf.set_xy(0, 175)
    pdf.cell(297, 6, "This certificate confirms successful completion of the Hunter888 level examination.", align="C")

    filename = f"cert_{cert.serial_number}.pdf"
    filepath = os.path.join(cert_dir, filename)
    pdf.output(filepath)
    return filepath
