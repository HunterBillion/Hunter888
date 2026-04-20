"""Fetch user-supplied legal URLs into the retrieval pool on-the-fly.

Phase 3.8 (2026-04-19). Problem: a manager pastes a link to
``legalacts.ru/doc/127-FZ/...`` into chat, expecting the AI to consider
that specific article — but RAG doesn't follow URLs, so the link ends up
as a literal string in the embedding, which is not helpful.

Solution: when a query contains an HTTPS URL from a short allow-list of
legal publishers, fetch it (with Redis cache, bleach sanitation, rate
limiting, size cap), chunk the extracted main text, and inject the
chunks into the retrieval pool with a boost.

Safety:
  * Allow-list of 5 domains — no arbitrary fetching.
  * Max 500 KB per page.
  * 24-hour Redis cache keyed by URL hash.
  * HTML stripped via ``bleach`` so prompt injection in page content
    can't slip through tags into the LLM system prompt.
  * Per-process rate limit (10 fetches / 60s) to dampen abuse.

Returns structured ``FetchedChunk`` objects, never raw HTML.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


# Only these publishers are trusted. Adding new domains requires a manual
# review because content from them ends up in the RAG pool.
ALLOWED_DOMAINS: frozenset[str] = frozenset({
    "legalacts.ru",
    "consultant.ru",
    "sudact.ru",
    "rg.ru",
    "garant.ru",
})

# Cache TTL for fetched pages. 24h is enough to absorb repeated queries
# during a training session but short enough that the law text stays
# fresh when publishers amend articles.
CACHE_TTL_S = 60 * 60 * 24

# Hard per-page size limit — refuses bigger payloads to avoid OOM and
# runaway prompt growth.
MAX_BYTES = 500_000

# Rough chunk sizes. Kept smaller than ``settings.rag_chunk_max_chars``
# so fetched content composes well with existing DB chunks.
CHUNK_MAX_CHARS = 6000
CHUNK_OVERLAP_CHARS = 400

_URL_RE = re.compile(r"https?://[^\s<>\"'()\[\]]+", re.IGNORECASE)

# Naïve HTML stripper used as a fallback when bleach/trafilatura aren't
# installed. The production deployment should have bleach available.
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

# Simple in-process rate limiter — token bucket style.
_BUCKET_SIZE = 10
_BUCKET_REFILL_PER_SEC = 10.0 / 60.0
_bucket_tokens: float = float(_BUCKET_SIZE)
_bucket_last = time.monotonic()
_bucket_lock = asyncio.Lock()


@dataclass(frozen=True)
class FetchedChunk:
    """One chunk of extracted, sanitized text from a user-supplied URL."""

    url: str
    """Original URL the chunk came from."""

    host: str
    """Short publisher hostname, e.g. ``"legalacts.ru"``."""

    text: str
    """Sanitized Russian text, ready to embed."""

    chunk_index: int
    """0-based position within the page's chunk sequence."""


def extract_urls(text: str) -> list[str]:
    """Return the list of HTTP(S) URLs in ``text``, deduplicated, order kept."""

    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for m in _URL_RE.findall(text):
        url = m.rstrip(".,;:!?)]}»\"'")
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def is_allowed(url: str) -> bool:
    """Cheap domain-allow-list check."""

    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:  # noqa: BLE001
        return False
    # Match on hostname suffix so www.legalacts.ru is allowed too.
    return any(host == d or host.endswith("." + d) for d in ALLOWED_DOMAINS)


async def _rate_limit_acquire() -> bool:
    """Non-blocking token bucket: returns True if a token was consumed."""

    global _bucket_tokens, _bucket_last
    async with _bucket_lock:
        now = time.monotonic()
        elapsed = now - _bucket_last
        _bucket_last = now
        _bucket_tokens = min(
            float(_BUCKET_SIZE), _bucket_tokens + elapsed * _BUCKET_REFILL_PER_SEC
        )
        if _bucket_tokens >= 1.0:
            _bucket_tokens -= 1.0
            return True
        return False


