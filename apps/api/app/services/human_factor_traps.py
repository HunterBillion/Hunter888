"""Human factor trap detector — wrapper over trigger_detector.py.

Implements combinatorial logic over the 23 triggers from trigger_detector
to detect human-factor traps: patience, empathy, flattery, urgency.

Architecture:
┌───────────────────────────────────────────────────────────────────┐
│ trigger_detector.py → TriggerResult (23 triggers detected)       │
│                          ↓                                        │
│ human_factor_traps.py → HumanFactorResult[]                      │
│  • patience_trap   — pressure/counter_aggression present          │
│  • empathy_trap    — resolve_fear WITHOUT empathy                 │
│  • flattery_trap   — flexible_offer after compliment              │
│  • urgency_trap    — speed + pressure / false promises            │
└───────────────────────────────────────────────────────────────────┘

Per architect decision: trigger_detector already detects 23 triggers,
human_factor traps = combinatorial logic on top. No new LLM calls needed.

Active factors are provided by Game Director via session state
(active_factors list). Only traps whose factor is active are evaluated.
"""

import logging
import uuid
from dataclasses import dataclass, field

from app.services.narrative_trap_detector import TrapConsequence
from app.services.trigger_detector import TriggerResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class HumanFactorResult:
    """Result of a human factor trap check."""

    trap_type: str  # "patience_trap" | "empathy_trap" | "flattery_trap" | "urgency_trap"
    status: str  # "fell" | "dodged" | "not_activated"
    score_delta: int  # penalty (negative) or bonus (positive)
    description: str  # human-readable description (Russian)
    severity: float  # 0.0-1.0 for Game Director ranking
    matched_triggers: list[str] = field(default_factory=list)  # which triggers contributed
    consequence_type: str = ""  # "emotion_shift" | "trust_change" | "patience_loss"
    consequence_payload: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Trap definitions: combinatorial rules over triggers
# ---------------------------------------------------------------------------

HUMAN_FACTOR_TRAP_RULES: dict[str, dict] = {
    "patience_trap": {
        # Manager loses patience under hostile client — uses pressure or counter_aggression
        "fell_triggers": {"pressure", "counter_aggression"},
        "fell_logic": "any",  # any of these = FELL
        "dodged_triggers": {"calm_response", "empathy", "acknowledge"},
        "dodged_logic": "any",  # any of these WITHOUT fell triggers = DODGED
        "required_factor": "patience",  # only active when Game Director enables this factor
        "fell_description": "Менеджер потерял терпение — применил давление или ответил агрессией",
        "dodged_description": "Менеджер сохранил терпение и ответил спокойно",
        "fell_score_delta": -10,
        "dodged_score_delta": 5,
        "fell_severity": 0.6,
        "consequence_type": "emotion_shift",
        "fell_payload": {"target_state": "hostile", "reason": "manager_impatient"},
    },
    "empathy_trap": {
        # Client is scared (resolve_fear context) but manager doesn't show empathy
        "context_triggers": {"resolve_fear"},  # resolve_fear must be present
        "fell_absent_triggers": {"empathy"},  # empathy MUST be present; absence = FELL
        "fell_logic": "absent",  # special: FELL when required trigger is ABSENT
        "dodged_triggers": {"empathy", "resolve_fear"},
        "dodged_logic": "all",  # both must be present = DODGED
        "required_factor": "empathy",
        "fell_description": "Менеджер не проявил сочувствия, когда клиент нуждался в поддержке",
        "dodged_description": "Менеджер проявил сочувствие и снял страх клиента",
        "fell_score_delta": -8,
        "dodged_score_delta": 5,
        "fell_severity": 0.5,
        "consequence_type": "trust_change",
        "fell_payload": {"delta": -10, "reason": "no_empathy_when_needed"},
    },
    "flattery_trap": {
        # Client compliments → manager immediately offers discount/flexibility
        # This means the manager is manipulable by flattery
        "fell_triggers": {"flexible_offer"},
        "fell_logic": "any",  # flexible_offer present after compliment context = FELL
        "dodged_triggers": {"boundary", "facts"},
        "dodged_logic": "any",  # manager sets boundaries or gives facts instead
        "required_factor": "flattery",
        "context_check": "compliment_context",  # additional context check needed
        "fell_description": "Менеджер поддался лести и сразу предложил скидку/уступку",
        "dodged_description": "Менеджер не поддался лести и продолжил по существу",
        "fell_score_delta": -7,
        "dodged_score_delta": 3,
        "fell_severity": 0.4,
        "consequence_type": "credibility_loss",
        "fell_payload": {"detail": "manager_susceptible_to_flattery"},
    },
    "urgency_trap": {
        # Manager rushes or makes unrealistic promises under time pressure
        "fell_triggers": {"speed", "pressure"},
        "fell_logic": "all",  # BOTH present = manager is rushing AND pressuring
        "dodged_triggers": {"honest_uncertainty", "boundary", "calm_response"},
        "dodged_logic": "any",
        "required_factor": "urgency",
        "fell_description": "Менеджер поспешил и применил давление — клиент чувствует фальшь",
        "dodged_description": "Менеджер не торопился и дал взвешенный ответ",
        "fell_score_delta": -6,
        "dodged_score_delta": 3,
        "fell_severity": 0.5,
        "consequence_type": "trust_change",
        "fell_payload": {"delta": -8, "reason": "rushed_response_under_pressure"},
    },
}


