"""Create all database tables using async engine (no psycopg2 needed).

Usage: python scripts/create_tables.py
"""
import asyncio
import sys
from pathlib import Path

# Ensure app is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import engine, Base
from app.models import *  # noqa: F401,F403 — import all models


async def main():
    print("Creating all tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Done! All tables created.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
