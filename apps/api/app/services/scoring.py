"""5-layer scoring engine (TZ section 7.6).

Layers (weights):
1. Script adherence  (0.25) — checkpoint keyword matching
2. Objection handling (0.20) — pattern detection in conversation
3. Communication      (0.20) — message quality heuristics
4. Emotional intel    (0.15) — emotion timeline analysis
5. Result             (0.20) — outcome indicators

Uses keyword/heuristic analysis for layers 2-5, script_checker for layer 1.
"""

import logging
import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scenario import Scenario
from app.models.training import Message, MessageRole, TrainingSession
from app.services.script_checker import get_session_checkpoint_progress

logger = logging.getLogger(__name__)


@dataclass
class ScoreBreakdown:
    script_adherence: float
    objection_handling: float
    communication: float
    emotional: float
    result: float
    total: float
    details: dict = field(default_factory=dict)


# ─── Objection-handling patterns (Russian) ─────────────────────────────────

# Patterns indicating the character raised an objection
OBJECTION_PATTERNS = [
    r"не\s*(уверен|знаю|хочу|нужн|интересн)",
    r"зачем\s+мне",
    r"у\s+меня\s+уже\s+есть",
    r"дорого|ставк[аи]\s+выше",
    r"мне\s+нужно\s+подумать",
    r"сомневаюсь",
    r"не\s+вижу\s+смысл",
    r"в\s+другом\s+банке",
    r"скрыт.+комисси",
    r"а\s+вдруг",
    r"а\s+если",
    r"боюсь",
    r"гарантии",
]

# Patterns indicating the manager acknowledged the objection
ACKNOWLEDGE_PATTERNS = [
    r"(я\s+)?вас?\s+понимаю",
    r"понимаю\s+ваш[еу]",
    r"вы\s+правы",
    r"хорош(ий|ая)\s+вопрос",
    r"справедлив",
    r"согласен",
    r"конечно",
    r"действительно",
    r"резонн",
]

# Patterns for clarifying question
CLARIFY_PATTERNS = [
    r"а\s+почему",
    r"расскажите\s+подробнее",
    r"что\s+именно\s+(вас|вам)",
    r"можете\s+уточнить",
    r"что\s+для\s+вас\s+важно",
    r"какой\s+опыт",
    r"с\s+чем\s+связан",
]

# Patterns for argumented response
ARGUMENT_PATTERNS = [
    r"\d+\s*%",
    r"\d+\s*(рублей|тысяч|млн|руб)",
    r"например",
    r"в\s+отличие\s+от",
    r"преимущество",
    r"выгод[аы]",
    r"экономи[тья]",
    r"снижа[ея]т",
    r"потому\s+что",
    r"дело\s+в\s+том",
]

# Patterns indicating objection was checked/resolved
CHECK_PATTERNS = [
    r"это\s+отвечает",
    r"снял[аи]?\s+(ваш|этот)",
    r"остались\s+.*вопрос",
    r"что\s+думаете",
    r"как\s+вам",
    r"устраивает",
    r"подходит",
]


def _has_pattern(text: str, patterns: list[str]) -> bool:
    text_lower = text.lower()
    return any(re.search(p, text_lower) for p in patterns)


def _score_objection_handling(
    user_messages: list[str],
    assistant_messages: list[str],
    pairs: list[tuple[str, str]],
) -> tuple[float, dict]:
    """Score objection handling (0-100).

    Scoring per scoring_instructions.md:
    - Heard the objection (didn't ignore): +20
    - Acknowledged ("I understand"): +20
    - Clarified the reason: +20
    - Gave argumented answer: +20
    - Checked if resolved: +20
    """
    # Find objections in assistant messages (character = assistant)
    objections_found = 0
    for msg in assistant_messages:
        if _has_pattern(msg, OBJECTION_PATTERNS):
            objections_found += 1

    if objections_found == 0:
        # No objections raised — give full score (nothing to handle)
        return 100.0, {"objections_found": 0, "note": "no objections raised"}

    # Check manager (user) responses after objections
    heard = False
    acknowledged = False
    clarified = False
    argued = False
    checked = False

    for user_msg in user_messages:
        if not heard:
            # Manager responded at all after objection = heard
            heard = True
        if _has_pattern(user_msg, ACKNOWLEDGE_PATTERNS):
            acknowledged = True
        if _has_pattern(user_msg, CLARIFY_PATTERNS):
            clarified = True
        if _has_pattern(user_msg, ARGUMENT_PATTERNS):
            argued = True
        if _has_pattern(user_msg, CHECK_PATTERNS):
            checked = True

    score = 0.0
    if heard:
        score += 20
    if acknowledged:
        score += 20
    if clarified:
        score += 20
    if argued:
        score += 20
    if checked:
        score += 20

    details = {
        "objections_found": objections_found,
        "heard": heard,
        "acknowledged": acknowledged,
        "clarified": clarified,
        "argued": argued,
        "checked": checked,
    }
    return score, details


