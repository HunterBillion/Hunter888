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
        # 2026-04-23 Sprint 2: expanded from 12 → 30+ markers. Real
        # dialogues routinely stalled here because the list required
        # specific phrases ("как вас зовут" exactly) while actual managers
        # used more colloquial rapport-building turns ("расскажите",
        # "давайте разберёмся"). Marker hunt now matches natural Russian.
        "markers": [
            # Name request / addressing
            "как вас зовут", "как к вам обращаться", "можно узнать ваше имя",
            "разрешите узнать", "можно по имени",
            # Empathy / acknowledgement
            "понимаю вашу ситуацию", "понимаю вас", "я понимаю",
            "сочувствую", "могу представить", "представляю как",
            "это непросто", "непростая ситуация", "это сложно",
            "тяжело", "сложная ситуация",
            # Rapport / invitation to share
            "расскажите", "расскажите подробнее", "что у вас случилось",
            "с чего всё началось", "поделитесь",
            "давайте разберём", "давайте разберёмся", "давайте разберемся",
            # Reassurance
            "не переживайте", "не волнуйтесь", "всё хорошо",
            "можете довериться", "конфиденциально",
            # Listening signals
            "я вас слушаю", "слушаю вас", "помочь вам", "могу помочь",
            "спасибо что ответили", "спасибо за открытость",
        ],
        "min_messages": 1,
        "max_messages": 8,
    },
    "qualification": {
        # 2026-04-23: expanded to catch soft asks ("примерно сколько") and
        # imperfect casing / stemming. Real managers rarely say "сумма долга"
        # verbatim — they circle around ("а сколько примерно?", "какие банки").
        "markers": [
            # Sum / amount probes
            "сумма долга", "сколько должны", "какая сумма", "примерно",
            "сколько у вас", "какой размер", "размер долга",
            # Creditors probes
            "кредиторы", "какие банки", "сколько банков", "сколько кредитов",
            "в каких банках", "микрофинансовые", "мфо", "займ", "заём",
            "кредит", "банки",
            # Payments / arrears
            "платежи", "просрочка", "задолженность", "долг",
            "платите", "как платите", "давно не платите",
            "когда перестали", "когда началось",
            # Property
            "имущество", "ипотека", "квартира", "машина", "есть ли работа",
            "какой доход", "с чего всё началось",
        ],
        "min_messages": 2,
        "max_messages": 14,
    },
    "presentation": {
        # 2026-04-23: widened to catch natural explanations ("объясню как",
        # "простыми словами", "будет стоить"). Previously needed exact legal
        # jargon like "127-фз" which managers often paraphrase.
        "markers": [
            # Procedure terminology
            "банкротство", "процедура", "127-фз", "127 фз", "127фз",
            "арбитражный", "финансовый управляющий", "реструктуризация",
            "банкротство физических", "процедура банкротства",
            # Explanations
            "объясню как", "простыми словами", "как это работает",
            "расскажу как", "поясню",
            # Outcomes / timing
            "списание", "списать долги", "освобождение от долгов",
            "закон", "срок", "какие сроки", "сколько длится",
            "8 месяцев", "10 месяцев", "полгода",
            # Property protection
            "защита имущества", "единственное жильё", "единственное жилье",
            "защищено законом", "суд назначает",
            # Cost transparency
            "будет стоить", "стоимость", "госпошлина", "депозит",
        ],
        "min_messages": 4,
        "max_messages": 18,
    },
    "objections": {
        # 2026-04-23: expanded to include "joining before arguing" phrases,
        # plus concrete counter-fears (кредитная история, квартира).
        "markers": [
            # Join-and-acknowledge
            "понимаю ваши опасения", "понимаю ваше беспокойство",
            "понимаю ваш страх", "понимаю что", "я понимаю",
            "на вашем месте", "многие клиенты", "многие думают",
            # Counter-doubt
            "рассрочка", "гарантия", "лицензия", "отзывы",
            "это законно", "можете проверить", "реестр",
            "вот наша лицензия",
            # Soft objections voiced
            "не уверен", "сомневаюсь", "опасения", "беспокоит",
            "тревожит", "боитесь", "переживаете",
            "боитесь потерять", "боитесь что",
            # Reassurance against specific fears
            "не переживайте", "не волнуйтесь", "всё в порядке",
            "давайте посчитаем", "посмотрите на выгоду",
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
# History:
#   - 0.12 (~2 markers)         → oscillation
#   - 0.25 (~3 markers)         → too strict on real dialogues
#   - 0.18 (~2 markers)         → still stuck after markers expansion
#   - 2026-04-23 Sprint 2: denominator was `len(markers)` which became
#     unstable when Sprint 2 expanded marker pools 12 → 30+. Two real
#     matches dropped from 0.17 → 0.07 and no longer triggered. Fixed by
#     capping denominator at MAX_DENOM below — now 2 matches → 0.25
#     regardless of how many markers a stage lists. Threshold itself
#     reduced to 0.15 for a touch more permissiveness.
TRANSITION_THRESHOLD = 0.15
# 2026-04-23 Sprint 2: score normalisation denominator cap. Prevents big
# marker pools from diluting signal strength.
MARKER_DENOMINATOR_CAP = 8

# S3-09: Hysteresis — require N consecutive messages confirming transition
# before actually advancing. Prevents single-message keyword noise from
# triggering false stage changes.
#
# History:
#   - 3 + 0.25 threshold (original) → too strict, short calls never advanced
#   - 2 + 0.18 threshold (2026-04-20) → still stuck on greeting→contact
#   - per-stage map (2026-04-23 Sprint 2) → greeting→contact needs only
#     ONE confirmation, because getting past the first turn is a well-
#     defined event (manager said hi, now wants rapport). Later transitions
#     keep 2 confirmations to avoid oscillation in objection/appointment
#     territory where markers may coincidentally pop up in unrelated talk.
HYSTERESIS_CONFIRMATIONS_BY_STAGE: dict[int, int] = {
    1: 1,  # greeting → contact (main fix — users were stuck here)
    2: 2,  # contact → qualification
    3: 2,  # qualification → presentation
    4: 2,  # presentation → objections
    5: 2,  # objections → appointment
    6: 1,  # appointment → closing (soft entry — one solid signal enough)
    7: 1,  # closing terminal
}

# Legacy constant kept so imports don't break (some tests reference it).
# Use HYSTERESIS_CONFIRMATIONS_BY_STAGE.get(state.current_stage, 2) in code.
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

    # 2026-04-23 Sprint 2 — post-session analytics fields.
    # skipped_stages: stages that were marked completed with score=0 because
    #   the manager jumped over them (e.g. greeting → qualification directly).
    #   Used by frontend ScriptPanel to show ⚠️ skip badge and by /results
    #   ScriptProgressReport to show ✗ in the table.
    skipped_stages: list[int] = field(default_factory=list)
    # stage_started_at_msg: {stage_num: message_index when stage became current}
    #   Used to compute stage_message_counts in build_scoring_details.
    stage_started_at_msg: dict[int, int] = field(default_factory=dict)
    # stage_started_at_ts: {stage_num: unix timestamp when stage became current}
    #   Used to compute stage_durations_sec (how long user spent on each stage).
    stage_started_at_ts: dict[int, float] = field(default_factory=dict)
    # stage_durations_sec: {stage_num: seconds spent on stage} — filled on transition
    stage_durations_sec: dict[int, float] = field(default_factory=dict)
    # stage_message_counts: {stage_num: number of user messages while on stage}
    stage_message_counts: dict[int, int] = field(default_factory=dict)


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
        import time as _time
        _now = _time.time()
        state = StageState(
            current_stage=1,
            current_stage_name="greeting",
            stages_completed=[],
            stage_scores={},
            total_stages=total_stages,
            last_detected_at=0,
            confidence=1.0,
            # 2026-04-23 Sprint 2: seed stage 1 start metadata so duration
            # tracking works even if session ends before any transition.
            stage_started_at_msg={1: 0},
            stage_started_at_ts={1: _now},
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
                    # 2026-04-23 Sprint 2: cap denominator so expanded
                    # marker pools don't dilute signal (see TRANSITION_THRESHOLD).
                    _denom = min(MARKER_DENOMINATOR_CAP, len(kw["markers"])) or 1
                    score = matched / _denom * 0.5  # Half weight for client msgs
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
            _denom_cur = min(MARKER_DENOMINATOR_CAP, len(current_kw["markers"])) or 1
            score = current_matched / _denom_cur
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

            # 2026-04-23 Sprint 2: capped denominator so expanded pools
            # don't dilute (see TRANSITION_THRESHOLD comment).
            _denom = min(MARKER_DENOMINATOR_CAP, len(kw["markers"])) or 1
            score = matched / _denom

            # Penalty for transitioning too early
            if message_index < kw["min_messages"]:
                score *= 0.5

            if score > best_score and score >= TRANSITION_THRESHOLD:
                best_score = score
                best_match_stage = check_stage

        # ── Hysteresis (2026-04-23 Sprint 2: soft-decay + per-stage) ──
        # Require N consecutive messages confirming the same candidate
        # stage before transitioning. N varies per current stage:
        # HYSTERESIS_CONFIRMATIONS_BY_STAGE[state.current_stage]. The
        # previous design cleared ALL pending confirmations on any non-
        # matching message — a single off-topic reply between two contact-
        # cues reset progress. Now we DECREMENT by 1 (floor 0), so one
        # interruption doesn't kill the run; two consecutive do.
        if best_match_stage is not None:
            state.transition_confirmations[best_match_stage] = (
                state.transition_confirmations.get(best_match_stage, 0) + 1
            )
            # Other candidates get soft decay too (they drifted).
            for k in list(state.transition_confirmations):
                if k != best_match_stage:
                    state.transition_confirmations[k] = max(
                        0, state.transition_confirmations[k] - 1
                    )
                    if state.transition_confirmations[k] == 0:
                        del state.transition_confirmations[k]
        else:
            # No match this turn — soft-decay instead of hard clear. One
            # neutral message shouldn't invalidate all prior progress.
            for k in list(state.transition_confirmations):
                state.transition_confirmations[k] = max(
                    0, state.transition_confirmations[k] - 1
                )
                if state.transition_confirmations[k] == 0:
                    del state.transition_confirmations[k]

        # ── Apply transition (only after enough confirmations) ──
        needed_confirmations = HYSTERESIS_CONFIRMATIONS_BY_STAGE.get(
            state.current_stage, HYSTERESIS_CONFIRMATIONS,
        )
        if (
            best_match_stage is not None
            and state.transition_confirmations.get(best_match_stage, 0) >= needed_confirmations
        ):
            # Clear confirmation counter on successful transition
            state.transition_confirmations.clear()

            # 2026-04-23 Sprint 2: close out the current stage with duration
            # and message count before moving on. Used by /results
            # ScriptProgressReport.
            import time as _time
            _now = _time.time()
            _started_ts = state.stage_started_at_ts.get(state.current_stage)
            if _started_ts is not None:
                state.stage_durations_sec[state.current_stage] = round(_now - _started_ts, 1)
            _started_msg = state.stage_started_at_msg.get(state.current_stage)
            if _started_msg is not None:
                state.stage_message_counts[state.current_stage] = max(
                    0, message_index - _started_msg,
                )

            # Mark current stage as completed
            if state.current_stage not in state.stages_completed:
                state.stages_completed.append(state.current_stage)
                # If no score recorded yet, give partial credit
                if state.current_stage not in state.stage_scores:
                    state.stage_scores[state.current_stage] = 0.3

            # Mark any skipped stages — track in BOTH stages_completed (with
            # score=0) AND a dedicated skipped_stages list so /results can
            # differentiate «passed» from «skipped».
            newly_skipped: list[int] = []
            for skipped in range(state.current_stage + 1, best_match_stage):
                if skipped not in state.stages_completed:
                    state.stages_completed.append(skipped)
                    state.stage_scores[skipped] = 0.0
                    if skipped not in state.skipped_stages:
                        state.skipped_stages.append(skipped)
                    # Skipped stages have zero duration / msgs — still record.
                    state.stage_durations_sec[skipped] = 0.0
                    state.stage_message_counts[skipped] = 0
                    newly_skipped.append(skipped)

            # Advance to new stage + record its start timestamp so we can
            # compute duration when IT transitions next.
            state.current_stage = best_match_stage
            state.current_stage_name = STAGE_ORDER[best_match_stage - 1]
            state.last_detected_at = message_index
            state.confidence = min(1.0, best_score * 3)
            state.stage_started_at_msg[best_match_stage] = message_index
            state.stage_started_at_ts[best_match_stage] = _now

            await self._save_state(state)
            return state, True, newly_skipped

        # ── Auto-complete greeting after first few messages ──
        # 2026-04-29 (User-first Bug 2): generalised auto-advance ceiling.
        # Pre-fix this fallback only fired for stage 1 (greeting). Stages
        # 2-6 had no ceiling, so a manager who didn't say magic keywords
        # was stuck on the same stage forever — field-reported as "после
        # 2 шага я уже сделал все но нихуя". The script panel dots
        # appeared "статичны" because nothing was moving them.
        #
        # Now: if we've been on the current stage for max_messages user
        # messages without a keyword-driven transition, force advance to
        # the next stage with minimal score credit (0.1) — same behaviour
        # the original stage-1 fallback used. Closing (stage 7) is
        # terminal — never auto-advance past it.
        _stage_idx = state.current_stage  # 1-based
        _is_advanceable = 1 <= _stage_idx <= len(STAGE_ORDER) - 1
        if _is_advanceable and _stage_idx not in state.stages_completed:
            _cur_name = STAGE_ORDER[_stage_idx - 1]
            _max_msgs = STAGE_KEYWORDS[_cur_name].get("max_messages")
            if _max_msgs is not None and message_index >= _max_msgs:
                import time as _time
                _now = _time.time()
                _started_ts = state.stage_started_at_ts.get(_stage_idx)
                if _started_ts is not None:
                    state.stage_durations_sec[_stage_idx] = round(_now - _started_ts, 1)
                state.stage_message_counts[_stage_idx] = message_index

                state.stages_completed.append(_stage_idx)
                if _stage_idx not in state.stage_scores:
                    state.stage_scores[_stage_idx] = 0.1  # Minimal credit
                _next_idx = _stage_idx + 1
                state.current_stage = _next_idx
                state.current_stage_name = STAGE_ORDER[_next_idx - 1]
                state.last_detected_at = message_index
                state.confidence = 0.5
                state.stage_started_at_msg[_next_idx] = message_index
                state.stage_started_at_ts[_next_idx] = _now
                # Clear any pending hysteresis confirmations — they are
                # for the OLD stage's transition candidates, irrelevant now.
                state.transition_confirmations.clear()

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
        """Build data for session.scoring_details['_stage_progress'].

        2026-04-23 Sprint 2: extended with durations, message counts and
        explicit skipped_stages list — consumed by /results
        ScriptProgressReport to render the per-stage table with
        ✓/✗/— states and time spent per stage.
        """
        # Ensure current stage has a rolling duration computed even if
        # the session ends mid-stage (no transition triggered).
        import time as _time
        _now = _time.time()
        _started_ts = state.stage_started_at_ts.get(state.current_stage)
        durations = dict(state.stage_durations_sec)
        if _started_ts is not None and state.current_stage not in durations:
            durations[state.current_stage] = round(_now - _started_ts, 1)

        msg_counts = dict(state.stage_message_counts)
        if (
            state.current_stage not in msg_counts
            and state.stage_started_at_msg.get(state.current_stage) is not None
        ):
            msg_counts[state.current_stage] = max(
                0, state.last_detected_at - state.stage_started_at_msg[state.current_stage],
            )

        return {
            "stages_completed": sorted(state.stages_completed),
            "stage_scores": {str(k): round(v, 3) for k, v in state.stage_scores.items()},
            "skipped_stages": sorted(state.skipped_stages),
            "stage_durations_sec": {str(k): v for k, v in durations.items()},
            "stage_message_counts": {str(k): v for k, v in msg_counts.items()},
            "final_stage": state.current_stage,
            "final_stage_name": state.current_stage_name,
            "total_stages": state.total_stages,
        }

    # ── Stage-Aware AI Prompt Builder ──

    def build_stage_prompt(self, state: StageState) -> str:
        """Build a comprehensive prompt section for the LLM describing current stage behavior.

        This replaces the simple [CURRENT_STAGE: ...] tag with detailed behavioral rules
        including how to act, what info to reveal, and relevant trap categories.

        Sprint 0 §A (User-first 2026-04-29): when CALL_HUMANIZED_V2 is on, the
        section is reframed from imperative directives ("ПОВЕДЕНИЕ НА ЭТОМ
        ЭТАПЕ: Ты настороженный...") to descriptive context with an explicit
        permission to follow the manager's actual question off-script. The
        original wording was effectively locking the AI into the stage role
        and producing the "скрипт блокирует" UX bug — manager asks about
        messengers mid-greeting, AI keeps replying like a wary stranger.
        """
        # Lazy local import: keeps the test-time import graph independent of
        # settings (some tests import this module without app.config available).
        from app.config import settings

        humanized = bool(settings.call_humanized_v2)

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

        if humanized:
            # New: descriptive frame + explicit off-script permission.
            if behavior.get("behavior"):
                parts.append(
                    f"ЕСТЕСТВЕННОЕ СОСТОЯНИЕ КЛИЕНТА В ЭТОТ МОМЕНТ: {behavior['behavior']}"
                )
            if behavior.get("info_reveal"):
                parts.append(
                    f"ЧТО УМЕСТНО РАСКРЫТЬ ПО НАСТРОЕНИЮ: {behavior['info_reveal']}"
                )
        else:
            # Legacy imperative — preserved bit-for-bit when flag is off.
            if behavior.get("behavior"):
                parts.append(f"ПОВЕДЕНИЕ НА ЭТОМ ЭТАПЕ: {behavior['behavior']}")
            if behavior.get("info_reveal"):
                parts.append(f"ЧТО МОЖЕШЬ РАСКРЫТЬ: {behavior['info_reveal']}")

        # Relevant trap categories — same in both modes.
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

        if humanized:
            # Sprint 0 §A: the master rule that fixes "скрипт блокирует". The
            # stage context above is a HINT about the natural mood, NOT a
            # script. If the manager goes off-script and asks an unrelated
            # question, the client must answer the question — not yank the
            # manager back to the checklist.
            parts.append(
                "ВАЖНО (свобода ответа): этап — это контекст, а не сценарий. "
                "Если менеджер задаёт вопрос вне темы этапа (например про "
                "мессенджеры на этапе знакомства, или про график при возражениях), "
                "отвечай ПО ЕГО ВОПРОСУ естественным языком. Не возвращай его "
                "на этап силой, не игнорируй его реальный вопрос."
            )

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
        # Short keys kept for compactness + backward-compat with old Redis
        # entries. New 2026-04-23 Sprint 2 fields get their own short keys
        # (sk, sm, st, sd, mc) so a fresh writer + old reader just ignores
        # unknown keys, and vice versa via .get() defaults.
        data = {
            "cs": state.current_stage,
            "cn": state.current_stage_name,
            "sc": state.stages_completed,
            "ss": {str(k): v for k, v in state.stage_scores.items()},
            "ts": state.total_stages,
            "ld": state.last_detected_at,
            "cf": state.confidence,
            "tc": {str(k): v for k, v in state.transition_confirmations.items()},
            "sk": state.skipped_stages,
            "sm": {str(k): v for k, v in state.stage_started_at_msg.items()},
            "st": {str(k): v for k, v in state.stage_started_at_ts.items()},
            "sd": {str(k): v for k, v in state.stage_durations_sec.items()},
            "mc": {str(k): v for k, v in state.stage_message_counts.items()},
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
                skipped_stages=data.get("sk", []),
                stage_started_at_msg={int(k): v for k, v in data.get("sm", {}).items()},
                stage_started_at_ts={int(k): v for k, v in data.get("st", {}).items()},
                stage_durations_sec={int(k): v for k, v in data.get("sd", {}).items()},
                stage_message_counts={int(k): v for k, v in data.get("mc", {}).items()},
            )
        except (json.JSONDecodeError, TypeError, KeyError):
            logger.warning("Corrupted stage state for session %s, resetting", self.session_id)
            return StageState()
