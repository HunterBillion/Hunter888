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
    """Full 12-layer score breakdown (v6: DOC_06)."""
    # Rescaled v3 layers (L1-L7)
    script_adherence: float       # L1: 0-22.5
    objection_handling: float     # L2: 0-18.75
    communication: float          # L3: 0-15
    anti_patterns: float          # L4: 0 to -11.25
    result: float                 # L5: 0-7.5
    chain_traversal: float        # L6: 0-7.5
    trap_handling: float          # L7: -7.5 to +7.5

    # v5 layers
    human_factor: float           # L8: 0-15
    narrative_progression: float  # L9: 0-10
    legal_accuracy: float         # L10: -5 to +5

    total: float                  # 0-100 clamped

    # v6 bonus layers (DOC_06)
    adaptation: float = 0.0       # L11: 0-7.5
    time_management: float = 0.0  # L12: 0-5.0
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
        """Sum of L1-L8 + L11-L12 bonus (available during session via WS)."""
        return self.base_score + self.human_factor + self.adaptation + self.time_management

    @property
    def skill_radar(self) -> dict[str, float]:
        """Compute 10-skill radar from 12 layer scores (DOC_06). Returns 0-100 per skill.

        S3-07: All L3 and L8 sub-scores are now stored normalized to [0, 1].
        This eliminates the V3_RESCALE bias where L3 (max 3.75) was artificially
        33% lower than L8 (max 5.0) on skill radar visualization.
        """
        details = self.details

        # L2.check_score is still stored after V3_RESCALE (0-3.75)
        _L2_CHECK_MAX = 5 * V3_RESCALE  # 3.75

        # ── empathy (L3 empathy + L8 patience + L8 empathy_check) ──
        # S3-07: sub-scores are already [0,1] — use directly as weights
        empathy_l3 = details.get("communication", {}).get("empathy_score", 0)
        empathy_l8_patience = details.get("human_factor", {}).get("patience_score", 0)
        empathy_l8_empathy = details.get("human_factor", {}).get("empathy_check_score", 0)
        empathy = (
            empathy_l3 * 0.4
            + empathy_l8_patience * 0.3
            + empathy_l8_empathy * 0.3
        ) * 100

        # ── knowledge (L1 + L10 + L7) ──
        knowledge_l1 = _normalize(self.script_adherence, 22.5) * 0.3
        knowledge_l10 = _normalize(self.legal_accuracy + 5, 10) * 0.4
        knowledge_l7 = _normalize(self.trap_handling + 7.5, 15) * 0.3
        knowledge = (knowledge_l1 + knowledge_l10 + knowledge_l7) * 100

        # ── objection_handling (L2 + L6 + L7) ──
        oh_l2 = _normalize(self.objection_handling, 18.75) * 0.5
        oh_l6 = _normalize(self.chain_traversal, 7.5) * 0.3
        oh_l7 = _normalize(self.trap_handling + 7.5, 15) * 0.2
        objection_handling_val = (oh_l2 + oh_l6 + oh_l7) * 100

        # ── stress_resistance (L4 + L8 composure + L3 pace) ──
        sr_l4 = _normalize(self.anti_patterns + 11.25, 11.25) * 0.4
        sr_l8_composure = details.get("human_factor", {}).get("composure_score", 0) * 0.3
        sr_l3_pace = details.get("communication", {}).get("pace_score", 0) * 0.3
        stress_resistance = (sr_l4 + sr_l8_composure + sr_l3_pace) * 100

        # ── closing (L5 + L9 + L2 check) ──
        closing_l5 = _normalize(self.result, 7.5) * 0.5
        closing_l9 = _normalize(self.narrative_progression, 10) * 0.3
        closing_l2_check = _normalize(
            details.get("objection_handling", {}).get("check_score", 0), _L2_CHECK_MAX
        ) * 0.2
        closing = (closing_l5 + closing_l9 + closing_l2_check) * 100

        # ── qualification (L1 discovery + L3 control + L3 listening) ──
        qual_l1_disc = _normalize(
            details.get("script_adherence", {}).get("discovery_score", 0), 10
        ) * 0.4
        qual_l3_ctrl = details.get("communication", {}).get("control_score", 0) * 0.3
        qual_l3_listen = details.get("communication", {}).get("listening_score", 0) * 0.3
        qualification = (qual_l1_disc + qual_l3_ctrl + qual_l3_listen) * 100

        # ── NEW: time_management (100% from L12) ──
        time_management = _normalize(self.time_management, 5.0) * 100

        # ── NEW: adaptation (100% from L11) ──
        adaptation_val = _normalize(self.adaptation, 7.5) * 100

        # ── NEW: legal_knowledge (60% L10 + 40% legal traps from L7) ──
        legal_l10 = _normalize(self.legal_accuracy + 5, 10) * 0.6
        legal_trap_score = sum(
            t.get("delta", 0) for t in details.get("trap_handling", {}).get("traps", [])
            if t.get("category") in ("legal", "factual", "expert_reference")
        )
        legal_l7 = _normalize(legal_trap_score + 3.75, 7.5) * 0.4
        legal_knowledge = (legal_l10 + legal_l7) * 100

        # ── NEW: rapport_building (40% L3 empathy + 30% L8 warmth + 30% L8 patience) ──
        warmth_l8 = details.get("human_factor", {}).get("warmth_score", 0)
        rapport = (
            empathy_l3 * 0.4
            + warmth_l8 * 0.3
            + empathy_l8_patience * 0.3
        ) * 100

        def _clamp(v: float) -> float:
            return round(min(100, max(0, v)), 1)

        return {
            "empathy": _clamp(empathy),
            "knowledge": _clamp(knowledge),
            "objection_handling": _clamp(objection_handling_val),
            "stress_resistance": _clamp(stress_resistance),
            "closing": _clamp(closing),
            "qualification": _clamp(qualification),
            "time_management": _clamp(time_management),
            "adaptation": _clamp(adaptation_val),
            "legal_knowledge": _clamp(legal_knowledge),
            "rapport_building": _clamp(rapport),
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


def count_human_moment_messages(user_messages: list[str]) -> int:
    """Count how many user messages are "human moments" (off-topic, typos, gibberish).

    Used to reduce scoring penalties: these messages should not be counted against
    the manager's script adherence, communication, or anti-pattern scores because
    the AI client is expected to react naturally, not continue the sales script.

    Returns count of messages that are human moments (0 = no adjustment needed).
    """
    from app.services.emotion_v6 import detect_human_moment

    count = 0
    for msg in user_messages:
        trigger = detect_human_moment(msg)
        if trigger is not None:
            count += 1
    return count


def apply_human_moment_adjustment(
    raw_score: float,
    max_score: float,
    human_moment_count: int,
    total_messages: int,
) -> float:
    """Adjust a layer score to compensate for human-moment messages.

    Logic: if 2 out of 20 messages were off-topic, don't penalize the manager
    for those 2 messages. Scale the score as if those messages didn't exist.

    The adjustment is capped at 20% of total messages to prevent abuse.
    """
    if human_moment_count == 0 or total_messages == 0:
        return raw_score

    # Cap: at most 20% of messages can be "forgiven"
    forgiven = min(human_moment_count, int(total_messages * 0.2))
    if forgiven == 0:
        return raw_score

    effective_messages = total_messages - forgiven
    if effective_messages <= 0:
        return raw_score

    # Scale score proportionally: if 18 of 20 messages were "real",
    # the score should be evaluated as if there were only 18 messages
    ratio = total_messages / effective_messages
    adjusted = raw_score * min(ratio, 1.15)  # Cap boost at 15%
    return min(adjusted, max_score)


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
        # If no user messages at all, award 0 (empty session exploit)
        if not user_messages:
            return 0.0, {
                "objections_found": 0,
                "note": "empty session — no user messages",
                "check_score": 0.0,
            }
        # No objections means easy conversation — award HALF credit, not full.
        _half_score = 9.375  # 50% of max L2
        return _half_score, {
            "objections_found": 0,
            "note": "no objections raised — partial credit (easy scenario)",
            "check_score": 2.5 * V3_RESCALE,
        }

    heard = False
    acknowledged = False
    clarified = False
    argued = False
    checked = False

    for user_msg in user_messages:
        # BUG-10 fix: "heard" means the manager acknowledged the objection,
        # not merely asked a clarifying question. Require ACKNOWLEDGE only.
        if _has_pattern(user_msg, ACKNOWLEDGE_PATTERNS):
            heard = True
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
    # S3-07: Store normalized [0,1] sub-scores (not rescaled raw)
    details["empathy_score"] = round(empathy_raw / 5.0, 3)
    score += empathy_raw

    # 2. Active listening (5 pts raw)
    avg_len = sum(len(m) for m in user_messages) / len(user_messages)
    long_messages = sum(1 for m in user_messages if len(m) > 500)
    listening_raw = 5.0
    if long_messages > len(user_messages) * 0.5:
        listening_raw = 2.0
    details["avg_message_length"] = round(avg_len, 1)
    details["listening_score"] = round(listening_raw / 5.0, 3)
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
    details["pace_score"] = round(pace_raw / 5.0, 3)
    score += pace_raw

    # 4. Conversation control (5 pts raw)
    polite_patterns = [
        r"здравствуйте", r"добрый\s+(день|вечер|утро)",
        r"спасибо", r"пожалуйста", r"будьте\s+добры",
        r"извините", r"благодар",
    ]
    # Count MESSAGES containing any polite marker, not total pattern matches.
    # Previously counted each pattern match separately — a single message with
    # "спасибо, пожалуйста" was double-counted, saturating control_raw too easily.
    polite_count = sum(
        1 for msg in user_messages
        if any(re.search(pat, msg.lower()) for pat in polite_patterns)
    )
    control_raw = min(5.0, 2.0 + polite_count * 1.0)
    details["polite_markers"] = polite_count
    details["control_score"] = round(control_raw / 5.0, 3)
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

    # Per-category cap: only the worst detection counts per category
    seen_categories: set[str] = set()
    for item in detected:
        cat = item["category"]
        if cat in seen_categories:
            # Already penalized this category — skip duplicate
            details["detected"].append({
                "category": cat,
                "score": item["score"],
                "penalty": 0.0,
                "note": "duplicate category — capped",
            })
            continue
        seen_categories.add(cat)
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
    # S3-07: Store normalized [0,1] sub-scores (unified scale with L3)
    details["patience_score"] = round(patience_score / 5.0, 3)
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
    details["empathy_check_score"] = round(empathy_check_score / 5.0, 3)
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
    details["composure_score"] = round(composure_score / 5.0, 3)
    details["aggressive_responses"] = aggressive_responses
    details["panic_count"] = panic_count
    score += composure_score

    # ── Warmth (derived, not scored separately) ──
    # S3-07: warmth_score was referenced in skill_radar but never stored.
    # Derive from empathy_check + composure as a soft proxy.
    warmth_score = (empathy_check_score + composure_score) / 2.0
    details["warmth_score"] = round(warmth_score / 5.0, 3)

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
        for idx, s in enumerate(states):
            v = state_order.get(s, 0)
            if v > peak_val:
                peak_val = v
                peak_index = idx

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

    # ── Hangup recovery bonus ──
    # If this call successfully recovered from a previous hangup in multi-call
    if session and session.scoring_details:
        _sd = session.scoring_details
        if _sd.get("had_hangup_recovery"):
            score += 5.0
            details["hangup_recovery_bonus"] = 5.0

    # ── 3.2: Promise fulfillment adjustment (CRM → Training link) ──
    # Kept promises boost L9, broken promises penalize it
    if session and session.scoring_details:
        promise_stats = session.scoring_details.get("_promise_stats")
        if promise_stats and promise_stats.get("total", 0) > 0:
            kept = promise_stats.get("kept", 0)
            broken = promise_stats.get("broken", 0)
            promise_bonus = min(1.5, kept * 0.5)       # +0.5 per kept, max +1.5
            promise_penalty = min(2.0, broken * 1.0)   # -1.0 per broken, max -2.0
            promise_delta = promise_bonus - promise_penalty
            score += promise_delta
            details["promise_kept"] = kept
            details["promise_broken"] = broken
            details["promise_delta"] = round(promise_delta, 1)

    return min(10.0, max(0.0, score)), details


# ---------------------------------------------------------------------------
# L10: Legal Accuracy (±5 modifier) — hybrid: regex (0.6) + vector (0.4)
# ---------------------------------------------------------------------------

async def _score_legal_accuracy_vector(
    session_id: uuid.UUID,
    db: AsyncSession,
) -> tuple[float, dict]:
    """L10 vector component: semantic search against legal_knowledge_chunks.

    Checks manager messages against pgvector embeddings for nuanced accuracy.
    Returns score in [-5, +5] range and details dict.
    """
    from app.services.rag_legal import retrieve_legal_context

    msg_result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.sequence_number)
    )
    messages = msg_result.scalars().all()

    user_messages = [m.content for m in messages if m.role == MessageRole.user]
    if not user_messages:
        return 0.0, {"method": "vector", "claims_found": 0}

    # Legal claim indicators — quick keyword filter before expensive embedding
    _LEGAL_KEYWORDS = [
        "банкротств", "списан", "долг", "кредит", "имущество", "квартир",
        "суд", "127", "реструктуриз", "реализац", "управляющ", "госпошлин",
        "алимент", "ипотек", "кредитн", "мораторий", "арбитражн", "заявлен",
        "процедур", "освобожд", "обязательств", "конкурсн", "массы",
    ]

    score = 0.0
    checks = []
    claims_checked = 0

    for msg_text in user_messages:
        msg_lower = msg_text.lower()
        # Quick filter: skip messages without legal content
        if not any(kw in msg_lower for kw in _LEGAL_KEYWORDS):
            continue

        context = await retrieve_legal_context(msg_text, db, top_k=3, prefer_embedding=True)
        if not context.has_results:
            continue

        claims_checked += 1
        top = context.results[0]

        # Check if message matches a common error
        is_error = False
        for err in top.common_errors:
            if isinstance(err, str) and err.lower() in msg_lower:
                is_error = True
                score -= 2.0
                checks.append({
                    "type": "error",
                    "chunk_id": str(top.chunk_id),
                    "similarity": top.relevance_score,
                    "fact": top.fact_text[:100],
                    "matched_error": err[:80],
                    "method": context.method,
                })
                break

        if not is_error and top.relevance_score >= 0.5:
            # High similarity to a correct fact — positive signal
            score += 0.5
            checks.append({
                "type": "correct",
                "chunk_id": str(top.chunk_id),
                "similarity": top.relevance_score,
                "fact": top.fact_text[:100],
                "method": context.method,
            })

    clamped = max(-5.0, min(5.0, score))

    return clamped, {
        "method": "vector",
        "claims_checked": claims_checked,
        "vector_checks": checks[:10],
    }


