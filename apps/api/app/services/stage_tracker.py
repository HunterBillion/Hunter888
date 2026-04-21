"""Content-based stage tracker for sales training sessions.

Determines the current conversation stage by analyzing message CONTENT
(keyword matching), not by message index or proportional mapping.

Stages follow a sequential 7-step sales script for BFL (personal bankruptcy):
1. greeting     — Приветствие и самопрезентация
2. contact      — Установление контакта
3. qualification — Квалификация (выявление потребности)
4. presentation — Презентация услуги
5. objections   — Работа с возражениями
6. appointment  — Назначение встречи / следующего шага
7. closing      — Закрытие сделки

Algorithm:
- Keyword scan on every manager message (O(1), no LLM calls)
- Stages progress sequentially; skipping is allowed, going back is not (v1)
- Each message can match current stage or up to 2 stages ahead (skip detection)
- Stage quality score accumulates per stage based on keyword coverage

Integration points:
- ws/training.py: init on session.start, process on each user message, cleanup on session.end
- Sends stage.update WS message on stage change
- Final state saved to session.scoring_details for L1 scoring
"""

import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ─── Stage definitions ──────────────────────────────────────────────────────

STAGE_ORDER = [
    "greeting",
    "contact",
    "qualification",
    "presentation",
    "objections",
    "appointment",
    "closing",
]

STAGE_LABELS = {
    "greeting": "Приветствие",
    "contact": "Контакт",
    "qualification": "Квалификация",
    "presentation": "Презентация",
    "objections": "Возражения",
    "appointment": "Встреча",
    "closing": "Закрытие",
}

# Keyword markers for each stage.
# "markers" — phrases indicating the manager is working within this stage.
# "min_messages" — earliest message index where this stage can realistically begin.
# "max_messages" — if this stage hasn't started by this index, it was likely skipped.
STAGE_KEYWORDS: dict[str, dict] = {
    "greeting": {
        "markers": [
            "здравствуйте", "добрый день", "добрый вечер", "доброе утро",
            "меня зовут", "компания", "звоню вам", "хотел бы поговорить",
            "представлюсь", "приветствую", "добрый",
        ],
        "min_messages": 0,
        "max_messages": 4,
    },
    "contact": {
        "markers": [
            "как вас зовут", "понимаю вашу ситуацию", "конфиденциально",
            "расскажите", "сочувствую", "непростая ситуация",
            "не переживайте", "можете довериться", "понимаю вас",
            "тяжело", "сложная ситуация", "как к вам обращаться",
        ],
        "min_messages": 1,
        "max_messages": 8,
    },
    "qualification": {
        "markers": [
            "сумма долга", "сколько должны", "кредиторы", "банки",
            "платежи", "просрочка", "ипотека", "кредит", "займ",
            "какая сумма", "сколько кредитов", "имущество",
            "задолженность", "долг", "платите", "заём",
            "сколько банков", "какие банки",
        ],
        "min_messages": 2,
        "max_messages": 14,
    },
    "presentation": {
        "markers": [
            "банкротство", "списание", "процедура", "127-фз",
            "арбитражный", "финансовый управляющий", "реструктуризация",
            "защита имущества", "единственное жильё", "срок",
            "списать долги", "освобождение от долгов", "закон",
            "банкротство физических", "процедура банкротства",
        ],
        "min_messages": 4,
        "max_messages": 18,
    },
    "objections": {
        "markers": [
            "понимаю ваши опасения", "рассрочка", "гарантия",
            "лицензия", "отзывы", "не переживайте",
            "не уверен", "сомневаюсь", "понимаю что",
            "многие клиенты", "на вашем месте", "опасения",
            "беспокоит", "тревожит", "боитесь",
        ],
        "min_messages": 6,
        "max_messages": 22,
    },
    "appointment": {
        "markers": [
            "встреча", "приехать", "офис", "консультация",
            "когда удобно", "завтра", "послезавтра", "на неделе",
            "записать вас", "забронировать", "следующий шаг",
            "можем встретиться", "приглашаю", "бесплатная консультация",
        ],
        "min_messages": 8,
        "max_messages": 26,
    },
    "closing": {
        "markers": [
            "договорились", "жду вас", "до встречи", "спасибо за время",
            "подведём итог", "резюмирую", "итого мы", "всего доброго",
            "хорошего дня", "до свидания", "рад что",
            "подтверждаю", "тогда ждём", "до связи",
        ],
        "min_messages": 10,
        "max_messages": 30,
    },
}

