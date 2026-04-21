"""Legal ingest pipeline — shared utilities."""

import asyncio
import hashlib
import logging
import sys
import time
from pathlib import Path

import httpx

from . import config as cfg

# ── Logging ──────────────────────────────────────────────────────────────


def make_logger(name: str) -> logging.Logger:
    lg = logging.getLogger(name)
    if lg.handlers:
        return lg
    lg.setLevel(logging.INFO)
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s", "%H:%M:%S")
    h_console = logging.StreamHandler(sys.stdout)
    h_console.setFormatter(fmt)
    lg.addHandler(h_console)
    # also log to file
    log_file = cfg.LOGS_DIR / f"{name}.log"
    h_file = logging.FileHandler(log_file, encoding="utf-8")
    h_file.setFormatter(fmt)
    lg.addHandler(h_file)
    return lg


# ── HTTP fetcher with rate limit + retry ────────────────────────────────


class RateLimitedFetcher:
    def __init__(self, rps: float = 1.0):
        self.min_interval = 1.0 / max(rps, 0.01)
        self._last_request_at: float = 0.0
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            headers={"User-Agent": cfg.USER_AGENT, "Accept-Language": "ru-RU,ru;q=0.9"},
            timeout=cfg.HTTP_TIMEOUT,
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *exc):
        if self._client:
            await self._client.aclose()

    async def get(self, url: str, retries: int = 3) -> httpx.Response | None:
        """GET with exponential backoff. Returns None if all retries exhausted."""
        assert self._client
        # Rate limit: ensure min_interval since last request
        since = time.monotonic() - self._last_request_at
        if since < self.min_interval:
            await asyncio.sleep(self.min_interval - since)
        for attempt in range(retries):
            try:
                self._last_request_at = time.monotonic()
                r = await self._client.get(url)
                if r.status_code == 200:
                    return r
                if r.status_code in (429, 503):
                    wait = 2 ** (attempt + 2)  # 4, 8, 16 sec
                    await asyncio.sleep(wait)
                    continue
                if 400 <= r.status_code < 500:
                    return r  # client error — not retried, return to caller
                await asyncio.sleep(2 ** attempt)
            except (httpx.ReadTimeout, httpx.ConnectError, httpx.RemoteProtocolError):
                await asyncio.sleep(2 ** attempt)
        return None


# ── File I/O ────────────────────────────────────────────────────────────


def save_html(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ── Text normalization ──────────────────────────────────────────────────


def normalize_whitespace(text: str) -> str:
    import re
    text = re.sub(r"\s+", " ", text)
    text = text.strip()
    return text


def count_tokens_estimate(text: str) -> int:
    """Heuristic token count for Russian text (3 chars/token)."""
    return len(text) // cfg.CHARS_PER_TOKEN_RU
