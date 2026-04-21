"""Stage 07 — load filtered court cases into legal_document.

For each case:
  - Insert parent row doc_type=court_case with the full text preview (first 2000 chars)
  - Split full text into paragraph-level children (doc_type=court_paragraph)

Idempotent via content_hash.

Run:
  .venv/bin/python -m scripts.legal_ingest.07_load_cases_to_db
"""

import asyncio
import json
import re
import sys
from pathlib import Path

if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from scripts.legal_ingest import config as cfg, common  # noqa: E402
else:
    from . import config as cfg, common

from sqlalchemy import select

log = common.make_logger("07_load_cases")


def split_paragraphs(text: str, target_chars: int = 1200, max_chars: int = 2400) -> list[str]:
    """Split case text into paragraph-sized chunks preserving sentence boundaries."""
    # First split on blank lines / hard breaks
    raw = re.split(r"\s{2,}|\n+", text)
    raw = [p.strip() for p in raw if p.strip()]

    chunks: list[str] = []
    buf = ""
    for p in raw:
        if len(buf) + len(p) + 2 <= max_chars:
            buf = (buf + " " + p).strip() if buf else p
        else:
            if buf:
                chunks.append(buf)
            buf = p[:max_chars]
    if buf:
        chunks.append(buf)

    # Merge tiny chunks into neighbors
    merged: list[str] = []
    for c in chunks:
        if merged and len(merged[-1]) + len(c) + 1 < target_chars:
            merged[-1] = merged[-1] + " " + c
        else:
            merged.append(c)
    return merged


async def main() -> int:
    log.info("Stage 07: loading filtered cases into legal_document")

    if not cfg.CASES_FILTERED_JSON.exists():
        log.error("Missing %s — run stage 06 first", cfg.CASES_FILTERED_JSON)
        return 1

    data = json.loads(cfg.CASES_FILTERED_JSON.read_text(encoding="utf-8"))
    cases = data["cases"][: cfg.TARGET_CASES]  # cap at target
    log.info("Will load %d cases", len(cases))

    from app.database import async_session
    from app.models.legal_document import LegalDocument

    inserted_cases = 0
    inserted_paras = 0
    skipped = 0

    async with async_session() as db:
        for i, c in enumerate(cases):
            case_hash = common.content_hash(c["text"])
            existing = (await db.execute(
                select(LegalDocument).where(
                    LegalDocument.doc_source.in_(["vsrf", "arbitral_sudact", "regular_sudact", "magistrate_sudact"]),
                    LegalDocument.doc_type == "court_case",
                    LegalDocument.content_hash == case_hash,
                )
            )).scalar_one_or_none()
            if existing:
                skipped += 1
                continue

            cat = c["category"]
            # map sudact category → doc_source
            source_map = {"vsrf": "vsrf", "arbitral": "arbitral_sudact",
                          "regular": "regular_sudact", "magistrate": "magistrate_sudact"}
            doc_source = source_map.get(cat, f"sudact_{cat}")

            # Parent row: the case itself (store the head/summary, 2000 char preview)
            preview = c["text"][:2000]
            parent_doc = LegalDocument(
                doc_type="court_case",
                doc_source=doc_source,
                number=c.get("case_number"),
                title=c.get("title"),
                content=preview,
                content_hash=case_hash,
                source_url=c.get("source_url"),
                metadata_json={
                    "case_date": c.get("case_date"),
                    "full_char_count": c.get("char_count"),
                    "matched_keywords": c.get("matched_keywords"),
                    "keyword_count": c.get("keyword_count"),
                    "sudact_category": cat,
                },
                token_count=common.count_tokens_estimate(preview),
            )
            db.add(parent_doc)
            await db.flush()
            inserted_cases += 1

            # Children: paragraph chunks
            for j, para in enumerate(split_paragraphs(c["text"])):
                para_hash = common.content_hash(para)
                # VARCHAR(32) limit on legal_document.number — if case_number
                # is missing we use UUID prefix (8 chars) + ".pNN" not the
                # full 36-char UUID to stay within schema.
                case_ref = c.get("case_number")
                if case_ref:
                    paragraph_number = f"{case_ref[:26]}.p{j+1}"
                else:
                    paragraph_number = f"{str(parent_doc.id)[:8]}.p{j+1}"
                db.add(LegalDocument(
                    parent_id=parent_doc.id,
                    doc_type="court_paragraph",
                    doc_source=doc_source,
                    number=paragraph_number[:32],  # hard cap
                    title=None,
                    content=para,
                    content_hash=para_hash,
                    metadata_json={
                        "paragraph_index": j + 1,
                        "case_number_full": case_ref,
                    },
                    token_count=common.count_tokens_estimate(para),
                ))
                inserted_paras += 1

            if (i + 1) % 25 == 0:
                await db.commit()
                log.info("  %d/%d cases, paragraphs so far: %d", i + 1, len(cases), inserted_paras)

        await db.commit()

    log.info("Stage 07 done: cases=%d paragraphs=%d skipped=%d", inserted_cases, inserted_paras, skipped)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
