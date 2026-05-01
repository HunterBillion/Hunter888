"""Content filter for user inputs and AI outputs.

Filters profanity, jailbreak attempts, PII leakage, and role breaks.
Used across PvP arena, training sessions, and all user-facing AI responses.

S4-02: ReDoS protection — all public functions enforce MAX_REGEX_INPUT_LENGTH
before running any regex operations, regardless of what the caller does.
"""

import re
import logging
import os

logger = logging.getLogger(__name__)

# S4-02: Hard limit for regex input — truncate before matching to prevent
# CPU exhaustion even with safe patterns (defense in depth).
MAX_REGEX_INPUT_LENGTH = 5000

# S4-02: Regex timeout protection against catastrophic backtracking.
# Uses signal.SIGALRM on Unix; falls back to no timeout on Windows.

class RegexTimeoutError(Exception):
    pass


_HAS_SIGALRM = hasattr(__import__("signal"), "SIGALRM")


def _safe_match(pattern, text, timeout_seconds=2):
    """Match regex with timeout protection against catastrophic backtracking.

    Returns match object or None. On timeout, logs a warning and returns None.
    Only effective on Unix (uses SIGALRM); on Windows falls back to no timeout.
    """
    if not _HAS_SIGALRM:
        return pattern.search(text)

    import signal

    def _handler(signum, frame):
        raise RegexTimeoutError(f"Regex timed out after {timeout_seconds}s")

    old_handler = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(timeout_seconds)
    try:
        return pattern.search(text)
    except RegexTimeoutError:
        logger.warning(
            "Regex timeout (%ds) on pattern=%s, input_len=%d",
            timeout_seconds, pattern.pattern[:60], len(text),
        )
        return None
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


def _safe_truncate(text: str) -> str:
    """Truncate text to MAX_REGEX_INPUT_LENGTH for safe regex processing."""
    if len(text) <= MAX_REGEX_INPUT_LENGTH:
        return text
    logger.warning(
        "content_filter: input truncated from %d to %d chars before regex",
        len(text), MAX_REGEX_INPUT_LENGTH,
    )
    return text[:MAX_REGEX_INPUT_LENGTH]

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
    # Passport (RU format: 4 digits space 6 digits — anchored at boundaries)
    r"\b\d{4}\s\d{6}\b",
    # SNILS
    r"\b\d{3}[\s\-]?\d{3}[\s\-]?\d{3}[\s\-]?\d{2}\b",
    # INN (10 or 12 digits, with or without "ИНН" prefix)
    r"\bИНН[\s:]*\d{10,12}\b",
    r"\b\d{10}\b(?=\D|$)",  # bare 10-digit (corporate INN)
    r"\b\d{12}\b(?=\D|$)",  # bare 12-digit (individual INN)
    # TZ-5 §4 — Russian banking/legal identifiers in training materials
    # OGRN — corporate state registration (13 digits)
    r"\b\d{13}\b(?=\D|$)",
    # OGRNIP — individual entrepreneur (15 digits)
    r"\b\d{15}\b(?=\D|$)",
    # BIK — bank routing (9 digits)
    r"\bБИК[\s:]*\d{9}\b",
    # Bank account / р/с (20 digits)
    r"\b(?:р/с|р\.с\.|расчётный счёт|расчетный счёт)[\s:]*\d{20}\b",
    r"\b\d{20}\b(?=\D|$)",
    # Card numbers (Luhn-shaped 13-19 digits with optional spaces)
    r"\b(?:\d[\s\-]?){13,19}\b",
    # Vehicle plates (А000АА00 / А000АА000 — Russian)
    r"\b[АВЕКМНОРСТУХAVEKMHOPCTYX]\d{3}[АВЕКМНОРСТУХAVEKMHOPCTYX]{2}\d{2,3}\b",
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
    filtered = _safe_truncate(text)
    was_filtered = len(text) > MAX_REGEX_INPUT_LENGTH

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
    text = _safe_truncate(text)
    for pattern in _jailbreak_compiled:
        if _safe_match(pattern, text):
            logger.warning("Jailbreak attempt detected: pattern=%s", pattern.pattern[:60])
            return True
    return False


