#!/usr/bin/env python
"""Resumable migration: capture-insights DuckDB → Thread PostgreSQL intel tables.

Designed for long background runs (64M+ rows). Prefer scripts/run-intel-migration.ps1
in a separate terminal window.

Usage (from repo root):
    .venv\\Scripts\\python.exe backend/scripts/migrate_intel_from_duckdb.py --status
    .venv\\Scripts\\python.exe backend/scripts/migrate_intel_from_duckdb.py
    .venv\\Scripts\\python.exe backend/scripts/migrate_intel_from_duckdb.py --chunk-size 500000
    .venv\\Scripts\\python.exe backend/scripts/migrate_intel_from_duckdb.py --indexes-only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "src"))


def _load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=False)
    except ImportError:
        pass


def main() -> int:
    _load_env()

    parser = argparse.ArgumentParser(
        description="Migrate USAspending intel DuckDB → PostgreSQL (resumable)"
    )
    parser.add_argument("--status", action="store_true", help="Print progress and exit")
    parser.add_argument("--force", action="store_true", help="Drop intel tables and restart")
    parser.add_argument("--chunk-size", type=int, default=500_000, help="Rows per batch (default 500k)")
    parser.add_argument("--skip-subawards", action="store_true", help="Prime awards only")
    parser.add_argument(
        "--skip-indexes",
        action="store_true",
        help="Skip index build at end (run --indexes-only later)",
    )
    parser.add_argument(
        "--indexes-only",
        action="store_true",
        help="Only build analytics indexes on existing intel tables",
    )
    args = parser.parse_args()

    from thread.config import get_settings
    from thread.intel.migration import get_migration_status, run_intel_migration

    get_settings.cache_clear()
    settings = get_settings()
    source = settings.resolve(settings.intel_migration_source)

    if args.status:
        status = get_migration_status(settings)
        print("Intel migration status")
        print(f"  Source:     {status.source_path} (exists={status.source_exists})")
        print(f"  Prime:      {status.prime_migrated:,} / {status.prime_source_total:,}")
        print(f"  Subawards:  {status.sub_migrated:,} / {status.sub_source_total:,}")
        print(f"  Phase:      {status.phase}")
        print(f"  Indexes:    {status.indexes_built}")
        print(f"  Complete:   {status.complete}")
        print(f"  State file: {status.state_path}")
        print(f"  Log file:   {status.log_path}")
        if status.last_updated:
            print(f"  Updated:    {status.last_updated}")
        return 0

    print(f"[intel] Source: {source}")
    print(f"[intel] Target: {settings.database_url}")
    print(f"[intel] Log:    {settings.resolve(settings.thread_state_dir) / 'intel_migration.log'}")
    print("[intel] Safe to close this window only after 'Migration finished' — re-run to resume.")

    result = run_intel_migration(
        settings,
        force=args.force,
        chunk_size=args.chunk_size,
        skip_subawards=args.skip_subawards,
        skip_indexes=args.skip_indexes,
        indexes_only=args.indexes_only,
        on_progress=lambda done, total, kind: print(
            f"[intel] {kind}: {done:,} / {total:,} ({100 * done / max(total, 1):.2f}%)"
        ),
    )
    if not result.migrated and "missing" in result.message:
        print(f"[intel] ERROR: {result.message}")
        return 1
    print(f"[intel] Done: {result.message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())