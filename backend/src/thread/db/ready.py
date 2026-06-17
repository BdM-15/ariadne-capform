"""PostgreSQL readiness — avoid racing docker compose startup."""

from __future__ import annotations

import asyncio
import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from thread.config import Settings


async def wait_for_postgres(
    engine: AsyncEngine,
    settings: Settings,
    *,
    timeout_sec: float = 90,
    interval_sec: float = 1.5,
) -> bool:
    """Block until PostgreSQL accepts connections or timeout."""
    host = "127.0.0.1"
    port = settings.thread_postgres_port
    deadline = time.monotonic() + timeout_sec
    last_err: Exception | None = None
    attempt = 0

    while time.monotonic() < deadline:
        attempt += 1
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            if attempt > 1:
                print(f"[thread] PostgreSQL ready on {host}:{port}")
            return True
        except Exception as exc:
            last_err = exc
            if attempt == 1:
                print(f"[thread] Waiting for PostgreSQL on {host}:{port}…")
            await asyncio.sleep(interval_sec)

    print(f"[thread] ERROR: PostgreSQL not ready after {timeout_sec:.0f}s: {last_err}")
    return False