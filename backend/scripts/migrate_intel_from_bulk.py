#!/usr/bin/env python
"""Resumable migration: USASpending bulk zip/CSV → Thread PostgreSQL via COPY.

Loads capture-insights 10year_bulk prime/sub directories directly into PG.
Prefer scripts/run-intel-migration.ps1 in a separate terminal.

Usage (from repo root):
    .venv\\Scripts\\python.exe backend/scripts/migrate_intel_from_bulk.py --status
    .venv\\Scripts\\python.exe backend/scripts/migrate_intel_from_bulk.py
    .venv\\Scripts\\python.exe backend/scripts/migrate_intel_from_bulk.py --force
    .venv\\Scripts\\python.exe backend/scripts/migrate_intel_from_bulk.py --skip-subawards
    .venv\\Scripts\\python.exe backend/scripts/migrate_intel_from_bulk.py --indexes-only
    .venv\\Scripts\\python.exe backend/scripts/migrate_intel_from_bulk.py --views-only
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
        description="Migrate USASpending bulk zip/CSV → PostgreSQL (COPY, resumable)"
    )
    parser.add_argument("--status", action="store_true", help="Print progress and exit")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Drop intel tables, clear chunk log, reload from scratch",
    )
    parser.add_argument("--skip-subawards", action="store_true", help="Prime awards only")
    parser.add_argument(
        "--skip-indexes",
        action="store_true",
        help="Skip index build at end (run --indexes-only later)",
    )
    parser.add_argument(
        "--indexes-only",
        action="store_true",
        help="Build analytics indexes + intel_analytics views (no data reload)",
    )
    parser.add_argument(
        "--views-only",
        action="store_true",
        help="Only (re)create intel_analytics SQL views",
    )
    parser.add_argument(
        "--with-dedup-matview",
        action="store_true",
        help="Also build dedup materialized view (slow on full 64M load)",
    )
    args = parser.parse_args()

    from thread.config import get_settings
    from thread.intel.bulk_migration import (
        bulk_prime_dir,
        bulk_sub_dir,
        get_migration_status,
        run_intel_migration,
    )

    get_settings.cache_clear()
    settings = get_settings()
    prime_dir = bulk_prime_dir(settings)
    sub_dir = bulk_sub_dir(settings)

    if args.status:
        status = get_migration_status(settings)
        print("Intel bulk migration status")
        print(f"  Prime dir:  {prime_dir} (exists={prime_dir.is_dir()})")
        print(f"  Sub dir:    {sub_dir} (exists={sub_dir.is_dir()})")
        print(
            f"  Prime:      {status.prime_migrated:,} rows · "
            f"{status.prime_files_done}/{status.prime_files_total} files"
        )
        print(
            f"  Subawards:  {status.sub_migrated:,} rows · "
            f"{status.sub_files_done}/{status.sub_files_total} files"
        )
        print(f"  Phase:      {status.phase}")
        print(f"  Indexes:    {status.indexes_built}")
        print(f"  Views:      {status.views_built}")
        print(f"  Complete:   {status.complete}")
        print(f"  State file: {status.state_path}")
        print(f"  Log file:   {status.log_path}")
        if status.last_updated:
            print(f"  Updated:    {status.last_updated}")
        return 0

    print(f"[intel] Prime bulk: {prime_dir}")
    print(f"[intel] Sub bulk:   {sub_dir}")
    print(f"[intel] Target:     {settings.database_url}")
    print(f"[intel] Log:        {settings.resolve(settings.thread_state_dir) / 'intel_migration.log'}")
    print("[intel] Safe to interrupt — re-run to resume from last completed zip.")

    result = run_intel_migration(
        settings,
        force=args.force,
        skip_subawards=args.skip_subawards,
        skip_indexes=args.skip_indexes,
        indexes_only=args.indexes_only,
        views_only=args.views_only,
        with_dedup_matview=args.with_dedup_matview,
        on_progress=lambda done, total, kind: print(
            f"[intel] {kind}: {done:,} / {total:,} files ({100 * done / max(total, 1):.1f}%)"
        ),
    )
    if not result.migrated and "missing" in result.message:
        print(f"[intel] ERROR: {result.message}")
        return 1
    print(f"[intel] Done: {result.message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())