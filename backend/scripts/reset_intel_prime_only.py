#!/usr/bin/env python
"""Drop prime intel tables + clear prime chunk log. Subawards untouched."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "src"))

_env = ROOT / ".env"
if _env.exists():
    try:
        from dotenv import load_dotenv

        load_dotenv(_env, override=False)
    except ImportError:
        pass


def main() -> int:
    import psycopg

    from thread.config import Settings
    from thread.intel.bulk_fields import PRIME_STAGING_TABLE, PRIME_TABLE, SUB_TABLE
    from thread.intel.bulk_migration import _pg_table_count, log_path, state_path

    settings = Settings()
    sp = state_path(settings)
    log_file = log_path(settings)

    state = {}
    if sp.exists():
        state = json.loads(sp.read_text(encoding="utf-8"))

    sub_chunks = (state.get("chunks_loaded") or {}).get("sub", [])
    sub_done = len(sub_chunks) if isinstance(sub_chunks, list) else int(state.get("sub_files_done", 0))

    dsn = settings.database_url.replace("+asyncpg", "").replace("postgresql://", "postgres://")
    with psycopg.connect(dsn) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            prime_before = _pg_table_count(cur, PRIME_TABLE)
            sub_before = _pg_table_count(cur, SUB_TABLE)
            cur.execute(f"DROP TABLE IF EXISTS {PRIME_TABLE} CASCADE")
            cur.execute(f"DROP TABLE IF EXISTS {PRIME_STAGING_TABLE} CASCADE")
            sub_after = _pg_table_count(cur, SUB_TABLE)

    ts = datetime.now(timezone.utc).isoformat()
    new_state = {
        "phase": "idle",
        "indexes_built": False,
        "chunks_loaded": {
            "prime": [],
            "sub": sub_chunks if isinstance(sub_chunks, list) else [],
        },
        "prime_files_done": 0,
        "sub_files_done": sub_done,
        "prime_rows_inserted": 0,
        "sub_rows_inserted": int(state.get("sub_rows_inserted", 0)),
        "prime_reset_at": ts,
        "prime_reset_reason": "prime-only reload — pytest wiped production prime table",
        "updated_at": ts,
    }
    if state.get("sub_last_chunk"):
        new_state["sub_last_chunk"] = state["sub_last_chunk"]
    if state.get("sub_rows"):
        new_state["sub_rows"] = state["sub_rows"]

    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(new_state, indent=2), encoding="utf-8")

    log_line = (
        f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}] "
        f"RESET prime only: dropped {PRIME_TABLE} ({prime_before:,} rows); "
        f"sub preserved ({sub_before:,} -> {sub_after:,} rows); "
        f"cleared {len((state.get('chunks_loaded') or {}).get('prime', []))} prime chunk entries"
    )
    with log_file.open("a", encoding="utf-8") as fh:
        fh.write(log_line + "\n")

    print("Prime reset complete")
    print(f"  Prime rows before: {prime_before:,} (table dropped)")
    print(f"  Sub rows kept:     {sub_after:,}")
    print(f"  Sub files in log:  {sub_done}")
    print(f"  State:             {sp}")
    print()
    print("Next (new PowerShell window, repo root):")
    print("  .\\scripts\\run-intel-migration.ps1 -SkipSubawards")
    print()
    print("Monitor:")
    print("  Get-Content .thread\\intel_migration.log -Wait")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())