# S3-09: Minimum fraction of matched markers required to trigger a stage transition.
# History: 0.12 (~2 markers) caused oscillation → raised to 0.25 (~3 markers).
# 2026-04-20: 0.25 proved too strict for real dialogues where managers handle
# objections (price / guarantees / fraud fears) without hitting ≥3 exact
# qualification markers. Lowered to 0.18 (~2 markers) — still above the
# oscillation floor but permissive enough for natural conversation flow.
TRANSITION_THRESHOLD = 0.18

# S3-09: Hysteresis — require N consecutive messages confirming transition
# before actually advancing. Prevents single-message keyword noise from
# triggering false stage changes.
# 2026-04-20: 3 confirmations paired with the old 0.25 threshold effectively
# required 3 back-to-back highly-matched turns — unrealistic in short calls.
# Reduced to 2: one strong match still needs confirmation, but a genuinely
# progressing dialogue advances without a 3-turn commitment.
HYSTERESIS_CONFIRMATIONS = 2


# ─── Stage-Aware AI Behavior Rules ──────────────────────────────────────────
# These rules are injected into the LLM system prompt to guide AI client behavior
# per conversation stage. Each stage has:
#   behavior  — how the client should act (tone, openness, resistance level)
#   info_reveal — what information the client is willing to share
#   traps     — which trap categories are relevant at this stage
#   skip_reaction — what the client says if the manager skips THIS stage

STAGE_BEHAVIOR: dict[str, dict] = {
    "greeting": {
        "behavior": (
            "Ты настороженный, немного напряжённый. Тебе звонит незнакомый человек. "
            "Отвечай коротко. Спроси 'Откуда у вас мой номер?' или 'Кто вы?'. "
            "Не раскрывай никакой личной информации на этом этапе."
        ),
        "info_reveal": "Только своё имя, если менеджер вежливо представился.",
        "traps": [],  # No traps on greeting
        "skip_reaction": None,  # Can't skip greeting — it's first
    },
    "contact": {
        "behavior": (
            "Ты всё ещё осторожен, но если менеджер проявляет эмпатию — "
            "начинаешь чуть расслабляться. Если менеджер не пытается установить контакт "
            "и сразу переходит к делу — ты раздражаешься."
        ),
        "info_reveal": "Можешь кратко упомянуть что у тебя 'есть проблемы' но без деталей.",
        "traps": ["emotional"],  # Emotional traps relevant here
        "skip_reaction": (
            "Подождите, мы даже не познакомились толком. "
            "Вы даже не спросили как у меня дела."
        ),
    },
    "qualification": {
        "behavior": (
            "Ты уклончив с цифрами. Не называй точную сумму долга сразу — "
            "сначала скажи 'ну, прилично' или 'много'. Только если менеджер настаивает "
            "мягко и уважительно — раскрывай детали постепенно. "
            "Если менеджер давит — замолкай или раздражайся."
        ),
        "info_reveal": (
            "Постепенно раскрывай: 1) примерную сумму ('около миллиона'), "
            "2) количество кредиторов ('три-четыре банка'), "
            "3) имущество только если спросят напрямую."
        ),
        "traps": ["emotional", "manipulative"],  # Client may manipulate with fake numbers
        "skip_reaction": (
            "Стоп, вы даже не спросили про мою ситуацию! "
            "Как вы можете что-то предлагать, не зная деталей?"
        ),
    },
    "presentation": {
        "behavior": (
            "Слушаешь с интересом но скептически. Задавай уточняющие вопросы: "
            "'А что будет с квартирой?', 'А сколько это длится?', 'А кредитная история?'. "
            "Если менеджер говорит неточные юридические факты — "
            "не поправляй его (это ловушка для оценки)."
        ),
        "info_reveal": "Можешь упомянуть свои страхи: 'я боюсь потерять квартиру'.",
        "traps": ["legal"],  # Legal accuracy traps are key here
        "skip_reaction": (
            "А что вы вообще предлагаете? Вы так и не объяснили "
            "что это за процедура и как она работает."
        ),
    },
    "objections": {
        "behavior": (
            "Ты выдвигаешь возражения — от мягких ('дорого', 'я подумаю') "
            "до жёстких ('мошенники', 'мне сказали что это развод'). "
            "Не соглашайся сразу — дай менеджеру 2-3 попытки. "
            "Если менеджер начинает спорить или давить — усиливай сопротивление. "
            "Если менеджер выслушивает и аргументирует — постепенно смягчайся."
        ),
        "info_reveal": "Можешь раскрыть свои истинные страхи и сомнения.",
        "traps": ["emotional", "legal", "manipulative"],  # All traps active
        "skip_reaction": (
            "У меня есть серьёзные сомнения, и вы их даже не обсудили. "
            "Как я могу вам доверять?"
        ),
    },
    "appointment": {
        "behavior": (
            "Если доверие накоплено — ты открыт к предложению встречи, "
            "но торгуешься по времени ('на этой неделе не могу', 'давайте на следующей'). "
            "Если доверия мало — отказываешься от встречи: 'я ещё подумаю'."
        ),
        "info_reveal": "Можешь обсуждать свой график.",
        "traps": [],  # Usually no traps at appointment stage
        "skip_reaction": (
            "А что дальше? Вы так и не предложили конкретный следующий шаг. "
            "Что мне делать с этой информацией?"
        ),
    },
    "closing": {
        "behavior": (
            "Если всё прошло хорошо — подтверждаешь договорённость. "
            "Если сомнения остались — просишь 'дать подумать до завтра'. "
            "Реагируй тепло если менеджер благодарит за время."
        ),
        "info_reveal": "Можешь подтвердить или отложить решение.",
        "traps": [],
        "skip_reaction": None,  # Can't skip closing
    },
}


