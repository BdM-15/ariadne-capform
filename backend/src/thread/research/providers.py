"""Research provider registry — free/local first."""

from __future__ import annotations

from dataclasses import dataclass

from thread.config import Settings
from thread.research.adapters import crawl4ai as crawl4ai_adapter
from thread.research.adapters import searxng as searxng_adapter
from thread.research.types import ProviderRole, ProviderStatus


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    name: str
    role: ProviderRole
    priority: int
    status: ProviderStatus
    detail: str


async def build_provider_registry(settings: Settings) -> list[ProviderInfo]:
    providers: list[ProviderInfo] = []

    searx_ok = await searxng_adapter.probe(settings.searxng_base_url)
    providers.append(
        ProviderInfo(
            id="searxng",
            name="SearXNG",
            role=ProviderRole.SEARCH,
            priority=1,
            status=ProviderStatus.AVAILABLE if searx_ok else ProviderStatus.UNREACHABLE,
            detail=settings.searxng_base_url,
        )
    )

    crawl_ok = await crawl4ai_adapter.probe(settings.crawl4ai_base_url)
    providers.append(
        ProviderInfo(
            id="crawl4ai",
            name="Crawl4AI",
            role=ProviderRole.CRAWL,
            priority=2,
            status=ProviderStatus.AVAILABLE if crawl_ok else ProviderStatus.UNREACHABLE,
            detail=settings.crawl4ai_base_url,
        )
    )

    for pid, name, key_attr, priority in (
        ("serpapi", "SerpAPI", "serpapi_api_key", 3),
        ("olostep", "Olostep", "olostep_api_key", 4),
        ("firecrawl", "Firecrawl", "firecrawl_api_key", 5),
    ):
        key = getattr(settings, key_attr)
        if key:
            status = (
                ProviderStatus.REQUIRES_APPROVAL
                if settings.research_require_approval_for_paid
                else ProviderStatus.MISSING_CONFIG
            )
            detail = "configured — paid provider not wired in MVP"
        else:
            status = ProviderStatus.MISSING_CONFIG
            detail = "API key not set"
        providers.append(
            ProviderInfo(
                id=pid,
                name=name,
                role=ProviderRole.SEARCH,
                priority=priority,
                status=status,
                detail=detail,
            )
        )

    providers.append(
        ProviderInfo(
            id="fake",
            name="Fake (tests)",
            role=ProviderRole.SEARCH,
            priority=99,
            status=ProviderStatus.AVAILABLE,
            detail="internal test adapter",
        )
    )
    return sorted(providers, key=lambda p: p.priority)