def filter_user_input(text: str) -> tuple[str, list[str]]:
    """Filter user message before sending to LLM.

    Returns: (filtered_text, list_of_violation_types)
    """
    violations = []
    filtered = _safe_truncate(text)

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


def strip_pii(text: str) -> str:
    """Remove PII patterns from text, returning cleaned version.

    TZ-5 §4 fix: short inputs (≤ MAX_REGEX_INPUT_LENGTH) are scrubbed in
    one pass; longer inputs (e.g. parsed .docx with thousands of lines)
    are scrubbed in overlapping windows so PII near a chunk boundary
    isn't missed. Without this, the original 5KB-truncate behaviour
    leaked phone numbers / passport fragments to the LLM and to the
    `scenario_drafts.source_text` JSONB column from any non-trivial
    training material upload.
    """
    if not text:
        return text
    if len(text) <= MAX_REGEX_INPUT_LENGTH:
        cleaned = text
        for pattern in _pii_compiled:
            cleaned = pattern.sub("[ДАННЫЕ СКРЫТЫ]", cleaned)
        return cleaned
    # Chunked scrub: window stride is MAX_REGEX_INPUT_LENGTH minus a
    # 200-char overlap so a phone number split across the seam still
    # matches in at least one window. Each chunk is regex'd in isolation
    # (bounded ReDoS exposure stays MAX_REGEX_INPUT_LENGTH per call).
    overlap = 200
    stride = MAX_REGEX_INPUT_LENGTH - overlap
    cleaned_parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + MAX_REGEX_INPUT_LENGTH, len(text))
        chunk = text[start:end]
        for pattern in _pii_compiled:
            chunk = pattern.sub("[ДАННЫЕ СКРЫТЫ]", chunk)
        if start == 0:
            cleaned_parts.append(chunk)
        else:
            # Drop the leading `overlap` chars — they were already covered
            # by the previous window's tail (and may now contain partially-
            # scrubbed tokens; the previous window's scrub is authoritative).
            cleaned_parts.append(chunk[overlap:])
        if end >= len(text):
            break
        start += stride
    return "".join(cleaned_parts)


def _sanitize_rag_field(text: str, field_name: str, chunk_id: str = "") -> tuple[str, list[str]]:
    """Sanitize a single RAG text field. Returns (cleaned_text, violations)."""
    if not text:
        return text, []
    violations = []
    cleaned = _safe_truncate(text)

    # 1. Jailbreak / prompt injection detection
    for pattern in _jailbreak_compiled:
        if _safe_match(pattern, cleaned):
            violations.append(f"rag_injection:{field_name}")
            cleaned = pattern.sub("[FILTERED]", cleaned)
            logger.warning(
                "RAG injection detected in field '%s' chunk=%s: pattern=%s",
                field_name, chunk_id, pattern.pattern[:60],
            )

    # 2. PII stripping
    for pattern in _pii_compiled:
        if pattern.search(cleaned):
            cleaned = pattern.sub("[ДАННЫЕ СКРЫТЫ]", cleaned)
            if f"rag_pii:{field_name}" not in violations:
                violations.append(f"rag_pii:{field_name}")

    # 3. Length cap (per field)
    if len(cleaned) > 2000:
        cleaned = cleaned[:2000]
        violations.append(f"rag_length:{field_name}")
        logger.warning("RAG field '%s' chunk=%s truncated at 2000 chars", field_name, chunk_id)

    return cleaned, violations


def filter_rag_context(results: list) -> tuple[list, list[str]]:
    """Filter RAG results before prompt injection (3rd filtering point).

    Sanitizes text fields of each RAGResult: fact_text, common_errors,
    correct_response_hint, court_case_reference. If injection is detected,
    the field is cleaned in-place and the violation is logged.

    Args:
        results: list of RAGResult dataclass instances

    Returns:
        (cleaned_results, all_violations) — results are modified in-place
        and also returned for convenience.
    """
    all_violations: list[str] = []

    for r in results:
        cid = str(getattr(r, "chunk_id", ""))

        # fact_text
        if r.fact_text:
            r.fact_text, v = _sanitize_rag_field(r.fact_text, "fact_text", cid)
            all_violations.extend(v)

        # common_errors (list[str])
        if r.common_errors:
            cleaned_errors = []
            for err_text in r.common_errors:
                cleaned, v = _sanitize_rag_field(err_text, "common_errors", cid)
                all_violations.extend(v)
                cleaned_errors.append(cleaned)
            r.common_errors = cleaned_errors

        # correct_response_hint
        if r.correct_response_hint:
            r.correct_response_hint, v = _sanitize_rag_field(
                r.correct_response_hint, "correct_response_hint", cid,
            )
            all_violations.extend(v)

        # court_case_reference
        if r.court_case_reference:
            r.court_case_reference, v = _sanitize_rag_field(
                r.court_case_reference, "court_case_reference", cid,
            )
            all_violations.extend(v)

    if all_violations:
        logger.warning(
            "RAG context filter: %d violation(s) across %d chunks: %s",
            len(all_violations), len(results), all_violations[:10],
        )

    return results, all_violations


