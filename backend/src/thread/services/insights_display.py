"""Data Insights page context — live explore + saved lens bookmarks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.intel import pg_queries as intel_queries
from thread.intel.facet_query import (
    InsightFacetQuery,
    describe_query,
    load_insight_queries,
)
from thread.intel.sam_query import (
    SamMonitorQuery,
    describe_sam_query,
    load_sam_queries,
)
from thread.mcp.service import MCPService


@dataclass(frozen=True)
class RadarLensCard:
    query: InsightFacetQuery
    summary: str
    expiring_count: int | None


@dataclass(frozen=True)
class SamLensCard:
    query: SamMonitorQuery
    summary: str


@dataclass(frozen=True)
class InsightsPageContext:
    intel_stats: dict[str, Any]
    intel_live: bool
    radar_lenses: tuple[RadarLensCard, ...]
    sam_lenses: tuple[SamLensCard, ...]
    sam_configured: bool


async def build_insights_page_context(
    session: AsyncSession,
    settings: Settings,
) -> InsightsPageContext:
    stats = await intel_queries.get_intel_stats(session)
    intel_live = bool(stats.get("prime_awards_ready") and stats.get("prime_award_count", 0) > 0)

    radar_queries = load_insight_queries(settings)
    radar_lenses: list[RadarLensCard] = []
    for q in radar_queries:
        expiring: int | None = None
        if intel_live:
            expiring = await intel_queries.count_expiring_for_query(session, q, months_ahead=18)
        radar_lenses.append(
            RadarLensCard(
                query=q,
                summary=describe_query(q),
                expiring_count=expiring,
            )
        )

    sam_queries = load_sam_queries(settings)
    sam_lenses = [
        SamLensCard(
            query=q,
            summary=describe_sam_query(q),
        )
        for q in sam_queries
    ]

    mcp = MCPService(settings)
    sam_srv = next((s for s in mcp.list_servers() if s["id"] == "sam_gov"), None)
    sam_configured = bool(sam_srv and sam_srv["configured"])

    return InsightsPageContext(
        intel_stats=stats,
        intel_live=intel_live,
        radar_lenses=tuple(radar_lenses),
        sam_lenses=tuple(sam_lenses),
        sam_configured=sam_configured,
    )