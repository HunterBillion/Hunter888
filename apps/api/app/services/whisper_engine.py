"""Real-time coaching whisper engine for training sessions.

Generates contextual hints for the manager based on:
- Current conversation stage
- Client emotion state
- Legal context (keyword + async RAG enrichment)
- Objection patterns
- Stage transition readiness

Throttled to max 1 whisper per 30 seconds per session.
Priority: legal > emotion > stage > objection > transition.
"""

import logging
import re
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ─── Configuration ────────────────────────────────────────────────────────────

THROTTLE_SEC = 30       # Min interval between whispers
MAX_WHISPERS = 10       # Max whispers per session (avoid spam for long sessions)
MIN_MESSAGES_FOR_WHISPER = 2  # Don't whisper until manager has sent 2+ messages

# Priority values (higher = more important, sent first)
PRIORITY_MAP = {
    "legal": 3,
    "emotion": 2,
    "script": 2,  # 2026-04-23 Sprint 3/7: stuck-on-stage educational hint
    "stage": 1,
    "objection": 1,
    "transition": 1,
}

# 2026-04-23 Sprint 3 (plan §3.1.5) — script-stuck hints. Frontend
# WhisperPanel renders type="script" as a clickable card with a Target
# icon; click scrolls ScriptPanel into view and expands it. We fire
# these when the manager has been on the same stage for N messages
# without a transition — "застрял, вот конкретная фраза чтобы двигаться".
SCRIPT_STUCK_HINTS: dict[str, str] = {
    "greeting": "Похоже, затянули приветствие. Попробуйте: «Здравствуйте, меня зовут {имя}, компания. Есть минутка?»",
    "contact": "Застряли на контакте. Попробуйте: «Расскажите, что у вас случилось? Я вас слушаю.»",
    "qualification": "Квалификация буксует. Попробуйте: «Какая примерно сумма долга? Сколько у вас кредиторов?»",
    "presentation": "Презентация затянулась. Упростите: «Банкротство по 127-ФЗ — списание долгов за 8–10 месяцев через суд.»",
    "objections": "Возражения висят. Присоединитесь: «Понимаю ваше беспокойство. Давайте посчитаем — сколько вы платите банкам сейчас?»",
    "appointment": "Пора назначать встречу. Попробуйте: «Давайте встретимся — завтра или на неделе удобнее?»",
    "closing": "Пора закрывать. Резюмируйте: «Итого: встреча в {день}, офис, с паспортом. Спасибо за доверие!»",
}

# Number of manager messages on the SAME stage before we consider them stuck.
SCRIPT_STUCK_THRESHOLD = 5

# ─── Emotion de-escalation hints ──────────────────────────────────────────────

EMOTION_HINTS: dict[str, str] = {
    "hostile": "Клиент раздражён. Снизьте темп, проявите понимание. Не спорьте — выслушайте.",
    "hangup": "Клиент готов положить трубку. Задайте открытый вопрос, покажите уважение к его времени.",
    "angry": "Клиент злится. Присоединитесь: «Я понимаю ваше возмущение». Не оправдывайтесь.",
    "anxious": "Клиент тревожится. Успокойте: конфиденциальность, поэтапность, контроль ситуации.",
    "crying": "Клиент в эмоциональном состоянии. Пауза, эмпатия, не торопите с решениями.",
}

# ─── Stage transition hints ───────────────────────────────────────────────────

STAGE_NAMES_RU = {
    "greeting": "Приветствие",
    "contact": "Установление контакта",
    "qualification": "Квалификация",
    "presentation": "Презентация",
    "objections": "Работа с возражениями",
    "appointment": "Назначение встречи",
    "closing": "Закрытие",
}

STAGE_ORDER = ["greeting", "contact", "qualification", "presentation", "objections", "appointment", "closing"]

