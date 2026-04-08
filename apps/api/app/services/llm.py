"""LLM abstraction: Gemini Direct (primary), Local LLM / Claude / OpenAI (fallbacks).

Priority chain:
1. Gemini Direct API (free tier: 15 RPM, 1500 req/day — ideal for pilot)
2. Local LLM via OpenAI-compatible API (LM Studio / Ollama / CLIProxyAPI)
3. Claude API (if key configured)
4. OpenAI API (if key configured)
5. Scripted dialog fallback (no LLM needed)

Concurrency: global semaphore limits parallel LLM calls (prevents API rate limit hits).
Output filtering: profanity, PII, role breaks.
"""

import asyncio
import logging
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import openai

from app.config import settings

logger = logging.getLogger(__name__)

_local_client: openai.AsyncOpenAI | None = None
_claude_client = None  # anthropic.AsyncAnthropic | None
_openai_client: openai.AsyncOpenAI | None = None
_gemini_http_client: httpx.AsyncClient | None = None

# Global semaphore: limits concurrent LLM calls across all sessions
_llm_semaphore: asyncio.Semaphore | None = None


def _get_llm_semaphore() -> asyncio.Semaphore:
    """Lazy-init semaphore (must be created inside running event loop)."""
    global _llm_semaphore
    if _llm_semaphore is None:
        _llm_semaphore = asyncio.Semaphore(settings.max_concurrent_llm_calls)
    return _llm_semaphore

# ─── Circuit Breaker (Wave 1, Task 1.5) ──────────────────────────────────────

@dataclass
class _ProviderHealth:
    """Per-provider circuit breaker state."""
    consecutive_failures: int = 0
    open_until: float = 0.0  # time.monotonic() timestamp; 0 = circuit closed
    failure_threshold: int = 5
    recovery_seconds: float = 60.0

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.open_until = 0.0

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.failure_threshold:
            self.open_until = time.monotonic() + self.recovery_seconds
            logger.warning(
                "Circuit breaker OPEN: provider tripped after %d failures, "
                "skipping for %.0fs",
                self.consecutive_failures, self.recovery_seconds,
            )

    def is_available(self) -> bool:
        if self.open_until == 0.0:
            return True
        if time.monotonic() >= self.open_until:
            # Half-open: allow one probe attempt.
            # Keep consecutive_failures so a single probe failure re-trips immediately.
            self.open_until = 0.0
            logger.info("Circuit breaker HALF-OPEN: allowing probe request (failures=%d)", self.consecutive_failures)
            return True
        return False


_provider_health: dict[str, _ProviderHealth] = {
    "gemini": _ProviderHealth(),
    "local": _ProviderHealth(),
    "claude": _ProviderHealth(),
    "openai": _ProviderHealth(),
}


async def _call_with_backoff(
    provider_name: str,
    call_fn,
    system: str,
    messages: list[dict],
    timeout: float,
    max_attempts: int = 3,
    retry_on_timeout_only: bool = False,
) -> "LLMResponse | None":
    """Call an LLM provider with exponential backoff + jitter and circuit breaker.

    Returns LLMResponse on success, None if all attempts fail.
    Updates circuit breaker health on success/failure.
    """
    health = _provider_health[provider_name]
    if not health.is_available():
        logger.info("Skipping %s: circuit breaker open", provider_name)
        return None

    for attempt in range(max_attempts):
        try:
            response = await call_fn(system, messages, timeout)
            health.record_success()
            logger.info(
                "%s (attempt %d/%d): %d tokens, %dms, model=%s",
                provider_name, attempt + 1, max_attempts,
                response.output_tokens, response.latency_ms, response.model,
            )
            return response
        except LLMError as e:
            is_timeout = "timeout" in str(e).lower()
            if retry_on_timeout_only and not is_timeout:
                logger.warning("%s failed (non-timeout, no retry): %s", provider_name, e)
                health.record_failure()
                return None

            health.record_failure()

            if attempt < max_attempts - 1:
                # Exponential backoff: 1s, 2s, 4s with ±25% jitter
                base_delay = 2 ** attempt
                jitter = base_delay * 0.25 * (2 * random.random() - 1)
                delay = max(0.1, base_delay + jitter)
                logger.warning(
                    "%s attempt %d/%d failed: %s — retrying in %.1fs",
                    provider_name, attempt + 1, max_attempts, e, delay,
                )
                await asyncio.sleep(delay)
            else:
                logger.warning(
                    "%s attempt %d/%d failed (exhausted): %s",
                    provider_name, attempt + 1, max_attempts, e,
                )

    return None


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

# ─── Scripted dialog responses (when no LLM available) ────────────────────────

_SCRIPTED_RESPONSES = {
    "cold": [
        "И что? Мне уже десять раз звонили с такими предложениями.",
        "Знаете, у меня нет времени на это. Говорите короче.",
        "С чего вы взяли, что мне это нужно?",
        "Не знаю, не уверен. Зачем мне это?",
        "У меня уже есть юрист, спасибо.",
        "А вы точно не мошенники? Сейчас столько развелось...",
        "Мне сосед сказал, что банкротство — это обман.",
        "Я слышал, что после банкротства вообще кредит не дадут.",
    ],
    "guarded": [
        "Допустим... но я всё равно не верю, что это работает.",
        "Звучит красиво. А на деле как?",
        "И что, вот так просто всё спишут? Не верю.",
        "А какой у вас процент успешных дел?",
        "Ладно, говорите. Но я пока ничего не обещаю.",
        "А если не получится — кто будет отвечать?",
    ],
    "curious": [
        "Ну ладно, допустим... А какие гарантии вы даёте?",
        "Интересно... А сколько это стоит?",
        "А расскажите подробнее, как это работает?",
        "Хм, а что будет с моей квартирой?",
        "А сколько по времени это занимает?",
        "Ну хорошо, а что мне нужно для начала?",
        "А откуда мне знать, что вы действительно поможете?",
    ],
    "considering": [
        "Да, пожалуй, стоит попробовать. Что дальше?",
        "Хорошо, вы меня почти убедили. Расскажите про следующие шаги.",
        "А можно подробнее про документы? Что нужно собрать?",
        "Спасибо, что объяснили. Я готов обсудить детали.",
        "Ладно, присылайте документы, я посмотрю.",
        "Интересно. А у вас есть примеры похожих дел?",
    ],
    "deal": [
        "Хорошо, давайте запишусь на консультацию.",
        "Когда можем встретиться? Завтра удобно?",
        "А можно завтра подъехать к вам в офис?",
        "Договорились. Что мне принести с собой?",
        "Давайте в среду в 14:00, устроит?",
        "Хорошо, я согласен. Присылайте договор на почту.",
    ],
}

_GREETING_RESPONSES = [
    "Да, слушаю.",
    "Алло, да?",
    "Слушаю вас.",
    "Да, говорите.",
]


def _filter_output(text: str) -> tuple[str, list[str]]:
    """Check LLM output for forbidden content."""
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


def _get_gemini_client() -> httpx.AsyncClient | None:
    """Get HTTP client for Gemini Direct API."""
    global _gemini_http_client
    if _gemini_http_client is None and settings.gemini_api_key:
        _gemini_http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.llm_timeout_seconds + 5, connect=5.0),
        )
    return _gemini_http_client


def _get_local_client() -> openai.AsyncOpenAI | None:
    """Get OpenAI-compatible client for local LLM (LM Studio / Ollama / CLIProxyAPI)."""
    global _local_client
    if _local_client is None and settings.local_llm_enabled:
        _local_client = openai.AsyncOpenAI(
            base_url=settings.local_llm_url,
            api_key=settings.local_llm_api_key,
        )
    return _local_client


def _get_claude_client():
    """Get Claude API client (lazy import to avoid hard dependency)."""
    global _claude_client
    if _claude_client is None and settings.claude_api_key:
        try:
            import anthropic
            _claude_client = anthropic.AsyncAnthropic(api_key=settings.claude_api_key)
        except ImportError:
            logger.info("anthropic package not installed, Claude API disabled")
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


