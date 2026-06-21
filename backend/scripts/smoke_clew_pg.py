#!/usr/bin/env python
"""Clew analyze smoke — direct PG (bypasses HTTP when server is busy)."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=False)

from thread.clew.analyze import run_facet_analysis
from thread.config import get_settings
from thread.db.session import SessionLocal
from thread.intel.facet_query import query_from_dict
from thread.intel.pg_queries import get_intel_stats


async def main() -> int:
    settings = get_settings()
    fails = 0

    async with SessionLocal() as session:
        stats = await get_intel_stats(session)
        print(
            f"PG intel: {stats.get('prime_award_count', 0):,} prime, "
            f"{stats.get('subaward_count', 0):,} sub"
        )

        cases = [
            ("money_flow", {"recipient": "Lockheed"}),
            ("spend_trend", {"recipient": "Boeing"}),
            ("recipient_landscape", {"naics_codes": "541512"}),
            ("teaming", {"recipient": "Lockheed"}),
        ]

        for mode, facets in cases:
            q = query_from_dict({"id": "smoke", "name": "smoke", **facets})
            t0 = time.perf_counter()
            result = await run_facet_analysis(session, q, mode, limit=8)
            dt = time.perf_counter() - t0
            err = result.get("error", "")
            items = result.get("bars") or result.get("flows") or result.get("recipients") or result.get("edges") or []
            if mode == "teaming":
                ok = bool(err) and "subaward" in err.lower()
            else:
                ok = not err and len(items) > 0
            status = "PASS" if ok else "FAIL"
            print(
                f"{status}: {mode} ({dt:.1f}s) items={len(items)} "
                f"summary={result.get('summary', err)[:70]}"
            )
            if not ok:
                fails += 1

    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))