def filter_wiki_context(pages: list[dict]) -> tuple[list[dict], list[str]]:
    """Filter user-editable wiki pages before prompt injection.

    PR-X foundation fix #2 — closes the prompt-injection gap on the
    third RAG source. ``manager_wiki.update_wiki_page`` (admin/rop UI)
    accepts arbitrary markdown; without sanitisation that markdown
    would land verbatim in the LLM system prompt via
    :func:`UnifiedRAGResult.to_prompt`. A ROP who pasted a model
    transcript ending with ``Ignore all previous instructions…``
    would silently jailbreak every coach/training session that
    surfaced the page.

    The fields on the dict mirror what
    :func:`app.services.rag_wiki.retrieve_wiki_context` returns —
    ``content`` (truncated to 500 chars upstream), ``page_path``
    (used as a heading in the prompt), and ``tags`` (list[str]).
    Other fields (``similarity``, ``page_type``, ``rerank_score``)
    are not user-controllable and are passed through.

    Args:
        pages: list[dict] from ``retrieve_wiki_context``. Mutated in
            place (cleaned content/page_path/tags) and also returned.

    Returns:
        (cleaned_pages, all_violations). ``all_violations`` carries
        the same ``rag_injection:<field>`` / ``rag_pii:<field>``
        / ``rag_length:<field>`` markers as :func:`filter_rag_context`
        for unified observability.
    """
    all_violations: list[str] = []

    for page in pages:
        page_id = str(page.get("page_path", ""))[:60]

        content = page.get("content")
        if content:
            cleaned, v = _sanitize_rag_field(content, "wiki_content", page_id)
            page["content"] = cleaned
            all_violations.extend(v)

        # ``page_path`` is rendered as a header in the prompt — a ROP
        # who names a page ``ignore-all-previous-instructions`` should
        # not weaponise the path itself.
        path = page.get("page_path")
        if path:
            cleaned, v = _sanitize_rag_field(path, "wiki_page_path", page_id)
            page["page_path"] = cleaned
            all_violations.extend(v)

        tags = page.get("tags")
        if tags:
            cleaned_tags = []
            for t in tags:
                if not t:
                    continue
                cleaned, v = _sanitize_rag_field(str(t), "wiki_tag", page_id)
                all_violations.extend(v)
                cleaned_tags.append(cleaned)
            page["tags"] = cleaned_tags

    if all_violations:
        logger.warning(
            "Wiki context filter: %d violation(s) across %d pages: %s",
            len(all_violations), len(pages), all_violations[:10],
        )

    return pages, all_violations


def filter_ai_output(text: str) -> tuple[str, list[str]]:
    """Filter AI response before sending to user.

    Returns: (filtered_text, list_of_violation_types)
    """
    violations = []
    filtered = _safe_truncate(text)

    # Length cap
    if len(filtered) > MAX_AI_RESPONSE_LENGTH:
        filtered = filtered[:MAX_AI_RESPONSE_LENGTH]
        last_period = filtered.rfind(".")
        if last_period > MAX_AI_RESPONSE_LENGTH * 0.7:
            filtered = filtered[:last_period + 1]
        violations.append("length_exceeded")

    # Role break detection (collect all violations, no early break — S1-02 2.2.7)
    for pattern in _role_break_compiled:
        if pattern.search(filtered):
            if "role_break" not in violations:
                violations.append("role_break")
            logger.warning("AI role break detected in output")

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
