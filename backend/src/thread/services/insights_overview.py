"""Phase 17e — Insights Overview lens (shared intel charts + ECharts payloads)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.intel import pg_queries as intel_queries
from thread.intel.charts import run_slice_overview
from thread.intel.echarts_options import attach_overview_echarts
from thread.intel.facet_query import InsightFacetQuery, describe_query
from thread.services.insights_explore import _facet_from_params


@dataclass(frozen=True)
class OverviewResult:
    query: InsightFacetQuery | None
    summary: str
    overview: dict[str, Any]
    intel_live: bool
    status: str
    error: str | None = None


def overview_charts_json(overview: dict[str, Any]) -> str:
    charts = overview.get("charts") or {}
    return json.dumps(charts, separators=(",", ":"))


async def build_overview(
    session: AsyncSession,
    settings: Settings,
    *,
    agency: str = "",
    sub_agency: str = "",
    recipient: str = "",
    naics_codes: str = "",
    psc_codes: str = "",
    awarding_office: str = "",
    funding_office: str = "",
    recipient_uei: str = "",
    pop_state: str = "",
    extent_competed: str = "",
    type_of_set_aside: str = "",
    run: bool = False,
) -> OverviewResult:
    stats = await intel_queries.get_intel_stats(session)
    intel_live = bool(stats.get("prime_awards_ready") and stats.get("prime_award_count", 0) > 0)
    query = _facet_from_params(
        agency=agency,
        sub_agency=sub_agency,
        recipient=recipient,
        naics_codes=naics_codes,
        psc_codes=psc_codes,
        awarding_office=awarding_office,
        funding_office=funding_office,
        recipient_uei=recipient_uei,
        pop_state=pop_state,
        extent_competed=extent_competed,
        type_of_set_aside=type_of_set_aside,
    )

    if not run:
        return OverviewResult(
            query=query,
            summary=describe_query(query) if query else "",
            overview={"idle": True},
            intel_live=intel_live,
            status="idle",
        )

    if query is None:
        return OverviewResult(
            query=None,
            summary="",
            overview={},
            intel_live=intel_live,
            status="no_query",
            error="Set at least one facet, then run slice.",
        )

    if not intel_live:
        return OverviewResult(
            query=query,
            summary=describe_query(query),
            overview={},
            intel_live=False,
            status="loading",
            error="PG intel not ready — resume migration.",
        )

    raw = await run_slice_overview(session, query)
    if raw.get("error"):
        return OverviewResult(
            query=query,
            summary=describe_query(query),
            overview=raw,
            intel_live=True,
            status=str(raw.get("status") or "error"),
            error=str(raw["error"]),
        )

    overview = attach_overview_echarts(raw)
    return OverviewResult(
        query=query,
        summary=describe_query(query),
        overview=overview,
        intel_live=True,
        status="ready",
    )