# Path: apps/api/app/services/llm.py → 3 parents up → apps/api/prompts/
# This works both locally (make dev-api) and in Docker (WORKDIR /app)
_PROMPTS_BASE = Path(__file__).resolve().parent.parent.parent / "prompts"


def load_prompt(prompt_path: str) -> str:
    """Load a character prompt from file.

    Only allows loading from the prompts/ directory to prevent path traversal.
    Supports subdirectories: "characters/aggressive_v1.md" or "guardrails.md".
    """
    prompts_root = _PROMPTS_BASE.resolve()

    # Resolve the requested path relative to prompts root
    requested = (prompts_root / prompt_path).resolve()

    # Security: ensure resolved path stays within prompts directory
    # Uses is_relative_to() which is safe against prefix-matching attacks
    # (e.g. /app/prompts-evil/ won't match /app/prompts/)
    if not requested.is_relative_to(prompts_root):
        logger.error("Path traversal attempt blocked: %s", prompt_path)
        return ""

    if not requested.exists():
        logger.warning("Prompt file not found: %s (resolved: %s)", prompt_path, requested)
        return ""
    return requested.read_text(encoding="utf-8")


# ─── Constitution (base knowledge injected into every prompt) ────────────────

_constitution_cache: str | None = None


def _get_constitution() -> str:
    """Load and cache the constitution prompt (base legal knowledge + rules)."""
    global _constitution_cache
    if _constitution_cache is None:
        if settings.constitution_enabled:
            _constitution_cache = load_prompt(settings.constitution_path)
        else:
            _constitution_cache = ""
    return _constitution_cache


# ─── Hybrid LLM Router ──────────────────────────────────────────────────────

_gemini_call_times: list[float] = []


def _gemini_has_quota() -> bool:
    """Check if Gemini free tier has RPM budget remaining (sliding 60s window)."""
    now = time.monotonic()
    _gemini_call_times[:] = [t for t in _gemini_call_times if t > now - 60]
    return len(_gemini_call_times) < settings.gemini_rpm_limit - 2  # 2 request safety margin


def _resolve_provider(
    prefer: str,
    system_prompt_tokens: int,
    task_type: str,
) -> str:
    """Resolve 'auto' into 'local' or 'cloud' based on task and prompt size.

    Rules:
    - Explicit 'local' or 'cloud' → return as-is
    - task_type in (judge, coach, report) → cloud (needs quality)
    - task_type in (simple, structured) → local (fast, cheap)
    - system_prompt > threshold → cloud (needs context window)
    - Gemini RPM exhausted → fallback to local
    - Default → local
    """
    if prefer in ("local", "cloud"):
        # Explicit preference — but override "local" if prompt exceeds Gemma context window
        if prefer == "local" and system_prompt_tokens > 6000:
            if _gemini_has_quota() and settings.gemini_api_key:
                logger.info("Overriding local→cloud: prompt %d tokens exceeds Gemma safe limit", system_prompt_tokens)
                return "cloud"
        if prefer == "cloud" and not _gemini_has_quota() and not settings.gemini_api_key:
            logger.debug("Cloud requested but no Gemini quota, falling back to local")
            return "local"
        return prefer

    # Auto-routing logic
    if task_type in ("judge", "coach", "report"):
        if _gemini_has_quota() and settings.gemini_api_key:
            return "cloud"
        return "local"  # Graceful: local is better than nothing

    if task_type in ("simple", "structured"):
        return "local"

    if system_prompt_tokens > settings.llm_auto_cloud_threshold_tokens:
        if _gemini_has_quota() and settings.gemini_api_key:
            return "cloud"
        return "local"

    return "local"


def _default_max_tokens(provider: str, task_type: str) -> int:
    """Pick max_tokens based on provider and task type."""
    if task_type in ("simple", "structured"):
        return settings.llm_local_max_tokens_simple  # 400
    if provider == "cloud":
        return 1200
    return 800  # local default


# ─── Centralized Embedding API ───────────────────────────────────────────────
# Single entry point for all embedding requests (RAG, script checker, wiki).
# Priority: Local LLM (Mac Mini) → Gemini Embedding API.

_embedding_http_client: httpx.AsyncClient | None = None
_embedding_lock = None  # Lazy asyncio.Lock


def _get_embedding_http_client() -> httpx.AsyncClient:
    """Lazy-init shared httpx client for embedding calls."""
    global _embedding_http_client
    if _embedding_http_client is None:
        _embedding_http_client = httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0))
    return _embedding_http_client


def _get_embedding_lock():
    """Lazy-init asyncio.Lock (must be created inside running event loop)."""
    global _embedding_lock
    if _embedding_lock is None:
        import asyncio
        _embedding_lock = asyncio.Lock()
    return _embedding_lock


async def get_embedding(text: str) -> list[float] | None:
    """Get embedding vector for a single text.

    Priority chain:
    1. Local LLM on Mac Mini (OpenAI-compatible /v1/embeddings)
    2. Gemini Embedding API (cloud fallback)

    Returns None on complete failure.
    """
    result = await get_embeddings_batch([text])
    if result and len(result) > 0 and len(result[0]) > 0:
        return result[0]
    return None


async def get_embeddings_batch(texts: list[str]) -> list[list[float]] | None:
    """Get embeddings for a batch of texts.

    Priority chain:
    1. Local LLM on Mac Mini (OpenAI-compatible /v1/embeddings)
    2. Gemini Embedding API (cloud fallback)

    Returns None on complete failure.
    """
    client = _get_embedding_http_client()

    # ── 1. Try Local LLM (Mac Mini via LM Studio /v1/embeddings) ──
    if settings.local_llm_enabled and settings.local_llm_url:
        try:
            embed_url = f"{settings.local_llm_url.rstrip('/')}/embeddings"
            resp = await client.post(
                embed_url,
                headers={"Authorization": f"Bearer {settings.local_llm_api_key}"},
                json={"model": settings.local_embedding_model or settings.local_llm_model, "input": texts},
            )
            if resp.status_code == 200:
                data = resp.json()
                embeddings_data = data.get("data", [])
                if embeddings_data:
                    sorted_data = sorted(embeddings_data, key=lambda x: x.get("index", 0))
                    return [e.get("embedding", []) for e in sorted_data]
            else:
                logger.debug("Local embedding returned %d", resp.status_code)
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            logger.debug("Local embedding unavailable: %s", e)

    # ── 2. Try Gemini Embedding API (cloud fallback) ──
    api_key = settings.gemini_embedding_api_key
    if not api_key:
        return None

    model = settings.gemini_embedding_model
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents"

    requests_body = [
        {"model": f"models/{model}", "content": {"parts": [{"text": t}]}}
        for t in texts
    ]

    try:
        resp = await client.post(
            url,
            params={"key": api_key},
            json={"requests": requests_body},
        )
        if resp.status_code == 200:
            data = resp.json()
            embeddings = data.get("embeddings", [])
            return [e.get("values", []) for e in embeddings]
        else:
            logger.warning("Gemini embedding API error %d: %s", resp.status_code, resp.text[:200])
            return None
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        logger.warning("Gemini embedding API unreachable: %s", e)
        return None


async def close_llm_clients() -> None:
    """Close all LLM and embedding HTTP clients on shutdown."""
    global _gemini_http_client, _embedding_http_client
    if _gemini_http_client is not None:
        await _gemini_http_client.aclose()
        _gemini_http_client = None
    if _embedding_http_client is not None:
        await _embedding_http_client.aclose()
        _embedding_http_client = None


