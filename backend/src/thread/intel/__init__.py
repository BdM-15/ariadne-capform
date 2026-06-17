"""USAspending intel layer — PostgreSQL queries migrated from capture-insights DuckDB."""

from thread.intel.pg_queries import (
    get_expiring_contracts,
    get_intel_stats,
    get_market_summary,
    get_quick_opportunity_snapshot,
    get_top_agencies,
)

__all__ = [
    "get_expiring_contracts",
    "get_intel_stats",
    "get_market_summary",
    "get_quick_opportunity_snapshot",
    "get_top_agencies",
]