# ---------------------------------------------------------------------------
# Compliment detection (simple keyword check for flattery_trap context)
# ---------------------------------------------------------------------------

COMPLIMENT_KEYWORDS_RU = [
    "молодец",
    "отлично",
    "вы хорошо",
    "вы лучше",
    "профессионал",
    "мне нравится",
    "замечательно",
    "спасибо большое",
    "как здорово",
    "вы так хорошо",
    "классно объясняете",
    "приятно общаться",
    "вы настоящий",
    "респект",
    "вы правда разбираетесь",
]


def _has_compliment_context(client_message: str) -> bool:
    """Check if client message contains compliment/flattery context."""
    msg_lower = client_message.lower()
    return any(kw in msg_lower for kw in COMPLIMENT_KEYWORDS_RU)


# ---------------------------------------------------------------------------
# Main detection logic
# ---------------------------------------------------------------------------

def detect_human_factor_traps(
    trigger_result: TriggerResult,
    client_message: str,
    active_factors: list[dict],
    session_id: str | None = None,
) -> list[HumanFactorResult]:
    """Detect human factor traps based on trigger_detector results.

    This function is SYNCHRONOUS — no LLM calls, pure combinatorial logic.

    Args:
        trigger_result: Result from trigger_detector.detect_triggers()
        client_message: Client's message (for compliment context check)
        active_factors: Active human factors from Game Director / ClientStory
            Format: [{"factor": "patience", "intensity": 0.7, "since_call": 2}, ...]
        session_id: Training session UUID (for consequence events)

    Returns:
        List of HumanFactorResult for each activated trap
    """
    results: list[HumanFactorResult] = []
    detected_triggers = set(trigger_result.triggers)

    # Build set of active factor names for quick lookup
    active_factor_names = {f["factor"] for f in active_factors if f.get("factor")}

    # Get intensity multipliers
    factor_intensities = {
        f["factor"]: f.get("intensity", 1.0)
        for f in active_factors
        if f.get("factor")
    }

    for trap_name, rule in HUMAN_FACTOR_TRAP_RULES.items():
        required_factor = rule["required_factor"]

        # Skip if this factor is not active in current session
        if required_factor not in active_factor_names:
            continue

        intensity = factor_intensities.get(required_factor, 1.0)

        # Additional context check for flattery
        if rule.get("context_check") == "compliment_context":
            if not _has_compliment_context(client_message):
                continue

        # Check for context triggers (empathy_trap: resolve_fear must be present)
        if "context_triggers" in rule:
            if not rule["context_triggers"].intersection(detected_triggers):
                continue

        # Evaluate FELL condition
        fell = _check_fell_condition(rule, detected_triggers)

        # Evaluate DODGED condition (only if not fell)
        dodged = False
        if not fell:
            dodged = _check_dodged_condition(rule, detected_triggers)

        if not fell and not dodged:
            continue

        # Build result
        status = "fell" if fell else "dodged"
        score_delta = rule["fell_score_delta"] if fell else rule["dodged_score_delta"]
        description = rule["fell_description"] if fell else rule["dodged_description"]
        severity = rule.get("fell_severity", 0.5) if fell else 0.0

        # Scale severity by factor intensity
        severity = min(1.0, severity * intensity)

        # Scale score delta by intensity (more intense factor = harsher penalty)
        score_delta = int(score_delta * intensity)

        matched = list(detected_triggers)

        result = HumanFactorResult(
            trap_type=trap_name,
            status=status,
            score_delta=score_delta,
            description=description,
            severity=severity,
            matched_triggers=matched,
            consequence_type=rule.get("consequence_type", ""),
            consequence_payload=rule.get("fell_payload", {}) if fell else {},
        )
        results.append(result)

        logger.info(
            "Human factor trap %s: %s (severity=%.2f, delta=%d, intensity=%.2f)",
            trap_name,
            status,
            severity,
            score_delta,
            intensity,
        )

    return results


