"""Bootstrap Obsidian vault — idempotent Karpathy LLM-wiki seed."""

from __future__ import annotations

from thread.bootstrap.vault_seed import SeedReport, ensure_vault_seed
from thread.config import Settings


def bootstrap_vault(settings: Settings) -> dict:
    """Ensure vault dirs + seeds exist. Never overwrites user/LLM wiki content."""
    report = ensure_vault_seed(settings)
    return {
        "bootstrapped": report.changed,
        "path": report.path,
        "created": report.created,
        "skipped_existing": len(report.skipped),
        "reason": None if report.changed else "vault already complete",
    }