"""5-layer scoring engine per TZ v3.0 section 7.6.

Layers (points):
1. Script adherence  (30 pts) — checkpoint cosine similarity via script_checker
2. Objection handling (25 pts) — recognized/acknowledged/argued/returned
3. Communication      (20 pts) — empathy/listening/pace/control
4. Anti-patterns      (-15 pts penalty) — false promises/intimidation/rudeness/incorrect info
5. Result             (+10 pts bonus) — consultation booked / callback agreed

Total range: 0-100 (30+25+20 = 75 base, -15 penalty, +10 bonus)
"""

import logging
import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scenario import Scenario
from app.models.training import Message, MessageRole, TrainingSession
from app.services.script_checker import detect_anti_patterns, get_session_checkpoint_progress

logger = logging.getLogger(__name__)


@dataclass
class ScoreBreakdown:
    script_adherence: float
    objection_handling: float
    communication: float
    anti_patterns: float
    result: float
    total: float
    details: dict = field(default_factory=dict)


# ─── Objection-handling patterns (Russian) ─────────────────────────────────

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

CLARIFY_PATTERNS = [
    r"а\s+почему",
    r"расскажите\s+подробнее",
    r"что\s+именно\s+(вас|вам)",
    r"можете\s+уточнить",
    r"что\s+для\s+вас\s+важно",
    r"какой\s+опыт",
    r"с\s+чем\s+связан",
]

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
) -> tuple[float, dict]:
    """Score objection handling (0-25 pts).

    Per TZ: recognized(5) + acknowledged(5) + clarified(5) + argued(5) + checked(5) = 25
    """
    objections_found = 0
    for msg in assistant_messages:
        if _has_pattern(msg, OBJECTION_PATTERNS):
            objections_found += 1

    if objections_found == 0:
        return 25.0, {"objections_found": 0, "note": "no objections raised"}

    heard = False
    acknowledged = False
    clarified = False
    argued = False
    checked = False

    for user_msg in user_messages:
        if not heard:
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
        score += 5
    if acknowledged:
        score += 5
    if clarified:
        score += 5
    if argued:
        score += 5
    if checked:
        score += 5

    return score, {
        "objections_found": objections_found,
        "heard": heard,
        "acknowledged": acknowledged,
        "clarified": clarified,
        "argued": argued,
        "checked": checked,
    }


def _score_communication(user_messages: list[str]) -> tuple[float, dict]:
    """Score communication skills (0-20 pts).

    Per TZ: empathy(5) + active listening(5) + pace(5) + conversation control(5) = 20
    """
    if not user_messages:
        return 0.0, {"note": "no user messages"}

    score = 0.0
    details: dict = {}

    # 1. Empathy (5 pts)
    empathy_patterns = [
        r"понимаю.*(чувств|переживан|ситуаци)",
        r"на\s+вашем\s+месте",
        r"это\s+(важно|неприятно|сложно)",
        r"вас\s+понимаю",
        r"(ваши?\s+)?беспокойств",
        r"сочувств",
    ]
    empathy_found = any(_has_pattern(msg, empathy_patterns) for msg in user_messages)
    empathy_score = 5.0 if empathy_found else 1.0
    details["empathy_detected"] = empathy_found
    score += empathy_score

    # 2. Active listening (5 pts) — not dominating conversation
    avg_len = sum(len(m) for m in user_messages) / len(user_messages)
    long_messages = sum(1 for m in user_messages if len(m) > 500)
    listening_score = 5.0
    if long_messages > len(user_messages) * 0.5:
        listening_score = 2.0
    details["avg_message_length"] = round(avg_len, 1)
    score += listening_score

    # 3. Pace (5 pts) — reasonable length variance
    if len(user_messages) > 1:
        lengths = [len(m) for m in user_messages]
        mean_len = sum(lengths) / len(lengths)
        variance = sum((l - mean_len) ** 2 for l in lengths) / len(lengths)
        cv = (variance ** 0.5) / max(mean_len, 1)
        pace_score = 5.0 if cv < 1.5 else max(0, 5.0 - (cv - 1.5) * 2)
    else:
        pace_score = 4.0
    score += pace_score

    # 4. Conversation control (5 pts) — politeness markers
    polite_patterns = [
        r"здравствуйте", r"добрый\s+(день|вечер|утро)",
        r"спасибо", r"пожалуйста", r"будьте\s+добры",
        r"извините", r"благодар",
    ]
    polite_count = 0
    for msg in user_messages:
        for pat in polite_patterns:
            if re.search(pat, msg.lower()):
                polite_count += 1
    control_score = min(5.0, 2.0 + polite_count * 1.0)
    details["polite_markers"] = polite_count
    score += control_score

    return min(20.0, score), details


