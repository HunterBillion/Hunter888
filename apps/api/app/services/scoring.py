"""10-layer scoring engine v5.0.

Weight distribution:
  Layers 1-7 (rescaled from v3): 75 pts total
    L1. Script adherence     (22.5 pts)  — was 30, ×0.75
    L2. Objection handling   (18.75 pts) — was 25, ×0.75
    L3. Communication        (15 pts)    — was 20, ×0.75
    L4. Anti-patterns        (-11.25 penalty) — was -15, ×0.75
    L5. Result               (7.5 pts)   — was 10, ×0.75
    L6. Chain traversal      (0-7.5 pts) — was 0-10, ×0.75
    L7. Trap handling        (-7.5 to +7.5) — was -10 to +10, ×0.75

  New layers:
    L8. Human Factor Handling (0-15 pts) — real-time
    L9. Narrative Progression (0-10 pts) — post-session only
    L10. Legal Accuracy       (±5 modifier) — post-session only

  Total: 0-100 (base 75 + L8 15 + L9 10 ± L10 5)

Real-time layers: 1-8 (sent via WS hints)
Post-session layers: 9-10 (computed after session end)

Skill radar mapping (6 skills):
  empathy           → L3.empathy(40%) + L8.patience(30%) + L8.empathy_check(30%)
  knowledge         → L1(30%) + L10(40%) + L7(30%)
  objection_handling → L2(50%) + L6(30%) + L7(20%)
  stress_resistance → L4(40%) + L8.composure(30%) + L3.pace(30%)
  closing           → L5(50%) + L9(30%) + L2.check(20%)
  qualification     → L1.discovery(40%) + L3.control(30%) + L3.listening(30%)
"""

import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scenario import Scenario
from app.models.training import Message, MessageRole, TrainingSession

logger = logging.getLogger(__name__)

