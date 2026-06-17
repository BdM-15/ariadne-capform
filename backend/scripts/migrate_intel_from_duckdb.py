#!/usr/bin/env python
"""One-time migration: capture-insights DuckDB → Thread PostgreSQL intel tables.

Usage (from repo root):
    .venv\\Scripts\\python.exe backend/scripts/migrate_intel_from_duckdb.py
    .venv\\Scripts\\python.exe backend/scripts/migrate_intel_from_duckdb.py --force
    .venv\\Scripts\\python.exe backend/scripts/migrate_intel_from_duckdb.py --chunk-size 500000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from thread.config import get_settings
from thread.intel.migration import run_intel_migration


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate USAspending intel DuckDB → PostgreSQL")
    parser.add_argument("--force", action="store_true", help="Drop and re-migrate intel tables")
    parser.add_argument("--chunk-size", type=int, default=250_000, help="Rows per batch")
    parser.add_argument("--skip-subawards", action="store_true", help="Migrate prime awards only")
    args = parser.parse_args()

    get_settings.cache_clear()
    settings = get_settings()
    source = settings.resolve(settings.intel_migration_source)
    print(f"[intel] Source: {source}")
    print(f"[intel] Target: {settings.database_url}")

    result = run_intel_migration(
        settings,
        force=args.force,
        chunk_size=args.chunk_size,
        skip_subawards=args.skip_subawards,
        on_progress=lambda done, total, kind: print(
            f"[intel] {kind}: {done:,} / {total:,} ({100 * done / max(total, 1):.1f}%)"
        ),
    )
    if not result.migrated and "missing" in result.message:
        print(f"[intel] ERROR: {result.message}")
        return 1
    print(f"[intel] Done: {result.message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())