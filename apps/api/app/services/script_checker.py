"""Script adherence checker using embeddings for cosine similarity.

Priority chain for embeddings:
1. Gemini Embedding API (free, 1500 req/day, zero RAM)
2. Local embeddings microservice (if configured)
3. Keyword matching fallback (always works)

Cosine similarity thresholds (tuned for Russian):
- Checkpoint match: >= 0.58 (Russian synonyms score 0.55-0.70)
- Anti-pattern detection: >= 0.65
- Keyword fallback: >= 0.25
"""

import logging
import math
import uuid
from functools import lru_cache

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import async_session
from app.models.script import Checkpoint, Script

logger = logging.getLogger(__name__)

# Thresholds tuned for Russian multilingual embeddings (Gemini embedding-001).
# 0.72 was too strict — synonym/paraphrase pairs in Russian score ~0.55-0.70.
# 0.58 catches "добрый день" ≈ "здравствуйте", "организация" ≈ "компания".
SIMILARITY_THRESHOLD = 0.58
KEYWORD_THRESHOLD = 0.25  # lowered: allows partial keyword overlap
ANTI_PATTERN_THRESHOLD = 0.55  # was 0.80→0.65→0.55: keyword overlap needs lower threshold

ANTI_PATTERNS = {
    "false_promises": [
        "гарантирую списание",
        "точно спишут",
        "сто процентов спишут",
        "гарантированное списание",
        "обещаю что спишут",
        "даю гарантию",
        "гарантирую результат",
    ],
    "intimidation": [
        "вас посадят",
        "посадят в тюрьму",
        "приставы придут домой",
        "вас арестуют",
        "заберут всё имущество",
        "опишут имущество",
        "отберут квартиру",
        "потеряете всё",
    ],
    "incorrect_info": [
        "банкротство бесплатно",
        "абсолютно бесплатно",
        "кредитная история не пострадает",
        "никаких последствий нет",
        "это не отразится на кредитной истории",
        "можно выехать за границу",
        "ограничений не будет",
    ],
}

# ─── Embedding cache (in-memory, per process) ────────────────────────────────
# Checkpoint descriptions are static, so we cache their embeddings.
_embedding_cache: dict[str, list[float]] = {}


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def _get_gemini_embeddings(texts: list[str]) -> list[list[float]] | None:
    """Get embeddings via priority chain:
    1. CLIProxyAPI (OpenAI-compatible /v1/embeddings) — works through proxy, no geo block
    2. Gemini direct API — may be geo-blocked in some regions
    Returns None on failure.
    """
    # ── 1. Try CLIProxyAPI (OpenAI-compatible) ──
    if settings.local_llm_enabled and settings.local_llm_url:
        try:
            embed_url = f"{settings.local_llm_url.rstrip('/')}/embeddings"
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    embed_url,
                    headers={"Authorization": f"Bearer {settings.local_llm_api_key}"},
                    json={"model": "text-embedding-004", "input": texts},
                )
            if resp.status_code == 200:
                data = resp.json()
                embeddings_data = data.get("data", [])
                if embeddings_data:
                    # Sort by index to preserve order
                    sorted_data = sorted(embeddings_data, key=lambda x: x.get("index", 0))
                    return [e.get("embedding", []) for e in sorted_data]
            else:
                logger.debug("CLIProxyAPI embedding returned %d", resp.status_code)
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            logger.debug("CLIProxyAPI embedding unavailable: %s", e)

    # ── 2. Try Gemini direct API ──
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
        async with httpx.AsyncClient(timeout=15.0) as client:
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


async def _get_embedding(text: str) -> list[float] | None:
    """Get embedding for a single text, with caching."""
    cache_key = text[:200]  # Truncate for cache key
    if cache_key in _embedding_cache:
        return _embedding_cache[cache_key]

    result = await _get_gemini_embeddings([text])
    if result and len(result) > 0 and len(result[0]) > 0:
        _embedding_cache[cache_key] = result[0]
        return result[0]

    # Fallback: try local embeddings service
    return await _get_local_embedding(text)


async def _get_local_embedding(text: str) -> list[float] | None:
    """Fallback: get embedding from local sentence-transformers service."""
    url = f"{settings.embeddings_service_url.rstrip('/')}/embed"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json={"text": text})
        if resp.status_code == 200:
            return resp.json().get("embedding", None)
        return None
    except (httpx.ConnectError, httpx.TimeoutException):
        return None