# v3→v5 rescale factor: old 100pts → new 75pts
V3_RESCALE = 0.75


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ScoreBreakdown:
    """Full 10-layer score breakdown."""
    # Rescaled v3 layers (L1-L7)
    script_adherence: float       # L1: 0-22.5
    objection_handling: float     # L2: 0-18.75
    communication: float          # L3: 0-15
    anti_patterns: float          # L4: 0 to -11.25
    result: float                 # L5: 0-7.5
    chain_traversal: float        # L6: 0-7.5
    trap_handling: float          # L7: -7.5 to +7.5

    # New v5 layers
    human_factor: float           # L8: 0-15
    narrative_progression: float  # L9: 0-10
    legal_accuracy: float         # L10: -5 to +5

    total: float                  # 0-100 clamped
    details: dict = field(default_factory=dict)

    @property
    def base_score(self) -> float:
        """Sum of L1-L7 (the rescaled old layers)."""
        return (
            self.script_adherence
            + self.objection_handling
            + self.communication
            + self.anti_patterns
            + self.result
            + self.chain_traversal
            + self.trap_handling
        )

    @property
    def realtime_score(self) -> float:
        """Sum of L1-L8 (available during session via WS)."""
        return self.base_score + self.human_factor

    @property
    def skill_radar(self) -> dict[str, float]:
        """Compute 6-skill radar from layer scores. Returns 0-100 per skill."""
        details = self.details

        # ── empathy ──
        empathy_l3 = details.get("communication", {}).get("empathy_score", 0)
        empathy_l8_patience = details.get("human_factor", {}).get("patience_score", 0)
        empathy_l8_empathy = details.get("human_factor", {}).get("empathy_check_score", 0)
        empathy = (
            _normalize(empathy_l3, 5) * 0.4
            + _normalize(empathy_l8_patience, 5) * 0.3
            + _normalize(empathy_l8_empathy, 5) * 0.3
        ) * 100

        # ── knowledge ──
        knowledge_l1 = _normalize(self.script_adherence, 22.5) * 0.3
        knowledge_l10 = _normalize(self.legal_accuracy + 5, 10) * 0.4  # shift [-5,+5] to [0,10]
        knowledge_l7 = _normalize(self.trap_handling + 7.5, 15) * 0.3  # shift [-7.5,+7.5] to [0,15]
        knowledge = (knowledge_l1 + knowledge_l10 + knowledge_l7) * 100

        # ── objection_handling ──
        oh_l2 = _normalize(self.objection_handling, 18.75) * 0.5
        oh_l6 = _normalize(self.chain_traversal, 7.5) * 0.3
        oh_l7 = _normalize(self.trap_handling + 7.5, 15) * 0.2
        objection_handling = (oh_l2 + oh_l6 + oh_l7) * 100

        # ── stress_resistance ──
        sr_l4 = _normalize(self.anti_patterns + 11.25, 11.25) * 0.4  # shift [-11.25,0] to [0,11.25]
        sr_l8_composure = _normalize(
            details.get("human_factor", {}).get("composure_score", 0), 5
        ) * 0.3
        sr_l3_pace = _normalize(
            details.get("communication", {}).get("pace_score", 0), 5
        ) * 0.3
        stress_resistance = (sr_l4 + sr_l8_composure + sr_l3_pace) * 100

        # ── closing ──
        closing_l5 = _normalize(self.result, 7.5) * 0.5
        closing_l9 = _normalize(self.narrative_progression, 10) * 0.3
        closing_l2_check = _normalize(
            details.get("objection_handling", {}).get("check_score", 0), 5
        ) * 0.2
        closing = (closing_l5 + closing_l9 + closing_l2_check) * 100

        # ── qualification ──
        qual_l1_disc = _normalize(
            details.get("script_adherence", {}).get("discovery_score", 0), 10
        ) * 0.4
        qual_l3_ctrl = _normalize(
            details.get("communication", {}).get("control_score", 0), 5
        ) * 0.3
        qual_l3_listen = _normalize(
            details.get("communication", {}).get("listening_score", 0), 5
        ) * 0.3
        qualification = (qual_l1_disc + qual_l3_ctrl + qual_l3_listen) * 100

        return {
            "empathy": round(min(100, max(0, empathy)), 1),
            "knowledge": round(min(100, max(0, knowledge)), 1),
            "objection_handling": round(min(100, max(0, objection_handling)), 1),
            "stress_resistance": round(min(100, max(0, stress_resistance)), 1),
            "closing": round(min(100, max(0, closing)), 1),
            "qualification": round(min(100, max(0, qualification)), 1),
        }


def _normalize(value: float, max_value: float) -> float:
    """Normalize value to 0-1 range."""
    if max_value <= 0:
        return 0.0
    return max(0.0, min(1.0, value / max_value))


# ---------------------------------------------------------------------------
# Objection-handling patterns (Russian) — unchanged from v3
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Layer scoring functions
# ---------------------------------------------------------------------------

def _score_objection_handling(
    user_messages: list[str],
    assistant_messages: list[str],
) -> tuple[float, dict]:
    """L2: Objection handling (0-18.75 pts after rescale).

    Sub-scores (each 0-5 before rescale):
    recognized(5) + acknowledged(5) + clarified(5) + argued(5) + checked(5) = 25 → ×0.75 = 18.75
    """
    objections_found = 0
    for msg in assistant_messages:
        if _has_pattern(msg, OBJECTION_PATTERNS):
            objections_found += 1

    if objections_found == 0:
        return 18.75, {"objections_found": 0, "note": "no objections raised", "check_score": 5 * V3_RESCALE}

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

    raw_score = 0.0
    if heard:
        raw_score += 5
    if acknowledged:
        raw_score += 5
    if clarified:
        raw_score += 5
    if argued:
        raw_score += 5
    if checked:
        raw_score += 5

    check_raw = 5.0 if checked else 0.0

    return raw_score * V3_RESCALE, {
        "objections_found": objections_found,
        "heard": heard,
        "acknowledged": acknowledged,
        "clarified": clarified,
        "argued": argued,
        "checked": checked,
        "check_score": check_raw * V3_RESCALE,
    }


