"""Seed personality lorebook entries from JSON files.

Usage:
    python -m scripts.seed_lorebook [archetype]

    archetype: optional, e.g. "skeptic". If omitted, seeds all archetypes found in data/lorebook/.
"""

import asyncio
import hashlib
import json
import logging
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, text

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data" / "lorebook"


async def seed_archetype(archetype_code: str, db) -> dict:
    """Seed one archetype from its JSON files. Returns stats."""
    from app.models.rag import PersonalityChunk, PersonalityExample

    arch_dir = DATA_DIR / archetype_code
    if not arch_dir.exists():
        logger.warning("No data dir for archetype: %s", archetype_code)
        return {"archetype": archetype_code, "error": "no data dir"}

    stats = {"archetype": archetype_code, "entries_created": 0, "entries_skipped": 0, "examples_created": 0}

    # ── Load card.json as core_identity entry ──
    card_file = arch_dir / "card.json"
    if card_file.exists():
        card_data = json.loads(card_file.read_text(encoding="utf-8"))
        content = card_data.get("character_card", "")
        if content:
            h = hashlib.md5(f"{archetype_code}:core_identity:{content}".encode()).hexdigest()
            exists = await db.execute(
                select(PersonalityChunk.id).where(PersonalityChunk.content_hash == h)
            )
            if not exists.scalar_one_or_none():
                db.add(PersonalityChunk(
                    id=uuid4(),
                    archetype_code=archetype_code,
                    trait_category="core_identity",
                    content=content,
                    keywords=[],
                    priority=10,
                    source="extracted",
                    content_hash=h,
                ))
                stats["entries_created"] += 1
            else:
                stats["entries_skipped"] += 1

    # ── Load entries.json ──
    entries_file = arch_dir / "entries.json"
    if entries_file.exists():
        entries = json.loads(entries_file.read_text(encoding="utf-8"))
        for entry in entries:
            content = entry.get("content", "")
            category = entry.get("trait_category", "speech_examples")
            h = hashlib.md5(f"{archetype_code}:{category}:{content}".encode()).hexdigest()
            exists = await db.execute(
                select(PersonalityChunk.id).where(PersonalityChunk.content_hash == h)
            )
            if not exists.scalar_one_or_none():
                db.add(PersonalityChunk(
                    id=uuid4(),
                    archetype_code=archetype_code,
                    trait_category=category,
                    content=content,
                    keywords=entry.get("keywords", []),
                    priority=entry.get("priority", 5),
                    source=entry.get("source", "extracted"),
                    content_hash=h,
                ))
                stats["entries_created"] += 1
            else:
                stats["entries_skipped"] += 1

    # ── Load examples.json ──
    examples_file = arch_dir / "examples.json"
    if examples_file.exists():
        examples = json.loads(examples_file.read_text(encoding="utf-8"))
        for ex in examples:
            situation = ex.get("situation", "")
            dialogue = ex.get("dialogue", "")
            # Check for duplicate by content
            exists = await db.execute(
                select(PersonalityExample.id).where(
                    PersonalityExample.archetype_code == archetype_code,
                    PersonalityExample.dialogue == dialogue,
                )
            )
            if not exists.scalar_one_or_none():
                db.add(PersonalityExample(
                    id=uuid4(),
                    archetype_code=archetype_code,
                    situation=situation,
                    dialogue=dialogue,
                    emotion=ex.get("emotion"),
                    source=ex.get("source", "extracted"),
                ))
                stats["examples_created"] += 1

    await db.commit()
    logger.info(
        "Seeded lorebook [%s]: %d entries (+%d skipped), %d examples",
        archetype_code,
        stats["entries_created"],
        stats["entries_skipped"],
        stats["examples_created"],
    )
    return stats


async def seed_all_archetypes(db) -> list[dict]:
    """Seed all archetypes found in data/lorebook/."""
    if not DATA_DIR.exists():
        logger.warning("Lorebook data dir not found: %s", DATA_DIR)
        return []

    results = []
    for arch_dir in sorted(DATA_DIR.iterdir()):
        if arch_dir.is_dir():
            result = await seed_archetype(arch_dir.name, db)
            results.append(result)
    return results


async def main():
    """CLI entry point."""
    from app.database import async_session

    archetype = sys.argv[1] if len(sys.argv) > 1 else None

    async with async_session() as db:
        if archetype:
            result = await seed_archetype(archetype, db)
            print(json.dumps(result, indent=2))
        else:
            results = await seed_all_archetypes(db)
            for r in results:
                print(json.dumps(r, indent=2))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
