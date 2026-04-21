"""Stage 04 — download sudact.ru sitemaps and build filtered URL lists.

Output:
  data/law/sudact_urls_all.txt       — все URL (все типы) one per line
  data/law/sudact_urls_to_fetch.txt  — отфильтрованные по CRAWL_ORDER и лимитам

Selection logic:
  - для каждого typeв CRAWL_ORDER взять до MAX_FETCH_PER_CATEGORY[type]
  - приоритет: vsrf (все 479) → arbitral → regular → magistrate
  - суммарно нацеливаемся получить ~TARGET_CASES * 3 сырых URL
    (после фильтра "банкротство" останется ~TARGET_CASES годных)

Run:
  .venv/bin/python -m scripts.legal_ingest.04_fetch_sudact_sitemap
"""

import asyncio
import gzip
import re
import sys
from pathlib import Path

if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from scripts.legal_ingest import config as cfg, common  # noqa: E402
else:
    from . import config as cfg, common

log = common.make_logger("04_fetch_sudact_sitemap")

URL_RE = re.compile(r"<loc>([^<]+)</loc>")
CATEGORY_RE = re.compile(r"https?://sudact\.ru/([a-z]+)/doc/", re.I)


async def main() -> int:
    log.info("Stage 04: fetching sudact sitemaps")
    all_urls_by_cat: dict[str, list[str]] = {}

    async with common.RateLimitedFetcher(rps=1.0) as f:
        for sm_url in cfg.SUDACT_SITEMAP_PARTS:
            log.info("Fetching %s", sm_url)
            r = await f.get(sm_url)
            if not r or r.status_code != 200:
                log.error("Failed %s: %s", sm_url, r.status_code if r else "None")
                continue
            raw = r.content
            # httpx may auto-decompress gzip transport encoding; detect and handle both
            if raw[:2] == b"\x1f\x8b":
                xml_data = gzip.decompress(raw).decode("utf-8", errors="replace")
            else:
                xml_data = raw.decode("utf-8", errors="replace")
            for url in URL_RE.findall(xml_data):
                m = CATEGORY_RE.match(url)
                if not m:
                    continue
                cat = m.group(1).lower()
                all_urls_by_cat.setdefault(cat, []).append(url)
            log.info("Sitemap parsed: %s", {k: len(v) for k, v in all_urls_by_cat.items()})

    # Write the combined file
    with cfg.SUDACT_URLS_FILE.open("w", encoding="utf-8") as out:
        for cat, urls in all_urls_by_cat.items():
            for u in urls:
                out.write(u + "\n")
    log.info("All URLs written to %s (%d total)", cfg.SUDACT_URLS_FILE,
             sum(len(v) for v in all_urls_by_cat.values()))

    # Build filtered list per CRAWL_ORDER limits
    filtered: list[str] = []
    for cat in cfg.CRAWL_ORDER:
        urls = all_urls_by_cat.get(cat, [])
        limit = cfg.MAX_FETCH_PER_CATEGORY.get(cat, 0)
        take = urls[:limit]
        log.info("  %s: %d available, taking %d", cat, len(urls), len(take))
        filtered.extend(take)

    with cfg.SUDACT_URLS_FILTERED.open("w", encoding="utf-8") as out:
        for u in filtered:
            out.write(u + "\n")
    log.info("Filtered URLs: %d → %s", len(filtered), cfg.SUDACT_URLS_FILTERED)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