async def _score_legal_accuracy(
    session_id: uuid.UUID,
    db: AsyncSession,
) -> tuple[float, dict]:
    """L10: Legal Accuracy (±5 modifier, post-session).

    Hybrid scoring: 0.6 × regex (legal_checker) + 0.4 × vector (rag_legal).
    Falls back to 100% regex if vector search is unavailable.
    """
    REGEX_WEIGHT = 0.6
    VECTOR_WEIGHT = 0.4

    # ── Regex component (always available) ──
    regex_score = 0.0
    regex_details: dict = {"error": "legal_checker_unavailable"}
    try:
        from app.services.legal_checker import check_session_legal_accuracy
        result = await check_session_legal_accuracy(session_id, db)
        regex_score = result.total_score
        regex_details = {
            "checks_triggered": result.checks_triggered,
            "correct_cited": result.correct_cited,
            "correct": result.correct,
            "partial": result.partial,
            "incorrect": result.incorrect,
            "details": result.details[:10],
        }
    except Exception:
        logger.exception("L10 regex scoring failed for %s", session_id)

    # ── Vector component (may be unavailable) ──
    vector_score = 0.0
    vector_details: dict = {"method": "vector", "status": "skipped"}
    vector_available = False
    try:
        vector_score, vector_details = await _score_legal_accuracy_vector(session_id, db)
        vector_available = vector_details.get("claims_checked", 0) > 0
    except Exception:
        logger.warning("L10 vector scoring failed for %s — using regex only", session_id)

    # ── Combine ──
    if vector_available:
        combined = REGEX_WEIGHT * regex_score + VECTOR_WEIGHT * vector_score
        scoring_method = "hybrid"
    else:
        combined = regex_score
        scoring_method = "regex_only"

    clamped = max(-5.0, min(5.0, round(combined, 2)))

    return clamped, {
        "scoring_method": scoring_method,
        "regex_weight": REGEX_WEIGHT if vector_available else 1.0,
        "vector_weight": VECTOR_WEIGHT if vector_available else 0.0,
        "regex_score": round(regex_score, 2),
        "vector_score": round(vector_score, 2),
        "combined_score": round(clamped, 2),
        "regex": regex_details,
        "vector": vector_details,
    }


