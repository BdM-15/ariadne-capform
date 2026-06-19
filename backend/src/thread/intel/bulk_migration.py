"""Resumable USASpending bulk zip/CSV → PostgreSQL via COPY (no DuckDB)."""

from __future__ import annotations

import csv
import json
import logging
import re
import shutil
import tempfile
import time
import zipfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg

from thread.config import Settings
from thread.intel.bulk_fields import (
    PRIME_KEY_COL,
    PRIME_STAGING_TABLE,
    PRIME_TABLE,
    PRIME_TARGET_FIELDS,
    SUB_TABLE,
    prime_insert_from_staging_sql,
    prime_staging_ddl,
    prime_table_ddl,
    sanitize_sub_column,
)

logger = logging.getLogger(__name__)

DEFAULT_PRIME_ROW_ESTIMATE = 64_206_069
CHUNK_NAME_RE = re.compile(
    r"^(?:prime|sub)_(\d{4}-\d{2}-\d{2})_to_(\d{4}-\d{2}-\d{2})\.(?:zip|csv)$",
    re.IGNORECASE,
)


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
    prime_files_total: int = 0
    prime_files_done: int = 0
    sub_files_total: int = 0
    sub_files_done: int = 0


def _pg_dsn(settings: Settings) -> str:
    return settings.database_url.replace("+asyncpg", "").replace("postgresql://", "postgres://")


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


def bulk_prime_dir(settings: Settings) -> Path:
    return settings.resolve(settings.intel_bulk_prime_dir)


def bulk_sub_dir(settings: Settings) -> Path:
    return settings.resolve(settings.intel_bulk_sub_dir)


def discover_bulk_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    files: list[Path] = []
    for ext in ("*.zip", "*.csv"):
        files.extend(directory.glob(ext))
    return sorted(files, key=lambda p: p.name.lower())


@contextmanager
def open_bulk_csv(path: Path) -> Iterator[Path]:
    """Yield a CSV path — extracts zip to a temp dir when needed."""
    if path.suffix.lower() == ".csv":
        yield path
        return

    tmp = Path(tempfile.mkdtemp(prefix="thread_intel_"))
    try:
        with zipfile.ZipFile(path) as zf:
            zf.extractall(tmp)
        csvs = sorted(tmp.rglob("*.csv"))
        if not csvs:
            raise FileNotFoundError(f"No CSV inside {path}")
        yield csvs[0]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _pg_table_count(cur: psycopg.Cursor, table: str) -> int:
    cur.execute("SELECT to_regclass(%s)", [table])
    if cur.fetchone()[0] is None:
        return 0
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    return int(cur.fetchone()[0])


def _ensure_prime_schema(cur: psycopg.Cursor) -> None:
    cur.execute(prime_table_ddl())
    cur.execute(prime_staging_ddl())


def _truncate_staging(cur: psycopg.Cursor) -> None:
    cur.execute(f"TRUNCATE {PRIME_STAGING_TABLE}")


def _copy_csv_to_table(
    cur: psycopg.Cursor,
    table: str,
    columns: list[str],
    csv_path: Path,
) -> int:
    col_sql = ", ".join(columns)
    with open(csv_path, "rb") as fh:
        with cur.copy(
            f"COPY {table} ({col_sql}) FROM STDIN WITH (FORMAT csv, HEADER true, NULL '')"
        ) as copy:
            copy.write(fh.read())
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    return int(cur.fetchone()[0])


def _read_sub_header(csv_path: Path) -> list[str]:
    with csv_path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
    return [sanitize_sub_column(h) for h in header]


