"""Command Center platform health widget — blocking status only (12e)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.intel import pg_queries as intel_queries
from thread.intel.migration import get_migration_status
from thread.services.mineru_client import probe_mineru_health


@dataclass(frozen=True)
class PlatformHealthWidget:
    status: str
    needs_attention: bool
    postgres_ready: bool
    intel_live: bool
    migration_complete: bool
    migration_pct: float
    migration_phase: str
    vault_healthy: bool
    grok_configured: bool
    mineru_enabled: bool
    mineru_reachable: bool
    blockers: tuple[str, ...]


async def build_platform_health_widget(
    session: AsyncSession,
    settings: Settings,
) -> PlatformHealthWidget:
    postgres_ready = False
    intel_stats: dict[str, Any] = {}

    try:
        await session.execute(select(1))
        postgres_ready = True
    except Exception:
        pass

    if postgres_ready:
        try:
            intel_stats = await intel_queries.get_intel_stats(session)
        except Exception:
            intel_stats = {}

    mig = get_migration_status(settings)
    migration_pct = round(100 * mig.prime_migrated / max(mig.prime_source_total, 1), 1)
    intel_live = bool(
        intel_stats.get("prime_awards_ready") and intel_stats.get("prime_award_count", 0) > 0
    )

    vault_root = settings.resolve(settings.knowledge_vault_path)
    vault_healthy = vault_root.is_dir() and any(vault_root.iterdir())
    grok_configured = bool(settings.xai_api_key)
    mineru_enabled = bool(settings.mineru_enabled)
    mineru_reachable = probe_mineru_health(settings) if mineru_enabled else False

    blockers: list[str] = []
    if not postgres_ready:
        blockers.append("Postgres unreachable")
    elif not mig.complete and not intel_live:
        blockers.append(f"Intel migration {migration_pct}% — radar/search blocked")
    elif not mig.complete and intel_live:
        blockers.append(f"Migration in progress ({migration_pct}%)")
    if not vault_healthy:
        blockers.append("Vault empty or missing")
    if not grok_configured:
        blockers.append("Grok API key not set")
    if mineru_enabled and not mineru_reachable:
        blockers.append("MinerU enabled but FastAPI unreachable")

    needs_attention = bool(blockers) and (
        not postgres_ready or (not mig.complete and not intel_live) or not grok_configured
    )

    if not postgres_ready:
        status = "blocked"
    elif needs_attention:
        status = "degraded"
    else:
        status = "ok"

    return PlatformHealthWidget(
        status=status,
        needs_attention=needs_attention,
        postgres_ready=postgres_ready,
        intel_live=intel_live,
        migration_complete=mig.complete,
        migration_pct=migration_pct,
        migration_phase=mig.phase,
        vault_healthy=vault_healthy,
        grok_configured=grok_configured,
        mineru_enabled=mineru_enabled,
        mineru_reachable=mineru_reachable,
        blockers=tuple(blockers),
    )