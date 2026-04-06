"""Content filter for user inputs and AI outputs.

Filters profanity, jailbreak attempts, PII leakage, and role breaks.
Used across PvP arena, training sessions, and all user-facing AI responses.
"""

import re
import logging

logger = logging.getLogger(__name__)

# ─── Profanity patterns (Russian + transliteration) ─────────────────────────

_PROFANITY_PATTERNS = [
    r"\b[хx][уy][йеёия]\w*\b",
    r"\b[пp][иi][зz][дd]\w*\b",
    r"\b[еe][бb][аa][тt]\w*\b",
    r"\b[бb][лl][яa][дт]?\w*\b",
    r"\b[сs][уy][кk][аaиi]\w*\b",
    r"\b[мm][уy][дd][аa][кk]\w*\b",
    r"\bгандон\w*\b",
    r"\bшлюх\w*\b",
    r"\bдерьм\w*\b",
    r"\bзасранец\w*\b",
    r"\bpidoras\w*\b",
    r"\bsuka\b",
    r"\bblyad\w*\b",
    r"\bhui\b",
    # English basics
    r"\bfuck\w*\b",
    r"\bshit\w*\b",
    r"\bbitch\w*\b",
    r"\bass(?:hole)?\b",
    r"\bdick(?:head)?\b",
]

_profanity_compiled = [re.compile(p, re.IGNORECASE | re.UNICODE) for p in _PROFANITY_PATTERNS]

# ─── Jailbreak / prompt injection patterns ──────────────────────────────────

_JAILBREAK_PATTERNS = [
    # Direct instruction override attempts
    r"(?:ignore|забудь|отмени|проигнорируй)\s+(?:all\s+)?(?:previous|предыдущ|систем|выше|above)\s+(?:instructions?|инструкц|prompt|промпт)",
    r"(?:you\s+are\s+now|ты\s+теперь|act\s+as|притворись|представь\s+что\s+ты)\s+(?:a\s+)?(?:different|друг|нов|свободн|DAN|jailbreak)",
    r"(?:system\s*prompt|системн\w*\s*промпт|system\s*message)",
    r"(?:reveal|покажи|расскажи|выведи)\s+(?:your|свой|свои|the)\s+(?:instructions?|инструкц|prompt|промпт|rules|правила)",
    # Role escape
    r"(?:stop\s+(?:being|pretending|playing)|перестань\s+(?:играть|притвор)|выйди\s+из\s+роли)",
    r"(?:break\s+character|сломай\s+персонаж|drop\s+the\s+act)",
    # Token manipulation
    r"\[/?(?:SYSTEM|INST|SYS)\]",
    r"<\|(?:im_start|im_end|system|endoftext)\|>",
    r"```(?:system|instruction)",
    # Developer mode tricks
    r"(?:developer\s+mode|режим\s+разработчика|admin\s+mode|debug\s+mode)",
    r"(?:enable\s+unrestricted|включи\s+без\s+ограничений)",
]

_jailbreak_compiled = [re.compile(p, re.IGNORECASE | re.UNICODE) for p in _JAILBREAK_PATTERNS]

# ─── PII patterns ───────────────────────────────────────────────────────────

_PII_PATTERNS = [
    # Russian phone numbers
    r"\+?7[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}",
    r"8[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}",
    # Email
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
    # Passport (RU format: 4 digits space 6 digits)
    r"\b\d{4}\s?\d{6}\b",
    # SNILS
    r"\b\d{3}[\s\-]?\d{3}[\s\-]?\d{3}[\s\-]?\d{2}\b",
    # INN (10 or 12 digits)
    r"\bИНН[\s:]*\d{10,12}\b",
]

_pii_compiled = [re.compile(p, re.UNICODE) for p in _PII_PATTERNS]

# ─── Role break patterns (AI output) ────────────────────────────────────────

_ROLE_BREAK_PATTERNS = [
    r"(?:как\s+(?:языковая\s+модель|искусственный\s+интеллект|ИИ|AI))",
    r"(?:as\s+an?\s+(?:AI|language\s+model|assistant))",
    r"(?:я\s+(?:не\s+)?(?:могу|умею)\s+(?:помочь|ответить)\s+как\s+(?:ИИ|AI))",
    r"(?:I\s+(?:can't|cannot|am\s+not\s+able)\s+(?:as|because\s+I'm)\s+an?\s+AI)",
]

_role_break_compiled = [re.compile(p, re.IGNORECASE | re.UNICODE) for p in _ROLE_BREAK_PATTERNS]

MAX_ANSWER_LENGTH = 1000
MAX_AI_RESPONSE_LENGTH = 2000


def filter_answer_text(text: str) -> tuple[str, bool]:
    """Filter user answer for PvP display.

    Returns: (filtered_text, was_filtered)
    """
    filtered = text
    was_filtered = False

    for pattern in _profanity_compiled:
        if pattern.search(filtered):
            filtered = pattern.sub("***", filtered)
            was_filtered = True

    if len(filtered) > MAX_ANSWER_LENGTH:
        filtered = filtered[:MAX_ANSWER_LENGTH] + "..."
        was_filtered = True

    return filtered, was_filtered


def detect_jailbreak(text: str) -> bool:
    """Check if user input contains jailbreak / prompt injection attempt.

    Returns True if suspicious patterns found.
    """
    for pattern in _jailbreak_compiled:
        if pattern.search(text):
            logger.warning("Jailbreak attempt detected: pattern=%s", pattern.pattern[:60])
            return True
    return False


def filter_user_input(text: str) -> tuple[str, list[str]]:
    """Filter user message before sending to LLM.

    Returns: (filtered_text, list_of_violation_types)
    """
    violations = []
    filtered = text

    # Check jailbreak
    if detect_jailbreak(filtered):
        violations.append("jailbreak_attempt")
        # Don't send to LLM at all — return safe replacement
        return "Клиент задал обычный вопрос о процедуре.", violations

    # Filter profanity
    for pattern in _profanity_compiled:
        if pattern.search(filtered):
            filtered = pattern.sub("***", filtered)
            if "profanity" not in violations:
                violations.append("profanity")

    # Filter PII
    for pattern in _pii_compiled:
        if pattern.search(filtered):
            filtered = pattern.sub("[ДАННЫЕ СКРЫТЫ]", filtered)
            if "pii" not in violations:
                violations.append("pii")

    return filtered, violations


def filter_ai_output(text: str) -> tuple[str, list[str]]:
    """Filter AI response before sending to user.

    Returns: (filtered_text, list_of_violation_types)
    """
    violations = []
    filtered = text

    # Length cap
    if len(filtered) > MAX_AI_RESPONSE_LENGTH:
        filtered = filtered[:MAX_AI_RESPONSE_LENGTH]
        last_period = filtered.rfind(".")
        if last_period > MAX_AI_RESPONSE_LENGTH * 0.7:
            filtered = filtered[:last_period + 1]
        violations.append("length_exceeded")

    # Role break detection
    for pattern in _role_break_compiled:
        if pattern.search(filtered):
            violations.append("role_break")
            logger.warning("AI role break detected in output")
            break

    # PII leak detection
    for pattern in _pii_compiled:
        if pattern.search(filtered):
            filtered = pattern.sub("[ДАННЫЕ СКРЫТЫ]", filtered)
            if "pii_leak" not in violations:
                violations.append("pii_leak")

    # Profanity in AI output
    for pattern in _profanity_compiled:
        if pattern.search(filtered):
            filtered = pattern.sub("***", filtered)
            if "profanity" not in violations:
                violations.append("profanity")

    return filtered, violations
