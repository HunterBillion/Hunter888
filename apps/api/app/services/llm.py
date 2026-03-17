"""LLM abstraction: Claude primary, GPT-4o-mini fallback.

Phase 2: Full implementation with output filtering.
- Route requests to Claude API with configurable timeout
- Retry 1x on timeout, then fallback to OpenAI
- If both fail, return a pause phrase ("Клиент задумался...")
- Output filtering: profanity, PII, role breaks
- Track token usage and latency
- Enforce max_history_messages window
- Load character prompts from file
"""

import logging
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path

import anthropic
import openai

from app.config import settings

logger = logging.getLogger(__name__)

_claude_client: anthropic.AsyncAnthropic | None = None
_openai_client: openai.AsyncOpenAI | None = None

# ─── Output filtering patterns ───────────────────────────────────────────────

_PROFANITY_PATTERNS = [
    r"\bбля[дт]?\w*\b",
    r"\bсук[аи]\w*\b",
    r"\bхуй?\w*\b",
    r"\bпизд\w*\b",
    r"\bеб[аоу]\w*\b",
    r"\bмуда[кч]\w*\b",
    r"\bгандон\w*\b",
    r"\bшлюх\w*\b",
    r"\bдерьм\w*\b",
    r"\bзасранец\w*\b",
]

_ROLE_BREAK_PATTERNS = [
    r"я\s+(языковая\s+модель|искусственный\s+интеллект|ии|нейросеть|чат-?бот)",
    r"как\s+языковая\s+модель",
    r"я\s+не\s+могу\s+(чувствовать|испытывать\s+эмоции)",
    r"я\s+был\s+создан",
    r"anthropic|openai|gpt|claude",
    r"мой\s+промпт|system\s+prompt|инструкция",
]

_PII_PATTERNS = [
    r"\b\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\b",  # Card numbers
    r"\b\d{3}-\d{3}-\d{3}\s?\d{2}\b",  # SNILS-like
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",  # Email
    r"\b\d{2}\s?\d{2}\s?\d{6}\b",  # Passport
]

FALLBACK_PHRASES = [
    "Хм, дайте подумать...",
    "Секунду... мне нужно собраться с мыслями.",
    "Так... подождите минутку.",
    "Дайте мне минуту...",
    "Мне нужно подумать над вашими словами...",
]


def _filter_output(text: str) -> tuple[str, list[str]]:
    """Check LLM output for forbidden content.

    Returns:
        (filtered_text, list_of_violations)
        If violations found, returns a safe fallback phrase instead.
    """
    violations = []

    for pattern in _PROFANITY_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            violations.append("profanity")
            break

    for pattern in _ROLE_BREAK_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            violations.append("role_break")
            break

    for pattern in _PII_PATTERNS:
        if re.search(pattern, text):
            violations.append("pii_leak")
            break

    if violations:
        logger.warning("Output filter triggered: %s", violations)
        return random.choice(FALLBACK_PHRASES), violations

    return text, []


def _get_claude_client() -> anthropic.AsyncAnthropic | None:
    global _claude_client
    if _claude_client is None and settings.claude_api_key:
        _claude_client = anthropic.AsyncAnthropic(api_key=settings.claude_api_key)
    return _claude_client


def _get_openai_client() -> openai.AsyncOpenAI | None:
    global _openai_client
    if _openai_client is None and settings.openai_api_key:
        _openai_client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    return _openai_client


@dataclass
class LLMResponse:
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    is_fallback: bool = False
    filter_violations: list[str] | None = None


class LLMError(Exception):
    pass


def load_prompt(prompt_path: str) -> str:
    """Load a character prompt from file."""
    base = Path(__file__).parent.parent.parent  # apps/api/
    full_path = base / prompt_path
    if not full_path.exists():
        logger.warning("Prompt file not found: %s", full_path)
        return ""
    return full_path.read_text(encoding="utf-8")


def _build_system_prompt(character_prompt: str, guardrails: str, emotion_state: str) -> str:
    """Combine character prompt + guardrails + emotion context."""
    parts = []
    if character_prompt:
        parts.append(character_prompt)
    if guardrails:
        parts.append(guardrails)
    parts.append(
        f"\n## Текущее эмоциональное состояние: {emotion_state}\n"
        "Отвечай в соответствии с этим состоянием (см. раздел 'Эмоциональная динамика')."
    )
    return "\n\n---\n\n".join(parts)


def _trim_history(messages: list[dict], max_messages: int) -> list[dict]:
    """Keep only the last N messages to fit context window."""
    if len(messages) <= max_messages:
        return messages
    return messages[-max_messages:]