def _score_communication(user_messages: list[str]) -> tuple[float, dict]:
    """L3: Communication skills (0-15 pts after rescale).

    Sub-scores (each 0-5 before rescale):
    empathy(5) + listening(5) + pace(5) + control(5) = 20 → ×0.75 = 15
    """
    if not user_messages:
        return 0.0, {"note": "no user messages"}

    score = 0.0
    details: dict[str, Any] = {}

    # 1. Empathy (5 pts raw)
    empathy_patterns = [
        r"понимаю.*(чувств|переживан|ситуаци)",
        r"на\s+вашем\s+месте",
        r"это\s+(важно|неприятно|сложно)",
        r"вас\s+понимаю",
        r"(ваши?\s+)?беспокойств",
        r"сочувств",
    ]
    empathy_found = any(_has_pattern(msg, empathy_patterns) for msg in user_messages)
    empathy_raw = 5.0 if empathy_found else 1.0
    details["empathy_detected"] = empathy_found
    details["empathy_score"] = empathy_raw * V3_RESCALE
    score += empathy_raw

    # 2. Active listening (5 pts raw)
    avg_len = sum(len(m) for m in user_messages) / len(user_messages)
    long_messages = sum(1 for m in user_messages if len(m) > 500)
    listening_raw = 5.0
    if long_messages > len(user_messages) * 0.5:
        listening_raw = 2.0
    details["avg_message_length"] = round(avg_len, 1)
    details["listening_score"] = listening_raw * V3_RESCALE
    score += listening_raw

    # 3. Pace (5 pts raw)
    if len(user_messages) > 1:
        lengths = [len(m) for m in user_messages]
        mean_len = sum(lengths) / len(lengths)
        variance = sum((l - mean_len) ** 2 for l in lengths) / len(lengths)
        cv = (variance ** 0.5) / max(mean_len, 1)
        pace_raw = 5.0 if cv < 1.5 else max(0, 5.0 - (cv - 1.5) * 2)
    else:
        pace_raw = 4.0
    details["pace_score"] = pace_raw * V3_RESCALE
    score += pace_raw

    # 4. Conversation control (5 pts raw)
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
    control_raw = min(5.0, 2.0 + polite_count * 1.0)
    details["polite_markers"] = polite_count
    details["control_score"] = control_raw * V3_RESCALE
    score += control_raw

    return min(20.0, score) * V3_RESCALE, details


async def _score_anti_patterns(user_messages: list[str]) -> tuple[float, dict]:
    """L4: Anti-patterns (0 to -11.25 penalty after rescale).

    false promises(-5) + intimidation(-5) + incorrect info(-5) = -15 → ×0.75 = -11.25
    """
    from app.services.script_checker import detect_anti_patterns

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
            "penalty": pen * V3_RESCALE,
        })

    penalty = max(-15.0, penalty) * V3_RESCALE
    return penalty, details


def _score_result(
    assistant_messages: list[str],
    emotion_timeline: list[dict],
) -> tuple[float, dict]:
    """L5: Result/outcome (0-7.5 pts after rescale).

    consultation agreed(5) + callback/meeting scheduled(5) = 10 → ×0.75 = 7.5
    """
    score = 0.0
    details: dict = {}

    if not assistant_messages:
        return 0.0, {"note": "no messages"}

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

    if emotion_timeline:
        last_state = emotion_timeline[-1].get("state", "cold")
        if last_state in ("considering", "deal"):
            details["ended_positive"] = True
            details["final_emotion"] = last_state

    return score * V3_RESCALE, details


# ---------------------------------------------------------------------------
# L8: Human Factor Handling (0-15 pts) — NEW, real-time
# ---------------------------------------------------------------------------

