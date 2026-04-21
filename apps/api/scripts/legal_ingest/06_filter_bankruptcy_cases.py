"""Stage 06 — filter fetched sudact cases for bankruptcy relevance.

For each case HTML:
  1. Extract case number, court, date, text content
  2. Count BANKRUPTCY_KEYWORDS matches
  3. Keep if ≥ BANKRUPTCY_MIN_KEYWORDS distinct keywords present

Output: data/law/cases_filtered.json — list of filtered cases with parsed fields

Run:
  .venv/bin/python -m scripts.legal_ingest.06_filter_bankruptcy_cases
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from scripts.legal_ingest import config as cfg, common  # noqa: E402
else:
    from . import config as cfg, common

from bs4 import BeautifulSoup

log = common.make_logger("06_filter")

# Russian case-number pattern: А40-123456/2023, №А60-12345/2024, etc.
CASE_NUMBER_RE = re.compile(r"(?:№\s*)?([АA]\d{2}-\d+/\d{4})")
DATE_RE = re.compile(r"(\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+\d{4})", re.I)


def extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    # sudact.ru case body likely in specific div
    for sel in [
        "div.main-center-block-article-text",
        "div.doc-text",
        "div.judgment-text",
        "article",
        "main",
    ]:
        el = soup.select_one(sel)
        if el:
            return el.get_text(" ", strip=True)
    # fallback — raw body
    body = soup.find("body")
    return body.get_text(" ", strip=True) if body else ""


def parse_case(path: Path) -> dict | None:
    try:
        html = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    soup = BeautifulSoup(html, "lxml")
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""
    # title typically: "Постановление от 23 марта 2026 г. Верховный Суд РФ :: СудАкт.ру"
    title_clean = title.split("::")[0].strip()

    text = extract_text(html)
    if len(text) < 500:
        return None

    # Keyword filter
    text_lower = text.lower()
    matched = [kw for kw in cfg.BANKRUPTCY_KEYWORDS if kw in text_lower]
    if len(matched) < cfg.BANKRUPTCY_MIN_KEYWORDS:
        return None

    # Extract structured fields
    m_num = CASE_NUMBER_RE.search(text)
    case_number = m_num.group(1) if m_num else None
    m_date = DATE_RE.search(title_clean) or DATE_RE.search(text[:1000])
    case_date = m_date.group(1) if m_date else None

    # Category inference from path (cases/vsrf/*.html, cases/arbitral/*.html, …)
    category = path.parent.name

    # Reconstruct URL (hash is filename stem)
    source_url = f"{cfg.SUDACT_BASE}/{category}/doc/{path.stem}/"

    return {
        "source_url": source_url,
        "category": category,
        "title": title_clean,
        "case_number": case_number,
        "case_date": case_date,
        "text": text,
        "char_count": len(text),
        "matched_keywords": matched,
        "keyword_count": len(matched),
    }


def main() -> int:
    log.info("Stage 06: filtering bankruptcy cases")

    all_files = sorted(cfg.CASES_DIR.rglob("*.html"))
    log.info("Found %d downloaded case files", len(all_files))

    kept: list[dict] = []
    stats_by_cat: dict[str, dict] = {}

    for p in all_files:
        cat = p.parent.name
        stats_by_cat.setdefault(cat, {"total": 0, "kept": 0, "short": 0, "no_kw": 0})
        stats_by_cat[cat]["total"] += 1

        case = parse_case(p)
        if case is None:
            # We don't know here which reason — get it explicitly
            try:
                text = extract_text(p.read_text(encoding="utf-8", errors="replace"))
                if len(text) < 500:
                    stats_by_cat[cat]["short"] += 1
                else:
                    stats_by_cat[cat]["no_kw"] += 1
            except Exception:
                pass
            continue
        kept.append(case)
        stats_by_cat[cat]["kept"] += 1

    log.info("Filter stats:")
    for cat, st in stats_by_cat.items():
        log.info("  %s: total=%d kept=%d short=%d no_kw=%d",
                 cat, st["total"], st["kept"], st["short"], st["no_kw"])

    # Sort by keyword match count descending (best first)
    kept.sort(key=lambda c: -c["keyword_count"])
    # Trim to TARGET_CASES
    kept = kept[: cfg.TARGET_CASES * 2]  # extra margin for chunking filter

    out = {
        "meta": {
            "parsed_at": datetime.now(timezone.utc).isoformat(),
            "total_cases": len(kept),
            "min_keywords": cfg.BANKRUPTCY_MIN_KEYWORDS,
        },
        "cases": kept,
    }
    cfg.CASES_FILTERED_JSON.write_text(
        json.dumps(out, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("Stage 06 done: kept %d cases → %s", len(kept), cfg.CASES_FILTERED_JSON)
    return 0


if __name__ == "__main__":
    sys.exit(main())