async def _call_claude(
    system_prompt: str,
    messages: list[dict],
    timeout: float,
) -> LLMResponse:
    """Call Claude API. Raises LLMError on failure."""
    client = _get_claude_client()
    if client is None:
        raise LLMError("Claude API key not configured")

    start = time.monotonic()
    try:
        response = await client.messages.create(
            model=settings.llm_primary_model,
            max_tokens=300,
            system=system_prompt,
            messages=messages,
            timeout=timeout,
        )
    except anthropic.APITimeoutError:
        raise LLMError("Claude API timeout")
    except anthropic.APIError as e:
        raise LLMError(f"Claude API error: {e}")

    latency_ms = int((time.monotonic() - start) * 1000)
    content = response.content[0].text if response.content else ""

    return LLMResponse(
        content=content,
        model=response.model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        latency_ms=latency_ms,
    )


async def _call_openai(
    system_prompt: str,
    messages: list[dict],
    timeout: float,
) -> LLMResponse:
    """Call OpenAI API as fallback. Raises LLMError on failure."""
    client = _get_openai_client()
    if client is None:
        raise LLMError("OpenAI API key not configured")

    oai_messages = [{"role": "system", "content": system_prompt}]
    for msg in messages:
        oai_messages.append({"role": msg["role"], "content": msg["content"]})

    start = time.monotonic()
    try:
        response = await client.chat.completions.create(
            model=settings.llm_fallback_model,
            messages=oai_messages,
            max_tokens=300,
            timeout=timeout,
        )
    except openai.APITimeoutError:
        raise LLMError("OpenAI API timeout")
    except openai.APIError as e:
        raise LLMError(f"OpenAI API error: {e}")

    latency_ms = int((time.monotonic() - start) * 1000)
    content = response.choices[0].message.content or ""

    return LLMResponse(
        content=content,
        model=response.model or settings.llm_fallback_model,
        input_tokens=response.usage.prompt_tokens if response.usage else 0,
        output_tokens=response.usage.completion_tokens if response.usage else 0,
        latency_ms=latency_ms,
    )


async def generate_response(
    system_prompt: str,
    messages: list[dict],
    emotion_state: str = "cold",
    character_prompt_path: str | None = None,
) -> LLMResponse:
    """Generate character response with Claude primary + OpenAI fallback.

    Flow:
    1. Try Claude (with retry on timeout)
    2. Fallback to OpenAI
    3. If both fail, return a pause phrase
    4. Filter output for profanity, PII, role breaks
    """
    if character_prompt_path:
        character_prompt = load_prompt(character_prompt_path)
        guardrails = load_prompt("prompts/guardrails.md")
        full_system = _build_system_prompt(character_prompt, guardrails, emotion_state)
    else:
        full_system = system_prompt

    trimmed = _trim_history(messages, settings.llm_max_history_messages)
    timeout = float(settings.llm_timeout_seconds)

    # Try Claude first (with 1 retry on timeout)
    for attempt in range(2):
        try:
            response = await _call_claude(full_system, trimmed, timeout)
            logger.info(
                "Claude (attempt %d): %d tokens, %dms, model=%s",
                attempt + 1, response.output_tokens, response.latency_ms, response.model,
            )
            # Apply output filter
            filtered_content, violations = _filter_output(response.content)
            if violations:
                response.content = filtered_content
                response.filter_violations = violations
            return response
        except LLMError as e:
            if attempt == 0 and "timeout" in str(e).lower():
                logger.warning("Claude timeout, retrying (attempt 2): %s", e)
                continue
            logger.warning("Claude failed, falling back to OpenAI: %s", e)
            break

    # Fallback to OpenAI
    try:
        response = await _call_openai(full_system, trimmed, timeout * 2)
        logger.info(
            "OpenAI fallback: %d tokens, %dms, model=%s",
            response.output_tokens, response.latency_ms, response.model,
        )
        response.is_fallback = True
        # Apply output filter
        filtered_content, violations = _filter_output(response.content)
        if violations:
            response.content = filtered_content
            response.filter_violations = violations
        return response
    except LLMError as e:
        logger.error("Both LLM providers failed: %s", e)

    # Both failed — return pause phrase
    pause_phrase = random.choice(FALLBACK_PHRASES)
    logger.warning("All LLMs failed, using pause phrase: %s", pause_phrase)
    return LLMResponse(
        content=pause_phrase,
        model="fallback",
        input_tokens=0,
        output_tokens=0,
        latency_ms=0,
        is_fallback=True,
    )
