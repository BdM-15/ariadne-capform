#!/usr/bin/env python
"""Quick smoke for intel_analytics views + index inventory."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "src"))

env_path = ROOT / ".env"
if env_path.exists():
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=False)
    except ImportError:
        pass

import psycopg

from thread.config import get_settings
from thread.intel.sql_expressions import PRIME_AWARDS_VIEW, SUBAWARDS_VIEW

get_settings.cache_clear()
settings = get_settings()
dsn = settings.database_url.replace("+asyncpg", "").replace("postgresql://", "postgres://")

with psycopg.connect(dsn) as conn:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT agency_normalized, obligation_kind, COUNT(*)
            FROM {PRIME_AWARDS_VIEW}
            WHERE parent_award_agency_name = 'DEPT OF DEFENSE'
            GROUP BY 1, 2
            ORDER BY 3 DESC
            LIMIT 3
            """
        )
        print("DOD normalize sample:", cur.fetchall())

        cur.execute(
            f"SELECT COUNT(*) FROM {PRIME_AWARDS_VIEW} WHERE is_deobligation"
        )
        print("deobligation rows:", cur.fetchone()[0])

        cur.execute(
            """
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'intel_usaspending_prime_awards'
              AND indexname LIKE 'idx_intel_prime_%'
            ORDER BY 1
            """
        )
        print("prime indexes:", [r[0] for r in cur.fetchall()])

        cur.execute(
            f"SELECT COUNT(*) FROM {SUBAWARDS_VIEW} WHERE prime_awardee_display != '(Unknown Prime)'"
        )
        print("sub rows with prime name:", cur.fetchone()[0])
        cur.execute(
            f"""
            SELECT set_aside_chart_bucket, COUNT(*)
            FROM {PRIME_AWARDS_VIEW}
            WHERE set_aside_chart_bucket IN ('NO SET ASIDE USED', '(Not Applicable)')
            GROUP BY 1
            """
        )
        print("set_aside chart buckets:", cur.fetchall())