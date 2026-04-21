"""Stage 03 — load parsed 127-ФЗ JSON into legal_document table.

Hierarchy built:
  law_fz (root: "127-ФЗ")
    ├── law_chapter (number=I, II, ...)
    │    ├── law_article (number=1, 2.1, 213.4, ...)
    │    │    └── law_item (number=1, 2, ...)   ← actual retrieval granularity

Idempotent: uses (doc_source, doc_type, number, content_hash) unique constraint.
Re-running after text changes creates new rows (different content_hash) and
marks the previous version is_active=False.

Run:
  .venv/bin/python -m scripts.legal_ingest.03_load_127fz_to_db
"""

import asyncio
import json
import sys
from pathlib import Path

if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from scripts.legal_ingest import config as cfg, common  # noqa: E402
else:
    from . import config as cfg, common

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

log = common.make_logger("03_load_127fz")


async def main() -> int:
    log.info("Stage 03: loading 127-ФЗ into legal_document")

    if not cfg.LAW_STRUCTURED.exists():
        log.error("Missing %s — run stage 02 first", cfg.LAW_STRUCTURED)
        return 1

    data = json.loads(cfg.LAW_STRUCTURED.read_text(encoding="utf-8"))
    meta = data["meta"]
    chapters = data["chapters"]

    # Lazy import to respect CWD / env
    from app.database import async_session
    from app.models.legal_document import LegalDocument

    inserted = 0
    skipped = 0
    updated_active = 0

    async with async_session() as db:
        # ── Root: law_fz ──
        root_content = f"Федеральный закон «{meta['title']}», №127-ФЗ от 26.10.2002"
        root_hash = common.content_hash(root_content)
        existing = (await db.execute(
            select(LegalDocument).where(
                LegalDocument.doc_source == "127-FZ",
                LegalDocument.doc_type == "law_fz",
                LegalDocument.number.is_(None),
                LegalDocument.content_hash == root_hash,
            )
        )).scalar_one_or_none()
        if existing:
            root_id = existing.id
            skipped += 1
        else:
            root = LegalDocument(
                doc_type="law_fz",
                doc_source="127-FZ",
                number=None,
                title=meta["title"],
                content=root_content,
                content_hash=root_hash,
                metadata_json={"parsed_at": meta["parsed_at"], "source": meta["source"]},
                token_count=common.count_tokens_estimate(root_content),
            )
            db.add(root)
            await db.flush()
            root_id = root.id
            inserted += 1

        # ── Chapters, articles, items ──
        for chap in chapters:
            chap_content = f"Глава {chap['number']}. {chap.get('title', '')}"
            chap_hash = common.content_hash(chap_content)
            existing_chap = (await db.execute(
                select(LegalDocument).where(
                    LegalDocument.doc_source == "127-FZ",
                    LegalDocument.doc_type == "law_chapter",
                    LegalDocument.number == chap["number"],
                    LegalDocument.content_hash == chap_hash,
                )
            )).scalar_one_or_none()
            if existing_chap:
                chap_id = existing_chap.id
                skipped += 1
            else:
                c = LegalDocument(
                    parent_id=root_id,
                    doc_type="law_chapter",
                    doc_source="127-FZ",
                    number=chap["number"],
                    title=chap.get("title"),
                    content=chap_content,
                    content_hash=chap_hash,
                    metadata_json={},
                    token_count=common.count_tokens_estimate(chap_content),
                )
                db.add(c)
                await db.flush()
                chap_id = c.id
                inserted += 1

            for art in chap["articles"]:
                art_hash = common.content_hash(art["text"])
                existing_art = (await db.execute(
                    select(LegalDocument).where(
                        LegalDocument.doc_source == "127-FZ",
                        LegalDocument.doc_type == "law_article",
                        LegalDocument.number == art["number"],
                        LegalDocument.content_hash == art_hash,
                    )
                )).scalar_one_or_none()
                if existing_art:
                    art_id = existing_art.id
                    skipped += 1
                    continue  # items under this article already exist too

                # If a different content_hash exists, deactivate the old version
                await db.execute(
                    update(LegalDocument)
                    .where(
                        LegalDocument.doc_source == "127-FZ",
                        LegalDocument.doc_type == "law_article",
                        LegalDocument.number == art["number"],
                        LegalDocument.is_active.is_(True),
                    )
                    .values(is_active=False)
                )

                a = LegalDocument(
                    parent_id=chap_id,
                    doc_type="law_article",
                    doc_source="127-FZ",
                    number=art["number"],
                    title=art["title"],
                    content=art["text"],
                    content_hash=art_hash,
                    source_url=art.get("source_url"),
                    metadata_json={
                        "chapter_number": chap["number"],
                        "chapter_title": chap.get("title"),
                    },
                    token_count=common.count_tokens_estimate(art["text"]),
                )
                db.add(a)
                await db.flush()
                art_id = a.id
                inserted += 1
                updated_active += 1

                for item in art["items"]:
                    item_text = f"{item['number']}. {item['text']}"
                    item_hash = common.content_hash(item_text)
                    i = LegalDocument(
                        parent_id=art_id,
                        doc_type="law_item",
                        doc_source="127-FZ",
                        number=f"{art['number']}.{item['number']}",
                        title=None,
                        content=item_text,
                        content_hash=item_hash,
                        metadata_json={
                            "article_number": art["number"],
                            "article_title": art["title"],
                        },
                        token_count=common.count_tokens_estimate(item_text),
                    )
                    db.add(i)
                    inserted += 1

            await db.commit()  # commit per chapter

    log.info("Stage 03 done: inserted=%d, skipped=%d (duplicate), updated_active=%d", inserted, skipped, updated_active)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
