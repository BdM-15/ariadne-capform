#!/usr/bin/env python
"""Deprecated — DuckDB bridge removed. Delegates to migrate_intel_from_bulk.py."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "src"))

if __name__ == "__main__":
    import runpy

    print("[intel] DuckDB migration retired — using bulk zip/CSV COPY loader.")
    runpy.run_path(
        str(ROOT / "backend" / "scripts" / "migrate_intel_from_bulk.py"),
        run_name="__main__",
    )