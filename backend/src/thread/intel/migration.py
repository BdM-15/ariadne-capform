"""One-time DuckDB → PostgreSQL intel migration via DuckDB postgres extension."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import duckdb

from thread.config import Settings

logger = logging.getLogger(__name__)

PRIME_TABLE = "intel_usaspending_prime_awards"
SUB_TABLE = "intel_usaspending_subawards"
CACHE_TABLE = "intel_naics_summary_cache"
PRIME_KEY_COL = "contract_transaction_unique_key"
DEFAULT_CHUNK_SIZE = 500_000
MAX_CHUNK_RETRIES = 5
RETRY_BACKOFF_SECONDS = (5, 15, 30, 60, 120)
VERIFY_EVERY_CHUNKS = 10


@dataclass
class MigrationResult:
    migrated: bool
    message: str
    prime_rows: int = 0
    sub_rows: int = 0
    cache_rows: int = 0


@dataclass
class MigrationStatus:
    source_path: str
    source_exists: bool
    prime_source_total: int
    prime_migrated: int
    sub_source_total: int
    sub_migrated: int
    phase: str
    complete: bool
    indexes_built: bool
    state_path: str
    log_path: str
    last_updated: str | None


def _postgres_attach_dsn(settings: Settings) -> str:
    parsed = urlparse(settings.database_url.replace("+asyncpg", ""))
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or settings.thread_postgres_port
    user = parsed.username or "thread"
    password = parsed.password or "thread"
    dbname = (parsed.path or "/thread").lstrip("/")
    return f"dbname={dbname} user={user} password={password} host={host} port={port}"


def state_path(settings: Settings) -> Path:
    return settings.resolve(settings.thread_state_dir) / "intel_migration_state.json"


def log_path(settings: Settings) -> Path:
    return settings.resolve(settings.thread_state_dir) / "intel_migration.log"


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(path)


def _append_log(settings: Settings, message: str) -> None:
    lp = log_path(settings)
    lp.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    with lp.open("a", encoding="utf-8") as fh:
        fh.write(f"[{stamp}] {message}\n")


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
    con.execute(f"CREATE TABLE thread_pg.{dest} AS SELECT * FROM src.{source} LIMIT 0")


def _run_with_retries(
    settings: Settings,
    source: Path,
    operation: Callable[[duckdb.DuckDBPyConnection], Any],
    *,
    label: str,
) -> Any:
    last_err: Exception | None = None
    for attempt, backoff in enumerate(RETRY_BACKOFF_SECONDS, start=1):
        con: duckdb.DuckDBPyConnection | None = None
        try:
            con = _open_bridge(settings, source)
            return operation(con)
        except Exception as exc:
            last_err = exc
            msg = f"{label} failed (attempt {attempt}/{MAX_CHUNK_RETRIES}): {exc}"
            logger.warning(msg)
            _append_log(settings, msg)
            if attempt >= MAX_CHUNK_RETRIES:
                break
            time.sleep(backoff)
        finally:
            if con is not None:
                con.close()
    assert last_err is not None
    raise last_err


def _migrate_prime_chunked(
    settings: Settings,
    source: Path,
    *,
    chunk_size: int,
    state: dict[str, Any],
    state_file: Path,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> int:
    def _prime_batch_count(con: duckdb.DuckDBPyConnection, last_key: str) -> int:
        if last_key:
            sql = f"""
                SELECT COUNT(*) FROM (
                    SELECT 1 FROM src.usaspending_prime_awards
                    WHERE {PRIME_KEY_COL} > ?
                    ORDER BY {PRIME_KEY_COL}
                    LIMIT ?
                )
            """
            return int(con.execute(sql, [last_key, chunk_size]).fetchone()[0])
        sql = f"""
            SELECT COUNT(*) FROM (
                SELECT 1 FROM src.usaspending_prime_awards
                ORDER BY {PRIME_KEY_COL}
                LIMIT ?
            )
        """
        return int(con.execute(sql, [chunk_size]).fetchone()[0])

    def _prime_batch_last_key(con: duckdb.DuckDBPyConnection, last_key: str) -> str | None:
        if last_key:
            sql = f"""
                SELECT MAX({PRIME_KEY_COL}) FROM (
                    SELECT {PRIME_KEY_COL} FROM src.usaspending_prime_awards
                    WHERE {PRIME_KEY_COL} > ?
                    ORDER BY {PRIME_KEY_COL}
                    LIMIT ?
                )
            """
            return con.execute(sql, [last_key, chunk_size]).fetchone()[0]
        sql = f"""
            SELECT MAX({PRIME_KEY_COL}) FROM (
                SELECT {PRIME_KEY_COL} FROM src.usaspending_prime_awards
                ORDER BY {PRIME_KEY_COL}
                LIMIT ?
            )
        """
        return con.execute(sql, [chunk_size]).fetchone()[0]

    def _insert_prime_batch(con: duckdb.DuckDBPyConnection, last_key: str) -> None:
        if last_key:
            con.execute(
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
            con.execute(
                f"""
                INSERT INTO thread_pg.{PRIME_TABLE}
                SELECT * FROM src.usaspending_prime_awards
                ORDER BY {PRIME_KEY_COL}
                LIMIT ?
                """,
                [chunk_size],
            )

    source_total = int(
        _run_with_retries(
            settings,
            source,
            lambda con: con.execute("SELECT COUNT(*) FROM src.usaspending_prime_awards").fetchone()[0],
            label="prime source count",
        )
    )

    migrated = int(state.get("prime_rows_migrated", 0))
    last_key = state.get("prime_last_key", "") or ""
    chunk_num = int(state.get("prime_chunks_completed", 0))

    if migrated == 0:

        def _init_table(con: duckdb.DuckDBPyConnection) -> int:
            if not _table_exists(con, PRIME_TABLE):
                _create_empty_table(con, PRIME_TABLE, "usaspending_prime_awards")
            return _pg_table_count(con, PRIME_TABLE)

        existing = _run_with_retries(settings, source, _init_table, label="prime table init")
        if existing > 0 and not last_key:
            migrated = existing
            last_key = _run_with_retries(
                settings,
                source,
                lambda con: con.execute(
                    f"SELECT MAX({PRIME_KEY_COL}) FROM thread_pg.{PRIME_TABLE}"
                ).fetchone()[0]
                or "",
                label="prime resume key",
            )

    if migrated >= source_total and source_total > 0:
        return migrated

    state["phase"] = "prime"
    _save_state(state_file, state)

    while migrated < source_total:
        chunk_num += 1

        def _one_chunk(con: duckdb.DuckDBPyConnection) -> tuple[int, str | None]:
            batch_size = _prime_batch_count(con, last_key)
            if batch_size == 0:
                return 0, last_key
            _insert_prime_batch(con, last_key)
            new_last = _prime_batch_last_key(con, last_key)
            return batch_size, new_last

        batch_size, new_last = _run_with_retries(
            settings, source, _one_chunk, label=f"prime chunk {chunk_num}"
        )
        if batch_size == 0:
            break

        migrated += batch_size
        if new_last:
            last_key = str(new_last)

        state.update(
            {
                "prime_last_key": last_key,
                "prime_rows_migrated": migrated,
                "prime_source_total": source_total,
                "prime_chunks_completed": chunk_num,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "phase": "prime",
            }
        )
        _save_state(state_file, state)

        if chunk_num % VERIFY_EVERY_CHUNKS == 0:

            def _verify(con: duckdb.DuckDBPyConnection) -> int:
                return _pg_table_count(con, PRIME_TABLE)

            pg_count = _run_with_retries(settings, source, _verify, label="prime verify count")
            drift = abs(pg_count - migrated)
            if drift > chunk_size:
                msg = (
                    f"prime count drift detected (tracked={migrated:,}, pg={pg_count:,}) "
                    f"— reconciling to PostgreSQL count"
                )
                _append_log(settings, msg)
                migrated = pg_count
                last_key = _run_with_retries(
                    settings,
                    source,
                    lambda con: con.execute(
                        f"SELECT MAX({PRIME_KEY_COL}) FROM thread_pg.{PRIME_TABLE}"
                    ).fetchone()[0]
                    or last_key,
                    label="prime reconcile key",
                )
                state["prime_rows_migrated"] = migrated
                state["prime_last_key"] = last_key
                _save_state(state_file, state)

        pct = 100 * migrated / max(source_total, 1)
        msg = f"prime chunk {chunk_num}: {migrated:,} / {source_total:,} ({pct:.2f}%)"
        _append_log(settings, msg)
        if on_progress:
            on_progress(migrated, source_total, "prime")
        logger.info("[intel] %s", msg)

    return migrated


def _migrate_subawards_chunked(
    settings: Settings,
    source: Path,
    *,
    chunk_size: int,
    state: dict[str, Any],
    state_file: Path,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> int:
    source_total = int(
        _run_with_retries(
            settings,
            source,
            lambda con: con.execute("SELECT COUNT(*) FROM src.usaspending_subawards").fetchone()[0],
            label="sub source count",
        )
    )
    if source_total == 0:
        return 0

    migrated = int(state.get("sub_rows_migrated", 0))
    offset = int(state.get("sub_offset", migrated))
    chunk_num = int(state.get("sub_chunks_completed", 0))

    if migrated == 0:

        def _init_sub(con: duckdb.DuckDBPyConnection) -> int:
            if not _table_exists(con, SUB_TABLE):
                _create_empty_table(con, SUB_TABLE, "usaspending_subawards")
            return _pg_table_count(con, SUB_TABLE)

        existing = _run_with_retries(settings, source, _init_sub, label="sub table init")
        if existing > 0:
            migrated = existing
            offset = existing

    if migrated >= source_total:
        return migrated

    state["phase"] = "subawards"
    _save_state(state_file, state)

    while migrated < source_total:
        chunk_num += 1

        def _one_chunk(con: duckdb.DuckDBPyConnection) -> int:
            batch_size = int(
                con.execute(
                    """
                    SELECT COUNT(*) FROM (
                        SELECT 1 FROM src.usaspending_subawards
                        LIMIT ? OFFSET ?
                    )
                    """,
                    [chunk_size, offset],
                ).fetchone()[0]
            )
            if batch_size == 0:
                return 0
            con.execute(
                f"""
                INSERT INTO thread_pg.{SUB_TABLE}
                SELECT * FROM src.usaspending_subawards
                LIMIT ? OFFSET ?
                """,
                [chunk_size, offset],
            )
            return batch_size

        inserted = _run_with_retries(
            settings, source, _one_chunk, label=f"sub chunk {chunk_num}"
        )
        if inserted <= 0:
            break

        migrated += inserted
        offset += inserted
        state.update(
            {
                "sub_offset": offset,
                "sub_rows_migrated": migrated,
                "sub_source_total": source_total,
                "sub_chunks_completed": chunk_num,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "phase": "subawards",
            }
        )
        _save_state(state_file, state)

        pct = 100 * migrated / max(source_total, 1)
        msg = f"sub chunk {chunk_num}: {migrated:,} / {source_total:,} ({pct:.2f}%)"
        _append_log(settings, msg)
        if on_progress:
            on_progress(migrated, source_total, "sub")
        logger.info("[intel] %s", msg)

    return migrated


def _migrate_naics_cache(settings: Settings, source: Path) -> int:
    def _cache(con: duckdb.DuckDBPyConnection) -> int:
        exists = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = 'src' AND table_name = 'naics_summary_cache'"
        ).fetchone()[0]
        if not exists:
            return 0
        con.execute(f"DROP TABLE IF EXISTS thread_pg.{CACHE_TABLE}")
        con.execute(
            f"CREATE TABLE thread_pg.{CACHE_TABLE} AS SELECT * FROM src.naics_summary_cache"
        )
        return int(con.execute(f"SELECT COUNT(*) FROM thread_pg.{CACHE_TABLE}").fetchone()[0])

    return int(_run_with_retries(settings, source, _cache, label="naics cache"))


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
    _append_log(settings, "building analytics indexes (may take 30+ minutes on full dataset)...")
    with psycopg.connect(dsn) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            for stmt in statements:
                _append_log(settings, f"index: {stmt}")
                cur.execute(stmt)
    state = _load_state(state_path(settings))
    state["indexes_built"] = True
    state["indexes_built_at"] = datetime.now(timezone.utc).isoformat()
    _save_state(state_path(settings), state)
    _append_log(settings, "indexes complete")


def get_migration_status(settings: Settings) -> MigrationStatus:
    source = settings.resolve(settings.intel_migration_source)
    sp = state_path(settings)
    state = _load_state(sp)
    prime_source = prime_migrated = sub_source = sub_migrated = 0
    if source.exists():
        try:
            con = _open_bridge(settings, source)
            prime_source = int(
                con.execute("SELECT COUNT(*) FROM src.usaspending_prime_awards").fetchone()[0]
            )
            sub_source = int(
                con.execute("SELECT COUNT(*) FROM src.usaspending_subawards").fetchone()[0]
            )
            prime_migrated = _pg_table_count(con, PRIME_TABLE)
            sub_migrated = _pg_table_count(con, SUB_TABLE)
            con.close()
        except Exception:
            prime_migrated = int(state.get("prime_rows_migrated", 0))
            sub_migrated = int(state.get("sub_rows_migrated", 0))
            prime_source = int(state.get("prime_source_total", 0))
            sub_source = int(state.get("sub_source_total", 0))
    else:
        prime_migrated = int(state.get("prime_rows_migrated", 0))
        sub_migrated = int(state.get("sub_rows_migrated", 0))

    phase = str(state.get("phase", "idle"))
    indexes_built = bool(state.get("indexes_built", False))
    complete = (
        source.exists()
        and prime_migrated >= prime_source > 0
        and sub_migrated >= sub_source
        and indexes_built
    )
    return MigrationStatus(
        source_path=str(source),
        source_exists=source.exists(),
        prime_source_total=prime_source,
        prime_migrated=prime_migrated,
        sub_source_total=sub_source,
        sub_migrated=sub_migrated,
        phase=phase,
        complete=complete,
        indexes_built=indexes_built,
        state_path=str(sp),
        log_path=str(log_path(settings)),
        last_updated=state.get("updated_at"),
    )


def needs_migration(settings: Settings) -> bool:
    status = get_migration_status(settings)
    if not status.source_exists:
        return False
    return not status.complete and status.prime_migrated < status.prime_source_total


def run_intel_migration(
    settings: Settings,
    *,
    force: bool = False,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    skip_subawards: bool = False,
    skip_indexes: bool = False,
    indexes_only: bool = False,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> MigrationResult:
    source = settings.resolve(settings.intel_migration_source)
    if not source.exists():
        return MigrationResult(False, f"Migration source missing: {source}")

    sp = state_path(settings)
    _append_log(settings, f"=== migration start (chunk_size={chunk_size:,}, force={force}) ===")

    if indexes_only:
        ensure_intel_indexes(settings)
        return MigrationResult(True, "Indexes built", prime_rows=0)

    state = {} if force else _load_state(sp)

    if force:

        def _drop(con: duckdb.DuckDBPyConnection) -> None:
            for table in (PRIME_TABLE, SUB_TABLE, CACHE_TABLE):
                try:
                    con.execute(f"DROP TABLE IF EXISTS thread_pg.{table}")
                except duckdb.CatalogException:
                    pass

        _run_with_retries(settings, source, _drop, label="drop intel tables")
        state = {}
        state["indexes_built"] = False
        _save_state(sp, state)
        _append_log(settings, "dropped existing intel tables (force)")

    prime_total = int(
        _run_with_retries(
            settings,
            source,
            lambda con: con.execute("SELECT COUNT(*) FROM src.usaspending_prime_awards").fetchone()[0],
            label="prime total",
        )
    )
    prime_before = int(state.get("prime_rows_migrated", 0))

    if prime_before < prime_total:
        if prime_before > 0:
            print(f"[intel] Resuming prime at {prime_before:,} / {prime_total:,}")
            _append_log(settings, f"resuming prime at {prime_before:,}/{prime_total:,}")
        else:
            print(f"[intel] Prime migration: {prime_total:,} rows, chunk={chunk_size:,}")
            _append_log(settings, f"starting prime migration ({prime_total:,} rows)")
        prime_rows = _migrate_prime_chunked(
            settings,
            source,
            chunk_size=chunk_size,
            state=state,
            state_file=sp,
            on_progress=on_progress,
        )
    else:
        prime_rows = prime_before
        print(f"[intel] Prime complete ({prime_rows:,} rows)")

    sub_rows = 0
    if not skip_subawards:
        sub_total = int(
            _run_with_retries(
                settings,
                source,
                lambda con: con.execute("SELECT COUNT(*) FROM src.usaspending_subawards").fetchone()[0],
                label="sub total",
            )
        )
        sub_before = int(state.get("sub_rows_migrated", 0))
        if sub_before < sub_total:
            if sub_before > 0:
                print(f"[intel] Resuming subawards at {sub_before:,} / {sub_total:,}")
            else:
                print(f"[intel] Subaward migration: {sub_total:,} rows")
            sub_rows = _migrate_subawards_chunked(
                settings,
                source,
                chunk_size=chunk_size,
                state=state,
                state_file=sp,
                on_progress=on_progress,
            )
        else:
            sub_rows = sub_before

    cache_rows = _migrate_naics_cache(settings, source)
    state["phase"] = "indexes" if not skip_indexes else "done"
    state["prime_rows"] = prime_rows
    state["sub_rows"] = sub_rows
    state["cache_rows"] = cache_rows
    _save_state(sp, state)

    if not skip_indexes and prime_rows >= prime_total:
        print("[intel] Building indexes (separate long step — safe to monitor in log)...")
        ensure_intel_indexes(settings)

    state["completed_at"] = datetime.now(timezone.utc).isoformat()
    state["phase"] = "complete"
    _save_state(sp, state)

    msg = (
        f"Migration finished: {prime_rows:,} prime, {sub_rows:,} sub, "
        f"{cache_rows:,} NAICS cache rows"
    )
    _append_log(settings, msg)
    print(f"[intel] {msg}")
    print(f"[intel] State: {sp}")
    print(f"[intel] Log:   {log_path(settings)}")
    return MigrationResult(True, msg, prime_rows=prime_rows, sub_rows=sub_rows, cache_rows=cache_rows)


def maybe_auto_migrate(settings: Settings) -> MigrationResult | None:
    """Deprecated for long runs — use scripts/run-intel-migration.ps1 instead."""
    if not settings.intel_auto_migrate_on_start:
        return None
    if not needs_migration(settings):
        return None
    return run_intel_migration(settings)