def _ensure_sub_schema(cur: psycopg.Cursor, columns: list[str]) -> None:
    cur.execute("SELECT to_regclass(%s)", [SUB_TABLE])
    exists = cur.fetchone()[0] is not None
    if not exists:
        col_defs = ",\n    ".join(f"{col} TEXT" for col in columns)
        cur.execute(f"CREATE TABLE {SUB_TABLE} (\n    {col_defs}\n)")
        return

    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        """,
        [SUB_TABLE],
    )
    existing = {row[0] for row in cur.fetchall()}
    for col in columns:
        if col not in existing:
            cur.execute(f"ALTER TABLE {SUB_TABLE} ADD COLUMN IF NOT EXISTS {col} TEXT")


def _loaded_chunks(state: dict[str, Any], award_type: str) -> set[str]:
    chunks = state.get("chunks_loaded", {})
    if isinstance(chunks, dict):
        raw = chunks.get(award_type, [])
        if isinstance(raw, list):
            return {str(x) for x in raw}
    legacy = state.get(f"{award_type}_chunks_loaded", [])
    if isinstance(legacy, list):
        return {str(x) for x in legacy}
    return set()


def _record_chunk(
    state: dict[str, Any],
    award_type: str,
    chunk_name: str,
    rows_in_file: int,
    rows_inserted: int,
) -> None:
    chunks = state.setdefault("chunks_loaded", {})
    loaded: set[str] = set(chunks.get(award_type, []))
    loaded.add(chunk_name)
    chunks[award_type] = sorted(loaded)
    if award_type == "prime":
        state["prime_rows_inserted"] = int(state.get("prime_rows_inserted", 0)) + rows_inserted
        state["prime_files_done"] = len(loaded)
    else:
        state["sub_rows_inserted"] = int(state.get("sub_rows_inserted", 0)) + rows_inserted
        state["sub_files_done"] = len(loaded)
    state[f"{award_type}_last_chunk"] = {
        "name": chunk_name,
        "rows_in_file": rows_in_file,
        "rows_inserted": rows_inserted,
        "at": datetime.now(timezone.utc).isoformat(),
    }


def _drop_intel_tables(cur: psycopg.Cursor) -> None:
    for table in (PRIME_TABLE, PRIME_STAGING_TABLE, SUB_TABLE):
        cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE")


def load_prime_file(cur: psycopg.Cursor, archive_path: Path) -> tuple[int, int]:
    """COPY one prime zip/csv into staging, INSERT into main. Returns (rows_in_file, rows_inserted)."""
    _ensure_prime_schema(cur)
    _truncate_staging(cur)
    with open_bulk_csv(archive_path) as csv_path:
        rows_in_file = _copy_csv_to_table(cur, PRIME_STAGING_TABLE, list(PRIME_TARGET_FIELDS), csv_path)
        before = _pg_table_count(cur, PRIME_TABLE)
        cur.execute(prime_insert_from_staging_sql())
        after = _pg_table_count(cur, PRIME_TABLE)
    _truncate_staging(cur)
    return rows_in_file, after - before


def load_sub_file(cur: psycopg.Cursor, archive_path: Path) -> tuple[int, int]:
    with open_bulk_csv(archive_path) as csv_path:
        columns = _read_sub_header(csv_path)
        _ensure_sub_schema(cur, columns)
        before = _pg_table_count(cur, SUB_TABLE)
        _copy_csv_to_table(cur, SUB_TABLE, columns, csv_path)
        after = _pg_table_count(cur, SUB_TABLE)
    inserted = after - before
    return inserted, inserted


def ensure_intel_indexes(settings: Settings) -> None:
    """Create analytics indexes on intel tables (idempotent)."""
    dsn = _pg_dsn(settings)
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
        (
            f"CREATE INDEX IF NOT EXISTS idx_intel_prime_txn_key "
            f"ON {PRIME_TABLE}({PRIME_KEY_COL})"
        ),
        f"CREATE INDEX IF NOT EXISTS idx_intel_sub_prime_name ON {SUB_TABLE}(prime_awardee_name)",
        f"CREATE INDEX IF NOT EXISTS idx_intel_sub_sub_name ON {SUB_TABLE}(subawardee_name)",
    ]
    _append_log(settings, "building analytics indexes (may take 30+ minutes on full dataset)...")
    with psycopg.connect(dsn) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s)", [PRIME_TABLE])
            if cur.fetchone()[0] is None:
                _append_log(settings, "skip indexes — prime table missing")
                return
            for stmt in statements:
                try:
                    _append_log(settings, f"index: {stmt}")
                    cur.execute(stmt)
                except psycopg.Error as exc:
                    if SUB_TABLE in stmt and "does not exist" in str(exc):
                        _append_log(settings, f"skip sub index — table not loaded yet: {exc}")
                        continue
                    raise
    sp = state_path(settings)
    state = _load_state(sp)
    state["indexes_built"] = True
    state["indexes_built_at"] = datetime.now(timezone.utc).isoformat()
    _save_state(sp, state)
    _append_log(settings, "indexes complete")


def _estimate_prime_total(state: dict[str, Any], files_total: int, pg_count: int) -> int:
    files_done = int(state.get("prime_files_done", 0))
    rows_inserted = int(state.get("prime_rows_inserted", 0))
    if files_done > 0 and files_total > files_done:
        avg = rows_inserted / files_done
        return int(pg_count + avg * (files_total - files_done))
    if pg_count > 0:
        return max(pg_count, DEFAULT_PRIME_ROW_ESTIMATE)
    return DEFAULT_PRIME_ROW_ESTIMATE


def get_migration_status(settings: Settings) -> MigrationStatus:
    prime_dir = bulk_prime_dir(settings)
    sub_dir = bulk_sub_dir(settings)
    sp = state_path(settings)
    state = _load_state(sp)

    prime_files = discover_bulk_files(prime_dir)
    sub_files = discover_bulk_files(sub_dir)
    prime_loaded = _loaded_chunks(state, "prime")
    sub_loaded = _loaded_chunks(state, "sub")

    prime_migrated = sub_migrated = 0
    try:
        with psycopg.connect(_pg_dsn(settings)) as conn:
            with conn.cursor() as cur:
                prime_migrated = _pg_table_count(cur, PRIME_TABLE)
                sub_migrated = _pg_table_count(cur, SUB_TABLE)
    except psycopg.Error:
        prime_migrated = int(state.get("prime_rows_inserted", 0))
        sub_migrated = int(state.get("sub_rows_inserted", 0))

    prime_files_done = len(prime_loaded) if prime_loaded else int(state.get("prime_files_done", 0))
    sub_files_done = len(sub_loaded) if sub_loaded else int(state.get("sub_files_done", 0))

    phase = str(state.get("phase", "idle"))
    indexes_built = bool(state.get("indexes_built", False))
    prime_complete = bool(prime_files) and prime_files_done >= len(prime_files)
    sub_complete = bool(sub_files) and sub_files_done >= len(sub_files)
    complete = (
        prime_dir.exists()
        and sub_dir.exists()
        and prime_complete
        and sub_complete
        and indexes_built
    )

    source = f"{prime_dir} + {sub_dir}"
    return MigrationStatus(
        source_path=source,
        source_exists=prime_dir.is_dir() and sub_dir.is_dir(),
        prime_source_total=_estimate_prime_total(state, len(prime_files), prime_migrated),
        prime_migrated=prime_migrated,
        sub_source_total=max(sub_migrated, len(sub_files) * max(sub_migrated // max(sub_files_done, 1), 1)),
        sub_migrated=sub_migrated,
        phase=phase,
        complete=complete,
        indexes_built=indexes_built,
        state_path=str(sp),
        log_path=str(log_path(settings)),
        last_updated=state.get("updated_at"),
        prime_files_total=len(prime_files),
        prime_files_done=prime_files_done,
        sub_files_total=len(sub_files),
        sub_files_done=sub_files_done,
    )


def needs_migration(settings: Settings) -> bool:
    status = get_migration_status(settings)
    if not status.source_exists:
        return False
    return not status.complete


def _migrate_files(
    settings: Settings,
    *,
    files: list[Path],
    award_type: str,
    loader: Callable[[psycopg.Cursor, Path], tuple[int, int]],
    state: dict[str, Any],
    state_file: Path,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> int:
    loaded = _loaded_chunks(state, award_type)
    total_rows = 0
    processed = 0

    with psycopg.connect(_pg_dsn(settings)) as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            for path in files:
                if path.name in loaded:
                    continue
                t0 = time.perf_counter()
                try:
                    rows_in_file, rows_inserted = loader(cur, path)
                    conn.commit()
                except Exception as exc:
                    conn.rollback()
                    msg = f"{award_type} {path.name} failed: {exc}"
                    _append_log(settings, msg)
                    logger.warning(msg)
                    raise

                elapsed = time.perf_counter() - t0
                total_rows += rows_inserted
                processed += 1
                _record_chunk(state, award_type, path.name, rows_in_file, rows_inserted)
                state["phase"] = award_type
                state["updated_at"] = datetime.now(timezone.utc).isoformat()
                _save_state(state_file, state)

                pg_count = _pg_table_count(cur, PRIME_TABLE if award_type == "prime" else SUB_TABLE)
                msg = (
                    f"{award_type} {path.name}: +{rows_inserted:,} rows "
                    f"({rows_in_file:,} in file, {pg_count:,} total) [{elapsed:.1f}s]"
                )
                _append_log(settings, msg)
                logger.info("[intel] %s", msg)
                if on_progress:
                    done = len(_loaded_chunks(state, award_type))
                    on_progress(done, len(files), award_type)

    return total_rows


def run_intel_migration(
    settings: Settings,
    *,
    force: bool = False,
    chunk_size: int = 0,  # noqa: ARG001 — legacy CLI compat, unused for file-based COPY
    skip_subawards: bool = False,
    skip_indexes: bool = False,
    indexes_only: bool = False,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> MigrationResult:
    prime_dir = bulk_prime_dir(settings)
    sub_dir = bulk_sub_dir(settings)
    if not prime_dir.is_dir():
        return MigrationResult(False, f"Prime bulk dir missing: {prime_dir}")

    sp = state_path(settings)
    _append_log(settings, f"=== bulk COPY migration start (force={force}) ===")

    if indexes_only:
        ensure_intel_indexes(settings)
        return MigrationResult(True, "Indexes built", prime_rows=0)

    state = {} if force else _load_state(sp)

    existing_prime = _pg_table_count_from_settings(settings, PRIME_TABLE)
    if not force and existing_prime > 0 and not _loaded_chunks(state, "prime"):
        print(
            f"[intel] WARN: {existing_prime:,} prime rows in PG but no chunk log "
            "(likely old DuckDB transfer). Use --force for a clean bulk reload."
        )

    if force:
        with psycopg.connect(_pg_dsn(settings)) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                _drop_intel_tables(cur)
        state = {"indexes_built": False}
        _save_state(sp, state)
        _append_log(settings, "dropped existing intel tables (force)")

    prime_files = discover_bulk_files(prime_dir)
    if not prime_files:
        return MigrationResult(False, f"No prime zip/csv files in {prime_dir}")

    print(f"[intel] Prime bulk: {len(prime_files)} files in {prime_dir}")
    _append_log(settings, f"prime files: {len(prime_files)} in {prime_dir}")

    prime_rows = _migrate_files(
        settings,
        files=prime_files,
        award_type="prime",
        loader=load_prime_file,
        state=state,
        state_file=sp,
        on_progress=on_progress,
    )

    sub_rows = 0
    if not skip_subawards:
        if not sub_dir.is_dir():
            print(f"[intel] WARN: sub dir missing: {sub_dir}")
        else:
            sub_files = discover_bulk_files(sub_dir)
            if sub_files:
                print(f"[intel] Sub bulk: {len(sub_files)} files in {sub_dir}")
                _append_log(settings, f"sub files: {len(sub_files)} in {sub_dir}")
                sub_rows = _migrate_files(
                    settings,
                    files=sub_files,
                    award_type="sub",
                    loader=load_sub_file,
                    state=state,
                    state_file=sp,
                    on_progress=on_progress,
                )

    state["phase"] = "indexes" if not skip_indexes else "done"
    state["prime_rows"] = _pg_table_count_from_settings(settings, PRIME_TABLE)
    state["sub_rows"] = _pg_table_count_from_settings(settings, SUB_TABLE)
    _save_state(sp, state)

    if not skip_indexes and state["prime_rows"] > 0:
        print("[intel] Building indexes (long step — monitor .thread/intel_migration.log)...")
        ensure_intel_indexes(settings)

    state["completed_at"] = datetime.now(timezone.utc).isoformat()
    state["phase"] = "complete"
    _save_state(sp, state)

    prime_total = state["prime_rows"]
    sub_total = state["sub_rows"]
    msg = f"Migration finished: {prime_total:,} prime, {sub_total:,} sub rows"
    _append_log(settings, msg)
    print(f"[intel] {msg}")
    print(f"[intel] State: {sp}")
    print(f"[intel] Log:   {log_path(settings)}")
    return MigrationResult(True, msg, prime_rows=prime_total, sub_rows=sub_total)


def _pg_table_count_from_settings(settings: Settings, table: str) -> int:
    with psycopg.connect(_pg_dsn(settings)) as conn:
        with conn.cursor() as cur:
            return _pg_table_count(cur, table)


def maybe_auto_migrate(settings: Settings) -> MigrationResult | None:
    if not settings.intel_auto_migrate_on_start:
        return None
    if not needs_migration(settings):
        return None
    return run_intel_migration(settings)