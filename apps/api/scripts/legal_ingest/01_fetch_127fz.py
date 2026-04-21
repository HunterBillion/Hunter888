"""Stage 01 — fetch 127-ФЗ from legalacts.ru.

Flow:
  1. Fetch main TOC page → extract chapter URLs (/glava-i/, /glava-ii/, …)
  2. Fetch each chapter page → contains full article text

Output: apps/api/scripts/legal_ingest/data/law/127fz_raw/{main,glava-*.html}

Idempotent: files are overwritten only if absent or size < 1KB (treated as broken).

Run:
  .venv/bin/python -m scripts.legal_ingest.01_fetch_127fz
"""

import asyncio
import re
import sys
from pathlib import Path

# Support running as `python 01_fetch_127fz.py` directly (not just as module)
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from scripts.legal_ingest import config as cfg, common  # noqa: E402
else:
    from . import config as cfg, common

log = common.make_logger("01_fetch_127fz")


def extract_chapter_urls(main_html: str) -> list[str]:
    """Find all `/doc/FZ-o-nesostojatelnosti-bankrotstve/glava-*/` links in TOC."""
    urls = set(
        re.findall(
            r'href="(/doc/FZ-o-nesostojatelnosti-bankrotstve/glava-[a-zA-Z0-9\-_]+/[^"]*)"',
            main_html,
        )
    )
    # Strip fragments, normalize
    cleaned: list[str] = []
    for u in urls:
        u = u.split("#")[0].rstrip("/") + "/"
        cleaned.append(u)
    return sorted(set(cleaned))


async def main() -> int:
    log.info("Stage 01: fetching 127-ФЗ from legalacts.ru")

    main_file = cfg.LAW_RAW_DIR / "_main_toc.html"

    async with common.RateLimitedFetcher(rps=cfg.LEGALACTS_RPS) as f:
        # ── Main TOC ──
        if main_file.exists() and main_file.stat().st_size > 1024:
            log.info("TOC already downloaded (%d bytes), using cache", main_file.stat().st_size)
            main_html = main_file.read_text(encoding="utf-8")
        else:
            r = await f.get(cfg.LEGALACTS_127FZ_URL)
            if not r or r.status_code != 200:
                log.error("Failed to fetch main TOC: %s", r.status_code if r else "None")
                return 1
            main_html = r.text
            common.save_html(main_file, main_html)
            log.info("TOC saved (%d bytes)", len(main_html))

        # ── Extract chapter URLs ──
        chapter_paths = extract_chapter_urls(main_html)
        log.info("Discovered %d chapter URLs", len(chapter_paths))
        if len(chapter_paths) < 5:
            log.warning("Expected ≥5 chapters — TOC extraction may have broken; got: %s", chapter_paths)

        # ── Fetch each chapter ──
        ok = 0
        skipped = 0
        for path in chapter_paths:
            slug = path.rstrip("/").split("/")[-1]  # e.g. "glava-i"
            out = cfg.LAW_RAW_DIR / f"{slug}.html"
            if out.exists() and out.stat().st_size > 1024:
                skipped += 1
                continue
            url = cfg.LEGALACTS_BASE + path
            r = await f.get(url)
            if not r or r.status_code != 200:
                log.warning("Failed %s → %s", slug, r.status_code if r else "None")
                continue
            common.save_html(out, r.text)
            ok += 1
            log.info("saved %s (%d bytes)", slug, len(r.text))

    log.info("Stage 01 done: %d new, %d cached, %d total", ok, skipped, ok + skipped)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
