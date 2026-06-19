"""Read-only settings / health context for the HTMX settings page (Phase 12b)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from thread import __version__
from thread.config import Settings
from thread.intel import pg_queries as intel_queries
from thread.intel.migration import get_migration_status
from thread.llm.router import probe_ollama
from thread.mcp.service import MCPService
from thread.research.providers import build_provider_registry
from thread.skills.registry import discover_skills


@dataclass
class SettingsHealthContext:
    status: str
    version: str
    postgres_ready: bool
    grok_configured: bool
    ollama_reachable: bool
    vault_path: str
    vault_healthy: bool
    reasoning_model: str
    local_daily_model: str
    local_admin_enabled: bool
    intel_stats: dict[str, Any]
    migration: dict[str, Any]
    providers: list[dict[str, Any]]
    mcp_server_count: int
    skill_count: int
    langgraph_enabled: bool
    langgraph_studio_port: int
    langsmith_configured: bool
    langsmith_tracing: bool
    vault_sandbox_mode: bool
    vault_allow_test_promote: bool
    env_flags: dict[str, Any]


async def build_settings_health_context(
    session: AsyncSession,
    settings: Settings,
) -> SettingsHealthContext:
    postgres_ready = False
    intel_stats: dict[str, Any] = {}
    ollama_reachable = False

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
        try:
            ollama_reachable = await probe_ollama(settings)
        except Exception:
            pass

    mig = get_migration_status(settings)
    prime_pct = round(100 * mig.prime_migrated / max(mig.prime_source_total, 1), 2)

    vault_root = settings.resolve(settings.knowledge_vault_path)
    vault_healthy = vault_root.is_dir() and any(vault_root.iterdir())

    providers = [
        {
            "id": p.id,
            "name": p.name,
            "role": p.role.value,
            "status": p.status.value,
            "detail": p.detail,
        }
        for p in await build_provider_registry(settings)
        if p.id != "fake"
    ]

    return SettingsHealthContext(
        status="ok" if postgres_ready else "degraded",
        version=__version__,
        postgres_ready=postgres_ready,
        grok_configured=bool(settings.xai_api_key),
        ollama_reachable=ollama_reachable,
        vault_path=str(vault_root),
        vault_healthy=vault_healthy,
        reasoning_model=settings.reasoning_llm_model,
        local_daily_model=settings.local_daily_model,
        local_admin_enabled=settings.local_admin_model_enabled,
        intel_stats=intel_stats,
        migration={
            "source_path": mig.source_path,
            "source_exists": mig.source_exists,
            "prime_migrated": mig.prime_migrated,
            "prime_source_total": mig.prime_source_total,
            "prime_pct": prime_pct,
            "sub_migrated": mig.sub_migrated,
            "sub_source_total": mig.sub_source_total,
            "phase": mig.phase,
            "complete": mig.complete,
            "indexes_built": mig.indexes_built,
            "last_updated": mig.last_updated,
            "log_path": mig.log_path,
        },
        providers=providers,
        mcp_server_count=len(MCPService(settings).list_servers()),
        skill_count=len(discover_skills(settings.resolve(settings.skills_root))),
        langgraph_enabled=settings.langgraph_enabled,
        langgraph_studio_port=settings.langgraph_studio_port,
        langsmith_configured=bool(settings.resolved_langchain_api_key),
        langsmith_tracing=settings.langsmith_tracing or settings.langchain_tracing_v2,
        vault_sandbox_mode=settings.vault_sandbox_mode,
        vault_allow_test_promote=settings.vault_allow_test_promote,
        env_flags={
            "app_env": settings.app_env,
            "intel_auto_migrate_on_start": settings.intel_auto_migrate_on_start,
            "knowledge_bootstrap_on_start": settings.knowledge_bootstrap_on_start,
            "enable_startup_warmup": settings.enable_startup_warmup,
            "autostart_research_providers": settings.autostart_research_providers,
            "enable_live_mcps": settings.enable_live_mcps,
            "mineru_enabled": settings.mineru_enabled,
            "llm_fallback_enabled": settings.llm_fallback_enabled,
            "research_require_approval_for_paid": settings.research_require_approval_for_paid,
            "default_naics": settings.default_naics,
            "sam_gov_configured": bool(settings.sam_gov_api_key),
            "vault_sandbox_mode": settings.vault_sandbox_mode,
            "vault_allow_test_promote": settings.vault_allow_test_promote,
        },
    )


def settings_health_as_dict(ctx: SettingsHealthContext) -> dict[str, Any]:
    return asdict(ctx)