def _score_human_factor(
    user_messages: list[str],
    assistant_messages: list[str],
    emotion_timeline: list[dict],
    custom_params: dict | None = None,
) -> tuple[float, dict]:
    """L8: Human Factor Handling (0-15 pts).

    Sub-layers:
    - Patience under aggression (0-5 pts): calm response to hostile/testing states
    - Empathy check (0-5 pts): emotional acknowledgment in negative states
    - Composure (0-5 pts): no counter-aggression, no panic phrases

    Also includes fake transition detection sub-score (bonus within patience).
    """
    score = 0.0
    details: dict[str, Any] = {}

    # ── Patience (0-5) ──
    hostile_turns = sum(
        1 for e in emotion_timeline
        if e.get("state") in ("hostile", "testing", "hangup")
    )
    total_turns = max(len(emotion_timeline), 1)
    hostile_ratio = hostile_turns / total_turns

    # Check if manager stayed calm during hostile states
    calm_during_hostile_patterns = [
        r"понимаю\s+(?:ваш[еу]?\s+)?(?:раздражение|недовольств|эмоц)",
        r"давайте\s+(?:спокойно|без\s+эмоц)",
        r"я\s+(?:вас?\s+)?слушаю",
        r"не\s+переживайте",
    ]
    aggressive_response_patterns = [
        r"(?:сам[иа]?\s+вы|да\s+вы\s+(?:что|как))",
        r"(?:не\s+кричите|хватит\s+(?:орать|кричать))",
        r"(?:грубит|хамит|невоспитанн)",
    ]

    calm_responses = 0
    aggressive_responses = 0
    for msg in user_messages:
        if _has_pattern(msg, calm_during_hostile_patterns):
            calm_responses += 1
        if _has_pattern(msg, aggressive_response_patterns):
            aggressive_responses += 1

    patience_score = 2.5  # base
    if hostile_ratio > 0.3:
        # Manager faced significant hostility
        if calm_responses >= 2 and aggressive_responses == 0:
            patience_score = 5.0
        elif calm_responses >= 1 and aggressive_responses == 0:
            patience_score = 4.0
        elif aggressive_responses > 0:
            patience_score = max(0, 2.5 - aggressive_responses * 1.0)
    elif hostile_ratio > 0:
        patience_score = 4.0 if aggressive_responses == 0 else 2.0
    else:
        patience_score = 3.0  # No hostility encountered — neutral score

    # Fake transition detection bonus (within patience)
    fake_detected = False
    if custom_params and custom_params.get("fake_transitions_detected"):
        fake_detected = True
        patience_score = min(5.0, patience_score + 1.0)
    details["patience_score"] = round(patience_score, 1)
    details["fake_detected"] = fake_detected
    score += patience_score

    # ── Empathy check (0-5) ──
    negative_states = {"cold", "guarded", "hostile", "hangup"}
    negative_turns = [
        i for i, e in enumerate(emotion_timeline)
        if e.get("state") in negative_states
    ]

    empathy_in_negative_patterns = [
        r"(?:понимаю|представляю)\s+(?:как|что|ваш|каково)",
        r"(?:это|ваша)\s+(?:ситуация|проблема|беспокойство)\s+(?:понятн|серьёзн|важн)",
        r"(?:многие|другие)\s+(?:клиенты|люди)\s+(?:тоже|также)\s+(?:переживают|боятся|сомневаются)",
        r"(?:вы\s+не\s+один|мы\s+вместе|я\s+(?:помогу|на\s+вашей\s+стороне))",
    ]

    empathy_check_score = 2.0  # base
    if negative_turns:
        empathy_matches = sum(
            1 for msg in user_messages
            if _has_pattern(msg, empathy_in_negative_patterns)
        )
        if empathy_matches >= 3:
            empathy_check_score = 5.0
        elif empathy_matches >= 2:
            empathy_check_score = 4.0
        elif empathy_matches >= 1:
            empathy_check_score = 3.0
        else:
            empathy_check_score = 1.0
    details["empathy_check_score"] = round(empathy_check_score, 1)
    score += empathy_check_score

    # ── Composure (0-5) ──
    panic_patterns = [
        r"(?:не\s+знаю\s+что\s+(?:делать|сказать)|я\s+(?:не\s+могу|теряюсь))",
        r"(?:подождите|секунду|минуточку|дайте\s+подумать)",
    ]
    panic_count = sum(1 for msg in user_messages if _has_pattern(msg, panic_patterns))

    composure_score = 5.0
    if aggressive_responses > 0:
        composure_score = max(0, composure_score - aggressive_responses * 2.0)
    if panic_count > 0:
        composure_score = max(0, composure_score - panic_count * 1.0)
    details["composure_score"] = round(composure_score, 1)
    details["aggressive_responses"] = aggressive_responses
    details["panic_count"] = panic_count
    score += composure_score

    return min(15.0, score), details