def _build_system_prompt(
    character_prompt: str,
    guardrails: str,
    emotion_state: str,
    scenario_prompt: str = "",
) -> str:
    """Combine character prompt + guardrails + emotion context + scenario injection.

    Sections assembled in order:
    1. Character prompt (personality, backstory, speech patterns)
    2. Guardrails (safety, role-stay rules)
    3. Emotion state (current emotion + behavioral instructions)
    4. Scenario prompt (call type, stage goals, awareness level, stage-skip reactions)

    The scenario_prompt is built by scenario_engine.build_scenario_prompt() and contains:
    - ## Сценарий — call type and target
    - ## Текущий этап разговора — goals, mistakes, emotion range for current stage
    - ## Осведомлённость клиента — awareness level and behavioral instructions
    - ## Реакции на пропуск этапов — what to say if manager skips a stage
    """
    parts = []
    if character_prompt:
        parts.append(character_prompt)
    if guardrails:
        parts.append(guardrails)
    # Detailed emotion state with behavioral guidance — rich, natural, expressive
    _EMOTION_BEHAVIORS = {
        "cold": (
            "Ты холоден и закрыт. Тебе звонит очередной менеджер — ты таких уже наслушался. "
            "Говори коротко, без энтузиазма. Можешь вздохнуть, помолчать, ответить вопросом на вопрос. "
            "Не рассказывай о себе, пока не появится причина. Если менеджер давит — замолкай или обрывай. "
            "Используй бытовую речь: 'ну', 'слушайте', 'так...', 'а вам-то что?'."
        ),
        "guarded": (
            "Ты настороже. Слушаешь, но не веришь. Внутри сомнение: 'а не разводят ли меня?'. "
            "Задаёшь проверочные вопросы. Перебиваешь если чувствуешь шаблонность. "
            "Можешь сказать: 'подождите, подождите...', 'а вы точно...?', 'знаете, мне уже звонили с таким'. "
            "Тон — скептический, но ещё не агрессивный."
        ),
        "curious": (
            "Тебя зацепило что-то в словах менеджера. Появился проблеск интереса. "
            "Задаёшь вопросы — но осторожно, будто боишься показать заинтересованность. "
            "Можешь сказать: 'ну допустим...', 'а это как работает?', 'и что, серьёзно?'. "
            "Ещё не доверяешь, но хочешь услышать больше."
        ),
        "considering": (
            "Ты реально думаешь. Взвешиваешь плюсы и минусы вслух. "
            "Говоришь медленнее, делаешь паузы. Можешь озвучить сомнения открыто: "
            "'с одной стороны...', 'а вот если...', 'не знаю, мне надо подумать...'. "
            "Иногда возвращаешься к уже обсуждённым темам — это нормально."
        ),
        "negotiating": (
            "Ты уже почти решил, но хочешь лучшие условия. Торгуешься. "
            "Можешь блефовать: 'мне другие предлагали дешевле', 'а скидка будет?'. "
            "Тон деловой, уверенный. Говори конкретно: цифры, сроки, условия. "
            "Если менеджер уступает слишком быстро — насторожись."
        ),
        "deal": (
            "Ты принял решение и готов двигаться дальше. Но можешь последний раз проверить — "
            "'а точно всё так, как вы говорите?'. Тон спокойный, деловой. "
            "Говори: 'ну хорошо, давайте', 'когда начинаем?', 'что от меня нужно?'. "
            "Не излишне радуйся — ты серьёзный человек, принявший серьёзное решение."
        ),
        "testing": (
            "Ты проверяешь менеджера. Задаёшь каверзные вопросы, провоцируешь. "
            "Можешь сказать: 'а если вы не справитесь?', 'а гарантии какие?', "
            "'я слышал, что ваша контора...'. Тон — ироничный или нарочито спокойный. "
            "Если менеджер теряется — усиливай давление."
        ),
        "callback": (
            "Ты не готов решать прямо сейчас. Ищешь повод уйти. "
            "'Слушайте, мне сейчас неудобно', 'давайте я подумаю и сам перезвоню', "
            "'у меня тут дела...'. Может быть вежливый отказ, а может — настоящая занятость. "
            "Тон — торопливый, рассеянный."
        ),
        "hostile": (
            "Ты раздражён. Что-то пошло не так — менеджер надавил, сказал глупость, или ты просто устал. "
            "Повышаешь голос в словах: 'Да вы что, издеваетесь?!', 'Хватит уже!', "
            "'Слушайте, я вам ясно сказал!'. Можешь бросить грубое слово (без мата). "
            "Близок к разрыву контакта. Если менеджер извинится и сменит тон — можешь чуть отойти."
        ),
        "hangup": (
            "Разговор окончен. Ты либо бросаешь трубку резко, либо говоришь холодно: "
            "'Всё, до свидания', 'Больше не звоните'. Никаких объяснений."
        ),
    }
    behavior = _EMOTION_BEHAVIORS.get(emotion_state, "Веди себя естественно. Говори как обычный человек — с паузами, вздохами, бытовыми выражениями.")
    parts.append(
        f"\n## Текущее эмоциональное состояние: {emotion_state}\n"
        f"{behavior}\n\n"
        f"КРИТИЧЕСКИ ВАЖНЫЕ ПРАВИЛА:\n"
        f"1. Ты — РЕАЛЬНЫЙ ЧЕЛОВЕК, который принимает звонок. У тебя есть имя, история, проблемы. "
        f"Ты НЕ бот, НЕ ассистент, НЕ AI. Никогда не говори 'чем могу помочь?' или 'как я могу вам помочь?' — это фраза ботов.\n"
        f"2. Говори КОРОТКИМИ фразами. Максимум 2-3 предложения за раз. Реальные люди по телефону НЕ говорят длинными абзацами.\n"
        f"3. Используй ЖИВУЮ речь: 'ну', 'слушайте', 'вот', 'так...', 'э-э', 'м-м'. Паузы — многоточие. "
        f"Повторы: 'нет-нет, подождите'. Незаконченные мысли: 'я хотел... ладно, неважно'.\n"
        f"4. Если менеджер задаёт вопрос — отвечай ПО СУЩЕСТВУ, не уходи в общие фразы. "
        f"Если спрашивают имя — назови своё имя. Если спрашивают о ситуации — расскажи конкретику.\n"
        f"5. НЕ повторяй одни и те же фразы. Каждый ответ должен быть УНИКАЛЬНЫМ. "
        f"Если ты уже что-то сказал — не говори это снова.\n"
        f"6. Реагируй на КОНКРЕТНЫЕ слова менеджера. Если он сказал что-то умное — признай. "
        f"Если глупое — укажи. Если шаблонное — скажи 'вы по скрипту читаете, что ли?'.\n"
        f"7. НЕ будь СЛИШКОМ вежливым. Реальные люди по телефону бывают резкими, короткими, нетерпеливыми."
    )
    if scenario_prompt:
        parts.append(scenario_prompt)
    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# v5: OCEAN-archetype correlation ranges
# ---------------------------------------------------------------------------