async def _score_anti_patterns(user_messages: list[str]) -> tuple[float, dict]:
    """Score anti-patterns (0 to -15 penalty).

    Per TZ: false promises(-5) + intimidation(-5) + incorrect info(-5) = -15 max penalty
    """
    combined_text = " ".join(user_messages)
    detected = await detect_anti_patterns(combined_text)

    penalty = 0.0
    details: dict = {"detected": []}

    category_penalties = {
        "false_promises": -5.0,
        "intimidation": -5.0,
        "incorrect_info": -5.0,
    }

    for item in detected:
        cat = item["category"]
        pen = category_penalties.get(cat, -3.0)
        penalty += pen
        details["detected"].append({
            "category": cat,
            "score": item["score"],
            "penalty": pen,
        })

    penalty = max(-15.0, penalty)
    return penalty, details


def _score_result(
    assistant_messages: list[str],
    emotion_timeline: list[dict],
) -> tuple[float, dict]:
    """Score result/outcome (0-10 bonus pts).

    Per TZ: consultation agreed(5) + callback/meeting scheduled(5) = +10 max bonus
    """
    score = 0.0
    details: dict = {}

    if not assistant_messages:
        return 0.0, {"note": "no messages"}

    # 1. Consultation agreed (5 pts)
    agree_patterns = [
        r"(ладно|хорошо|давайте)",
        r"присылайте",
        r"можно\s+попробовать",
        r"согласен|согласна",
        r"расскажите\s+подробнее",
        r"интересно",
    ]
    agreed = any(_has_pattern(msg, agree_patterns) for msg in assistant_messages)
    if agreed:
        score += 5.0
    details["consultation_agreed"] = agreed

    # 2. Callback/meeting scheduled (5 pts)
    schedule_patterns = [
        r"(в\s+)?(понедельник|вторник|сред[уы]|четверг|пятниц[уы]|суббот[уы]|воскресенье)",
        r"\d{1,2}[:.]\d{2}",
        r"(завтра|послезавтра|на\s+следующей)",
        r"перезвоните",
        r"назнач(им|ить|ьте)",
        r"когда\s+можем\s+встретиться",
    ]
    scheduled = any(_has_pattern(msg, schedule_patterns) for msg in assistant_messages)
    if scheduled:
        score += 5.0
    details["meeting_scheduled"] = scheduled

    # Emotion bonus: if ended in "open" state
    if emotion_timeline:
        last_state = emotion_timeline[-1].get("state", "cold")
        if last_state == "open":
            details["ended_open"] = True

    return score, details


async def calculate_scores(
    session_id: str | uuid.UUID,
    db: AsyncSession,
) -> ScoreBreakdown:
    """Calculate 5-layer scores for a completed training session.

    Weights per TZ v3.0:
    - Layer 1: Script adherence = 30 pts
    - Layer 2: Objection handling = 25 pts
    - Layer 3: Communication = 20 pts
    - Layer 4: Anti-patterns = -15 pts (penalty)
    - Layer 5: Result = +10 pts (bonus)
    Total: 0-100
    """
    if isinstance(session_id, str):
        session_id = uuid.UUID(session_id)

    result = await db.execute(
        select(TrainingSession).where(TrainingSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        logger.error("Session %s not found for scoring", session_id)
        return ScoreBreakdown(0, 0, 0, 0, 0, 0, {"error": "session_not_found"})

    msg_result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.sequence_number)
    )
    messages = msg_result.scalars().all()

    user_messages = [m.content for m in messages if m.role == MessageRole.user]
    assistant_messages = [m.content for m in messages if m.role == MessageRole.assistant]

    emotion_timeline = session.emotion_timeline or []
    all_details: dict = {}

    # ── Layer 1: Script adherence (30 pts) ──
    script_score = 0.0
    script_details: dict = {"note": "no script assigned"}

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
        # Scale from 0-100 to 0-30
        script_score = progress["total_score"] * 0.3
        script_details = {
            "raw_score": progress["total_score"],
            "checkpoints": progress["checkpoints"],
            "reached_count": progress["reached_count"],
            "total_count": progress["total_count"],
        }

    all_details["script_adherence"] = script_details

    # ── Layer 2: Objection handling (25 pts) ──
    objection_score, objection_details = _score_objection_handling(
        user_messages, assistant_messages
    )
    all_details["objection_handling"] = objection_details

    # ── Layer 3: Communication (20 pts) ──
    comm_score, comm_details = _score_communication(user_messages)
    all_details["communication"] = comm_details

    # ── Layer 4: Anti-patterns (-15 pts penalty) ──
    anti_penalty, anti_details = await _score_anti_patterns(user_messages)
    all_details["anti_patterns"] = anti_details

    # ── Layer 5: Result (+10 pts bonus) ──
    result_score, result_details = _score_result(assistant_messages, emotion_timeline)
    all_details["result"] = result_details

    # ── Total: sum all layers, clamp to 0-100 ──
    total = script_score + objection_score + comm_score + anti_penalty + result_score
    total = max(0.0, min(100.0, total))

    return ScoreBreakdown(
        script_adherence=round(script_score, 1),
        objection_handling=round(objection_score, 1),
        communication=round(comm_score, 1),
        anti_patterns=round(anti_penalty, 1),
        result=round(result_score, 1),
        total=round(total, 1),
        details=all_details,
    )