STAGE_HINTS: dict[str, str] = {
    "greeting": "Представьтесь, назовите компанию и цель звонка. Коротко — за 15 секунд.",
    "contact": "Установите контакт: обратитесь по имени, проявите эмпатию, снизьте тревожность.",
    "qualification": "Выясните: сумму долга, количество кредиторов, наличие просрочек и имущества.",
    "presentation": "Объясните процедуру банкротства: 127-ФЗ, сроки 8-10 месяцев, защита имущества.",
    "objections": "Выслушайте возражение полностью. Не спорьте — присоединитесь, затем аргументируйте.",
    "appointment": "Предложите конкретное время встречи/консультации. Дайте альтернативу.",
    "closing": "Резюмируйте договорённости, поблагодарите за время, попрощайтесь корректно.",
}

# ─── Objection patterns and strategies ────────────────────────────────────────

OBJECTION_PATTERNS: dict[str, dict] = {
    "price": {
        "patterns": [r"дорого", r"стоимость", r"цена", r"не могу\s+позволить", r"денег\s+нет", r"сколько\s+стоит"],
        "strategy": "Клиент говорит о цене. Предложите рассрочку. Сравните с ежемесячными платежами по кредитам.",
        "icon": "shield",
    },
    "trust": {
        "patterns": [r"мошенник", r"не верю", r"развод", r"обман", r"кидалово", r"не доверяю"],
        "strategy": "Клиент не доверяет. Упомяните лицензию, реальные отзывы, юридическую ответственность.",
        "icon": "shield",
    },
    "delay": {
        "patterns": [r"подумаю", r"перезвоню", r"не\s+сейчас", r"потом", r"не\s+готов"],
        "strategy": "Клиент откладывает решение. Спросите: «Что именно хотели бы обдумать?» Конкретизируйте.",
        "icon": "shield",
    },
    "self_solve": {
        "patterns": [r"сам\s+разберусь", r"не\s+нужно", r"справлюсь", r"мфц", r"через\s+суд\s+сам"],
        "strategy": "Клиент хочет разобраться сам. Покажите последствия бездействия и сложность процедуры.",
        "icon": "shield",
    },
    "competitor": {
        "patterns": [r"юрист", r"адвокат", r"другая\s+компания", r"уже\s+обращался", r"знакомый\s+юрист"],
        "strategy": "У клиента есть альтернатива. Подчеркните специализацию именно на банкротстве ФЛ и комплексный подход.",
        "icon": "shield",
    },
}

# ─── Legal keyword triggers (subset from legal_checker for real-time) ─────────

LEGAL_TRIGGERS: list[dict] = [
    {
        "keywords": [r"квартир", r"жильё", r"жилье", r"дом\b", r"недвижимост"],
        "hint": "Клиент спросил про жильё. Упомяните ст. 213.25 — единственное жильё защищено (кроме ипотечного).",
        "article": "ст. 213.25 127-ФЗ",
    },
    {
        "keywords": [r"машин", r"автомобил", r"авто\b", r"транспорт"],
        "hint": "Клиент спросил про автомобиль. Автомобиль НЕ защищён по умолчанию. Исключение: если необходим для работы (такси, инвалидность).",
        "article": "ст. 446 ГПК",
    },
    {
        "keywords": [r"алимент", r"ребён", r"дет"],
        "hint": "Алименты НЕ списываются при банкротстве. Это исключение из освобождения от долгов.",
        "article": "ст. 213.28 п.5 127-ФЗ",
    },
    {
        "keywords": [r"100\s*%\s*спиш", r"все\s+долги\s+спиш", r"гарантир\w+\s+списан", r"точно\s+спиш"],
        "hint": "Нельзя гарантировать 100% списание. Есть исключения: алименты, вред здоровью, субсидиарная ответственность.",
        "article": "ст. 213.28 п.5-6 127-ФЗ",
    },
    {
        "keywords": [r"(?:сколько|как\s+долго|срок|время)\s*(?:длится|займёт|процедур)"],
        "hint": "Стандартный срок процедуры реализации имущества — 6 месяцев. Реструктуризация долгов — до 3 лет.",
        "article": "ст. 213.24, ст. 213.14 127-ФЗ",
    },
    {
        "keywords": [r"кредитн\w+\s+истор", r"бки", r"бюро"],
        "hint": "Информация о банкротстве сохраняется в кредитной истории 10 лет. Не говорите что 'не повлияет'.",
        "article": "ст. 213.30 127-ФЗ",
    },
    {
        "keywords": [r"за\s+границ", r"выезд", r"загранпаспорт", r"путешеств"],
        "hint": "Суд МОЖЕТ ограничить выезд за границу во время процедуры. Не обещайте что ограничений не будет.",
        "article": "ст. 213.24 п.3 127-ФЗ",
    },
    {
        "keywords": [r"зарплат", r"доход", r"пенси", r"прожиточн"],
        "hint": "При банкротстве должнику оставляют прожиточный минимум + на иждивенцев. Зарплата свыше — в конкурсную массу.",
        "article": "ст. 213.25 п.3 127-ФЗ",
    },
    {
        "keywords": [r"бесплатн", r"ничего\s+не\s+стоит", r"без\s+оплат"],
        "hint": "Банкротство НЕ бесплатно: госпошлина 300₽, депозит на управляющего 25 000₽, плюс юридические услуги.",
        "article": "ст. 213.4 п.4 127-ФЗ",
    },
    {
        "keywords": [r"управляющ", r"финансов\w+\s+управляющ", r"арбитражн\w+\s+управляющ"],
        "hint": "Финансовый управляющий назначается судом. Его вознаграждение — 25 000₽ фиксированно + 7% от реализации.",
        "article": "ст. 213.9 127-ФЗ",
    },
]