# ---------------------------------------------------------------------------
# L9: Narrative Progression (0-10 pts) — post-session only
# ---------------------------------------------------------------------------

async def _score_narrative_progression(
    session_id: uuid.UUID,
    emotion_timeline: list[dict],
    db: AsyncSession,
) -> tuple[float, dict]:
    """L9: Narrative Progression (0-10 pts, post-session).

    Sub-layers:
    - Emotion arc quality (0-4): did the conversation progress logically?
    - Call objective met (0-3): was the goal of this specific call achieved?
    - Story advancement (0-3): for multi-call stories, did this call advance the arc?
    """
    score = 0.0
    details: dict[str, Any] = {}

    # ── Emotion arc quality (0-4) ──
    if not emotion_timeline:
        details["arc_score"] = 0.0
        details["arc_note"] = "no timeline"
    else:
        states = [e.get("state", "cold") for e in emotion_timeline]
        positive_states = {"curious", "considering", "negotiating", "deal"}
        terminal_positive = {"deal", "callback"}

        # Did conversation progress forward at any point?
        peak_index = 0
        state_order = {
            "cold": 0, "guarded": 1, "hostile": -1, "hangup": -2,
            "testing": 2, "curious": 3, "callback": 4,
            "considering": 5, "negotiating": 6, "deal": 7,
        }
        peak_val = state_order.get(states[0], 0)
        for s in states:
            v = state_order.get(s, 0)
            if v > peak_val:
                peak_val = v
                peak_index = states.index(s)

        # Score based on peak reached and ending
        final_state = states[-1]
        final_val = state_order.get(final_state, 0)

        arc_score = 0.0
        if final_state in terminal_positive:
            arc_score = 4.0
        elif peak_val >= 5:
            arc_score = 3.0 if final_val >= 3 else 2.0
        elif peak_val >= 3:
            arc_score = 2.0 if final_val >= 1 else 1.0
        else:
            arc_score = 0.5

        details["arc_score"] = arc_score
        details["peak_state"] = states[peak_index] if states else "cold"
        details["final_state"] = final_state
        score += arc_score

    # ── Call objective (0-3) ──
    session_result = await db.execute(
        select(TrainingSession).where(TrainingSession.id == session_id)
    )
    session = session_result.scalar_one_or_none()
    objective_score = 0.0

    if session:
        # Check if session ended in a positive state
        emotion_tl = session.emotion_timeline or []
        if emotion_tl:
            last = emotion_tl[-1].get("state", "cold")
            if last == "deal":
                objective_score = 3.0
            elif last in ("callback", "considering", "negotiating"):
                objective_score = 2.0
            elif last in ("curious",):
                objective_score = 1.0

        # Multi-call bonus: check if this call was part of a story
        if session.client_story_id:
            objective_score = min(3.0, objective_score + 0.5)

    details["objective_score"] = objective_score
    score += objective_score

    # ── Story advancement (0-3) ──
    story_score = 0.0
    if session and session.client_story_id:
        from app.models.roleplay import ClientStory
        story_result = await db.execute(
            select(ClientStory).where(ClientStory.id == session.client_story_id)
        )
        story = story_result.scalar_one_or_none()
        if story:
            # Check progress through calls
            call_num = session.call_number_in_story or 1
            total_planned = story.total_calls_planned or 3
            progress_ratio = call_num / total_planned

            if story.is_completed:
                story_score = 3.0
            elif progress_ratio >= 0.66:
                story_score = 2.0
            elif progress_ratio >= 0.33:
                story_score = 1.5
            else:
                story_score = 1.0

            details["story_call"] = call_num
            details["story_total"] = total_planned
    details["story_score"] = story_score
    score += story_score

    return min(10.0, score), details


