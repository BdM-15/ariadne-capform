"""Intel migration — bulk zip/CSV → PostgreSQL (re-exports bulk_migration)."""

from thread.intel.bulk_migration import (
    MigrationResult,
    MigrationStatus,
    bulk_prime_dir,
    bulk_sub_dir,
    ensure_intel_indexes,
    get_migration_status,
    log_path,
    maybe_auto_migrate,
    needs_migration,
    run_intel_migration,
    state_path,
)
from thread.intel.intel_analytics import ensure_intel_analytics_views

__all__ = [
    "MigrationResult",
    "MigrationStatus",
    "bulk_prime_dir",
    "bulk_sub_dir",
    "ensure_intel_analytics_views",
    "ensure_intel_indexes",
    "get_migration_status",
    "log_path",
    "maybe_auto_migrate",
    "needs_migration",
    "run_intel_migration",
    "state_path",
]