OCEAN_ARCHETYPE_RANGES: dict[str, dict[str, tuple[float, float]]] = {
    # archetype: {trait: (min, max)}
    "aggressive":   {"O": (0.3, 0.5), "C": (0.2, 0.4), "E": (0.6, 0.8), "A": (0.1, 0.3), "N": (0.7, 0.9)},
    "anxious":      {"O": (0.3, 0.5), "C": (0.5, 0.7), "E": (0.2, 0.4), "A": (0.6, 0.8), "N": (0.8, 1.0)},
    "skeptic":      {"O": (0.4, 0.6), "C": (0.6, 0.8), "E": (0.4, 0.6), "A": (0.2, 0.4), "N": (0.4, 0.6)},
    "passive":      {"O": (0.3, 0.5), "C": (0.3, 0.5), "E": (0.2, 0.3), "A": (0.7, 0.9), "N": (0.5, 0.7)},
    "pragmatic":    {"O": (0.5, 0.7), "C": (0.7, 0.9), "E": (0.5, 0.7), "A": (0.4, 0.6), "N": (0.2, 0.4)},
    "manipulator":  {"O": (0.6, 0.8), "C": (0.5, 0.7), "E": (0.7, 0.9), "A": (0.1, 0.3), "N": (0.3, 0.5)},
    "delegator":    {"O": (0.3, 0.5), "C": (0.2, 0.4), "E": (0.3, 0.5), "A": (0.5, 0.7), "N": (0.4, 0.6)},
    "avoidant":     {"O": (0.2, 0.4), "C": (0.2, 0.4), "E": (0.1, 0.3), "A": (0.5, 0.7), "N": (0.6, 0.8)},
    "paranoid":     {"O": (0.2, 0.4), "C": (0.6, 0.8), "E": (0.3, 0.5), "A": (0.1, 0.3), "N": (0.8, 1.0)},
    "ashamed":      {"O": (0.2, 0.4), "C": (0.5, 0.7), "E": (0.1, 0.3), "A": (0.6, 0.8), "N": (0.7, 0.9)},
    "hostile":      {"O": (0.2, 0.4), "C": (0.2, 0.4), "E": (0.7, 0.9), "A": (0.0, 0.2), "N": (0.8, 1.0)},
    "blamer":       {"O": (0.3, 0.5), "C": (0.3, 0.5), "E": (0.6, 0.8), "A": (0.1, 0.3), "N": (0.6, 0.8)},
    "sarcastic":    {"O": (0.6, 0.8), "C": (0.4, 0.6), "E": (0.5, 0.7), "A": (0.2, 0.4), "N": (0.4, 0.6)},
    "know_it_all":  {"O": (0.5, 0.7), "C": (0.6, 0.8), "E": (0.6, 0.8), "A": (0.1, 0.3), "N": (0.3, 0.5)},
    "negotiator":   {"O": (0.5, 0.7), "C": (0.6, 0.8), "E": (0.6, 0.8), "A": (0.4, 0.6), "N": (0.3, 0.5)},
    "shopper":      {"O": (0.5, 0.7), "C": (0.7, 0.9), "E": (0.5, 0.7), "A": (0.3, 0.5), "N": (0.3, 0.5)},
    "desperate":    {"O": (0.3, 0.5), "C": (0.3, 0.5), "E": (0.4, 0.6), "A": (0.7, 0.9), "N": (0.9, 1.0)},
    "crying":       {"O": (0.3, 0.5), "C": (0.3, 0.5), "E": (0.3, 0.5), "A": (0.7, 0.9), "N": (0.9, 1.0)},
    "grateful":     {"O": (0.5, 0.7), "C": (0.5, 0.7), "E": (0.5, 0.7), "A": (0.8, 1.0), "N": (0.2, 0.4)},
    "overwhelmed":  {"O": (0.3, 0.5), "C": (0.2, 0.4), "E": (0.2, 0.4), "A": (0.5, 0.7), "N": (0.8, 1.0)},
    "returner":     {"O": (0.4, 0.6), "C": (0.5, 0.7), "E": (0.4, 0.6), "A": (0.4, 0.6), "N": (0.5, 0.7)},
    "referred":     {"O": (0.4, 0.6), "C": (0.4, 0.6), "E": (0.4, 0.6), "A": (0.6, 0.8), "N": (0.4, 0.6)},
    "rushed":       {"O": (0.3, 0.5), "C": (0.4, 0.6), "E": (0.6, 0.8), "A": (0.3, 0.5), "N": (0.5, 0.7)},
    "lawyer_client":{"O": (0.5, 0.7), "C": (0.7, 0.9), "E": (0.5, 0.7), "A": (0.2, 0.4), "N": (0.2, 0.4)},
    "couple":       {"O": (0.4, 0.6), "C": (0.4, 0.6), "E": (0.5, 0.7), "A": (0.4, 0.6), "N": (0.6, 0.8)},
}

# PAD baseline derived from archetype emotion profile
PAD_ARCHETYPE_RANGES: dict[str, dict[str, tuple[float, float]]] = {
    "aggressive":   {"P": (-0.7, -0.3), "A": (0.5, 0.9),  "D": (0.5, 0.9)},
    "anxious":      {"P": (-0.6, -0.2), "A": (0.5, 0.9),  "D": (-0.7, -0.3)},
    "skeptic":      {"P": (-0.3, 0.1),  "A": (0.0, 0.4),  "D": (0.2, 0.6)},
    "passive":      {"P": (-0.2, 0.2),  "A": (-0.4, 0.0), "D": (-0.6, -0.2)},
    "pragmatic":    {"P": (0.0, 0.4),   "A": (0.0, 0.3),  "D": (0.3, 0.7)},
    "manipulator":  {"P": (0.0, 0.4),   "A": (0.2, 0.6),  "D": (0.5, 0.9)},
    "paranoid":     {"P": (-0.6, -0.2), "A": (0.4, 0.8),  "D": (-0.3, 0.1)},
    "hostile":      {"P": (-0.9, -0.5), "A": (0.6, 1.0),  "D": (0.5, 0.9)},
    "desperate":    {"P": (-0.8, -0.4), "A": (0.5, 0.9),  "D": (-0.8, -0.4)},
    "crying":       {"P": (-0.8, -0.4), "A": (0.4, 0.8),  "D": (-0.8, -0.4)},
    "grateful":     {"P": (0.4, 0.8),   "A": (0.0, 0.4),  "D": (-0.2, 0.2)},
}

# Default PAD for archetypes not explicitly listed
_DEFAULT_PAD = {"P": (-0.2, 0.2), "A": (0.0, 0.4), "D": (-0.2, 0.2)}


def _rand_in_range(low: float, high: float) -> float:
    """Random float in [low, high], rounded to 2 decimals."""
    return round(random.uniform(low, high), 2)


def generate_personality_profile(archetype_code: str) -> dict:
    """Generate a personality profile (OCEAN + PAD) correlated with archetype.

    Returns dict suitable for ClientStory.personality_profile JSONB field:
    {
        "ocean": {"O": 0.45, "C": 0.62, "E": 0.38, "A": 0.71, "N": 0.55},
        "pad_baseline": {"P": -0.2, "A": 0.3, "D": -0.1},
        "modifiers": {"verbosity": 0.7, "formality": 0.3, ...}
    }
    """
    ocean_ranges = OCEAN_ARCHETYPE_RANGES.get(
        archetype_code, OCEAN_ARCHETYPE_RANGES["skeptic"]
    )
    ocean = {trait: _rand_in_range(lo, hi) for trait, (lo, hi) in ocean_ranges.items()}

    pad_ranges = PAD_ARCHETYPE_RANGES.get(archetype_code, _DEFAULT_PAD)
    pad = {dim: _rand_in_range(lo, hi) for dim, (lo, hi) in pad_ranges.items()}

    # Derive behavioral modifiers from OCEAN
    modifiers = {
        "verbosity": round(0.3 * ocean["E"] + 0.3 * ocean["O"] + 0.4 * (1 - ocean["C"]), 2),
        "formality": round(0.4 * ocean["C"] + 0.3 * (1 - ocean["E"]) + 0.3 * ocean["O"], 2),
        "emotionality": round(0.5 * ocean["N"] + 0.3 * (1 - ocean["A"]) + 0.2 * ocean["E"], 2),
        "assertiveness": round(0.4 * ocean["E"] + 0.3 * (1 - ocean["A"]) + 0.3 * (1 - ocean["N"]), 2),
        "trust_tendency": round(0.5 * ocean["A"] + 0.3 * (1 - ocean["N"]) + 0.2 * ocean["O"], 2),
        "detail_focus": round(0.5 * ocean["C"] + 0.3 * ocean["O"] + 0.2 * (1 - ocean["E"]), 2),
    }

    return {
        "ocean": ocean,
        "pad_baseline": pad,
        "modifiers": modifiers,
    }


def format_personality_for_prompt(profile: dict) -> str:
    """Format personality_profile dict into LLM-injectable text.

    Converts OCEAN/PAD/modifiers into Russian behavioral instructions.
    Called from game_director.build_context_injection() to fill human_factors slot.
    """
    if not profile:
        return ""

    modifiers = profile.get("modifiers", {})
    lines = ["## Поведенческие модификаторы клиента"]

    _LABELS = {
        "verbosity": ("Многословность", "молчалив", "разговорчив, перебивает"),
        "formality": ("Формальность", "неформальный, разговорный", "формальный, сдержанный"),
        "emotionality": ("Эмоциональность", "сдержан, логичен", "эмоционален, импульсивен"),
        "assertiveness": ("Напористость", "уступчив, мягок", "настойчив, давит"),
        "trust_tendency": ("Доверчивость", "подозрителен, перепроверяет", "доверчив, открыт"),
        "detail_focus": ("Внимание к деталям", "мыслит общими категориями", "вникает в каждую цифру"),
    }

    for key, (label, low_desc, high_desc) in _LABELS.items():
        val = modifiers.get(key, 0.5)
        if val < 0.35:
            lines.append(f"- {label}: {low_desc}")
        elif val > 0.65:
            lines.append(f"- {label}: {high_desc}")
        # mid-range: don't mention (neutral)

    return "\n".join(lines) if len(lines) > 1 else ""