# ---------------------------------------------------------------------------
# L11: Adaptation (DOC_06) — 0-7.5 pts
# ---------------------------------------------------------------------------

def _score_adaptation(
    user_messages: list[str],
    emotion_timeline: list[dict],
    archetype_code: str | None,
    details: dict,
) -> tuple[float, dict]:
    """L11: How well the manager adapts to the archetype. 3 sub-scores × 2.5."""
    import math
    import re

    TRIGGER_DETECTORS = {
        "facts": [r"\d+\s*%", r"\d+\s*(рублей|тысяч|млн)", r"статистик", r"исследован"],
        "social_proof": [r"другие\s+клиенты", r"многие\s+(?:люди|должники)", r"похожая\s+ситуация"],
        "empathy": [r"понимаю", r"сочувств", r"на\s+вашем\s+месте", r"чувств"],
        "patience": [r"не\s+торопитесь", r"давайте\s+не\s+спеша", r"без\s+давления"],
        "authority": [r"(?:закон|статья|127|ФЗ|кодекс)", r"(?:суд|арбитраж)", r"(?:эксперт|специалист)"],
        "urgency": [r"срочно", r"прямо\s+сейчас", r"не\s+откладыв", r"время\s+(?:идёт|уходит)"],
    }

    def _extract_triggers(msgs: list[str]) -> dict[str, float]:
        counts = {k: 0 for k in TRIGGER_DETECTORS}
        for msg in msgs:
            low = msg.lower()
            for trigger, patterns in TRIGGER_DETECTORS.items():
                if any(re.search(p, low) for p in patterns):
                    counts[trigger] += 1
        total = max(1, sum(counts.values()))
        return {k: v / total for k, v in counts.items()}

    def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
        keys = set(a) | set(b)
        dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
        na = math.sqrt(sum(a.get(k, 0) ** 2 for k in keys))
        nb = math.sqrt(sum(b.get(k, 0) ** 2 for k in keys))
        return dot / (na * nb) if na > 0 and nb > 0 else 0.0

    # Sub-score 1: archetype_recognition (0-2.5)
    # Ideal trigger profiles per archetype group (DOC_05 §6.2)
    ARCHETYPE_IDEAL_TRIGGERS = {
        "resistance": {"facts": 0.8, "authority": 0.6, "patience": 0.4},
        "emotional": {"empathy": 0.9, "social_proof": 0.5, "patience": 0.6},
        "control": {"authority": 0.7, "facts": 0.6, "urgency": 0.5},
        "avoidance": {"patience": 0.8, "urgency": 0.6, "facts": 0.4},
        "special": {"empathy": 0.5, "facts": 0.5, "social_proof": 0.5},
        "cognitive": {"facts": 0.8, "urgency": 0.7, "patience": 0.3},
        "social": {"empathy": 0.8, "social_proof": 0.6, "patience": 0.4},
        "temporal": {"empathy": 0.6, "authority": 0.5, "urgency": 0.5},
        "professional": {"facts": 0.7, "authority": 0.6, "patience": 0.4},
        "compound": {"empathy": 0.5, "facts": 0.5, "authority": 0.5},
    }

    # Map archetype_code to group: use first segment before '_' or fallback
    _arch_group = (archetype_code or "").split("_")[0].lower()
    if _arch_group not in ARCHETYPE_IDEAL_TRIGGERS:
        # Heuristic mapping for known prefixes
        _GROUP_MAP = {
            "skeptic": "resistance", "denier": "resistance", "legal": "resistance",
            "angry": "emotional", "crying": "emotional", "anxious": "emotional",
            "dominant": "control", "micromanager": "control",
            "ghosting": "avoidance", "passive": "avoidance",
            "vip": "special", "celebrity": "special",
            "analytical": "cognitive", "engineer": "cognitive",
            "family": "social", "community": "social",
            "busy": "temporal", "deadline": "temporal",
            "expert": "professional", "cfo": "professional",
        }
        _arch_group = _GROUP_MAP.get(_arch_group, "compound")

    actual_triggers = _extract_triggers(user_messages)
    ideal_triggers = ARCHETYPE_IDEAL_TRIGGERS.get(_arch_group, ARCHETYPE_IDEAL_TRIGGERS["compound"])
    _sim = _cosine(actual_triggers, ideal_triggers)
    recognition_score = min(2.5, max(0.0, _sim * 2.5))

    # Sub-score 2: style_shift (0-2.5)
    style_shift_score = 1.5  # default
    if len(user_messages) >= 4:
        mid = len(user_messages) // 2
        first_half = _extract_triggers(user_messages[:mid])
        second_half = _extract_triggers(user_messages[mid:])
        shift_distance = 1 - _cosine(first_half, second_half)

        STATE_ORDER = {"cold": 0, "hostile": 0, "hangup": 0, "guarded": 1, "testing": 2,
                       "curious": 3, "callback": 4, "considering": 5, "negotiating": 6, "deal": 7}
        states = [e.get("state", "cold") for e in emotion_timeline if "state" in e]
        if len(states) >= 3:
            e_start = STATE_ORDER.get(states[0], 0)
            e_mid = STATE_ORDER.get(states[len(states) // 2], 0)
            e_end = STATE_ORDER.get(states[-1], 0)
            if e_mid <= e_start and shift_distance > 0.3 and e_end > e_mid:
                style_shift_score = 2.5
            elif e_mid <= e_start and shift_distance > 0.3:
                style_shift_score = 1.5
            elif e_end > e_start:
                style_shift_score = 2.0
            else:
                style_shift_score = 0.5

    # Sub-score 3: archetype_counter (0-2.5)
    # Checks if manager used the archetype's weakness trigger or
    # matched the recommended approach for the archetype group.
    counter_score = 1.0  # baseline
    if archetype_code and emotion_timeline:
        # If client reached deal/negotiating → manager found the right approach
        final_states = [e.get("state") for e in emotion_timeline[-3:] if "state" in e]
        if any(s in ("deal", "negotiating", "considering") for s in final_states):
            counter_score = 2.0
            # Bonus: if reached deal quickly (< 60% of messages)
            deal_idx = next(
                (i for i, e in enumerate(emotion_timeline) if e.get("state") in ("deal", "negotiating")),
                len(emotion_timeline),
            )
            if deal_idx < len(emotion_timeline) * 0.6:
                counter_score = 2.5
        elif any(s in ("curious",) for s in final_states):
            counter_score = 1.5
        elif any(s in ("hostile", "hangup") for s in final_states):
            counter_score = 0.0

    # v6 bonus: emotion awareness (0-1.25 extra)
    emotion_awareness_bonus = 0.0
    try:
        from app.services.emotion_v6 import score_emotion_awareness, IntensityLevel
        if emotion_timeline and len(emotion_timeline) >= 3:
            _last_state = emotion_timeline[-1].get("state", "cold")
            _last_intensity = IntensityLevel.MEDIUM  # default
            _manager_triggers = list(actual_triggers.keys())
            emotion_awareness_bonus = score_emotion_awareness(
                current_state=_last_state,
                intensity=_last_intensity,
                compound=None,
                micro=None,
                manager_triggers=_manager_triggers,
                archetype_group=_arch_group,
            )
    except Exception:
        pass

    total = min(7.5, recognition_score + style_shift_score + counter_score + emotion_awareness_bonus)
    adapt_details = {
        "recognition_score": round(recognition_score, 2),
        "style_shift_score": round(style_shift_score, 2),
        "counter_score": round(counter_score, 2),
        "emotion_awareness_bonus": round(emotion_awareness_bonus, 2),
    }
    return total, adapt_details


# ---------------------------------------------------------------------------
# L12: Time Management (DOC_06) — 0-5.0 pts
# ---------------------------------------------------------------------------

def _score_time_management(
    user_messages: list[str],
    assistant_messages: list[str],
    session_duration_seconds: float | None,
    typical_duration_minutes: float,
) -> tuple[float, dict]:
    """L12: Session pacing, timing, talk-listen balance. 3 sub-scores + penalties."""
    # Sub-score 1: optimal_duration (0-2.0)
    target_min = typical_duration_minutes or 10.0
    actual_min = (session_duration_seconds or 0) / 60.0
    ratio = actual_min / target_min if target_min > 0 else 1.0

    if 0.7 <= ratio <= 1.3:
        duration_score = 2.0
    elif 0.5 <= ratio < 0.7:
        duration_score = 1.0 + (ratio - 0.5) / 0.2
    elif 1.3 < ratio <= 1.6:
        duration_score = 1.0 + (1.6 - ratio) / 0.3
    else:
        duration_score = 0.0

    # Sub-score 2: silence_handling (0-1.5)
    short_client = sum(1 for m in assistant_messages if len(m.strip()) < 20)
    total_client = max(1, len(assistant_messages))
    silence_ratio = short_client / total_client

    CLARIFY_PATTERNS = [r"\?$", r"можете.*уточн", r"расскажите.*подробн", r"что.*имеете.*в виду"]
    import re
    clarifying = sum(1 for msg in user_messages if any(re.search(p, msg.lower()) for p in CLARIFY_PATTERNS))

    if silence_ratio > 0.3:
        silence_score = 1.5 if clarifying >= 2 else (1.0 if clarifying >= 1 else 0.5)
    else:
        silence_score = 1.0

    # Sub-score 3: talk_listen_ratio (0-1.5)
    user_chars = sum(len(m) for m in user_messages)
    assist_chars = sum(len(m) for m in assistant_messages)
    total_chars = max(1, user_chars + assist_chars)
    talk_ratio = user_chars / total_chars

    if talk_ratio <= 0.40:
        ratio_score = 1.5
    elif talk_ratio <= 0.50:
        ratio_score = 1.2
    elif talk_ratio <= 0.55:
        ratio_score = 1.0
    elif talk_ratio <= 0.70:
        ratio_score = 0.5
    else:
        ratio_score = 0.0

    # Penalties
    penalties = 0.0
    if talk_ratio > 0.70:
        penalties -= 2.0
    if (session_duration_seconds or 0) < 180:
        penalties -= 1.5

    total = max(0.0, min(5.0, duration_score + silence_score + ratio_score + penalties))
    tm_details = {
        "duration_score": round(duration_score, 2),
        "silence_score": round(silence_score, 2),
        "ratio_score": round(ratio_score, 2),
        "talk_ratio": round(talk_ratio, 3),
        "penalties": round(penalties, 2),
    }
    return total, tm_details


# ---------------------------------------------------------------------------
# Real-time scoring (L1-L8) — called during session via WS
# ---------------------------------------------------------------------------

async def calculate_realtime_scores(
    session_id: str | uuid.UUID,
    db: AsyncSession,
) -> dict:
    """Calculate real-time scores (L1-L8) for WS hints during active session.

    Phase 2 (B9): All 8 real-time layers calculated and sent.
    L9 (narrative) and L10 (legal) are post-session only.

    Returns a dict suitable for WS emission.
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

    # L1: Script adherence (0-22.5)
    l1_score = 0.0
    try:
        scenario_result = await db.execute(
            select(Scenario).where(Scenario.id == session.scenario_id)
        )
        scenario = scenario_result.scalar_one_or_none()
        if scenario and scenario.script_id:
            from app.services.script_checker import get_session_checkpoint_progress
            message_history = [{"role": m.role.value, "content": m.content} for m in messages]
            progress = await get_session_checkpoint_progress(scenario.script_id, message_history)
            l1_score = progress["total_score"] * 0.225
    except Exception:
        logger.warning("Scoring layer L1 failed", exc_info=True)

    # L2: Objection handling (0-18.75)
    l2_score, _ = _score_objection_handling(user_messages, assistant_messages)

    # L3: Communication (0-15)
    l3_score, _ = _score_communication(user_messages)

    # L4: Anti-patterns (0 to -11.25 penalty)
    l4_penalty = 0.0
    try:
        l4_penalty, _ = await _score_anti_patterns(user_messages)
    except Exception:
        logger.warning("Scoring layer L4 failed", exc_info=True)

    # L5: Result (0-7.5)
    l5_score, _ = _score_result(assistant_messages, emotion_timeline)

    # L6: Chain traversal (0-7.5)
    l6_score = 0.0
    try:
        from app.services.objection_chain import calculate_chain_score
        chain_data = await calculate_chain_score(session_id)
        l6_score = float(chain_data.get("chain_score", 0)) * V3_RESCALE
    except Exception:
        logger.warning("Scoring layer L6 failed", exc_info=True)

    # L7: Trap handling (-7.5 to +7.5)
    l7_score = 0.0
    try:
        from app.services.trap_detector import get_session_trap_state
        trap_state = await get_session_trap_state(session_id)
        l7_score = float(trap_state.net_score) * V3_RESCALE
    except Exception:
        logger.warning("Scoring layer L7 failed", exc_info=True)

    # L8: Human Factor (0-15)
    l8_score, _ = _score_human_factor(
        user_messages, assistant_messages, emotion_timeline,
        session.custom_params,
    )

    # v6.1: Human moment adjustment — don't penalize for off-topic/typo messages
    hm_count = count_human_moment_messages(user_messages)
    if hm_count > 0:
        total_user = len(user_messages)
        l1_score = apply_human_moment_adjustment(l1_score, 22.5, hm_count, total_user)
        l3_score = apply_human_moment_adjustment(l3_score, 15.0, hm_count, total_user)
        # Reduce anti-pattern penalty (human moments shouldn't count as anti-patterns)
        if l4_penalty < 0:
            forgiven = min(hm_count, int(total_user * 0.2))
            l4_penalty = l4_penalty * (1.0 - forgiven / max(total_user, 1) * 0.5)

    # Total (L1-L8, excluding L9/L10 which are post-session)
    realtime_total = l1_score + l2_score + l3_score + l4_penalty + l5_score + l6_score + l7_score + l8_score
    max_possible = 22.5 + 18.75 + 15 + 0 + 7.5 + 7.5 + 7.5 + 15  # 93.75 (L4 is penalty only)

    return {
        "script_adherence": round(l1_score, 1),
        "objection_handling": round(l2_score, 1),
        "communication": round(l3_score, 1),
        "anti_patterns": round(l4_penalty, 1),
        "result": round(l5_score, 1),
        "chain_traversal": round(l6_score, 1),
        "trap_handling": round(l7_score, 1),
        "human_factor": round(l8_score, 1),
        "realtime_estimate": round(max(0, realtime_total), 1),
        "max_possible_realtime": round(max_possible, 1),
        "layers_count": 8,
        "note": "L9 (narrative) and L10 (legal) calculated after session end",
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

    # Guard: empty session (0 user messages) → all zeros, skip all LLM calls
    if len(user_messages) == 0:
        logger.warning("Session %s has 0 user messages — returning zero scores", session_id)
        return ScoreBreakdown(
            script_adherence=0,
            objection_handling=0,
            communication=0,
            anti_patterns=0,
            result=0,
            chain_traversal=0,
            trap_handling=0,
            human_factor=0,
            narrative_progression=0,
            legal_accuracy=0,
            total=0,
            details={"_completeness": 0.0, "_empty_session": True},
        )

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
    # Check for hangup outcome — hangup = 0 pts for L5
    _scoring_details = session.scoring_details or {}
    _call_outcome = _scoring_details.get("call_outcome")
    if _call_outcome == "hangup":
        result_score = 0.0
        result_details = {"note": "hangup — client terminated the call", "consultation_agreed": False}
    else:
        result_score, result_details = _score_result(assistant_messages, emotion_timeline)
        # Bonus for recovery after hangup in multi-call
        if _scoring_details.get("had_hangup_recovery"):
            result_score = min(result_score + 2.5 * V3_RESCALE, 7.5)
            result_details["hangup_recovery_bonus"] = True
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
                    "client_phrase": t.client_phrase,
                    "correct_example": t.correct_example,
                    "explanation": t.explanation,
                    "law_reference": t.law_reference,
                    "correct_keywords": t.correct_keywords_found,
                    "wrong_keywords": t.wrong_keywords_found,
                    "detection_level": t.detection_level,
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

    # L10 accuracy metrics logging
    _l10_method = legal_details.get("scoring_method", "unknown")
    _l10_regex = legal_details.get("regex_score", 0)
    _l10_vector = legal_details.get("vector_score", 0)
    _l10_claims = legal_details.get("vector", {}).get("claims_checked", 0)
    logger.info(
        "L10 metrics session=%s method=%s regex=%.1f vector=%.1f combined=%.1f claims=%d",
        session_id, _l10_method, _l10_regex, _l10_vector, legal_score, _l10_claims,
    )

    # ── RAG Feedback Loop: capture L10 validation results ──
    try:
        from app.services.rag_feedback import record_training_feedback
        vector_checks = legal_details.get("vector", {}).get("vector_checks", [])
        if vector_checks:
            validation_results = []
            for vc in vector_checks:
                chunk_id = vc.get("chunk_id")
                if not chunk_id:
                    continue
                validation_results.append({
                    "chunk_id": chunk_id,
                    "accuracy": vc.get("type", "partial"),
                    "manager_statement": vc.get("fact", ""),
                    "score_delta": -2.0 if vc.get("type") == "error" else 0.5,
                })
            if validation_results:
                await record_training_feedback(
                    db,
                    session_id=session_id,
                    user_id=session.user_id,  # BUG-3 fix: was session_id
                    validation_results=validation_results,
                )
    except Exception as e:
        logger.warning("RAG feedback from L10 failed (non-critical): %s", e)

    # ── v6.1: Human moment adjustment (full scoring) ──
    hm_count = count_human_moment_messages(user_messages)
    if hm_count > 0:
        total_user = len(user_messages)
        script_score = apply_human_moment_adjustment(script_score, 22.5, hm_count, total_user)
        comm_score = apply_human_moment_adjustment(comm_score, 15.0, hm_count, total_user)
        if anti_penalty < 0:
            forgiven = min(hm_count, int(total_user * 0.2))
            anti_penalty = anti_penalty * (1.0 - forgiven / max(total_user, 1) * 0.5)
        all_details["_human_moment_count"] = hm_count
        all_details["_human_moment_adjustment"] = True

    # ── Completeness factor: scale scores by conversation depth ──
    # Short conversations (2-3 messages) shouldn't get inflated scores.
    # Factor: 3msg=0.3, 6msg=0.6, 10+=1.0
    user_msg_count = len(user_messages)
    completeness = min(1.0, user_msg_count / 10.0) if user_msg_count < 10 else 1.0
    all_details["_completeness"] = round(completeness, 2)
    all_details["_user_message_count"] = user_msg_count

    if completeness < 1.0:
        script_score *= completeness
        objection_score *= completeness
        comm_score *= completeness
        result_score *= completeness
        human_score *= completeness
        chain_bonus *= completeness
        # L4/L7/L9/L10 are penalties/bonuses — don't scale down penalties
        logger.info(
            "Session %s: short conversation (%d msgs), completeness=%.1f",
            session_id, user_msg_count, completeness,
        )

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

def _generate_rule_based_recommendations(scores: ScoreBreakdown) -> str:
    """Generate recommendations from 10-layer scores without LLM.

    Always works, instant. Returns markdown-formatted numbered list.
    """
    LAYER_RULES = [
        ("script_adherence", 15.0, 22.5,
         "**Следование скрипту:** Придерживайтесь этапов: представление → квалификация → презентация → возражения → закрытие. Задавайте квалифицирующие вопросы: сумма долга, кредиторы, наличие имущества."),
        ("objection_handling", 12.0, 18.75,
         "**Работа с возражениями:** Используйте схему: услышать → подтвердить → уточнить → аргументировать → проверить. Каждое возражение — это сигнал о страхе клиента, не игнорируйте."),
        ("communication", 10.0, 15.0,
         "**Коммуникация:** Больше эмпатии: «Я понимаю вашу ситуацию», «Это непростое решение». Слушайте активно, перефразируйте слова клиента."),
        ("human_factor", 10.0, 15.0,
         "**Человеческий фактор:** Сохраняйте спокойствие и терпение. Если клиент агрессивен — не реагируйте в ответ, покажите понимание."),
        ("result", 4.0, 7.5,
         "**Закрытие:** Предлагайте 2-3 конкретных слота для встречи, объясните что будет на встрече, подчеркните что консультация бесплатна."),
        ("chain_traversal", 4.0, 7.5,
         "**Цепочки возражений:** Используйте разные аргументы для разных возражений. Если один аргумент не сработал — попробуйте другой подход."),
    ]

    recs: list[str] = []
    for attr, threshold, max_val, text in LAYER_RULES:
        val = getattr(scores, attr, 0) or 0
        pct = val / max_val if max_val > 0 else 0
        if val < threshold:
            recs.append(text)

    # Anti-patterns (negative score = bad)
    if (scores.anti_patterns or 0) < -3:
        recs.append(
            "**Антипаттерны:** Обнаружены негативные паттерны (давление, обесценивание, перебивание). "
            "Избегайте фраз-манипуляций. Фокусируйтесь на фактах и выгоде для клиента."
        )

    # Legal accuracy
    if (scores.legal_accuracy or 0) < -1:
        recs.append(
            "**Юридическая точность:** Были допущены неточности в юридической информации. "
            "Перечитайте ключевые положения 127-ФЗ: сроки, условия, последствия процедуры."
        )

    # Completeness
    completeness = (scores.details or {}).get("_completeness", 1.0)
    if completeness < 0.6:
        user_count = (scores.details or {}).get("_user_message_count", 0)
        recs.insert(0,
            f"**Внимание:** Разговор был очень коротким ({user_count} сообщ.). "
            "Для полноценной оценки проведите сессию с 10+ репликами."
        )

    if not recs:
        recs.append("Отличная работа! Все показатели на высоком уровне. Продолжайте в том же духе.")

    return "\n".join(f"{i+1}. {r}" for i, r in enumerate(recs[:5]))


async def generate_recommendations(
    session_id: str | uuid.UUID,
    db: AsyncSession,
    scores: ScoreBreakdown | None = None,
) -> str:
    """Generate recommendations: rule-based instant + LLM enrichment if available."""
    # Step 1: Instant rule-based recommendations (always works)
    rule_based = ""
    if scores:
        rule_based = _generate_rule_based_recommendations(scores)

    if not rule_based:
        rule_based = "Недостаточно данных для анализа."

    # Step 2: Try LLM enrichment (may fail — that's OK)
    try:
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
        if len(user_messages) < 4:
            # Too short for LLM — use rule-based only
            return rule_based

        from app.services.scenario_engine import _sanitize_db_prompt
        dialog_summary = "\n".join(
            f"{'Менеджер' if m.role == MessageRole.user else 'Клиент'}: {_sanitize_db_prompt(m.content or '', 'dialog_msg')}"
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

        system_prompt = (
            "Ты — опытный тренер по продажам услуги банкротства физических лиц (БФЛ). "
            "Проанализируй диалог менеджера с клиентом и дай 3-5 конкретных рекомендаций. "
            "Учитывай все 10 слоёв оценки. "
            "Формат: нумерованный список. Каждая рекомендация — 1-2 предложения. "
            "Фокусируйся на самых слабых навыках. Будь конкретен, избегай общих фраз. "
            "Если были юридические ошибки (L10) — укажи правильную информацию со ссылкой на 127-ФЗ. "
            "Пиши на русском."
        )

        result = await generate_response(
            system_prompt=system_prompt,
            messages=[{
                "role": "user",
                "content": f"Диалог:\n{dialog_summary}\n{score_info}\n\nДай рекомендации менеджеру.",
            }],
            emotion_state="cold",
            task_type="coach",
            prefer_provider="cloud",
        )
        if result and result.content and len(result.content) > 20:
            return result.content  # LLM succeeded — use richer response
    except Exception:
        logger.info("LLM recommendations unavailable — using rule-based fallback")

    return rule_based


# ---------------------------------------------------------------------------
# Per-layer explanations with message references (Task 2.1)
# ---------------------------------------------------------------------------

@dataclass
class LayerExplanation:
    """Human-readable explanation for a single scoring layer."""
    layer: str              # e.g. "L1", "L2"
    label: str              # e.g. "Следование скрипту"
    score: float
    max_score: float
    percentage: float       # 0-100
    summary: str            # e.g. "Completed 4/6 stages"
    highlights: list[dict] = field(default_factory=list)
    # Each highlight: {"message_index": int, "role": "user"|"assistant",
    #                   "excerpt": str, "impact": str, "delta": float}


def generate_layer_explanations(
    breakdown: ScoreBreakdown,
    messages: list[dict],
) -> list[LayerExplanation]:
    """Generate human-readable explanations for all 10 layers.

    Args:
        breakdown: Full ScoreBreakdown from calculate_scores()
        messages: List of {"role": "user"|"assistant", "content": str, "index": int}

    Returns:
        List of LayerExplanation for each L1-L10
    """
    details = breakdown.details
    explanations: list[LayerExplanation] = []

    user_msgs = [(m["index"], m["content"]) for m in messages if m["role"] == "user"]
    asst_msgs = [(m["index"], m["content"]) for m in messages if m["role"] == "assistant"]

    # ── L1: Script Adherence ──
    l1 = details.get("script_adherence", {})
    reached = l1.get("reached_count", 0)
    total = l1.get("total_count", 0)
    checkpoints = l1.get("checkpoints", [])
    l1_highlights = []
    missed = [cp for cp in checkpoints if not cp.get("reached")]
    for cp in missed[:3]:
        l1_highlights.append({
            "message_index": -1,
            "role": "system",
            "excerpt": cp.get("name", ""),
            "impact": f"Пропущен этап: {cp.get('name', 'N/A')}",
            "delta": 0,
        })
    explanations.append(LayerExplanation(
        layer="L1", label="Следование скрипту",
        score=breakdown.script_adherence, max_score=22.5,
        percentage=round(_normalize(breakdown.script_adherence, 22.5) * 100, 1),
        summary=f"Пройдено {reached}/{total} этапов скрипта." if total > 0 else "Скрипт не назначен.",
        highlights=l1_highlights,
    ))

    # ── L2: Objection Handling ──
    l2 = details.get("objection_handling", {})
    obj_count = l2.get("objections_found", 0)
    steps = ["heard", "acknowledged", "clarified", "argued", "checked"]
    step_labels = {
        "heard": "Услышано", "acknowledged": "Признано",
        "clarified": "Уточнено", "argued": "Аргументировано", "checked": "Проверено",
    }
    done_steps = [s for s in steps if l2.get(s)]
    missed_steps = [s for s in steps if not l2.get(s)]
    l2_summary = f"{obj_count} возражений обнаружено. "
    if missed_steps:
        l2_summary += f"Пропущены: {', '.join(step_labels[s] for s in missed_steps)}."
    else:
        l2_summary += "Все шаги обработки выполнены."

    l2_highlights = []
    # Find messages with objection patterns
    for idx, msg in asst_msgs:
        if _has_pattern(msg, OBJECTION_PATTERNS):
            l2_highlights.append({
                "message_index": idx, "role": "assistant",
                "excerpt": msg[:80] + ("..." if len(msg) > 80 else ""),
                "impact": "Возражение клиента", "delta": 0,
            })
            if len(l2_highlights) >= 3:
                break
    explanations.append(LayerExplanation(
        layer="L2", label="Работа с возражениями",
        score=breakdown.objection_handling, max_score=18.75,
        percentage=round(_normalize(breakdown.objection_handling, 18.75) * 100, 1),
        summary=l2_summary, highlights=l2_highlights,
    ))

    # ── L3: Communication ──
    l3 = details.get("communication", {})
    empathy_found = l3.get("empathy_detected", False)
    avg_len = l3.get("avg_message_length", 0)
    l3_notes = []
    if not empathy_found:
        l3_notes.append("Эмпатия не обнаружена")
    if avg_len > 500:
        l3_notes.append(f"Слишком длинные ответы (ср. {int(avg_len)} символов)")
    polite = l3.get("polite_markers", 0)
    if polite == 0:
        l3_notes.append("Нет вежливых маркеров (здравствуйте, спасибо)")
    l3_summary = "; ".join(l3_notes) if l3_notes else "Хорошая коммуникация."
    explanations.append(LayerExplanation(
        layer="L3", label="Коммуникация",
        score=breakdown.communication, max_score=15.0,
        percentage=round(_normalize(breakdown.communication, 15.0) * 100, 1),
        summary=l3_summary, highlights=[],
    ))

    # ── L4: Anti-patterns ──
    l4 = details.get("anti_patterns", {})
    detected_patterns = l4.get("detected", [])
    l4_highlights = []
    for ap in detected_patterns[:3]:
        l4_highlights.append({
            "message_index": -1, "role": "user",
            "excerpt": ap.get("category", ""),
            "impact": f"Антипаттерн: {ap.get('category', 'N/A')} ({ap.get('penalty', 0):+.1f})",
            "delta": ap.get("penalty", 0),
        })
    l4_summary = f"{len(detected_patterns)} антипаттернов обнаружено." if detected_patterns else "Антипаттерны не обнаружены."
    explanations.append(LayerExplanation(
        layer="L4", label="Антипаттерны",
        score=breakdown.anti_patterns, max_score=0,
        percentage=round(max(0, _normalize(breakdown.anti_patterns + 11.25, 11.25)) * 100, 1),
        summary=l4_summary, highlights=l4_highlights,
    ))

    # ── L5: Result ──
    l5 = details.get("result", {})
    agreed = l5.get("consultation_agreed", False)
    scheduled = l5.get("meeting_scheduled", False)
    l5_parts = []
    if agreed:
        l5_parts.append("клиент согласился на консультацию")
    if scheduled:
        l5_parts.append("встреча/звонок назначен")
    if not agreed and not scheduled:
        l5_parts.append("не удалось продвинуть клиента к действию")
    l5_summary = "Результат: " + ", ".join(l5_parts) + "."
    explanations.append(LayerExplanation(
        layer="L5", label="Результат",
        score=breakdown.result, max_score=7.5,
        percentage=round(_normalize(breakdown.result, 7.5) * 100, 1),
        summary=l5_summary, highlights=[],
    ))

    # ── L6: Chain Traversal ──
    l6 = details.get("chain_traversal", {})
    has_chain = l6.get("has_chain", False)
    l6_summary = "Цепочки возражений обработаны." if has_chain else "Цепочки возражений не обнаружены или не обработаны."
    explanations.append(LayerExplanation(
        layer="L6", label="Цепочки возражений",
        score=breakdown.chain_traversal, max_score=7.5,
        percentage=round(_normalize(breakdown.chain_traversal, 7.5) * 100, 1),
        summary=l6_summary, highlights=[],
    ))

    # ── L7: Trap Handling ──
    l7 = details.get("trap_handling", {})
    traps = l7.get("traps", [])
    caught = [t for t in traps if t.get("status") == "caught"]
    missed_traps = [t for t in traps if t.get("status") != "caught"]
    l7_highlights = []
    for t in missed_traps[:3]:
        l7_highlights.append({
            "message_index": -1, "role": "system",
            "excerpt": t.get("name", ""),
            "impact": f"Ловушка пропущена: {t.get('name', 'N/A')} ({t.get('delta', 0):+.1f})",
            "delta": t.get("delta", 0),
        })
    l7_summary = f"Поймано {len(caught)}/{len(traps)} ловушек." if traps else "Ловушки не активировались."
    explanations.append(LayerExplanation(
        layer="L7", label="Ловушки",
        score=breakdown.trap_handling, max_score=7.5,
        percentage=round(_normalize(breakdown.trap_handling + 7.5, 15) * 100, 1),
        summary=l7_summary, highlights=l7_highlights,
    ))

    # ── L8: Human Factor ──
    l8 = details.get("human_factor", {})
    patience = l8.get("patience_score", 0)
    empathy_check = l8.get("empathy_check_score", 0)
    composure = l8.get("composure_score", 0)
    aggressive_cnt = l8.get("aggressive_responses", 0)
    panic_cnt = l8.get("panic_count", 0)
    l8_notes = []
    if aggressive_cnt > 0:
        l8_notes.append(f"{aggressive_cnt} агрессивных ответов")
    if panic_cnt > 0:
        l8_notes.append(f"{panic_cnt} паник-фраз")
    if l8.get("fake_detected"):
        l8_notes.append("обнаружена фейковая смена настроения (+бонус)")
    # S3-07: sub-scores are now [0,1] — display as ×5 for human-readable /5 scale
    l8_summary = (
        f"Терпение: {patience * 5:.0f}/5, Эмпатия: {empathy_check * 5:.0f}/5, Самообладание: {composure * 5:.0f}/5."
    )
    if l8_notes:
        l8_summary += " " + "; ".join(l8_notes) + "."

    l8_highlights = []
    # Find aggressive response messages
    aggressive_patterns_check = [
        r"(?:сам[иа]?\s+вы|да\s+вы\s+(?:что|как))",
        r"(?:не\s+кричите|хватит\s+(?:орать|кричать))",
    ]
    for idx, msg in user_msgs:
        if _has_pattern(msg, aggressive_patterns_check):
            l8_highlights.append({
                "message_index": idx, "role": "user",
                "excerpt": msg[:80] + ("..." if len(msg) > 80 else ""),
                "impact": "Агрессивный ответ менеджера (-2 самообладание)",
                "delta": -2.0,
            })
    explanations.append(LayerExplanation(
        layer="L8", label="Человеческий фактор",
        score=breakdown.human_factor, max_score=15.0,
        percentage=round(_normalize(breakdown.human_factor, 15.0) * 100, 1),
        summary=l8_summary, highlights=l8_highlights[:3],
    ))

    # ── L9: Narrative Progression ──
    l9 = details.get("narrative_progression", {})
    peak = l9.get("peak_state", "cold")
    final = l9.get("final_state", "cold")
    arc = l9.get("arc_score", 0)
    l9_summary = f"Пик: {peak}, финал: {final}. Арка: {arc:.0f}/4."
    if l9.get("hangup_recovery_bonus"):
        l9_summary += " Бонус за восстановление после hangup."
    explanations.append(LayerExplanation(
        layer="L9", label="Нарративная прогрессия",
        score=breakdown.narrative_progression, max_score=10.0,
        percentage=round(_normalize(breakdown.narrative_progression, 10.0) * 100, 1),
        summary=l9_summary, highlights=[],
    ))

    # ── L10: Legal Accuracy ──
    l10 = details.get("legal_accuracy", {})
    method = l10.get("scoring_method", "unknown")
    regex_details = l10.get("regex", {})
    correct = regex_details.get("correct", 0)
    incorrect = regex_details.get("incorrect", 0)
    checks = regex_details.get("checks_triggered", 0)
    l10_highlights = []
    for check in regex_details.get("details", [])[:3]:
        if isinstance(check, dict) and check.get("result") == "incorrect":
            l10_highlights.append({
                "message_index": -1, "role": "user",
                "excerpt": check.get("claim", "")[:80],
                "impact": f"Юридическая ошибка: {check.get('correction', 'N/A')[:80]}",
                "delta": -2.0,
            })
    l10_summary = f"{correct} верных, {incorrect} ошибок из {checks} проверок ({method})."
    explanations.append(LayerExplanation(
        layer="L10", label="Юридическая точность",
        score=breakdown.legal_accuracy, max_score=5.0,
        percentage=round(_normalize(breakdown.legal_accuracy + 5, 10) * 100, 1),
        summary=l10_summary, highlights=l10_highlights,
    ))

    return explanations


def layer_explanations_to_dict(explanations: list[LayerExplanation]) -> list[dict]:
    """Convert LayerExplanations to JSON-serializable dicts for API response."""
    return [
        {
            "layer": e.layer,
            "label": e.label,
            "score": e.score,
            "max_score": e.max_score,
            "percentage": e.percentage,
            "summary": e.summary,
            "highlights": e.highlights,
        }
        for e in explanations
    ]
