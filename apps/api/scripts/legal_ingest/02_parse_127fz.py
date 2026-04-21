"""Stage 02 — parse 127-ФЗ HTML files into a structured JSON tree.

Each statja-N.html page contains one article with full text. We parse:
  - article number (from filename slug: statja-2.1 → "2.1")
  - article title (from h1)
  - article body (main content block)
  - chapter reference (from breadcrumbs / meta)
  - section (subsection) markers within article body

Output structure:
  {
    "meta": {
      "law_id": "127-ФЗ",
      "title": "О несостоятельности (банкротстве)",
      "redaction_date": "...",  # extracted from HTML if present
      "total_articles": 520,
      "parsed_at": "...",
    },
    "chapters": [
      {
        "number": "I", "title": "Общие положения",
        "articles": [
          {
            "number": "1",
            "title": "Отношения, регулируемые настоящим Федеральным законом",
            "text": "...",
            "items": [ { "number": "1", "text": "..." }, ... ],
          },
          ...
        ],
      }, ...
    ],
  }

Run:
  .venv/bin/python -m scripts.legal_ingest.02_parse_127fz
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

log = common.make_logger("02_parse_127fz")

# ── Patterns ────────────────────────────────────────────────────────────

ARTICLE_SLUG_RE = re.compile(r"^statja-([0-9.]+)(?:-([0-9]+))?$")
CHAPTER_SLUG_RE = re.compile(r"^glava-([ivxlcdm]+)$", re.I)
ITEM_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\.\s*")  # "1.", "2.3.", "4.5.1."
SUBITEM_RE = re.compile(r"^\s*([а-яa-z])\)\s*")  # "а)", "b)"


def parse_article_file(path: Path) -> dict | None:
    """Parse one statja-N.html into structured article dict."""
    slug = path.stem
    m = ARTICLE_SLUG_RE.match(slug)
    if not m:
        return None
    article_number = m.group(1)
    # Skip paginated variants (statja-N-2, statja-N-3, …) — same content spread
    # across pages; we only want the canonical statja-N.html.
    if m.group(2):
        return None

    html = path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")

    # ── Title ──
    h1 = soup.find("h1")
    title_raw = h1.get_text(" ", strip=True) if h1 else ""
    # legalacts.ru titles look like: "Статья 2. Основные понятия..." — strip leading "Статья N."
    title = re.sub(r"^\s*Статья\s+[0-9.]+\.\s*", "", title_raw)
    # fallback if h1 format differs
    if not title or title == title_raw:
        # Look in <title>
        t_tag = soup.find("title")
        if t_tag:
            title = re.sub(r"^\s*Статья\s+[0-9.]+\.\s*", "", t_tag.get_text(strip=True))
            title = title.split("::")[0].strip()  # "... :: legalacts.ru"

    # ── Chapter ref (from breadcrumbs) ──
    chapter_number = None
    chapter_title = None
    for a in soup.find_all("a", href=True):
        m2 = re.search(r"/glava-([ivxlcdm]+)/$", a["href"], re.I)
        if m2:
            chapter_number = m2.group(1).upper()
            chapter_title = a.get_text(" ", strip=True)
            break

    # ── Body: legalacts.ru-specific selector ──
    body_container = soup.select_one("div.main-center-block-article-text")
    if not body_container:
        return None  # Not a valid article page (e.g. chapter TOC)

    raw_text = body_container.get_text("\n", strip=True)
    # Split on newlines (from our <br> -> \n conversion)
    raw_paragraphs = [p.strip() for p in raw_text.split("\n") if p.strip()]

    paragraphs: list[str] = []
    for p in raw_paragraphs:
        if len(p) < 10:
            continue
        paragraphs.append(common.normalize_whitespace(p))

    # Deduplicate consecutive identical paragraphs
    deduped: list[str] = []
    for p in paragraphs:
        if deduped and deduped[-1] == p:
            continue
        deduped.append(p)

    # ── Split into items (1., 2., …) if present ──
    items: list[dict] = []
    current_item_number: str | None = None
    current_item_text: list[str] = []
    preface: list[str] = []

    for p in deduped:
        # Skip the article title line if it appears in body
        if p.startswith("Статья " + article_number + "."):
            continue
        item_match = ITEM_RE.match(p)
        if item_match and item_match.group(1) != article_number:
            # Start a new item
            if current_item_number is not None:
                items.append({
                    "number": current_item_number,
                    "text": " ".join(current_item_text).strip(),
                })
            current_item_number = item_match.group(1)
            current_item_text = [p[item_match.end():].strip()]
        else:
            if current_item_number is None:
                preface.append(p)
            else:
                current_item_text.append(p)

    if current_item_number is not None:
        items.append({
            "number": current_item_number,
            "text": " ".join(current_item_text).strip(),
        })

    # Full article text = preface + all items joined
    full_text_parts: list[str] = list(preface)
    for it in items:
        full_text_parts.append(f"{it['number']}. {it['text']}")
    full_text = "\n\n".join(full_text_parts).strip()

    return {
        "number": article_number,
        "title": title,
        "text": full_text,
        "items": items,
        "chapter_number": chapter_number,
        "chapter_title": chapter_title,
        "source_url": f"{cfg.LEGALACTS_BASE}/doc/FZ-o-nesostojatelnosti-bankrotstve/{slug}/",
        "slug": slug,
        "char_count": len(full_text),
    }


def article_sort_key(art: dict) -> tuple:
    """Sort articles by numeric hierarchy: '1', '2', '2.1', '10', '100', '213.4'."""
    parts = art["number"].split(".")
    return tuple(int(p) if p.isdigit() else 0 for p in parts)


def main() -> int:
    log.info("Stage 02: parsing 127-ФЗ HTML files")

    article_files = sorted(cfg.LAW_RAW_DIR.glob("statja-*.html"))
    log.info("Found %d article HTML files", len(article_files))

    articles: list[dict] = []
    for f in article_files:
        try:
            art = parse_article_file(f)
            if art and art["text"]:
                articles.append(art)
            else:
                log.warning("  skipped %s: empty text", f.name)
        except Exception as e:
            log.warning("  failed %s: %s", f.name, e)

    log.info("Parsed %d articles", len(articles))

    # Group by chapter
    chapters_map: dict[str, dict] = {}
    for art in articles:
        chap_n = art.get("chapter_number") or "UNKNOWN"
        if chap_n not in chapters_map:
            chapters_map[chap_n] = {
                "number": chap_n,
                "title": art.get("chapter_title") or "",
                "articles": [],
            }
        # Don't duplicate chapter title; just keep first non-empty
        if not chapters_map[chap_n]["title"] and art.get("chapter_title"):
            chapters_map[chap_n]["title"] = art["chapter_title"]
        chapters_map[chap_n]["articles"].append({
            "number": art["number"],
            "title": art["title"],
            "text": art["text"],
            "items": art["items"],
            "source_url": art["source_url"],
            "char_count": art["char_count"],
        })

    # Sort chapters by Roman numeral → arabic (I=1, II=2, ... VIII=8, IX=9)
    def roman_to_int(s: str) -> int:
        roman_map = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
        result = 0
        for i, ch in enumerate(s):
            v = roman_map.get(ch.upper(), 0)
            nv = roman_map.get(s[i + 1].upper(), 0) if i + 1 < len(s) else 0
            result += -v if v < nv else v
        return result or 9999

    chapter_list = sorted(chapters_map.values(), key=lambda c: roman_to_int(c["number"]))
    for chap in chapter_list:
        chap["articles"].sort(key=article_sort_key)

    out = {
        "meta": {
            "law_id": "127-ФЗ",
            "title": "О несостоятельности (банкротстве)",
            "source": "legalacts.ru",
            "total_articles": len(articles),
            "total_chapters": len(chapter_list),
            "parsed_at": datetime.now(timezone.utc).isoformat(),
        },
        "chapters": chapter_list,
    }

    cfg.LAW_STRUCTURED.write_text(
        json.dumps(out, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("Stage 02 done: %d articles across %d chapters → %s", len(articles), len(chapter_list), cfg.LAW_STRUCTURED)

    # Diagnostics
    total_items = sum(len(a["items"]) for c in chapter_list for a in c["articles"])
    total_chars = sum(a["char_count"] for c in chapter_list for a in c["articles"])
    log.info("Total items: %d, total chars: %d (≈ %d tokens)", total_items, total_chars, total_chars // 3)

    # Sample
    if chapter_list and chapter_list[0]["articles"]:
        a0 = chapter_list[0]["articles"][0]
        log.info("Sample: глава %s / статья %s — %s (items=%d, chars=%d)",
                 chapter_list[0]["number"], a0["number"], a0["title"][:60], len(a0["items"]), a0["char_count"])

    return 0


if __name__ == "__main__":
    sys.exit(main())