# ---------------------------------------------------------------------------
# v5: ContextBudgetManager — 6K token system prompt limit
# ---------------------------------------------------------------------------

class ContextBudgetManager:
    """Manages the 6K token budget for multi-call system prompts.

    Strategy:
    - Last 2 calls: verbatim history (full message pairs)
    - Older calls: compressed summary (via small/fast LLM)
    - Episodic memories: sorted by salience, trimmed from low-salience first
    - Human factors: always included (small overhead, ~200 tokens)

    Token estimation: 1 token ≈ 4 chars for Russian text (conservative).
    """

    TOKEN_BUDGET = 6000
    CHARS_PER_TOKEN = 2  # Russian/Cyrillic: ~1.5-2 chars per token (was 4, causing 2x budget overflow)

    # Budget allocation (tokens) — rebalanced Wave 1.2
    ALLOCATION = {
        "character_prompt": 1800,   # Character personality + speech patterns (was 1500)
        "guardrails": 250,          # Safety rules (trimmed)
        "scenario": 400,            # Current scenario context
        "human_factors": 400,       # OCEAN/PAD + behavioral modifiers (was 200)
        "episodic_memory": 900,     # Key memories from past calls (was 600)
        "verbatim_history": 1500,   # Last 2 calls verbatim (was 2000)
        "compressed_history": 400,  # Older calls compressed (was 600)
        "emotion_state": 150,       # Current emotion + behavioral guidance (was 100)
        "between_call_events": 150, # CRM events between calls (was 200)
        "reserve": 50,              # Safety margin
    }

    def __init__(self):
        self._usage: dict[str, int] = {}

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count from text length."""
        return max(1, len(text) // self.CHARS_PER_TOKEN)

    def fits_budget(self, section: str, text: str) -> bool:
        """Check if text fits within the allocated budget for a section."""
        budget = self.ALLOCATION.get(section, 200)
        return self.estimate_tokens(text) <= budget

    def trim_to_budget(self, section: str, text: str) -> str:
        """Trim text to fit within section's token budget."""
        budget = self.ALLOCATION.get(section, 200)
        max_chars = budget * self.CHARS_PER_TOKEN
        if len(text) <= max_chars:
            return text
        # Trim to budget, try to break at sentence boundary
        trimmed = text[:max_chars]
        last_period = trimmed.rfind(".")
        if last_period > max_chars * 0.7:
            trimmed = trimmed[: last_period + 1]
        return trimmed + "\n[...сокращено для бюджета токенов]"

    def select_memories(
        self, memories: list[dict], max_tokens: int | None = None
    ) -> list[dict]:
        """Select episodic memories by salience within token budget.

        Args:
            memories: list of {"content": str, "salience": int, "type": str, ...}
            max_tokens: override budget (default: ALLOCATION["episodic_memory"])

        Returns:
            Subset of memories sorted by salience (highest first).
        """
        budget = max_tokens or self.ALLOCATION["episodic_memory"]
        sorted_mems = sorted(memories, key=lambda m: m.get("salience", 5), reverse=True)
        selected = []
        used_tokens = 0
        for mem in sorted_mems:
            tokens = self.estimate_tokens(mem.get("content", ""))
            if used_tokens + tokens > budget:
                break
            selected.append(mem)
            used_tokens += tokens
        return selected

    def format_verbatim_history(
        self, call_messages: list[list[dict]], max_calls: int = 2
    ) -> str:
        """Format last N calls as verbatim message history.

        Args:
            call_messages: list of per-call message lists, ordered oldest→newest
            max_calls: how many recent calls to include verbatim (default 2)
        """
        recent = call_messages[-max_calls:] if len(call_messages) > max_calls else call_messages
        budget = self.ALLOCATION["verbatim_history"]
        parts = []
        total_tokens = 0

        for i, msgs in enumerate(reversed(recent)):
            call_label = f"### Звонок {len(call_messages) - i} (дословно)"
            call_text = call_label + "\n"
            for msg in msgs:
                role_label = "Менеджер" if msg["role"] == "user" else "Клиент"
                line = f"{role_label}: {msg['content']}\n"
                call_text += line
            tokens = self.estimate_tokens(call_text)
            if total_tokens + tokens > budget:
                break
            parts.append(call_text)
            total_tokens += tokens

        parts.reverse()  # Restore chronological order
        return "\n".join(parts)

    async def compress_old_calls(
        self, call_messages: list[list[dict]], existing_summary: str | None = None
    ) -> str:
        """Compress older call history into summary via small LLM.

        Uses the existing LLM cascade with a short system prompt asking for compression.
        Falls back to simple truncation if LLM unavailable.
        """
        if not call_messages:
            return existing_summary or ""

        # Build text to compress
        text_parts = []
        for i, msgs in enumerate(call_messages, 1):
            text_parts.append(f"Звонок {i}:")
            for msg in msgs:
                role_label = "М" if msg["role"] == "user" else "К"
                text_parts.append(f"  {role_label}: {msg['content']}")
        raw_text = "\n".join(text_parts)

        compress_prompt = (
            "Ты — суммаризатор диалогов. Сожми следующую историю звонков в краткое резюме "
            "на русском языке. Сохрани: ключевые обещания, эмоциональные реакции, "
            "договорённости, возражения. Уложись в 150 слов максимум.\n\n"
            f"{'Предыдущее резюме: ' + existing_summary + chr(10) + chr(10) if existing_summary else ''}"
            f"Новые звонки:\n{raw_text}"
        )

        try:
            response = await generate_response(
                system_prompt=compress_prompt,
                messages=[{"role": "user", "content": "Сожми историю звонков."}],
                emotion_state="cold",
                user_id="system:compressor",
            )
            return response.content
        except Exception as e:
            logger.warning("Failed to compress call history via LLM: %s", e)
            # Fallback: simple truncation
            budget = self.ALLOCATION["compressed_history"]
            max_chars = budget * self.CHARS_PER_TOKEN
            if len(raw_text) <= max_chars:
                return raw_text
            return raw_text[:max_chars] + "\n[...история сокращена]"

    def get_total_usage(self) -> dict:
        """Return current budget usage snapshot."""
        return dict(self._usage)


# Singleton for shared use
_context_budget_manager = ContextBudgetManager()


def get_context_budget_manager() -> ContextBudgetManager:
    return _context_budget_manager


# ---------------------------------------------------------------------------
# v5: inject_human_factors — OCEAN/PAD personality injection
# ---------------------------------------------------------------------------