@dataclass
class Whisper:
    """A coaching whisper to send to the manager."""
    type: str       # legal, emotion, stage, objection, transition
    message: str
    stage: str      # current stage name
    priority: str   # high, medium, low
    icon: str       # lucide icon name: scale, heart, arrow-right, shield, zap

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "message": self.message,
            "stage": self.stage,
            "priority": self.priority,
            "icon": self.icon,
        }


class WhisperEngine:
    """Generates contextual coaching whispers during training sessions."""

    def __init__(self, redis_client=None):
        self._redis = redis_client

    async def generate_whisper(
        self,
        session_id: str,
        current_stage: str,
        client_emotion: str,
        last_client_message: str,
        last_manager_message: str,
        manager_message_count: int,
        difficulty: int,
        whispers_enabled: bool = True,
        # 2026-04-23 Sprint 3: messages on the CURRENT stage (not total).
        # Used by _check_script_stuck to detect «завис на этапе».
        stage_message_count: int | None = None,
        stage_number: int | None = None,
    ) -> dict | None:
        """Analyze context and generate a whisper if appropriate.

        Returns None if no whisper needed (throttled, disabled, or no relevant hint).
        """
        if not whispers_enabled:
            return None

        if manager_message_count < MIN_MESSAGES_FOR_WHISPER:
            return None

        # Check throttle
        if not await self._check_throttle(session_id):
            return None

        # Generate candidates in priority order
        candidates: list[Whisper] = []

        # 1. Legal (highest priority) — check client message for legal triggers
        legal = self._check_legal(last_client_message, current_stage)
        if legal:
            candidates.append(legal)

        # 2. Emotion — check if client is in distress
        emotion = self._check_emotion(client_emotion, current_stage)
        if emotion:
            candidates.append(emotion)

        # 3. Stage hint — if manager seems stuck (no transition for many messages)
        stage = self._check_stage_hint(current_stage, manager_message_count)
        if stage:
            candidates.append(stage)

        # 3b. 2026-04-23 Sprint 3 (plan §3.1.5) — script-stuck educational
        # whisper. Fires when the manager has been on the SAME stage for
        # too many messages without transitioning. Priority 2 (same as
        # emotion) so it surfaces above generic stage hints.
        if stage_message_count is not None:
            script = self._check_script_stuck(
                current_stage, stage_message_count, stage_number,
            )
            if script:
                candidates.append(script)

        # 4. Objection — check client message for objection patterns
        objection = self._check_objection(last_client_message, current_stage)
        if objection:
            candidates.append(objection)

        if not candidates:
            return None

        # Pick highest priority candidate
        candidates.sort(key=lambda w: PRIORITY_MAP.get(w.type, 0), reverse=True)
        best = candidates[0]

        # Record throttle
        await self._set_throttle(session_id)

        return best.to_dict()

    async def generate_legal_enrichment(
        self,
        query: str,
        session_id: str,
        current_stage: str,
    ) -> dict | None:
        """Background RAG enrichment for legal whispers.

        Called via asyncio.create_task after an initial keyword-based legal whisper.
        Returns an enriched whisper with specific article references, or None.
        """
        try:
            from app.database import async_session
            from app.services.rag_legal import retrieve_legal_context

            async with async_session() as db:
                rag_result = await retrieve_legal_context(query, db, top_k=2)

            if not rag_result or not rag_result.results:
                return None

            top = rag_result.results[0]
            message = f"{top.fact_text}"
            if top.law_article:
                message += f" ({top.law_article})"
            if top.correct_response_hint:
                message += f"\nСовет: {top.correct_response_hint}"

            return Whisper(
                type="legal",
                message=message,
                stage=current_stage,
                priority="high",
                icon="scale",
            ).to_dict()

        except Exception:
            logger.debug("Legal RAG enrichment failed for session %s", session_id, exc_info=True)
            return None

    # ─── Private methods ──────────────────────────────────────────────────

    def _check_legal(self, client_message: str, stage: str) -> Whisper | None:
        """Check client message for legal topic triggers.

        2026-05-04 (NEW-2 fix): the keyword match was too greedy. Production
        session example 1 fired «Алименты НЕ списываются при банкротстве»
        because the text contained the bare word "детей" (matched ``r"дет"``)
        in an unrelated context. Now we require BOTH:

          1. Keyword match (existing).
          2. The client message is actually ASKING something — has a "?"
             in the message OR contains an interrogative root or law-topic
             verb. Without this gate, every passing mention of "квартира"
             or "дети" produces a misleading legal claim from the coach.

        For the few keyword sets that are themselves explicit claims
        (100%-списание, бесплатно) we keep the old behaviour — the manager
        IS being misleading, no question gate needed.
        """
        if not client_message:
            return None

        text = client_message.lower()

        # Triggers that ALWAYS fire (manager-claim patterns) — these are
        # explicit misleading statements, not topical questions.
        _CLAIM_PATTERNS = {
            r"100\s*%\s*спиш", r"все\s+долги\s+спиш",
            r"гарантир\w+\s+списан", r"точно\s+спиш",
            r"бесплатн", r"ничего\s+не\s+стоит", r"без\s+оплат",
        }

        # Question / topical-discussion gate for the rest.
        _QUESTION_GATE = re.compile(
            r"\?|"
            r"\b(как|почему|зачем|что|сколько|когда|где|куда|можно ли|правда ли|"
            r"действительно|объясн|расскаж|подскаж|поясн|правильно ли|"
            r"снимут|защищ|оставят|заберут|потеряю|сохран|спишут|спишется)\b",
            flags=re.IGNORECASE,
        )
        has_question_context = bool(_QUESTION_GATE.search(text))

        for trigger in LEGAL_TRIGGERS:
            for pattern in trigger["keywords"]:
                if not re.search(pattern, text):
                    continue
                # Always-fire patterns bypass the question gate.
                if pattern in _CLAIM_PATTERNS:
                    return self._make_legal_whisper(trigger, stage, validated=False)
                # All others require question/topical context.
                if has_question_context:
                    return self._make_legal_whisper(trigger, stage, validated=False)
                # Word matched but client is just mentioning it casually
                # ("у меня дети маленькие") — do NOT fire a legal claim.
                logger.debug(
                    "legal trigger %r suppressed: keyword matched but no question context (text=%r)",
                    pattern, text[:80],
                )
                break  # don't try other patterns of same trigger
        return None

    def _make_legal_whisper(self, trigger: dict, stage: str, validated: bool) -> Whisper:
        """Build a legal Whisper, optionally tagging it as RAG-validated."""
        msg = trigger["hint"]
        article = trigger.get("article")
        if article and article not in msg:
            msg = f"{msg} ({article})"
        return Whisper(
            type="legal",
            message=msg,
            stage=stage,
            priority="high",
            icon="scale",
        )

    def _check_emotion(self, emotion: str, stage: str) -> Whisper | None:
        """Check if client emotion requires coaching hint."""
        hint = EMOTION_HINTS.get(emotion)
        if hint:
            return Whisper(
                type="emotion",
                message=hint,
                stage=stage,
                priority="high" if emotion in ("hostile", "hangup") else "medium",
                icon="heart",
            )
        return None

    def _check_stage_hint(self, current_stage: str, msg_count: int) -> Whisper | None:
        """Suggest stage-specific action if manager seems stuck."""
        hint = STAGE_HINTS.get(current_stage)
        if not hint:
            return None

        # Only suggest if enough messages have passed for this stage
        stage_idx = STAGE_ORDER.index(current_stage) if current_stage in STAGE_ORDER else 0
        # Suggest hint after ~4 messages per stage (adaptive)
        expected_messages = (stage_idx + 1) * 4
        if msg_count >= expected_messages and msg_count % 4 == 0:
            return Whisper(
                type="stage",
                message=f"Стадия: {STAGE_NAMES_RU.get(current_stage, current_stage)}. {hint}",
                stage=current_stage,
                priority="low",
                icon="zap",
            )
        return None

    def _check_script_stuck(
        self,
        current_stage: str,
        stage_msg_count: int,
        stage_number: int | None,
    ) -> Whisper | None:
        """2026-04-23 Sprint 3: fire when manager has been on the same
        stage for ≥ SCRIPT_STUCK_THRESHOLD messages without transitioning.

        Frontend `WhisperPanel` (type="script") renders these as a
        clickable card that scrolls ScriptPanel into view so the user
        can copy an example phrase. The `stage` field carries the
        1-based stage number (not the key) for the «Этап N» mini-header.
        """
        if stage_msg_count < SCRIPT_STUCK_THRESHOLD:
            return None
        # Fire once every SCRIPT_STUCK_THRESHOLD messages (so a persistent
        # stuck state doesn't spam — the existing throttle in
        # generate_whisper also caps to THROTTLE_SEC).
        if stage_msg_count % SCRIPT_STUCK_THRESHOLD != 0:
            return None
        hint = SCRIPT_STUCK_HINTS.get(current_stage)
        if not hint:
            return None
        stage_label = str(stage_number) if stage_number is not None else current_stage
        return Whisper(
            type="script",
            message=hint,
            stage=stage_label,
            priority="high",
            icon="target",
        )

    def _check_objection(self, client_message: str, stage: str) -> Whisper | None:
        """Check client message for objection patterns."""
        if not client_message:
            return None

        text = client_message.lower()
        for category, data in OBJECTION_PATTERNS.items():
            for pattern in data["patterns"]:
                if re.search(pattern, text):
                    return Whisper(
                        type="objection",
                        message=data["strategy"],
                        stage=stage,
                        priority="medium",
                        icon=data["icon"],
                    )
        return None

    async def _check_throttle(self, session_id: str) -> bool:
        """Return True if enough time has passed since last whisper."""
        if not self._redis:
            return True

        try:
            key = f"whisper:last:{session_id}"
            last_ts = await self._redis.get(key)
            if last_ts:
                elapsed = time.time() - float(last_ts)
                if elapsed < THROTTLE_SEC:
                    return False

            # Check max whispers
            count_key = f"whisper:count:{session_id}"
            count = await self._redis.get(count_key)
            if count and int(count) >= MAX_WHISPERS:
                return False

        except Exception:
            pass  # Non-critical — allow whisper if Redis fails

        return True

    async def _set_throttle(self, session_id: str) -> None:
        """Record whisper timestamp and increment counter."""
        if not self._redis:
            return

        try:
            key = f"whisper:last:{session_id}"
            await self._redis.set(key, str(time.time()), ex=THROTTLE_SEC + 5)

            count_key = f"whisper:count:{session_id}"
            await self._redis.incr(count_key)
            await self._redis.expire(count_key, 7200)  # 2h TTL
        except Exception:
            pass