def _score_communication(user_messages: list[str]) -> tuple[float, dict]:
    """Score communication skills (0-100).

    - Active listening (didn't interrupt — heuristic: reasonable message lengths): +25
    - Clear speech (no filler words/stuttering): +25
    - Appropriate pace (message length variance): +25
    - Politeness and professionalism: +25
    """
    if not user_messages:
        return 0.0, {"note": "no user messages"}

    score = 0.0
    details: dict = {}

    # 1. Active listening — messages not too long (not dominating)
    avg_len = sum(len(m) for m in user_messages) / len(user_messages)
    long_messages = sum(1 for m in user_messages if len(m) > 500)
    listening_score = 25.0
    if long_messages > len(user_messages) * 0.5:
        listening_score = 10.0  # Too many long monologues
    details["avg_message_length"] = round(avg_len, 1)
    details["long_messages_ratio"] = round(long_messages / len(user_messages), 2)
    score += listening_score

    # 2. Clear speech — check for filler words
    filler_patterns = [r"\bэээ\b", r"\bнуу+\b", r"\bтипа\b", r"\bкак\s+бы\b", r"\bвот\b"]
    filler_count = 0
    for msg in user_messages:
        for pat in filler_patterns:
            filler_count += len(re.findall(pat, msg.lower()))
    filler_ratio = filler_count / max(len(user_messages), 1)
    clarity_score = max(0, 25.0 - filler_ratio * 5)
    details["filler_count"] = filler_count
    score += clarity_score

    # 3. Appropriate pace — reasonable length variance
    if len(user_messages) > 1:
        lengths = [len(m) for m in user_messages]
        mean_len = sum(lengths) / len(lengths)
        variance = sum((l - mean_len) ** 2 for l in lengths) / len(lengths)
        cv = (variance ** 0.5) / max(mean_len, 1)  # coefficient of variation
        pace_score = 25.0 if cv < 1.5 else max(0, 25.0 - (cv - 1.5) * 10)
    else:
        pace_score = 20.0
    score += pace_score

    # 4. Politeness — check for polite markers
    polite_patterns = [
        r"здравствуйте",
        r"добрый\s+(день|вечер|утро)",
        r"спасибо",
        r"пожалуйста",
        r"будьте\s+добры",
        r"извините",
        r"благодар",
    ]
    polite_count = 0
    for msg in user_messages:
        for pat in polite_patterns:
            if re.search(pat, msg.lower()):
                polite_count += 1
    polite_score = min(25.0, 10.0 + polite_count * 5)
    details["polite_markers"] = polite_count
    score += polite_score

    return min(100.0, score), details