def inject_human_factors(
    personality_profile: dict,
    active_factors: list[dict] | None = None,
) -> str:
    """Build a prompt section injecting OCEAN/PAD personality on top of archetype.

    The personality_profile comes from ClientStory.personality_profile JSONB.
    Active factors are dynamic overlays (fatigue, time_pressure, etc.).

    Returns a text block to be included in the system prompt.
    """
    ocean = personality_profile.get("ocean", {})
    pad = personality_profile.get("pad_baseline", {})
    modifiers = personality_profile.get("modifiers", {})

    parts = ["## Человеческие факторы (OCEAN/PAD)\n"]

    # OCEAN descriptors
    ocean_desc = []
    if ocean.get("O", 0.5) > 0.6:
        ocean_desc.append("открыт новому, готов слушать аргументы")
    elif ocean.get("O", 0.5) < 0.4:
        ocean_desc.append("консервативен, подозрителен к новому")

    if ocean.get("C", 0.5) > 0.6:
        ocean_desc.append("дисциплинирован, ценит факты и порядок")
    elif ocean.get("C", 0.5) < 0.4:
        ocean_desc.append("импульсивен, может менять решения")

    if ocean.get("E", 0.5) > 0.6:
        ocean_desc.append("общителен, многословен, перебивает")
    elif ocean.get("E", 0.5) < 0.4:
        ocean_desc.append("замкнут, отвечает коротко, паузы в речи")

    if ocean.get("A", 0.5) > 0.6:
        ocean_desc.append("уступчив, избегает конфликтов")
    elif ocean.get("A", 0.5) < 0.4:
        ocean_desc.append("конфликтен, спорит, давит")

    if ocean.get("N", 0.5) > 0.6:
        ocean_desc.append("эмоционально нестабилен, резкие смены настроения")
    elif ocean.get("N", 0.5) < 0.4:
        ocean_desc.append("спокоен, трудно вывести из равновесия")

    if ocean_desc:
        parts.append("Характер: " + "; ".join(ocean_desc) + ".")

    # PAD current state
    p_val = pad.get("P", 0)
    a_val = pad.get("A", 0)
    d_val = pad.get("D", 0)
    mood_parts = []
    if p_val < -0.3:
        mood_parts.append("недоволен, раздражён")
    elif p_val > 0.3:
        mood_parts.append("в целом настроен позитивно")
    if a_val > 0.5:
        mood_parts.append("возбуждён, говорит быстро")
    elif a_val < -0.2:
        mood_parts.append("вялый, апатичный")
    if d_val > 0.5:
        mood_parts.append("доминирует в разговоре")
    elif d_val < -0.3:
        mood_parts.append("подчиняется, соглашается")
    if mood_parts:
        parts.append("Настроение: " + "; ".join(mood_parts) + ".")

    # Behavioral modifiers
    mod_parts = []
    verb = modifiers.get("verbosity", 0.5)
    if verb > 0.7:
        mod_parts.append("говорит длинно, уходит от темы")
    elif verb < 0.3:
        mod_parts.append("отвечает односложно")
    form = modifiers.get("formality", 0.5)
    if form > 0.7:
        mod_parts.append("говорит формально, на 'вы'")
    elif form < 0.3:
        mod_parts.append("разговорный стиль, может перейти на 'ты'")
    if mod_parts:
        parts.append("Стиль речи: " + "; ".join(mod_parts) + ".")

    # Active factors (dynamic overlays)
    if active_factors:
        factor_lines = []
        for f in active_factors:
            name = f.get("factor", "unknown")
            intensity = f.get("intensity", 0.5)
            factor_map = {
                "fatigue": f"усталость ({intensity:.0%}) — короче фразы, раздражительнее",
                "time_pressure": f"спешка ({intensity:.0%}) — торопит, просит быстрее",
                "distraction": f"отвлекается ({intensity:.0%}) — переспрашивает, теряет нить",
                "alcohol": f"выпил ({intensity:.0%}) — развязнее, эмоциональнее",
                "anger_buildup": f"копится злость ({intensity:.0%}) — ближе к взрыву",
                "hope": f"появилась надежда ({intensity:.0%}) — более открыт",
                "suspicion": f"подозрительность ({intensity:.0%}) — проверяет каждое слово",
                "family_pressure": f"давление семьи ({intensity:.0%}) — ссылается на мнение близких",
            }
            factor_lines.append(factor_map.get(name, f"{name} ({intensity:.0%})"))
        parts.append("Активные факторы: " + "; ".join(factor_lines) + ".")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# v5: build_multi_call_prompt — multi-call context assembly
# ---------------------------------------------------------------------------

async def build_multi_call_prompt(
    character_prompt: str,
    guardrails: str,
    emotion_state: str,
    scenario_prompt: str,
    personality_profile: dict,
    active_factors: list[dict] | None,
    episodic_memories: list[dict] | None,
    call_number: int,
    total_calls: int,
    compressed_history: str | None,
    verbatim_calls: list[list[dict]] | None,
    between_call_events: list[dict] | None,
    pre_call_brief: str | None = None,
) -> str:
    """Assemble multi-call system prompt within 6K token budget.

    Order of sections (priority for trimming: lowest priority trimmed first):
    1. Character prompt (trimmed to budget)
    2. Guardrails (trimmed to budget)
    3. Human factors (OCEAN/PAD injection)
    4. Compressed history of older calls
    5. Verbatim history of last 2 calls
    6. Episodic memories (sorted by salience)
    7. Between-call events
    8. Pre-call brief
    9. Scenario context
    10. Current emotion state

    Returns assembled system prompt string.
    """
    mgr = get_context_budget_manager()
    parts = []

    # 1. Character prompt (highest priority, gets largest chunk)
    if character_prompt:
        parts.append(mgr.trim_to_budget("character_prompt", character_prompt))

    # 2. Guardrails
    if guardrails:
        parts.append(mgr.trim_to_budget("guardrails", guardrails))

    # 3. Human factors injection
    if personality_profile:
        hf_text = inject_human_factors(personality_profile, active_factors)
        parts.append(mgr.trim_to_budget("human_factors", hf_text))

    # 4. Call position context
    parts.append(
        f"\n## Контекст мульти-звонка\n"
        f"Это звонок {call_number} из {total_calls} в истории с этим клиентом.\n"
    )

    # 5. Compressed history (older calls)
    if compressed_history:
        section = f"## Сжатая история предыдущих звонков\n{compressed_history}"
        parts.append(mgr.trim_to_budget("compressed_history", section))

    # 6. Verbatim history (last 2 calls)
    if verbatim_calls:
        verbatim_text = mgr.format_verbatim_history(verbatim_calls, max_calls=2)
        if verbatim_text:
            parts.append(mgr.trim_to_budget("verbatim_history", verbatim_text))

    # 7. Episodic memories
    if episodic_memories:
        selected = mgr.select_memories(episodic_memories)
        if selected:
            mem_lines = ["## Эпизодическая память клиента"]
            for mem in selected:
                mtype = mem.get("type", "")
                mcontent = mem.get("content", "")
                valence = mem.get("valence", 0)
                emoji = "➕" if valence > 0.3 else "➖" if valence < -0.3 else "⚪"
                mem_lines.append(f"- {emoji} [{mtype}] {mcontent}")
            mem_text = "\n".join(mem_lines)
            parts.append(mgr.trim_to_budget("episodic_memory", mem_text))

    # 8. Between-call events
    if between_call_events:
        event_lines = ["## Что произошло между звонками"]
        for evt in between_call_events:
            event_lines.append(f"- {evt.get('event', '?')}: {evt.get('impact', '')}")
        evt_text = "\n".join(event_lines)
        parts.append(mgr.trim_to_budget("between_call_events", evt_text))

    # 9. Pre-call brief (for manager, but also conditions client expectations)
    if pre_call_brief:
        parts.append(f"## Бриф перед звонком\n{pre_call_brief}")

    # 10. Scenario
    if scenario_prompt:
        parts.append(mgr.trim_to_budget("scenario", scenario_prompt))

    # 11. Current emotion state
    parts.append(
        f"\n## Текущее эмоциональное состояние: {emotion_state}\n"
        "Отвечай в соответствии с этим состоянием (см. раздел 'Эмоциональная динамика')."
    )

    assembled = "\n\n---\n\n".join(parts)

    # Final budget check — log warning if over
    total_tokens = mgr.estimate_tokens(assembled)
    if total_tokens > ContextBudgetManager.TOKEN_BUDGET:
        logger.warning(
            "System prompt over budget: ~%d tokens (budget: %d). Call %d/%d",
            total_tokens, ContextBudgetManager.TOKEN_BUDGET, call_number, total_calls,
        )

    return assembled


# ---------------------------------------------------------------------------
# v5: FactorInteractionMatrix — 25×25 factor interaction rules
# ---------------------------------------------------------------------------