# ─── Data classes ────────────────────────────────────────────────────────────

@dataclass
class StageState:
    """Current stage tracking state, persisted in Redis."""
    current_stage: int = 1                                    # 1-based index
    current_stage_name: str = "greeting"                      # key from STAGE_ORDER
    stages_completed: list[int] = field(default_factory=list) # 1-based indices
    stage_scores: dict[int, float] = field(default_factory=dict)  # {stage_num: quality 0-1}
    total_stages: int = 7
    last_detected_at: int = 0                                 # message_index of last transition
    confidence: float = 1.0                                   # 0-1, how sure we are
    # S3-09: Hysteresis — {candidate_stage: consecutive_confirmations}
    transition_confirmations: dict[int, int] = field(default_factory=dict)


# ─── StageTracker ────────────────────────────────────────────────────────────

class StageTracker:
    """Determines conversation stage from message content via keyword matching.

    Usage:
        tracker = StageTracker(session_id, redis)
        await tracker.init_state()
        ...
        state, changed = await tracker.process_message(text, msg_idx, "user")
        if changed:
            # send stage.update WS message
    """

    def __init__(self, session_id: str, redis) -> None:
        self.session_id = str(session_id)
        self.redis = redis
        self._state_key = f"stage:{self.session_id}"

    # ── Lifecycle ──

    async def init_state(self, total_stages: int = 7) -> StageState:
        """Initialize stage tracking at session start."""
        state = StageState(
            current_stage=1,
            current_stage_name="greeting",
            stages_completed=[],
            stage_scores={},
            total_stages=total_stages,
            last_detected_at=0,
            confidence=1.0,
        )
        await self._save_state(state)
        return state

    async def cleanup(self) -> StageState:
        """Remove Redis key and return final state (for scoring_details)."""
        state = await self._load_state()
        try:
            await self.redis.delete(self._state_key)
        except Exception:
            logger.debug("Failed to delete stage key for session %s", self.session_id)
        return state

    async def get_state(self) -> StageState:
        """Read current state without modification."""
        return await self._load_state()

    # ── Core processing ──

    async def process_message(
        self,
        message_text: str,
        message_index: int,
        role: str = "user",
    ) -> tuple[StageState, bool, list[int]]:
        """Analyze a message and potentially advance the stage.

        Only manager (role="user") messages can advance stages.
        Returns (current_state, stage_changed_flag, skipped_stage_numbers).
        """
        state = await self._load_state()

        # Assistant messages update current stage quality (confirmatory signal)
        # but do NOT trigger stage transitions — only user messages advance stages
        if role != "user":
            if 1 <= state.current_stage <= len(STAGE_ORDER):
                text_lower = message_text.lower()
                current_stage_name = STAGE_ORDER[state.current_stage - 1]
                kw = STAGE_KEYWORDS[current_stage_name]
                matched = sum(1 for m in kw["markers"] if m in text_lower)
                if matched > 0:
                    score = matched / len(kw["markers"]) * 0.5  # Half weight for client msgs
                    prev = state.stage_scores.get(state.current_stage, 0.0)
                    state.stage_scores[state.current_stage] = min(1.0, max(prev, score))
                    await self._save_state(state)
            return state, False, []

        # All stages completed or invalid — nothing to do
        if state.current_stage > len(STAGE_ORDER) or state.current_stage < 1:
            return state, False, []

        # v6.1: Skip stage processing for "human moment" messages (off-topic, typos).
        # These messages shouldn't block or advance stage progression — just ignore them.
        try:
            from app.services.emotion_v6 import detect_human_moment
            human_trigger = detect_human_moment(message_text)
            if human_trigger is not None:
                logger.debug(
                    "Stage tracker: skipping human_moment message (trigger=%s) at stage %s",
                    human_trigger, state.current_stage_name,
                )
                return state, False, []
        except Exception:
            pass  # Graceful degradation if emotion_v6 import fails

        text_lower = message_text.lower()

        # ── Score current stage (accumulative quality tracking) ──
        current_stage_name = STAGE_ORDER[state.current_stage - 1]
        current_kw = STAGE_KEYWORDS[current_stage_name]
        current_matched = sum(1 for m in current_kw["markers"] if m in text_lower)
        if current_matched > 0:
            score = current_matched / len(current_kw["markers"])
            prev = state.stage_scores.get(state.current_stage, 0.0)
            state.stage_scores[state.current_stage] = min(1.0, max(prev, score))

        # ── Check for stage transition ──
        # Look at next 1-2 stages (allow skipping one stage ahead)
        best_match_stage: int | None = None
        best_score = 0.0

        for offset in range(1, 3):  # +1, +2 stages ahead
            check_stage = state.current_stage + offset
            if check_stage > len(STAGE_ORDER):
                break

            stage_name = STAGE_ORDER[check_stage - 1]
            kw = STAGE_KEYWORDS[stage_name]

            matched = sum(1 for m in kw["markers"] if m in text_lower)
            if matched == 0:
                continue

            score = matched / len(kw["markers"])

            # Penalty for transitioning too early
            if message_index < kw["min_messages"]:
                score *= 0.5

            if score > best_score and score >= TRANSITION_THRESHOLD:
                best_score = score
                best_match_stage = check_stage

        # S3-09: Hysteresis — require HYSTERESIS_CONFIRMATIONS consecutive
        # messages confirming the same candidate stage before transitioning.
        # Reset confirmation counter for candidates that weren't matched this turn.
        if best_match_stage is not None:
            state.transition_confirmations[best_match_stage] = (
                state.transition_confirmations.get(best_match_stage, 0) + 1
            )
            # Clear confirmations for other candidate stages (they broke continuity)
            for k in list(state.transition_confirmations):
                if k != best_match_stage:
                    state.transition_confirmations.pop(k, None)
        else:
            # No match this message — reset all pending confirmations
            state.transition_confirmations.clear()

        # ── Apply transition (only after enough confirmations) ──
        if (
            best_match_stage is not None
            and state.transition_confirmations.get(best_match_stage, 0) >= HYSTERESIS_CONFIRMATIONS
        ):
            # Clear confirmation counter on successful transition
            state.transition_confirmations.clear()
            # Mark current stage as completed
            if state.current_stage not in state.stages_completed:
                state.stages_completed.append(state.current_stage)
                # If no score recorded yet, give partial credit
                if state.current_stage not in state.stage_scores:
                    state.stage_scores[state.current_stage] = 0.3

            # Mark any skipped stages and collect them
            newly_skipped: list[int] = []
            for skipped in range(state.current_stage + 1, best_match_stage):
                if skipped not in state.stages_completed:
                    state.stages_completed.append(skipped)
                    state.stage_scores[skipped] = 0.0  # Skipped = 0 quality
                    newly_skipped.append(skipped)

            # Advance to new stage
            state.current_stage = best_match_stage
            state.current_stage_name = STAGE_ORDER[best_match_stage - 1]
            state.last_detected_at = message_index
            state.confidence = min(1.0, best_score * 3)

            await self._save_state(state)
            return state, True, newly_skipped

        # ── Auto-complete greeting after first few messages ──
        # If we're still on greeting after 4+ messages with ANY content, auto-advance
        if (
            state.current_stage == 1
            and message_index >= STAGE_KEYWORDS["greeting"]["max_messages"]
            and state.current_stage not in state.stages_completed
        ):
            state.stages_completed.append(1)
            if 1 not in state.stage_scores:
                state.stage_scores[1] = 0.1  # Minimal credit
            state.current_stage = 2
            state.current_stage_name = "contact"
            state.last_detected_at = message_index
            state.confidence = 0.5

            await self._save_state(state)
            return state, True, []

        await self._save_state(state)
        return state, False, []

    # ── Utility ──

    async def force_complete_stage(self, stage_number: int, score: float = 1.0) -> None:
        """Force-complete a stage (for LLM-based override or testing)."""
        state = await self._load_state()
        if stage_number not in state.stages_completed:
            state.stages_completed.append(stage_number)
        state.stage_scores[stage_number] = score
        if stage_number >= state.current_stage:
            next_stage = stage_number + 1
            if next_stage <= len(STAGE_ORDER):
                state.current_stage = next_stage
                state.current_stage_name = STAGE_ORDER[next_stage - 1]
        await self._save_state(state)

    def build_ws_payload(self, state: StageState) -> dict:
        """Build the payload for a stage.update WS message."""
        return {
            "stage_number": state.current_stage,
            "stage_name": state.current_stage_name,
            "stage_label": STAGE_LABELS.get(state.current_stage_name, state.current_stage_name),
            "total_stages": state.total_stages,
            "stages_completed": sorted(state.stages_completed),
            "stage_scores": {str(k): round(v, 2) for k, v in state.stage_scores.items()},
            "confidence": round(state.confidence, 2),
        }

    def build_scoring_details(self, state: StageState) -> dict:
        """Build data for session.scoring_details['_stage_progress']."""
        return {
            "stages_completed": sorted(state.stages_completed),
            "stage_scores": {str(k): round(v, 3) for k, v in state.stage_scores.items()},
            "final_stage": state.current_stage,
            "final_stage_name": state.current_stage_name,
            "total_stages": state.total_stages,
        }

    # ── Stage-Aware AI Prompt Builder ──

    def build_stage_prompt(self, state: StageState) -> str:
        """Build a comprehensive prompt section for the LLM describing current stage behavior.

        This replaces the simple [CURRENT_STAGE: ...] tag with detailed behavioral rules
        including how to act, what info to reveal, and relevant trap categories.
        """
        if state.current_stage > len(STAGE_ORDER):
            return (
                "\n\n[STAGE_CONTEXT]\n"
                "Все этапы скрипта пройдены. Веди разговор естественно. "
                "Реагируй на резюмирование и прощание."
            )

        stage_name = state.current_stage_name
        stage_label = STAGE_LABELS.get(stage_name, stage_name)
        behavior = STAGE_BEHAVIOR.get(stage_name, {})

        parts = [
            f"\n\n[STAGE_CONTEXT: {stage_name} ({stage_label}), этап {state.current_stage}/{state.total_stages}]",
        ]

        # Behavioral instructions
        if behavior.get("behavior"):
            parts.append(f"ПОВЕДЕНИЕ НА ЭТОМ ЭТАПЕ: {behavior['behavior']}")

        # Info reveal rules
        if behavior.get("info_reveal"):
            parts.append(f"ЧТО МОЖЕШЬ РАСКРЫТЬ: {behavior['info_reveal']}")

        # Relevant trap categories
        trap_cats = behavior.get("traps", [])
        if trap_cats:
            cat_labels = {
                "emotional": "эмоциональные",
                "legal": "юридические",
                "manipulative": "манипулятивные",
            }
            trap_str = ", ".join(cat_labels.get(c, c) for c in trap_cats)
            parts.append(f"АКТИВНЫЕ КАТЕГОРИИ ЛОВУШЕК: {trap_str}")

        # Stage progress context
        completed = len(state.stages_completed)
        if completed == 0:
            parts.append("Разговор только начался.")
        elif completed <= 2:
            parts.append("Начальная фаза разговора. Держи дистанцию.")
        elif completed <= 4:
            parts.append("Разговор продвигается. Можешь быть чуть открытее.")
        else:
            parts.append("Разговор в продвинутой фазе. Можно обсуждать детали.")

        return "\n".join(parts)

    def get_skip_reactions(self, state: StageState, skipped_stages: list[int]) -> list[str]:
        """Get client reaction phrases for skipped stages.

        Called when process_message detects that stages were skipped.
        Returns phrases the AI client should say to challenge the manager.
        """
        reactions = []
        for stage_num in skipped_stages:
            if stage_num < 1 or stage_num > len(STAGE_ORDER):
                continue
            stage_name = STAGE_ORDER[stage_num - 1]
            behavior = STAGE_BEHAVIOR.get(stage_name, {})
            reaction = behavior.get("skip_reaction")
            if reaction:
                reactions.append(reaction)
        return reactions

    def get_stage_trap_categories(self, state: StageState) -> list[str]:
        """Get trap categories relevant to the current stage.

        Used to filter which traps should be active at this point.
        """
        if state.current_stage > len(STAGE_ORDER):
            return []
        stage_name = state.current_stage_name
        behavior = STAGE_BEHAVIOR.get(stage_name, {})
        return behavior.get("traps", [])

    # ── Redis persistence ──

    async def _save_state(self, state: StageState) -> None:
        data = {
            "cs": state.current_stage,
            "cn": state.current_stage_name,
            "sc": state.stages_completed,
            "ss": {str(k): v for k, v in state.stage_scores.items()},
            "ts": state.total_stages,
            "ld": state.last_detected_at,
            "cf": state.confidence,
            "tc": {str(k): v for k, v in state.transition_confirmations.items()},
        }
        try:
            await self.redis.set(self._state_key, json.dumps(data), ex=7200)
        except Exception:
            logger.warning("Failed to save stage state for session %s", self.session_id)

    async def _load_state(self) -> StageState:
        try:
            raw = await self.redis.get(self._state_key)
        except Exception:
            logger.warning("Failed to load stage state for session %s", self.session_id)
            return StageState()

        if not raw:
            return StageState()

        try:
            data = json.loads(raw)
            return StageState(
                current_stage=data.get("cs", 1),
                current_stage_name=data.get("cn", "greeting"),
                stages_completed=data.get("sc", []),
                stage_scores={int(k): v for k, v in data.get("ss", {}).items()},
                total_stages=data.get("ts", 7),
                last_detected_at=data.get("ld", 0),
                confidence=data.get("cf", 1.0),
                transition_confirmations={int(k): v for k, v in data.get("tc", {}).items()},
            )
        except (json.JSONDecodeError, TypeError, KeyError):
            logger.warning("Corrupted stage state for session %s, resetting", self.session_id)
            return StageState()
