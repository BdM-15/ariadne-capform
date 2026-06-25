"""Shared fixtures — optional Postgres session with per-test rollback."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from thread.config import Settings

_BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def _run_from_backend_dir():
    """Pin cwd to backend/ so asset/template tests using paths like
    ``Path("src/thread/ui/templates/...")`` resolve regardless of where pytest
    is invoked from."""
    prev = Path.cwd()
    os.chdir(_BACKEND_DIR)
    yield
    os.chdir(prev)


@pytest.fixture(autouse=True)
def _isolate_thread_state(tmp_path, monkeypatch):
    """Hermetic per-test ``.thread`` state and neutralized operator overrides.

    Tests construct ``Settings()`` which reads the real repo ``.env`` and
    ``.thread/`` directory. Without isolation, operator overrides
    (``THREAD_ALLOW_TEST_PROMOTE``) and saved state (``insight_queries.json``,
    ``watchlist.json``, ...) leak in and pollute assertions. Each test gets a
    fresh temp state dir; tests needing an override set it explicitly via
    ``Settings(...)`` kwargs (init kwargs outrank env).
    """
    from thread.config import get_settings

    monkeypatch.setenv("THREAD_STATE_DIR", str(tmp_path / "thread_state"))
    monkeypatch.setenv("THREAD_VAULT_SANDBOX", "false")
    monkeypatch.setenv("THREAD_ALLOW_TEST_PROMOTE", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _postgres_available() -> bool:
    if os.environ.get("THREAD_SKIP_PG_TESTS", "").lower() in ("1", "true", "yes"):
        return False
    return True


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture(scope="session", autouse=True)
def _ensure_workflow_migrations():
    """Alembic head before any PG test — operator_tasks etc."""
    from thread.db.migrate import run_workflow_migrations

    run_workflow_migrations()
    yield


_E2E_SMOKE_ORDER = {
    "test_a_smoke_api_http_path": 0,
    "test_z_smoke_service_path": 1,
    "test_b_smoke_htmx_track_signal_redirect": 2,
}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Run E2E sync smokes before async service path (Windows asyncpg loop clash)."""
    e2e = [item for item in items if item.name in _E2E_SMOKE_ORDER]
    if len(e2e) < 2:
        return
    e2e.sort(key=lambda item: _E2E_SMOKE_ORDER[item.name])
    first_idx = items.index(e2e[0])
    for item in e2e:
        items.remove(item)
    for offset, item in enumerate(e2e):
        items.insert(first_idx + offset, item)


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