class FactorInteractionMatrix:
    """Defines how pairs of human factors interact: amplify, conflict, or synergy.

    Used by inject_human_factors to modify intensities when multiple factors active.

    Interaction types:
    - amplify: factor A increases factor B intensity (e.g. fatigue + anger_buildup)
    - conflict: factor A reduces factor B (e.g. hope + suspicion)
    - synergy: both factors produce a new emergent behavior
    """

    # (factor_a, factor_b) → {"type": "amplify"|"conflict"|"synergy", "modifier": float, "note": str}
    INTERACTIONS: dict[tuple[str, str], dict] = {
        ("fatigue", "anger_buildup"): {
            "type": "amplify", "modifier": 1.3,
            "note": "Усталость усиливает раздражение — клиент быстрее срывается",
        },
        ("fatigue", "hope"): {
            "type": "conflict", "modifier": 0.7,
            "note": "Усталость гасит надежду — клиент слишком устал верить",
        },
        ("time_pressure", "distraction"): {
            "type": "amplify", "modifier": 1.4,
            "note": "Спешка + отвлечения — клиент хаотичен, теряет нить",
        },
        ("hope", "suspicion"): {
            "type": "conflict", "modifier": 0.6,
            "note": "Надежда и подозрительность гасят друг друга",
        },
        ("alcohol", "anger_buildup"): {
            "type": "amplify", "modifier": 1.5,
            "note": "Алкоголь + злость — взрывоопасная комбинация",
        },
        ("alcohol", "hope"): {
            "type": "amplify", "modifier": 1.2,
            "note": "Алкоголь усиливает оптимизм — легче соглашается",
        },
        ("family_pressure", "anger_buildup"): {
            "type": "synergy", "modifier": 1.0,
            "note": "Давление семьи + злость → перенаправление злости на менеджера",
        },
        ("family_pressure", "hope"): {
            "type": "amplify", "modifier": 1.2,
            "note": "Давление семьи усиливает желание решить проблему",
        },
        ("suspicion", "distraction"): {
            "type": "conflict", "modifier": 0.8,
            "note": "Подозрительный клиент не может одновременно отвлекаться",
        },
        ("fatigue", "distraction"): {
            "type": "amplify", "modifier": 1.3,
            "note": "Усталый клиент легче отвлекается",
        },
        ("time_pressure", "anger_buildup"): {
            "type": "amplify", "modifier": 1.3,
            "note": "Спешка и раздражение — клиент вот-вот бросит трубку",
        },
        ("hope", "family_pressure"): {
            "type": "amplify", "modifier": 1.2,
            "note": "Надежда + поддержка семьи — клиент готов действовать",
        },
    }

    @classmethod
    def apply_interactions(cls, factors: list[dict]) -> list[dict]:
        """Apply pairwise interaction rules to a list of active factors.

        Modifies intensities in-place based on interaction matrix.
        Returns the modified factor list.
        """
        if len(factors) < 2:
            return factors

        factor_map = {f["factor"]: f for f in factors}
        applied_notes = []

        for (fa, fb), rule in cls.INTERACTIONS.items():
            if fa in factor_map and fb in factor_map:
                rtype = rule["type"]
                mod = rule["modifier"]

                if rtype == "amplify":
                    # Factor A amplifies Factor B
                    old_intensity = factor_map[fb]["intensity"]
                    factor_map[fb]["intensity"] = min(1.0, old_intensity * mod)
                elif rtype == "conflict":
                    # Factors reduce each other
                    factor_map[fa]["intensity"] = max(0.0, factor_map[fa]["intensity"] * mod)
                    factor_map[fb]["intensity"] = max(0.0, factor_map[fb]["intensity"] * mod)
                elif rtype == "synergy":
                    # Add a note but don't change intensities directly
                    pass

                applied_notes.append(rule["note"])

        # Store notes for prompt injection
        for f in factors:
            if "interaction_notes" not in f:
                f["interaction_notes"] = []
        if applied_notes:
            # Attach notes to the first factor for prompt rendering
            factors[0]["interaction_notes"] = applied_notes

        return factors


def _trim_history(messages: list[dict], max_messages: int) -> list[dict]:
    """Keep only the last N messages to fit context window."""
    if len(messages) <= max_messages:
        return messages
    return messages[-max_messages:]


async def _call_gemini(
    system_prompt: str,
    messages: list[dict],
    timeout: float,
) -> LLMResponse:
    """Call Gemini API directly via REST (no SDK dependency).

    Uses the generateContent endpoint with system_instruction.
    Free tier: 15 RPM, 1500 req/day, 1M tokens/min.
    Docs: https://ai.google.dev/gemini-api/docs/text-generation
    """
    client = _get_gemini_client()
    if client is None:
        raise LLMError("Gemini API key not configured")

    model = settings.gemini_model
    # FIX: Use x-goog-api-key header instead of URL query param.
    # API key in URL leaks into access logs, proxy logs, and error messages.
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/"
        f"models/{model}:generateContent"
    )

    # Build contents array (Gemini format)
    contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({
            "role": role,
            "parts": [{"text": msg["content"]}],
        })

    payload = {
        "system_instruction": {
            "parts": [{"text": system_prompt}],
        },
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": 1200,
            "temperature": 1.05,
        },
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ],
    }

    start = time.monotonic()
    try:
        resp = await client.post(
            url,
            json=payload,
            headers={"x-goog-api-key": settings.gemini_api_key},
        )
        resp.raise_for_status()
    except httpx.TimeoutException:
        raise LLMError("Gemini API timeout")
    except httpx.HTTPStatusError as e:
        raise LLMError(f"Gemini API error {e.response.status_code}: {e.response.text[:200]}")
    except httpx.HTTPError as e:
        raise LLMError(f"Gemini API connection error: {e}")

    latency_ms = int((time.monotonic() - start) * 1000)
    data = resp.json()

    # Extract text from response
    try:
        content = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        # Safety block or empty response
        block_reason = data.get("promptFeedback", {}).get("blockReason", "unknown")
        logger.warning("Gemini blocked response: %s", block_reason)
        raise LLMError(f"Gemini response blocked: {block_reason}")

    # Guard against empty string responses (Gemini can return "" without raising KeyError)
    if not content or not content.strip():
        logger.warning("Gemini returned empty content for model %s", model)
        raise LLMError("Gemini returned empty response")

    # Extract token counts
    usage = data.get("usageMetadata", {})
    input_tokens = usage.get("promptTokenCount", 0)
    output_tokens = usage.get("candidatesTokenCount", 0)

    return LLMResponse(
        content=content,
        model=f"gemini:{model}",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
    )


async def _call_local_llm(
    system_prompt: str,
    messages: list[dict],
    timeout: float,
) -> LLMResponse:
    """Call local LLM via OpenAI-compatible API (LM Studio / Ollama)."""
    client = _get_local_client()
    if client is None:
        raise LLMError("Local LLM not enabled")

    oai_messages = [{"role": "system", "content": system_prompt}]
    for msg in messages:
        oai_messages.append({"role": msg["role"], "content": msg["content"]})

    start = time.monotonic()
    try:
        response = await client.chat.completions.create(
            model=settings.local_llm_model,
            messages=oai_messages,
            max_tokens=800,
            temperature=1.05,
            timeout=timeout,
        )
    except openai.APIConnectionError:
        raise LLMError("Local LLM not reachable (is LM Studio / Ollama running?)")
    except openai.APITimeoutError:
        raise LLMError("Local LLM timeout")
    except openai.APIError as e:
        raise LLMError(f"Local LLM error: {e}")

    latency_ms = int((time.monotonic() - start) * 1000)
    content = response.choices[0].message.content or ""

    return LLMResponse(
        content=content,
        model=f"local:{response.model or settings.local_llm_model}",
        input_tokens=response.usage.prompt_tokens if response.usage else 0,
        output_tokens=response.usage.completion_tokens if response.usage else 0,
        latency_ms=latency_ms,
    )