def _check_fell_condition(rule: dict, detected: set[str]) -> bool:
    """Check if FELL condition is met based on rule logic."""
    logic = rule.get("fell_logic", "any")

    if logic == "absent":
        # Special: FELL when required trigger is absent
        absent_triggers = rule.get("fell_absent_triggers", set())
        return not absent_triggers.intersection(detected)

    fell_triggers = rule.get("fell_triggers", set())
    if not fell_triggers:
        return False

    if logic == "any":
        return bool(fell_triggers.intersection(detected))
    elif logic == "all":
        return fell_triggers.issubset(detected)

    return False


def _check_dodged_condition(rule: dict, detected: set[str]) -> bool:
    """Check if DODGED condition is met based on rule logic."""
    logic = rule.get("dodged_logic", "any")
    dodged_triggers = rule.get("dodged_triggers", set())

    if not dodged_triggers:
        return False

    if logic == "any":
        return bool(dodged_triggers.intersection(detected))
    elif logic == "all":
        return dodged_triggers.issubset(detected)

    return False


# ---------------------------------------------------------------------------
# Consequence builder (mirrors narrative_trap_detector.build_consequences)
# ---------------------------------------------------------------------------

def build_consequences(
    results: list[HumanFactorResult],
    session_id: str,
) -> list[TrapConsequence]:
    """Convert HumanFactorResult list to TrapConsequence events for Game Director.

    Args:
        results: Results from detect_human_factor_traps()
        session_id: Training session UUID

    Returns:
        List of TrapConsequence events (only for fell/dodged, not not_activated)
    """
    consequences: list[TrapConsequence] = []

    for r in results:
        if r.status == "not_activated":
            continue

        trap_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"hf-{r.trap_type}-{session_id}"))

        consequence = TrapConsequence(
            trap_id=trap_id,
            session_id=session_id,
            trap_type="human_factor",
            outcome=r.status,
            consequence_type=r.consequence_type,
            severity=r.severity,
            payload=r.consequence_payload,
        )
        consequences.append(consequence)

    return consequences


# ---------------------------------------------------------------------------
# Prompt injection for character system prompt
# ---------------------------------------------------------------------------

def build_human_factor_prompt(
    active_factors: list[dict],
    results: list[HumanFactorResult] | None = None,
) -> str:
    """Build prompt fragment injecting active human factors into character system prompt.

    This is injected ALONGSIDE the narrative trap prompt, NOT replacing it.

    Args:
        active_factors: Active factors from Game Director
        results: Optional previous results from this call (for context)

    Returns:
        Prompt fragment (Russian) for character system prompt, or empty string
    """
    if not active_factors:
        return ""

    lines = [
        "\n\n## АКТИВНЫЕ ЧЕЛОВЕЧЕСКИЕ ФАКТОРЫ",
        "Эти факторы влияют на поведение клиента в ЭТОМ звонке:",
    ]

    factor_descriptions = {
        "patience": (
            "ТЕРПЕНИЕ — клиент проверяет терпение менеджера. "
            "Ведёт себя сложно, ждёт спокойного ответа. "
            "Давление или агрессия = провал."
        ),
        "empathy": (
            "ЭМПАТИЯ — клиент эмоционально уязвим, ждёт сочувствия. "
            "Если менеджер не проявит эмпатию — теряет доверие."
        ),
        "flattery": (
            "ЛЕСТЬ — клиент хвалит менеджера, пытается манипулировать. "
            "Если менеджер сразу предложит скидку/уступку — потеряет авторитет."
        ),
        "urgency": (
            "СРОЧНОСТЬ — ситуация давит на менеджера. "
            "Если менеджер начнёт торопить или давить — клиент почувствует фальшь."
        ),
        "fatigue": (
            "УСТАЛОСТЬ — клиент устал от долгого процесса. "
            "Менеджер должен быть кратким и конкретным."
        ),
        "distrust": (
            "НЕДОВЕРИЕ — клиент не доверяет юристам/компаниям. "
            "Нужны факты и ссылки на закон, не обещания."
        ),
    }

    for factor in active_factors:
        name = factor.get("factor", "")
        intensity = factor.get("intensity", 0.5)
        desc = factor_descriptions.get(name, f"Фактор: {name}")

        intensity_label = "слабый" if intensity < 0.4 else "средний" if intensity < 0.7 else "сильный"
        lines.append(f"- [{intensity_label}] {desc}")

    # If we have results from current turn, add context
    if results:
        fell_results = [r for r in results if r.status == "fell"]
        if fell_results:
            lines.append("\n⚠️ ВНИМАНИЕ: менеджер уже провалил:")
            for r in fell_results:
                lines.append(f"  - {r.description}")

    return "\n".join(lines)