async def _llm_similarity(text1: str, text2: str) -> float | None:
    """Use LLM-as-judge to compute semantic similarity via CLIProxyAPI.

    This bypasses the Gemini Embedding API geo-block by using the chat endpoint
    to evaluate similarity directly. Returns 0.0-1.0 or None on failure.
    """
    if not settings.local_llm_enabled or not settings.local_llm_url:
        return None

    cache_key = f"sim:{text1[:80]}|{text2[:80]}"
    if cache_key in _embedding_cache:
        cached = _embedding_cache[cache_key]
        if isinstance(cached, (int, float)):
            return float(cached)

    prompt = (
        "Оцени семантическое сходство двух фраз числом от 0.0 до 1.0.\n"
        "0.0 = совершенно разный смысл, 1.0 = идентичный смысл.\n"
        "Ответь ТОЛЬКО числом, ничего больше.\n\n"
        f'Фраза 1: "{text1}"\n'
        f'Фраза 2: "{text2}"'
    )

    try:
        url = f"{settings.local_llm_url.rstrip('/')}/chat/completions"
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {settings.local_llm_api_key}"},
                json={
                    "model": settings.local_llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 10,
                    "temperature": 0.0,
                },
            )
        if resp.status_code != 200:
            return None

        import re
        content = resp.json()["choices"][0]["message"]["content"].strip()
        match = re.search(r"(0\.\d+|1\.0|0|1)", content)
        if match:
            score = float(match.group(1))
            _embedding_cache[cache_key] = score
            return score
        return None
    except Exception:
        logger.debug("LLM similarity failed for pair")
        return None


async def _llm_batch_similarity(text: str, references: list[str]) -> list[float] | None:
    """Batch similarity via single LLM call — score one text against N references.

    Much more efficient than N individual calls. Returns list of floats or None.
    """
    if not settings.local_llm_enabled or not settings.local_llm_url:
        return None

    if not references:
        return None

    pairs = "\n".join(
        f'{i + 1}. "{ref}"'
        for i, ref in enumerate(references)
    )
    prompt = (
        "Оцени семантическое сходство текста с каждой из фраз ниже.\n"
        "Верни ТОЛЬКО JSON массив чисел от 0.0 до 1.0, без пояснений.\n\n"
        f'Текст: "{text[:500]}"\n\n'
        f"Фразы:\n{pairs}"
    )

    try:
        url = f"{settings.local_llm_url.rstrip('/')}/chat/completions"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {settings.local_llm_api_key}"},
                json={
                    "model": settings.local_llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": len(references) * 8 + 20,
                    "temperature": 0.0,
                },
            )
        if resp.status_code != 200:
            return None

        import re
        content = resp.json()["choices"][0]["message"]["content"].strip()
        nums = re.findall(r"(0\.\d+|1\.0|0|1)", content)
        if len(nums) >= len(references):
            return [float(n) for n in nums[:len(references)]]
        return None
    except Exception:
        logger.debug("LLM batch similarity failed")
        return None


async def _get_similarity(text1: str, text2: str) -> float | None:
    """Compute semantic similarity between two texts.

    Priority chain:
    1. LLM-as-judge via CLIProxyAPI (works through proxy, no geo-block)
    2. Gemini Embedding API (may be geo-blocked)
    3. Local embeddings service (if configured)
    4. Returns None → caller falls back to keyword matching
    """
    # 1. LLM-as-judge (most reliable, works through CLIProxyAPI)
    score = await _llm_similarity(text1, text2)
    if score is not None:
        return score

    # 2. Try embedding-based similarity
    if settings.gemini_embedding_api_key:
        results = await _get_gemini_embeddings([text1, text2])
        if results and len(results) == 2 and results[0] and results[1]:
            return _cosine_similarity(results[0], results[1])

    # 3. Fallback: local embeddings service
    emb1 = await _get_local_embedding(text1)
    emb2 = await _get_local_embedding(text2)
    if emb1 and emb2:
        return _cosine_similarity(emb1, emb2)

    return None