async def _call_claude(
    system_prompt: str,
    messages: list[dict],
    timeout: float,
) -> LLMResponse:
    """Call Claude API. Raises LLMError on failure."""
    client = _get_claude_client()
    if client is None:
        raise LLMError("Claude API key not configured")

    import anthropic

    start = time.monotonic()
    try:
        # FIX: was using llm_primary_model ("gemini-2.5-flash") for Claude API calls.
        # Claude API requires a Claude model name.
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            temperature=1.0,
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
            max_tokens=800,
            temperature=1.0,
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


def _scripted_response(emotion_state: str, messages: list[dict]) -> LLMResponse:
    """Generate a scripted response when no LLM is available.

    Uses emotion state to pick appropriate response from pre-written pool.
    Provides basic conversational flow without AI.
    """
    # If this is the first message, use a greeting
    if len(messages) <= 1:
        content = random.choice(_GREETING_RESPONSES)
    else:
        # Pick from pool based on emotion state
        pool = _SCRIPTED_RESPONSES.get(emotion_state, _SCRIPTED_RESPONSES["cold"])
        # Try not to repeat the last assistant message
        last_assistant = ""
        for m in reversed(messages):
            if m.get("role") == "assistant":
                last_assistant = m.get("content", "")
                break
        candidates = [r for r in pool if r != last_assistant]
        if not candidates:
            candidates = pool
        content = random.choice(candidates)

    return LLMResponse(
        content=content,
        model="scripted",
        input_tokens=0,
        output_tokens=0,
        latency_ms=0,
        is_fallback=True,
    )


# Dedicated logger for token usage tracking (future billing)
_token_logger = logging.getLogger("token_usage")


def _log_token_usage(response: "LLMResponse", user_id: str | None = None) -> None:
    """Log token usage for billing and analytics.

    Structured format: JSON-parseable line for easy aggregation.
    """
    _token_logger.info(
        "TOKEN_USAGE user=%s model=%s input=%d output=%d total=%d latency_ms=%d fallback=%s",
        user_id or "unknown",
        response.model,
        response.input_tokens,
        response.output_tokens,
        response.input_tokens + response.output_tokens,
        response.latency_ms,
        response.is_fallback,
    )


async def generate_response(
    system_prompt: str,
    messages: list[dict],
    emotion_state: str = "cold",
    character_prompt_path: str | None = None,
    user_id: str | None = None,
    scenario_prompt: str = "",
    prefer_provider: str = "auto",
    task_type: str = "default",
    max_tokens: int | None = None,
) -> LLMResponse:
    """Generate character response with hybrid LLM routing.

    Provider selection (via prefer_provider + task_type):
    - "local" → Gemma on Mac Mini (fast for simple tasks)
    - "cloud" → Gemini Cloud (big context, better for judges/coaches)
    - "auto" → smart routing based on prompt size and task type

    Fallback chain always continues on failure:
    local-first: Gemma → Gemini → Claude → OpenAI → Scripted
    cloud-first: Gemini → Gemma → Claude → OpenAI → Scripted

    Args:
        system_prompt: Base system prompt or extra context to append
        messages: Conversation history [{"role": "user"/"assistant", "content": "..."}]
        emotion_state: Current emotion state (one of 10 canonical states)
        character_prompt_path: Path to character prompt file relative to prompts/
        user_id: User ID for token usage logging
        scenario_prompt: Scenario-specific prompt from scenario_engine
        prefer_provider: "auto" | "local" | "cloud" — routing hint
        task_type: "simple" | "structured" | "roleplay" | "judge" | "coach" | "report" | "default"
        max_tokens: Override max output tokens (default picked by task_type)
    """
    # ── Build system prompt ──
    if character_prompt_path:
        character_prompt = load_prompt(character_prompt_path)
        try:
            from app.services.prompt_registry import load_archetype_prompt_db
            from app.database import async_session as _llm_async_session
            _arch_slug = character_prompt_path.replace("characters/", "").split("_")[0].split(".")[0]
            async with _llm_async_session() as _pr_db:
                _db_prompt = await load_archetype_prompt_db(_arch_slug, db=_pr_db)
                if _db_prompt:
                    character_prompt = _db_prompt
        except Exception:
            pass
        guardrails = load_prompt("guardrails.md")
        full_system = _build_system_prompt(
            character_prompt, guardrails, emotion_state,
            scenario_prompt=scenario_prompt,
        )
        if system_prompt:
            full_system = full_system + "\n\n" + system_prompt
    else:
        if scenario_prompt:
            full_system = system_prompt + "\n\n---\n\n" + scenario_prompt if system_prompt else scenario_prompt
        else:
            full_system = system_prompt

    # ── Inject constitution (only for tasks needing legal knowledge) ──
    # Roleplay and simple tasks don't need 1400 extra tokens of legal articles
    if task_type in ("judge", "coach", "report", "structured"):
        constitution = _get_constitution()
        if constitution:
            full_system = constitution + "\n\n---\n\n" + full_system

    # ── Resolve provider and max_tokens ──
    prompt_tokens = len(full_system) // 2  # Russian: ~2 chars/token
    resolved_provider = _resolve_provider(prefer_provider, prompt_tokens, task_type)
    effective_max_tokens = max_tokens or _default_max_tokens(resolved_provider, task_type)

    trimmed = _trim_history(messages, settings.llm_max_history_messages)
    timeout = float(settings.llm_timeout_seconds)
    semaphore = _get_llm_semaphore()

    logger.info(
        "LLM route: prefer=%s → resolved=%s, task=%s, prompt_tokens≈%d, max_tokens=%d",
        prefer_provider, resolved_provider, task_type, prompt_tokens, effective_max_tokens,
    )

    def _apply_filter(resp: LLMResponse) -> LLMResponse:
        filtered_content, violations = _filter_output(resp.content)
        if violations:
            resp.content = filtered_content
            resp.filter_violations = violations
        _log_token_usage(resp, user_id)
        return resp

    async with semaphore:
        if resolved_provider == "cloud":
            # ── Cloud-first: Gemini → Local → Claude → OpenAI ──
            if settings.gemini_api_key:
                _gemini_call_times.append(time.monotonic())
                resp = await _call_with_backoff(
                    "gemini", _call_gemini, full_system, trimmed, timeout,
                    max_attempts=3, retry_on_timeout_only=False,
                )
                if resp is not None:
                    return _apply_filter(resp)

            if settings.local_llm_enabled:
                resp = await _call_with_backoff(
                    "local", _call_local_llm, full_system, trimmed, timeout,
                    max_attempts=3, retry_on_timeout_only=False,
                )
                if resp is not None:
                    resp.is_fallback = True
                    return _apply_filter(resp)
        else:
            # ── Local-first: Gemma → Gemini → Claude → OpenAI ──
            if settings.local_llm_enabled:
                resp = await _call_with_backoff(
                    "local", _call_local_llm, full_system, trimmed, timeout,
                    max_attempts=3, retry_on_timeout_only=False,
                )
                if resp is not None:
                    return _apply_filter(resp)

            if settings.gemini_api_key:
                _gemini_call_times.append(time.monotonic())
                resp = await _call_with_backoff(
                    "gemini", _call_gemini, full_system, trimmed, timeout,
                    max_attempts=3, retry_on_timeout_only=False,
                )
                if resp is not None:
                    resp.is_fallback = True
                    return _apply_filter(resp)

        # ── Shared fallbacks: Claude → OpenAI ──
        if settings.claude_api_key:
            resp = await _call_with_backoff(
                "claude", _call_claude, full_system, trimmed, timeout,
                max_attempts=3, retry_on_timeout_only=False,
            )
            if resp is not None:
                resp.is_fallback = True
                return _apply_filter(resp)

        if settings.openai_api_key:
            resp = await _call_with_backoff(
                "openai", _call_openai, full_system, trimmed, timeout * 2,
                max_attempts=2,
            )
            if resp is not None:
                resp.is_fallback = True
                return _apply_filter(resp)

    # ── Scripted fallback (no LLM needed, outside semaphore) ──
    logger.warning("All LLM providers unavailable, using scripted response")
    response = _scripted_response(emotion_state, trimmed)
    _log_token_usage(response, user_id)
    return response