def _score_emotional_intelligence(
    emotion_timeline: list[dict],
    user_messages: list[str],
) -> tuple[float, dict]:
    """Score emotional intelligence (0-100).

    - Empathy (acknowledged client feelings): +25
    - Tone adaptation: +25
    - Conflict management (didn't escalate): +25
    - Positive emotion dynamics: +25
    """
    score = 0.0
    details: dict = {}

    # 1. Empathy — detect empathy markers in user (manager) messages
    empathy_patterns = [
        r"понимаю.*(чувств|переживан|ситуаци)",
        r"на\s+вашем\s+месте",
        r"это\s+(важно|неприятно|сложно)",
        r"вас\s+понимаю",
        r"(ваши?\s+)?беспокойств",
    ]
    empathy_found = any(
        _has_pattern(msg, empathy_patterns) for msg in user_messages
    )
    empathy_score = 25.0 if empathy_found else 5.0
    details["empathy_detected"] = empathy_found
    score += empathy_score

    # 2. Tone adaptation — hard to detect from text alone, give base score
    # If manager uses varied sentence structures, assume some adaptation
    if len(user_messages) >= 3:
        adaptation_score = 15.0  # Base — can't fully assess from text
    else:
        adaptation_score = 10.0
    score += adaptation_score
    details["tone_adaptation_base"] = adaptation_score

    # 3. Conflict management — check no aggressive patterns from manager
    aggressive_manager = [
        r"сами\s+виноваты",
        r"это\s+не\s+моя\s+проблема",
        r"вы\s+не\s+понимаете",
        r"послушайте\s+меня",
        r"я\s+вам\s+говорю",
    ]
    escalated = any(
        _has_pattern(msg, aggressive_manager) for msg in user_messages
    )
    conflict_score = 5.0 if escalated else 25.0
    details["escalation_detected"] = escalated
    score += conflict_score

    # 4. Positive emotion dynamics — analyze timeline
    if emotion_timeline and len(emotion_timeline) >= 2:
        states = [e.get("state", "cold") for e in emotion_timeline]
        state_values = {"cold": 0, "warming": 1, "open": 2}
        values = [state_values.get(s, 0) for s in states]

        first_val = values[0]
        last_val = values[-1]
        max_val = max(values)

        if last_val > first_val:
            dynamic_score = 25.0  # Improved
        elif last_val == first_val and max_val > first_val:
            dynamic_score = 15.0  # Peaked but returned
        elif last_val == first_val:
            dynamic_score = 10.0  # No change
        else:
            dynamic_score = 5.0  # Got worse

        details["emotion_start"] = states[0]
        details["emotion_end"] = states[-1]
        details["emotion_peak"] = max(states, key=lambda s: state_values.get(s, 0))
    else:
        dynamic_score = 10.0
        details["emotion_timeline_length"] = len(emotion_timeline) if emotion_timeline else 0

    score += dynamic_score

    return min(100.0, score), details


def _score_result(
    assistant_messages: list[str],
    emotion_timeline: list[dict],
    session_duration_seconds: int | None,
) -> tuple[float, dict]:
    """Score result/outcome (0-100).

    - Client didn't hang up: +20
    - Client revealed their situation: +20
    - Client asked about the product: +20
    - Client agreed to next step: +20
    - Client scheduled specific time: +20
    """
    score = 0.0
    details: dict = {}

    # 1. Client didn't hang up — if session ended normally (has messages)
    if assistant_messages:
        score += 20.0
        details["completed_conversation"] = True
    else:
        details["completed_conversation"] = False
        return score, details

    # 2. Client revealed situation — check for personal info sharing
    reveal_patterns = [
        r"у\s+меня\s+(есть|был|компания|бизнес|фирма)",
        r"мы\s+(работаем|занимаемся|используем)",
        r"наш[аеи]?\s+(компания|фирма|бизнес)",
        r"оборот|выручк|прибыл",
        r"сотрудник",
        r"я\s+(работаю|руковожу|владею|занимаюсь)",
    ]
    revealed = any(
        _has_pattern(msg, reveal_patterns) for msg in assistant_messages
    )
    if revealed:
        score += 20.0
    details["client_revealed_situation"] = revealed

    # 3. Client asked about product
    product_q_patterns = [
        r"а\s+(как|какие|сколько|что)",
        r"расскажите\s+подробнее",
        r"а\s+если\s+я",
        r"какие\s+условия",
        r"что\s+включает",
        r"интересно",
    ]
    asked_questions = any(
        _has_pattern(msg, product_q_patterns) for msg in assistant_messages
    )
    if asked_questions:
        score += 20.0
    details["client_asked_questions"] = asked_questions

    # 4. Client agreed to next step
    agree_patterns = [
        r"(ладно|хорошо|давайте)",
        r"присылайте",
        r"можно\s+попробовать",
        r"согласен|согласна",
        r"предложение",
        r"перезвоните",
    ]
    agreed = any(
        _has_pattern(msg, agree_patterns) for msg in assistant_messages
    )
    if agreed:
        score += 20.0
    details["client_agreed_next_step"] = agreed

    # 5. Client scheduled specific time
    time_patterns = [
        r"(в\s+)?(понедельник|вторник|сред[уы]|четверг|пятниц[уы]|суббот[уы]|воскресенье)",
        r"\d{1,2}[:.]\d{2}",
        r"(завтра|послезавтра|на\s+следующей)",
        r"(утром|вечером|днём|после\s+обеда)",
        r"когда\s+можем\s+встретиться",
        r"назнач(им|ить|ьте)",
    ]
    scheduled = any(
        _has_pattern(msg, time_patterns) for msg in assistant_messages
    )
    if scheduled:
        score += 20.0
    details["client_scheduled_time"] = scheduled

    return score, details


