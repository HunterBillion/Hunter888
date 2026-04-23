"""Rule-based quality audit for chat/call sessions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Sequence

from app.services.conversation_policy import audit_assistant_reply
from app.services.session_state import normalize_session_mode, normalize_session_outcome


@dataclass(frozen=True)
class QualityFinding:
    code: str
    severity: str
    message: str
    evidence: dict = field(default_factory=dict)


@dataclass(frozen=True)
class QualityReview:
    score: int
    findings: list[QualityFinding]
    metrics: dict

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "findings": [asdict(f) for f in self.findings],
            "metrics": self.metrics,
        }


def _value(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _role_value(role: Any) -> str:
    return role.value if hasattr(role, "value") else str(role)


def review_session_quality(session: Any, messages: Sequence[Any]) -> QualityReview:
    custom_params = _value(session, "custom_params", {}) or {}
    scoring_details = _value(session, "scoring_details", {}) or {}
    mode = normalize_session_mode(custom_params.get("session_mode")) or "chat"
    outcome = normalize_session_outcome(scoring_details.get("call_outcome") or scoring_details.get("outcome"))

    findings: list[QualityFinding] = []
    assistant_replies: list[str] = []
    assistant_count = 0
    user_count = 0
    missing_next_step_count = 0
    repeat_count = 0
    too_long_count = 0

    for idx, msg in enumerate(messages):
        role = _role_value(_value(msg, "role", ""))
        content = _value(msg, "content", "") or ""
        if role.endswith("user"):
            user_count += 1
        if role.endswith("assistant"):
            assistant_count += 1
            audit = audit_assistant_reply(
                reply=content,
                previous_assistant_replies=assistant_replies[-5:],
                mode=mode,
            )
            assistant_replies.append(content)
            for violation in audit.violations:
                if violation.code == "near_repeat":
                    repeat_count += 1
                elif violation.code == "too_long":
                    too_long_count += 1
                elif violation.code == "missing_next_step":
                    missing_next_step_count += 1
                findings.append(QualityFinding(
                    code=violation.code,
                    severity=violation.severity,
                    message=violation.message,
                    evidence={"message_index": idx},
                ))

    if mode == "center" and outcome is None:
        findings.append(QualityFinding(
            code="missing_terminal_outcome",
            severity="critical",
            message="Центр-сессия не имеет обязательного исхода",
            evidence={"required": ["deal_agreed", "deal_not_agreed", "continue_next_call"]},
        ))

    if user_count >= 4 and assistant_count > 0 and missing_next_step_count >= max(2, assistant_count // 2):
        findings.append(QualityFinding(
            code="weak_progression",
            severity="high",
            message="Диалог долго идёт без явного следующего шага",
            evidence={"missing_next_step_count": missing_next_step_count},
        ))

    penalty = repeat_count * 15 + too_long_count * 8 + missing_next_step_count * 5
    penalty += 30 if any(f.code == "missing_terminal_outcome" for f in findings) else 0
    penalty += 15 if any(f.code == "weak_progression" for f in findings) else 0
    score = max(0, min(100, 100 - penalty))

    return QualityReview(
        score=score,
        findings=findings,
        metrics={
            "mode": mode,
            "outcome": outcome,
            "messages": len(messages),
            "user_messages": user_count,
            "assistant_messages": assistant_count,
            "repeat_count": repeat_count,
            "too_long_count": too_long_count,
            "missing_next_step_count": missing_next_step_count,
        },
    )
