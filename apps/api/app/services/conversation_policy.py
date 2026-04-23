"""Conversation policy rules shared by chat, call and center modes."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from app.services.session_state import normalize_session_mode


@dataclass(frozen=True)
class PolicyViolation:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class ConversationPolicyResult:
    violations: list[PolicyViolation] = field(default_factory=list)

    @property
    def is_ok(self) -> bool:
        return not self.violations


def conversation_policy_prompt(mode: object = None) -> str:
    normalized_mode = normalize_session_mode(mode) or "chat"
    length_rule = (
        "Звонок/центр: отвечай 1-2 короткими фразами, без лекций."
        if normalized_mode in {"call", "center"}
        else "Чат: отвечай кратко, максимум 4 предложения, если пользователь не просит подробности."
    )
    terminal_rule = (
        "В центре нельзя завершать без одного из исходов: договор согласован, договор не согласован, продолжить в другом звонке."
        if normalized_mode == "center"
        else "Не закрывай сценарий, если следующий шаг бизнес-логики ещё не зафиксирован."
    )
    return (
        "\n\n## Conversation Policy Engine\n"
        f"- {length_rule}\n"
        "- Не повторяй вопрос, если факт уже был получен в предыдущих сообщениях.\n"
        "- Каждая существенная реплика должна фиксировать один факт или вести к одному следующему шагу.\n"
        "- Если не хватает данных, спроси только минимально нужный следующий вопрос.\n"
        "- Не меняй имя, пол, роль или обращение клиента без явного обновления профиля.\n"
        f"- {terminal_rule}\n"
    )


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def is_near_repeat(current: str, previous: str, *, threshold: float = 0.86) -> bool:
    cur = _normalize_text(current)
    prev = _normalize_text(previous)
    if not cur or not prev:
        return False
    if cur == prev:
        return True
    return SequenceMatcher(None, cur, prev).ratio() >= threshold


def audit_assistant_reply(
    *,
    reply: str,
    previous_assistant_replies: list[str] | None = None,
    mode: object = None,
) -> ConversationPolicyResult:
    violations: list[PolicyViolation] = []
    normalized_mode = normalize_session_mode(mode) or "chat"
    text = _normalize_text(reply)

    max_sentences = 3 if normalized_mode in {"call", "center"} else 5
    sentence_count = len([s for s in re.split(r"[.!?]+", reply) if s.strip()])
    if sentence_count > max_sentences:
        violations.append(PolicyViolation(
            code="too_long",
            severity="medium",
            message=f"Ответ слишком длинный для режима {normalized_mode}",
        ))

    for previous in previous_assistant_replies or []:
        if is_near_repeat(reply, previous):
            violations.append(PolicyViolation(
                code="near_repeat",
                severity="high",
                message="Ответ почти повторяет предыдущую реплику AI",
            ))
            break

    if normalized_mode in {"chat", "center"} and text and not re.search(
        r"(следующ|дальше|пришл|уточн|провер|созвон|перезвон|договор|решим|зафиксир)",
        text,
    ):
        violations.append(PolicyViolation(
            code="missing_next_step",
            severity="low",
            message="В ответе нет явного следующего шага",
        ))

    return ConversationPolicyResult(violations=violations)