# ---------------------------------------------------------------------------
# L10: Legal Accuracy (±5 modifier) — post-session, delegates to legal_checker
# ---------------------------------------------------------------------------

async def _score_legal_accuracy(
    session_id: uuid.UUID,
    db: AsyncSession,
) -> tuple[float, dict]:
    """L10: Legal Accuracy (±5 modifier, post-session).

    Delegates to legal_checker.check_session_legal_accuracy().
    """
    try:
        from app.services.legal_checker import check_session_legal_accuracy
        result = await check_session_legal_accuracy(session_id, db)
        return result.total_score, {
            "checks_triggered": result.checks_triggered,
            "correct_cited": result.correct_cited,
            "correct": result.correct,
            "partial": result.partial,
            "incorrect": result.incorrect,
            "details": result.details[:10],  # Limit for JSONB storage
        }
    except Exception:
        logger.exception("Legal accuracy scoring failed for %s", session_id)
        return 0.0, {"error": "legal_checker_unavailable"}


# ---------------------------------------------------------------------------
# Real-time scoring (L1-L8) — called during session via WS
# ---------------------------------------------------------------------------

async def calculate_realtime_scores(
    session_id: str | uuid.UUID,
    db: AsyncSession,
) -> dict:
    """Calculate real-time scores (L1-L8) for WS hints during active session.

    Returns a dict suitable for WS emission, not full ScoreBreakdown.
    """
    if isinstance(session_id, str):
        session_id = uuid.UUID(session_id)

    result = await db.execute(
        select(TrainingSession).where(TrainingSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        return {"error": "session_not_found", "total": 0}

    msg_result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.sequence_number)
    )
    messages = msg_result.scalars().all()

    user_messages = [m.content for m in messages if m.role == MessageRole.user]
    assistant_messages = [m.content for m in messages if m.role == MessageRole.assistant]
    emotion_timeline = session.emotion_timeline or []

    # L2: Objection handling
    l2_score, _ = _score_objection_handling(user_messages, assistant_messages)

    # L3: Communication
    l3_score, _ = _score_communication(user_messages)

    # L8: Human Factor
    l8_score, _ = _score_human_factor(
        user_messages, assistant_messages, emotion_timeline,
        session.custom_params,
    )

    # Simplified real-time total (L2 + L3 + L8 as main indicators)
    realtime_est = l2_score + l3_score + l8_score

    return {
        "objection_handling": round(l2_score, 1),
        "communication": round(l3_score, 1),
        "human_factor": round(l8_score, 1),
        "realtime_estimate": round(realtime_est, 1),
        "max_possible_realtime": round(18.75 + 15 + 15, 1),  # 48.75
    }


# ---------------------------------------------------------------------------
# Full scoring (L1-L10) — called after session end
# ---------------------------------------------------------------------------

