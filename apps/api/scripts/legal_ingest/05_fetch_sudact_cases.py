"""Stage 05 — fetch individual sudact case pages.

RESUMABLE: уже скачанные файлы (в data/law/cases/{hash}.html) пропускаются.
Можно остановить Ctrl+C и перезапустить — продолжит с того же места.

RATE-LIMITED: cfg.SUDACT_RPS (по умолчанию 0.5 rps = 2 сек между запросами).

На 500-2000 URL займёт 15-60 мин.

Run:
  .venv/bin/python -m scripts.legal_ingest.05_fetch_sudact_cases
"""

import asyncio
import re
import sys
from pathlib import Path

if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from scripts.legal_ingest import config as cfg, common  # noqa: E402
else:
    from . import config as cfg, common

log = common.make_logger("05_fetch_sudact_cases")

URL_HASH_RE = re.compile(r"sudact\.ru/([a-z]+)/doc/([A-Za-z0-9]+)/?$", re.I)


def url_to_path(url: str) -> Path | None:
    m = URL_HASH_RE.search(url.strip())
    if not m:
        return None
    cat, h = m.group(1).lower(), m.group(2)
    return cfg.CASES_DIR / cat / f"{h}.html"


async def main() -> int:
    log.info("Stage 05: fetching sudact case pages")

    if not cfg.SUDACT_URLS_FILTERED.exists():
        log.error("Missing %s — run stage 04 first", cfg.SUDACT_URLS_FILTERED)
        return 1

    urls = [u.strip() for u in cfg.SUDACT_URLS_FILTERED.read_text(encoding="utf-8").splitlines() if u.strip()]
    total = len(urls)
    log.info("Queue: %d URLs", total)

    ok = skipped = failed = 0

    async with common.RateLimitedFetcher(rps=cfg.SUDACT_RPS) as f:
        for i, url in enumerate(urls):
            path = url_to_path(url)
            if not path:
                failed += 1
                continue
            if path.exists() and path.stat().st_size > 500:
                skipped += 1
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            r = await f.get(url)
            if not r:
                failed += 1
                log.warning("  [%d/%d] None %s", i + 1, total, url)
                continue
            if r.status_code != 200:
                failed += 1
                log.warning("  [%d/%d] %d %s", i + 1, total, r.status_code, url)
                continue
            # Skip near-empty responses (redirects, 404 pages)
            if len(r.text) < 2000:
                failed += 1
                continue
            common.save_html(path, r.text)
            ok += 1
            if ok % 25 == 0:
                log.info("  progress: ok=%d skipped=%d failed=%d / %d", ok, skipped, failed, total)

    log.info("Stage 05 done: ok=%d skipped=%d failed=%d", ok, skipped, failed)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