def _keyword_similarity(text: str, keywords: list[str]) -> float:
    """Enhanced keyword matching with Russian synonym awareness.

    Beyond exact substring match, also checks common Russian synonyms
    and word stems to catch paraphrases like "добрый день" ≈ "здравствуйте".
    """
    if not keywords:
        return 0.0
    text_lower = text.lower()

    # Russian synonym groups — if ANY synonym in group matches, the keyword counts
    _SYNONYMS: dict[str, list[str]] = {
        "здравствуйте": ["добрый день", "добрый вечер", "доброе утро", "приветствую", "алло"],
        "компания": ["организация", "фирма", "агентство", "бюро"],
        "меня зовут": ["это", "моё имя", "представлюсь"],
        "долг": ["задолженность", "кредит", "займ", "заём"],
        "банкротство": ["процедура", "списание долгов", "127-фз", "несостоятельность"],
        "стоимость": ["цена", "сколько стоит", "расценки", "тариф"],
        "консультация": ["встреча", "запись", "приём", "визит"],
        "понимаю": ["слышу вас", "осознаю", "разделяю"],
        "гарантирую": ["обещаю", "даю гарантию", "точно", "сто процентов"],
        "приставы": ["судебные исполнители", "фссп", "взыскание"],
    }

    matched = 0
    for kw in keywords:
        kw_lower = kw.lower()
        # Direct match
        if kw_lower in text_lower:
            matched += 1
            continue
        # Synonym match
        synonyms = _SYNONYMS.get(kw_lower, [])
        if any(syn in text_lower for syn in synonyms):
            matched += 1
            continue
        # Check if keyword is a synonym of something in text
        for base, syns in _SYNONYMS.items():
            if kw_lower in syns or kw_lower == base:
                all_forms = [base] + syns
                if any(form in text_lower for form in all_forms):
                    matched += 1
                    break

    return matched / len(keywords)


async def check_checkpoint_match(
    user_text: str,
    checkpoint_id: str | uuid.UUID,
    threshold: float = SIMILARITY_THRESHOLD,
) -> tuple[bool, float]:
    if isinstance(checkpoint_id, str):
        checkpoint_id = uuid.UUID(checkpoint_id)

    async with async_session() as db:
        result = await db.execute(
            select(Checkpoint).where(Checkpoint.id == checkpoint_id)
        )
        checkpoint = result.scalar_one_or_none()

    if checkpoint is None:
        return False, 0.0

    ref_text = checkpoint.description

    score = await _get_similarity(user_text, ref_text)
    if score is not None:
        return score >= threshold, round(score, 3)

    keywords = checkpoint.keywords if isinstance(checkpoint.keywords, list) else []
    desc_words = [w for w in checkpoint.description.lower().split() if len(w) > 3]
    all_keywords = list(set(keywords + desc_words[:5]))
    score = _keyword_similarity(user_text, all_keywords)
    return score >= KEYWORD_THRESHOLD, round(score, 3)


async def check_all_checkpoints(
    user_text: str,
    script_id: uuid.UUID,
    threshold: float = SIMILARITY_THRESHOLD,
) -> list[dict]:
    async with async_session() as db:
        result = await db.execute(
            select(Script)
            .options(selectinload(Script.checkpoints))
            .where(Script.id == script_id)
        )
        script = result.scalar_one_or_none()

    if script is None:
        return []

    results = []
    for cp in script.checkpoints:
        ref_text = cp.description

        score = await _get_similarity(user_text, ref_text)
        if score is not None:
            matched = score >= threshold
        else:
            keywords = cp.keywords if isinstance(cp.keywords, list) else []
            score = _keyword_similarity(user_text, keywords)
            matched = score >= KEYWORD_THRESHOLD

        results.append({
            "checkpoint_id": str(cp.id),
            "title": cp.title,
            "order_index": cp.order_index,
            "score": round(score, 3),
            "matched": matched,
            "weight": cp.weight,
        })

    return sorted(results, key=lambda x: x["order_index"])