async def calculate_scores(
    session_id: str | uuid.UUID,
    db: AsyncSession,
) -> ScoreBreakdown:
    """Calculate 5-layer scores for a completed training session.

    Retrieves messages, emotion timeline, and script progress, then
    computes each layer score according to scoring_instructions.md.
    """
    if isinstance(session_id, str):
        session_id = uuid.UUID(session_id)

    # Load session
    result = await db.execute(
        select(TrainingSession).where(TrainingSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        logger.error("Session %s not found for scoring", session_id)
        return ScoreBreakdown(0, 0, 0, 0, 0, 0, {"error": "session_not_found"})

    # Load messages
    msg_result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.sequence_number)
    )
    messages = msg_result.scalars().all()

    user_messages = [m.content for m in messages if m.role == MessageRole.user]
    assistant_messages = [m.content for m in messages if m.role == MessageRole.assistant]
    pairs = []
    for m in messages:
        if m.role == MessageRole.user:
            pairs.append((m.content, ""))
        elif m.role == MessageRole.assistant and pairs:
            pairs[-1] = (pairs[-1][0], m.content)

    emotion_timeline = session.emotion_timeline or []

    all_details: dict = {}

    # ── Layer 1: Script adherence (weight 0.25) ──
    script_score = 0.0
    script_details: dict = {"note": "no script assigned"}

    # Find script_id from scenario
    scenario_result = await db.execute(
        select(Scenario).where(Scenario.id == session.scenario_id)
    )
    scenario = scenario_result.scalar_one_or_none()

    if scenario and scenario.script_id:
        message_history = [
            {"role": m.role.value, "content": m.content}
            for m in messages
        ]
        progress = await get_session_checkpoint_progress(
            scenario.script_id, message_history
        )
        script_score = progress["total_score"]
        script_details = {
            "checkpoints": progress["checkpoints"],
            "reached_count": progress["reached_count"],
            "total_count": progress["total_count"],
        }

    all_details["script_adherence"] = script_details

    # ── Layer 2: Objection handling (weight 0.20) ──
    objection_score, objection_details = _score_objection_handling(
        user_messages, assistant_messages, pairs
    )
    all_details["objection_handling"] = objection_details

    # ── Layer 3: Communication (weight 0.20) ──
    comm_score, comm_details = _score_communication(user_messages)
    all_details["communication"] = comm_details

    # ── Layer 4: Emotional intelligence (weight 0.15) ──
    emotional_score, emotional_details = _score_emotional_intelligence(
        emotion_timeline, user_messages
    )
    all_details["emotional"] = emotional_details

    # ── Layer 5: Result (weight 0.20) ──
    result_score, result_details = _score_result(
        assistant_messages, emotion_timeline, session.duration_seconds
    )
    all_details["result"] = result_details

    # ── Total weighted score ──
    total = (
        script_score * 0.25
        + objection_score * 0.20
        + comm_score * 0.20
        + emotional_score * 0.15
        + result_score * 0.20
    )

    return ScoreBreakdown(
        script_adherence=round(script_score, 1),
        objection_handling=round(objection_score, 1),
        communication=round(comm_score, 1),
        emotional=round(emotional_score, 1),
        result=round(result_score, 1),
        total=round(total, 1),
        details=all_details,
    )
