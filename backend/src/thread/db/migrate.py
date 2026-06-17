"""Run Alembic migrations for workflow tables."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from thread.config import Settings, get_settings

BACKEND_ROOT = Path(__file__).resolve().parents[3]


def sync_database_url(async_url: str) -> str:
    if async_url.startswith("postgresql+asyncpg://"):
        return async_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    return async_url


def alembic_config(settings: Settings | None = None) -> Config:
    settings = settings or get_settings()
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", sync_database_url(settings.database_url))
    return cfg


def _workflow_tables_present(engine) -> bool:
    return "opportunities" in inspect(engine).get_table_names()


def _current_revision(engine) -> str | None:
    if "alembic_version" not in inspect(engine).get_table_names():
        return None
    with engine.connect() as conn:
        row = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).fetchone()
    return row[0] if row else None


def run_workflow_migrations(settings: Settings | None = None) -> str:
    """Upgrade workflow schema to head. Stamp existing DBs that predate Alembic."""
    settings = settings or get_settings()
    cfg = alembic_config(settings)
    url = sync_database_url(settings.database_url)
    engine = create_engine(url, pool_pre_ping=True)

    try:
        if _workflow_tables_present(engine) and _current_revision(engine) is None:
            command.stamp(cfg, "head")
            return "stamped"
        command.upgrade(cfg, "head")
        return "upgraded"
    finally:
        engine.dispose()