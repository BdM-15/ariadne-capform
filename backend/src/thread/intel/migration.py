"""One-time DuckDB → PostgreSQL intel migration via DuckDB postgres extension."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import duckdb

from thread.config import Settings

logger = logging.getLogger(__name__)

PRIME_TABLE = "intel_usaspending_prime_awards"
SUB_TABLE = "intel_usaspending_subawards"
CACHE_TABLE = "intel_naics_summary_cache"
PRIME_KEY_COL = "contract_transaction_unique_key"
DEFAULT_CHUNK_SIZE = 250_000


@dataclass
class MigrationResult:
    migrated: bool
    message: str
    prime_rows: int = 0
    sub_rows: int = 0
    cache_rows: int = 0


def _postgres_attach_dsn(settings: Settings) -> str:
    parsed = urlparse(settings.database_url.replace("+asyncpg", ""))
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or settings.thread_postgres_port
    user = parsed.username or "thread"
    password = parsed.password or "thread"
    dbname = (parsed.path or "/thread").lstrip("/")
    return f"dbname={dbname} user={user} password={password} host={host} port={port}"


def _state_path(settings: Settings) -> Path:
    return settings.resolve(settings.thread_state_dir) / "intel_migration_state.json"


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _open_bridge(settings: Settings, source: Path) -> duckdb.DuckDBPyConnection:
    if not source.exists():
        raise FileNotFoundError(f"Intel migration source not found: {source}")
    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{source.as_posix()}' AS src (READ_ONLY);")
    con.execute(f"ATTACH '{_postgres_attach_dsn(settings)}' AS thread_pg (TYPE postgres);")
    return con


def _pg_table_count(con: duckdb.DuckDBPyConnection, table: str) -> int:
    try:
        return int(con.execute(f"SELECT COUNT(*) FROM thread_pg.{table}").fetchone()[0])
    except duckdb.CatalogException:
        return 0


def _table_exists(con: duckdb.DuckDBPyConnection, table: str) -> bool:
    try:
        con.execute(f"SELECT 1 FROM thread_pg.{table} LIMIT 1")
        return True
    except duckdb.CatalogException:
        return False


def _create_empty_table(con: duckdb.DuckDBPyConnection, dest: str, source: str) -> None:
    con.execute(f"DROP TABLE IF EXISTS thread_pg.{dest}")
    con.execute(
        f"CREATE TABLE thread_pg.{dest} AS SELECT * FROM src.{source} LIMIT 0"
    )


def _migrate_prime_chunked(
    con: duckdb.DuckDBPyConnection,
    *,
    chunk_size: int,
    state: dict[str, Any],
    on_progress: Callable[[int, int, str], None] | None = None,
) -> int:
    source_total = int(
        con.execute("SELECT COUNT(*) FROM src.usaspending_prime_awards").fetchone()[0]
    )
    if not _table_exists(con, PRIME_TABLE):
        _create_empty_table(con, PRIME_TABLE, "usaspending_prime_awards")

    migrated = _pg_table_count(con, PRIME_TABLE)
    last_key = state.get("prime_last_key", "")

    if migrated >= source_total and source_total > 0:
        return migrated

    while migrated < source_total:
        if last_key:
            batch = con.execute(
                f"""
                INSERT INTO thread_pg.{PRIME_TABLE}
                SELECT * FROM src.usaspending_prime_awards
                WHERE {PRIME_KEY_COL} > ?
                ORDER BY {PRIME_KEY_COL}
                LIMIT ?
                """,
                [last_key, chunk_size],
            )
        else:
            batch = con.execute(
                f"""
                INSERT INTO thread_pg.{PRIME_TABLE}
                SELECT * FROM src.usaspending_prime_awards
                ORDER BY {PRIME_KEY_COL}
                LIMIT ?
                """,
                [chunk_size],
            )
        inserted = batch.fetchone()
        _ = inserted  # INSERT returns no useful row count in duckdb postgres

        new_count = _pg_table_count(con, PRIME_TABLE)
        if new_count <= migrated:
            break
        migrated = new_count

        last_key = con.execute(
            f"SELECT MAX({PRIME_KEY_COL}) FROM thread_pg.{PRIME_TABLE}"
        ).fetchone()[0]
        state["prime_last_key"] = last_key
        state["prime_rows_migrated"] = migrated
        state["updated_at"] = datetime.now(timezone.utc).isoformat()

        if on_progress:
            on_progress(migrated, source_total, "prime")
        logger.info("[intel] prime migration %s / %s", f"{migrated:,}", f"{source_total:,}")

    return migrated


def _migrate_subawards_chunked(
    con: duckdb.DuckDBPyConnection,
    *,
    chunk_size: int,
    state: dict[str, Any],
    on_progress: Callable[[int, int, str], None] | None = None,
) -> int:
    source_total = int(
        con.execute("SELECT COUNT(*) FROM src.usaspending_subawards").fetchone()[0]
    )
    if source_total == 0:
        return 0

    if not _table_exists(con, SUB_TABLE):
        _create_empty_table(con, SUB_TABLE, "usaspending_subawards")

    migrated = _pg_table_count(con, SUB_TABLE)
    offset = int(state.get("sub_offset", 0))

    if migrated >= source_total:
        return migrated

    while migrated < source_total:
        con.execute(
            f"""
            INSERT INTO thread_pg.{SUB_TABLE}
            SELECT * FROM src.usaspending_subawards
            LIMIT ? OFFSET ?
            """,
            [chunk_size, offset],
        )
        new_count = _pg_table_count(con, SUB_TABLE)
        if new_count <= migrated:
            break
        migrated = new_count
        offset = migrated
        state["sub_offset"] = offset
        state["sub_rows_migrated"] = migrated
        if on_progress:
            on_progress(migrated, source_total, "sub")
        logger.info("[intel] subaward migration %s / %s", f"{migrated:,}", f"{source_total:,}")

    return migrated


def _migrate_naics_cache(con: duckdb.DuckDBPyConnection) -> int:
    exists = con.execute(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = 'src' AND table_name = 'naics_summary_cache'"
    ).fetchone()[0]
    if not exists:
        return 0
    con.execute(f"DROP TABLE IF EXISTS thread_pg.{CACHE_TABLE}")
    con.execute(
        f"CREATE TABLE thread_pg.{CACHE_TABLE} AS "
        f"SELECT * FROM src.naics_summary_cache"
    )
    return int(con.execute(f"SELECT COUNT(*) FROM thread_pg.{CACHE_TABLE}").fetchone()[0])


def ensure_intel_indexes(settings: Settings) -> None:
    """Create analytics indexes on intel tables (idempotent)."""
    import psycopg

    dsn = settings.database_url.replace("+asyncpg", "").replace("postgresql://", "postgres://")
    statements = [
        f"CREATE INDEX IF NOT EXISTS idx_intel_prime_naics ON {PRIME_TABLE}(naics_code)",
        (
            f"CREATE INDEX IF NOT EXISTS idx_intel_prime_naics_pop_end "
            f"ON {PRIME_TABLE}(naics_code, period_of_performance_current_end_date)"
        ),
        (
            f"CREATE INDEX IF NOT EXISTS idx_intel_prime_award_key "
            f"ON {PRIME_TABLE}(contract_award_unique_key)"
        ),
    ]
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            for stmt in statements:
                cur.execute(stmt)
        conn.commit()


def needs_migration(settings: Settings) -> bool:
    source = settings.resolve(settings.intel_migration_source)
    if not source.exists():
        return False
    try:
        con = _open_bridge(settings, source)
        migrated = _pg_table_count(con, PRIME_TABLE)
        source_total = int(
            con.execute("SELECT COUNT(*) FROM src.usaspending_prime_awards").fetchone()[0]
        )
        con.close()
        return migrated < source_total
    except Exception:
        return False


def run_intel_migration(
    settings: Settings,
    *,
    force: bool = False,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    skip_subawards: bool = False,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> MigrationResult:
    source = settings.resolve(settings.intel_migration_source)
    if not source.exists():
        return MigrationResult(False, f"Migration source missing: {source}")

    state_path = _state_path(settings)
    state = {} if force else _load_state(state_path)

    con = _open_bridge(settings, source)
    try:
        if force:
            for table in (PRIME_TABLE, SUB_TABLE, CACHE_TABLE):
                try:
                    con.execute(f"DROP TABLE IF EXISTS thread_pg.{table}")
                except duckdb.CatalogException:
                    pass
            state = {}

        prime_before = _pg_table_count(con, PRIME_TABLE)
        prime_total = int(
            con.execute("SELECT COUNT(*) FROM src.usaspending_prime_awards").fetchone()[0]
        )

        if prime_before < prime_total:
            if prime_before > 0:
                print(f"[intel] Resuming prime migration at {prime_before:,} / {prime_total:,} rows...")
            else:
                print(f"[intel] Migrating {prime_total:,} prime awards (chunk={chunk_size:,})...")
            prime_rows = _migrate_prime_chunked(
                con, chunk_size=chunk_size, state=state, on_progress=on_progress
            )
        else:
            prime_rows = prime_before
            print(f"[intel] Prime awards already present ({prime_rows:,} rows)")

        sub_rows = 0
        if not skip_subawards:
            sub_total = int(
                con.execute("SELECT COUNT(*) FROM src.usaspending_subawards").fetchone()[0]
            )
            sub_before = _pg_table_count(con, SUB_TABLE)
            if sub_before < sub_total:
                if sub_before > 0:
                    print(f"[intel] Resuming subaward migration at {sub_before:,} / {sub_total:,}...")
                else:
                    print(f"[intel] Migrating {sub_total:,} subawards...")
                sub_rows = _migrate_subawards_chunked(
                    con, chunk_size=chunk_size, state=state, on_progress=on_progress
                )
            else:
                sub_rows = sub_before

        cache_rows = _migrate_naics_cache(con)

        state["completed_at"] = datetime.now(timezone.utc).isoformat()
        state["prime_rows"] = prime_rows
        state["sub_rows"] = sub_rows
        _save_state(state_path, state)

        print("[intel] Creating analytics indexes (may take several minutes)...")
        ensure_intel_indexes(settings)

        msg = (
            f"Migrated intel: {prime_rows:,} prime awards, {sub_rows:,} subawards, "
            f"{cache_rows:,} NAICS cache rows"
        )
        print(f"[intel] {msg}")
        return MigrationResult(True, msg, prime_rows=prime_rows, sub_rows=sub_rows, cache_rows=cache_rows)
    finally:
        con.close()


def maybe_auto_migrate(settings: Settings) -> MigrationResult | None:
    if not settings.intel_auto_migrate_on_start:
        return None
    if not needs_migration(settings):
        return None
    return run_intel_migration(settings)