async def detect_anti_patterns(user_text: str) -> list[dict]:
    """Detect anti-patterns in user text using batch LLM similarity.

    Uses single LLM call to check all anti-pattern phrases at once.
    Falls back to keyword matching if LLM unavailable.
    """
    # Flatten all phrases with category tracking
    all_phrases = []
    phrase_categories = []
    for category, phrases in ANTI_PATTERNS.items():
        for phrase in phrases:
            all_phrases.append(phrase)
            phrase_categories.append(category)

    # Try batch LLM similarity (1 API call for all anti-patterns)
    batch_scores = await _llm_batch_similarity(user_text, all_phrases)

    detected = []
    category_max: dict[str, float] = {}

    for i, phrase in enumerate(all_phrases):
        cat = phrase_categories[i]

        if batch_scores and i < len(batch_scores):
            score = batch_scores[i]
        else:
            # Fallback: try individual similarity or keywords
            score = await _get_similarity(user_text, phrase)
            if score is None:
                words = phrase.lower().split()
                score = _keyword_similarity(user_text, words)

        if cat not in category_max or score > category_max[cat]:
            category_max[cat] = score

    for cat, max_score in category_max.items():
        if max_score >= ANTI_PATTERN_THRESHOLD:
            detected.append({"category": cat, "score": round(max_score, 3)})

    return detected


# ─── In-memory checkpoint cache (per process) ──────────────────────────────
# Caches checkpoint definitions by script_id to avoid DB queries every message.
_checkpoint_cache: dict[str, list[dict]] = {}
_CHECKPOINT_CACHE_MAX = 50


def _cache_checkpoints(script_id: str, checkpoints: list[dict]) -> None:
    """Cache checkpoint definitions for a script_id (LRU-style)."""
    if len(_checkpoint_cache) >= _CHECKPOINT_CACHE_MAX:
        # Remove oldest entry
        oldest = next(iter(_checkpoint_cache))
        del _checkpoint_cache[oldest]
    _checkpoint_cache[script_id] = checkpoints


def _get_cached_checkpoints(script_id: str) -> list[dict] | None:
    return _checkpoint_cache.get(script_id)


async def check_checkpoints_with_accumulation(
    user_text: str,
    script_id: uuid.UUID,
    already_matched: set[str],
    threshold: float = SIMILARITY_THRESHOLD,
) -> tuple[list[dict], list[dict]]:
    """Check checkpoints with accumulation of already-matched ones.

    Preserves previously matched checkpoints and only checks remaining ones
    against the current user message. Returns (all_checkpoints, new_matches).

    Args:
        user_text: Current user message text
        script_id: UUID of the script to check against
        already_matched: Set of checkpoint IDs already matched in this session
        threshold: Similarity threshold for matching

    Returns:
        Tuple of (all_checkpoints_with_status, newly_matched_checkpoints)
        Each checkpoint: {"checkpoint_id", "title", "order_index", "score", "matched", "weight"}
    """
    sid = str(script_id)
    cached = _get_cached_checkpoints(sid)

    if cached is None:
        async with async_session() as db:
            result = await db.execute(
                select(Script)
                .options(selectinload(Script.checkpoints))
                .where(Script.id == script_id)
            )
            script = result.scalar_one_or_none()

        if script is None:
            return [], []

        cached = [
            {
                "checkpoint_id": str(cp.id),
                "title": cp.title,
                "description": cp.description,
                "order_index": cp.order_index,
                "keywords": cp.keywords if isinstance(cp.keywords, list) else [],
                "weight": cp.weight,
            }
            for cp in script.checkpoints
        ]
        _cache_checkpoints(sid, cached)

    # Separate already-matched from remaining
    remaining = [cp for cp in cached if cp["checkpoint_id"] not in already_matched]

    # Check remaining checkpoints against current message
    new_matches: list[dict] = []
    for cp in remaining:
        score = await _get_similarity(user_text, cp["description"])
        if score is not None:
            matched = score >= threshold
        else:
            score = _keyword_similarity(user_text, cp["keywords"])
            matched = score >= KEYWORD_THRESHOLD

        if matched:
            new_matches.append({
                "checkpoint_id": cp["checkpoint_id"],
                "title": cp["title"],
                "order_index": cp["order_index"],
                "score": round(score, 3),
                "matched": True,
                "weight": cp["weight"],
            })

    # Build full result: already_matched + new_matches + unmatched
    all_matched_ids = already_matched | {m["checkpoint_id"] for m in new_matches}
    all_results = []
    for cp in cached:
        if cp["checkpoint_id"] in all_matched_ids:
            # Find score from new_matches or default to 1.0 for previously matched
            nm = next((m for m in new_matches if m["checkpoint_id"] == cp["checkpoint_id"]), None)
            all_results.append({
                "checkpoint_id": cp["checkpoint_id"],
                "title": cp["title"],
                "order_index": cp["order_index"],
                "score": nm["score"] if nm else 1.0,
                "matched": True,
                "weight": cp["weight"],
            })
        else:
            all_results.append({
                "checkpoint_id": cp["checkpoint_id"],
                "title": cp["title"],
                "order_index": cp["order_index"],
                "score": 0.0,
                "matched": False,
                "weight": cp["weight"],
            })

    all_results.sort(key=lambda x: x["order_index"])
    return all_results, new_matches


