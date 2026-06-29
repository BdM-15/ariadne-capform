"""Apply the Tavern PostgreSQL schema. Usage: python tavern/run_tavern_schema.py"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILE = Path(__file__).resolve().parent / "schema" / "tavern_schema.sql"
DEFAULT_DSN = "postgresql://thread:thread@127.0.0.1:55432/thread"


def _dsn() -> str:
    load_dotenv(ROOT / ".env", override=False)
    url = os.environ.get("DATABASE_URL", DEFAULT_DSN)
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def apply_schema() -> None:
    conn = await asyncpg.connect(_dsn())
    try:
        await conn.execute(SCHEMA_FILE.read_text(encoding="utf-8"))
        print("Tavern schema applied successfully.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(apply_schema())