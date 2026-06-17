"""Shared fixtures — optional Postgres session with per-test rollback."""

from __future__ import annotations

import os

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from thread.config import Settings


def _postgres_available() -> bool:
    if os.environ.get("THREAD_SKIP_PG_TESTS", "").lower() in ("1", "true", "yes"):
        return False
    return True


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
async def db_session(settings: Settings):
    """Yield a session inside a rolled-back transaction (requires local Postgres)."""
    if not _postgres_available():
        pytest.skip("Postgres tests disabled (THREAD_SKIP_PG_TESTS)")

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            trans = await conn.begin()
            session = AsyncSession(bind=conn, expire_on_commit=False)
            try:
                yield session
            finally:
                await session.close()
                await trans.rollback()
    except OSError:
        pytest.skip("Postgres unreachable — start docker postgres")
    except Exception as exc:
        pytest.skip(f"Postgres unavailable: {exc}")
    finally:
        await engine.dispose()