def generate_checkpoints_from_template(stages: list[dict]) -> list[dict]:
    """Generate virtual checkpoint definitions from ScenarioTemplate stages.

    Used as fallback when a Scenario has no script_id assigned.
    Each manager_goal becomes a checkpoint with auto-generated keywords.

    Args:
        stages: List of stage dicts from ScenarioTemplate.stages JSONB field

    Returns:
        List of checkpoint-like dicts compatible with accumulation logic
    """
    checkpoints = []
    for stage in stages:
        order = stage.get("order", 0)
        name = stage.get("name", f"Этап {order}")
        goals = stage.get("manager_goals", [])

        if not goals:
            continue

        # Each goal = one checkpoint
        for gi, goal in enumerate(goals):
            # Extract keywords from goal text (words > 3 chars)
            words = [w.strip(".,!?;:()\"'") for w in goal.lower().split()]
            keywords = [w for w in words if len(w) > 3][:8]

            checkpoints.append({
                "checkpoint_id": f"tmpl-{order}-{gi}",
                "title": f"{name}: {goal[:60]}",
                "description": goal,
                "order_index": order * 10 + gi,
                "keywords": keywords,
                "weight": 1.0,
            })

    return checkpoints


async def get_session_checkpoint_progress(
    script_id: uuid.UUID,
    message_history: list[dict],
    threshold: float = SIMILARITY_THRESHOLD,
) -> dict:
    user_texts = [
        m["content"]
        for m in message_history
        if m.get("role") == "user" and m.get("content")
    ]
    combined_text = " ".join(user_texts)

    async with async_session() as db:
        result = await db.execute(
            select(Script)
            .options(selectinload(Script.checkpoints))
            .where(Script.id == script_id)
        )
        script = result.scalar_one_or_none()

    if script is None:
        return {"total_score": 0, "checkpoints": [], "reached_count": 0, "total_count": 0}

    # Try batch LLM similarity first (1 API call for all checkpoints)
    references = [cp.description for cp in script.checkpoints]
    batch_scores = await _llm_batch_similarity(combined_text, references)

    # Fallback: try batch embeddings
    embeddings = None
    if batch_scores is None:
        all_texts = [combined_text] + references
        embeddings = await _get_gemini_embeddings(all_texts) if settings.gemini_embedding_api_key else None

    checkpoints_results = []
    total_weighted = 0.0
    reached_weighted = 0.0

    for i, cp in enumerate(script.checkpoints):
        score: float
        matched: bool

        if batch_scores and i < len(batch_scores):
            # Best: LLM-as-judge batch (1 API call, high accuracy)
            score = batch_scores[i]
            matched = score >= threshold
        elif embeddings and len(embeddings) > i + 1 and embeddings[0] and embeddings[i + 1]:
            # Fallback: batch embeddings
            score = _cosine_similarity(embeddings[0], embeddings[i + 1])
            matched = score >= threshold
        else:
            # Last resort: keyword matching with synonyms
            keywords = cp.keywords if isinstance(cp.keywords, list) else []
            score = _keyword_similarity(combined_text, keywords)
            matched = score >= KEYWORD_THRESHOLD

        total_weighted += cp.weight
        if matched:
            reached_weighted += cp.weight * min(score / threshold, 1.0)

        checkpoints_results.append({
            "checkpoint_id": str(cp.id),
            "title": cp.title,
            "order_index": cp.order_index,
            "score": round(score, 3),
            "matched": matched,
            "weight": cp.weight,
        })

    total_score = (reached_weighted / total_weighted * 100) if total_weighted > 0 else 0
    reached_count = sum(1 for c in checkpoints_results if c["matched"])

    return {
        "total_score": round(total_score, 1),
        "checkpoints": sorted(checkpoints_results, key=lambda x: x["order_index"]),
        "reached_count": reached_count,
        "total_count": len(checkpoints_results),
    }