async def calculate_scores(
    session_id: str | uuid.UUID,
    db: AsyncSession,
) -> ScoreBreakdown:
    """Calculate full 10-layer scores for a completed training session.

    Layers 1-8: real-time capable
    Layers 9-10: post-session only
    Total: 0-100 clamped
    """
    if isinstance(session_id, str):
        session_id = uuid.UUID(session_id)

    result = await db.execute(
        select(TrainingSession).where(TrainingSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        logger.error("Session %s not found for scoring", session_id)
        return ScoreBreakdown(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, {"error": "session_not_found"})

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

    # ── L1: Script adherence (22.5 pts) ──
    script_score = 0.0
    script_details: dict = {"note": "no script assigned", "discovery_score": 0.0}

    scenario_result = await db.execute(
        select(Scenario).where(Scenario.id == session.scenario_id)
    )
    scenario = scenario_result.scalar_one_or_none()

    if scenario and scenario.script_id:
        from app.services.script_checker import get_session_checkpoint_progress
        message_history = [
            {"role": m.role.value, "content": m.content}
            for m in messages
        ]
        progress = await get_session_checkpoint_progress(
            scenario.script_id, message_history
        )
        raw_score = progress["total_score"]  # 0-100
        script_score = raw_score * 0.225  # Scale to 0-22.5
        script_details = {
            "raw_score": raw_score,
            "checkpoints": progress.get("checkpoints", []),
            "reached_count": progress.get("reached_count", 0),
            "total_count": progress.get("total_count", 0),
            "discovery_score": min(10.0, progress.get("reached_count", 0) * 2.5),
        }
    all_details["script_adherence"] = script_details

    # ── L2: Objection handling (18.75 pts) ──
    objection_score, objection_details = _score_objection_handling(
        user_messages, assistant_messages
    )
    all_details["objection_handling"] = objection_details

    # ── L3: Communication (15 pts) ──
    comm_score, comm_details = _score_communication(user_messages)
    all_details["communication"] = comm_details

    # ── L4: Anti-patterns (-11.25 penalty) ──
    anti_penalty, anti_details = await _score_anti_patterns(user_messages)
    all_details["anti_patterns"] = anti_details

    # ── L5: Result (7.5 pts) ──
    result_score, result_details = _score_result(assistant_messages, emotion_timeline)
    all_details["result"] = result_details

    # ── L6: Chain traversal (0-7.5 pts) ──
    chain_bonus = 0.0
    chain_details: dict = {"has_chain": False}
    try:
        from app.services.objection_chain import calculate_chain_score
        chain_data = await calculate_chain_score(session_id)
        chain_bonus = float(chain_data.get("chain_score", 0)) * V3_RESCALE
        chain_details = chain_data.get("chain_details", {})
    except Exception:
        logger.debug("Chain scoring unavailable for session %s", session_id)
    all_details["chain_traversal"] = chain_details

    # ── L7: Trap handling (-7.5 to +7.5) ──
    trap_score = 0.0
    trap_details: dict = {"traps": [], "net_score": 0}
    try:
        from app.services.trap_detector import get_session_trap_state
        trap_state = await get_session_trap_state(session_id)
        trap_score = float(trap_state.net_score) * V3_RESCALE
        trap_details = {
            "traps": [
                {
                    "name": t.trap_name,
                    "category": t.category,
                    "status": t.status,
                    "delta": t.score_delta * V3_RESCALE,
                }
                for t in trap_state.activated
            ],
            "total_penalty": trap_state.total_penalty * V3_RESCALE,
            "total_bonus": trap_state.total_bonus * V3_RESCALE,
            "net_score": trap_state.net_score * V3_RESCALE,
        }
    except Exception:
        logger.debug("Trap scoring unavailable for session %s", session_id)
    all_details["trap_handling"] = trap_details

    # ── L8: Human Factor Handling (0-15 pts) ──
    human_score, human_details = _score_human_factor(
        user_messages, assistant_messages, emotion_timeline,
        session.custom_params,
    )
    all_details["human_factor"] = human_details

    # ── L9: Narrative Progression (0-10 pts, post-session) ──
    narrative_score, narrative_details = await _score_narrative_progression(
        session_id, emotion_timeline, db
    )
    all_details["narrative_progression"] = narrative_details

    # ── L10: Legal Accuracy (±5 modifier, post-session) ──
    legal_score, legal_details = await _score_legal_accuracy(session_id, db)
    all_details["legal_accuracy"] = legal_details

    # ── Total: sum all layers, clamp to 0-100 ──
    total = (
        float(script_score or 0)       # L1: 0-22.5
        + float(objection_score or 0)  # L2: 0-18.75
        + float(comm_score or 0)       # L3: 0-15
        + float(anti_penalty or 0)     # L4: 0 to -11.25
        + float(result_score or 0)     # L5: 0-7.5
        + float(chain_bonus or 0)      # L6: 0-7.5
        + float(trap_score or 0)       # L7: -7.5 to +7.5
        + float(human_score or 0)      # L8: 0-15
        + float(narrative_score or 0)  # L9: 0-10
        + float(legal_score or 0)      # L10: -5 to +5
    )
    total = max(0.0, min(100.0, total))

    breakdown = ScoreBreakdown(
        script_adherence=round(script_score, 2),
        objection_handling=round(objection_score, 2),
        communication=round(comm_score, 2),
        anti_patterns=round(anti_penalty, 2),
        result=round(result_score, 2),
        chain_traversal=round(chain_bonus, 2),
        trap_handling=round(trap_score, 2),
        human_factor=round(human_score, 2),
        narrative_progression=round(narrative_score, 2),
        legal_accuracy=round(legal_score, 2),
        total=round(total, 1),
        details=all_details,
    )

    return breakdown


# ---------------------------------------------------------------------------
# Recommendations (LLM-based, updated for v5)
# ---------------------------------------------------------------------------

async def generate_recommendations(
    session_id: str | uuid.UUID,
    db: AsyncSession,
    scores: ScoreBreakdown | None = None,
) -> str:
    """Generate AI recommendations based on 10-layer session performance."""
    from app.services.llm import generate_response

    if isinstance(session_id, str):
        session_id = uuid.UUID(session_id)

    msg_result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.sequence_number)
    )
    messages = msg_result.scalars().all()

    user_messages = [m.content for m in messages if m.role == MessageRole.user]
    if not user_messages:
        return "Недостаточно данных для анализа."

    dialog_summary = "\n".join(
        f"{'Менеджер' if m.role == MessageRole.user else 'Клиент'}: {m.content}"
        for m in messages[:30]
        if m.role in (MessageRole.user, MessageRole.assistant)
    )

    score_info = ""
    if scores:
        score_info = (
            f"\nОценки (v5, 10 слоёв):\n"
            f"  L1 Следование скрипту: {scores.script_adherence}/22.5\n"
            f"  L2 Работа с возражениями: {scores.objection_handling}/18.75\n"
            f"  L3 Коммуникация: {scores.communication}/15\n"
            f"  L4 Антипаттерны: {scores.anti_patterns}\n"
            f"  L5 Результат: {scores.result}/7.5\n"
            f"  L6 Цепочки возражений: {scores.chain_traversal}/7.5\n"
            f"  L7 Ловушки: {scores.trap_handling}\n"
            f"  L8 Человеческий фактор: {scores.human_factor}/15\n"
            f"  L9 Нарратив: {scores.narrative_progression}/10\n"
            f"  L10 Юр. точность: {scores.legal_accuracy} (±5)\n"
            f"  ИТОГО: {scores.total}/100\n"
        )
        radar = scores.skill_radar
        score_info += (
            f"\nРадар навыков:\n"
            f"  Эмпатия: {radar['empathy']}\n"
            f"  Знания: {radar['knowledge']}\n"
            f"  Работа с возражениями: {radar['objection_handling']}\n"
            f"  Стрессоустойчивость: {radar['stress_resistance']}\n"
            f"  Закрытие сделки: {radar['closing']}\n"
            f"  Квалификация: {radar['qualification']}\n"
        )

    system_prompt = (
        "Ты — опытный тренер по продажам услуги банкротства физических лиц (БФЛ). "
        "Проанализируй диалог менеджера с клиентом и дай 3-5 конкретных рекомендаций. "
        "Учитывай все 10 слоёв оценки и радар навыков. "
        "Формат: нумерованный список. Каждая рекомендация — 1-2 предложения. "
        "Фокусируйся на самых слабых навыках по радару. Будь конкретен, избегай общих фраз. "
        "Если были юридические ошибки (L10) — обязательно укажи правильную информацию со ссылкой на закон. "
        "Пиши на русском."
    )

    try:
        result = await generate_response(
            system_prompt=system_prompt,
            messages=[{
                "role": "user",
                "content": f"Диалог:\n{dialog_summary}\n{score_info}\n\nДай рекомендации менеджеру.",
            }],
            emotion_state="cold",
        )
        return result.content
    except Exception:
        logger.exception("Failed to generate recommendations")
        return "Не удалось сгенерировать рекомендации."