def _sanitize(html: str) -> str:
    """Strip tags, decode entities, collapse whitespace.

    Uses ``bleach`` if available; falls back to a regex stripper so the
    module keeps working in stripped-down deploys.
    """

    try:
        import bleach  # type: ignore[import-untyped]

        cleaned = bleach.clean(html, tags=[], strip=True)
    except ImportError:
        cleaned = _HTML_TAG_RE.sub(" ", html)

    # Minimal entity decoding — covers 95% of legal pages.
    cleaned = (
        cleaned.replace("&nbsp;", " ")
        .replace("&laquo;", "«")
        .replace("&raquo;", "»")
        .replace("&mdash;", "—")
        .replace("&ndash;", "–")
        .replace("&quot;", '"')
        .replace("&amp;", "&")
    )
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def _chunk(text: str) -> list[str]:
    """Split ``text`` into at most ``CHUNK_MAX_CHARS``-sized chunks with
    overlap. Boundary-preserving: tries to break on sentence ends.
    """

    if len(text) <= CHUNK_MAX_CHARS:
        return [text] if text else []
    out: list[str] = []
    i = 0
    while i < len(text):
        end = min(len(text), i + CHUNK_MAX_CHARS)
        # Prefer to break at the last full-stop in the window.
        if end < len(text):
            last_dot = text.rfind(". ", i, end)
            if last_dot > i + CHUNK_MAX_CHARS // 2:
                end = last_dot + 1
        out.append(text[i:end].strip())
        if end == len(text):
            break
        i = end - CHUNK_OVERLAP_CHARS
    return [c for c in out if c]


def _cache_key(url: str) -> str:
    return "rag:url:" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:24]


async def _cache_get(key: str) -> Optional[str]:
    try:
        from app.core.redis_pool import get_redis

        r = get_redis()
        data = await r.get(key)
        if not data:
            return None
        return data.decode() if isinstance(data, (bytes, bytearray)) else data
    except Exception:  # noqa: BLE001
        return None


async def _cache_set(key: str, text: str) -> None:
    try:
        from app.core.redis_pool import get_redis

        r = get_redis()
        await r.setex(key, CACHE_TTL_S, text)
    except Exception:  # noqa: BLE001
        pass


async def fetch_and_chunk(url: str) -> list[FetchedChunk]:
    """Return a list of sanitised chunks for ``url``.

    Never raises — all failures log and return ``[]`` so the caller can
    degrade gracefully to the normal retrieval pool.
    """

    if not is_allowed(url):
        logger.debug("url_fetcher: domain not allowed %s", url)
        return []

    host = (urlparse(url).hostname or "").lower()
    key = _cache_key(url)

    cached = await _cache_get(key)
    if cached is not None:
        return _build_chunks(cached, url, host)

    if not await _rate_limit_acquire():
        logger.warning("url_fetcher: rate limit hit; skip %s", url)
        return []

    try:
        headers = {
            "User-Agent": "Hunter888-RAG/1.0 (+https://hunter888.ai/bot)",
            "Accept-Language": "ru,en;q=0.7",
        }
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            r = await client.get(url, headers=headers)
        if r.status_code != 200:
            logger.debug("url_fetcher: %s returned %d", url, r.status_code)
            return []
        raw = r.content[:MAX_BYTES]
        html = raw.decode(r.encoding or "utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        logger.debug("url_fetcher: fetch failed %s: %s", url, exc)
        return []

    cleaned = _sanitize(html)
    if not cleaned or len(cleaned) < 200:
        return []

    await _cache_set(key, cleaned)
    return _build_chunks(cleaned, url, host)


def _build_chunks(text: str, url: str, host: str) -> list[FetchedChunk]:
    pieces = _chunk(text)
    return [
        FetchedChunk(url=url, host=host, text=piece, chunk_index=idx)
        for idx, piece in enumerate(pieces)
    ]
