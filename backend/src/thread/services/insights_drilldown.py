"""Phase 17b — Insights drill-down analytics context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.intel import pg_queries as intel_queries
from thread.clew import ANALYSIS_MODES, run_facet_analysis
from thread.clew.charts import attach_echarts_option
from thread.clew.path_link import analysis_from_path, parse_path_param
from thread.intel.facet_query import InsightFacetQuery, describe_query
from thread.clew.mcp_overlay import fetch_mcp_overlay
from thread.services.insights_explore import _facet_from_params
from thread.services.mineru_stub import mineru_ingest_status


@dataclass(frozen=True)
class DrilldownResult:
    query: InsightFacetQuery | None
    summary: str
    mode: str
    analysis: dict[str, Any]
    intel_live: bool
    status: str
    review_id: str | None = None
    error: str | None = None


async def build_drilldown(
    session: AsyncSession,
    settings: Settings,
    *,
    agency: str = "",
    sub_agency: str = "",
    recipient: str = "",
    naics_codes: str = "",
    psc_codes: str = "",
    min_obligation: str = "",
    awarding_office: str = "",
    funding_office: str = "",
    recipient_uei: str = "",
    pop_state: str = "",
    extent_competed: str = "",
    type_of_set_aside: str = "",
    exclude_agencies: str = "",
    mode: str = "money_flow",
    run: bool = False,
    review_id: str | None = None,
    include_mcp: bool = False,
    path: str = "",
) -> DrilldownResult:
    facet_kwargs = {
        "agency": agency,
        "sub_agency": sub_agency,
        "recipient": recipient,
        "naics_codes": naics_codes,
        "psc_codes": psc_codes,
        "min_obligation": min_obligation,
        "awarding_office": awarding_office,
        "funding_office": funding_office,
        "recipient_uei": recipient_uei,
        "pop_state": pop_state,
        "extent_competed": extent_competed,
        "type_of_set_aside": type_of_set_aside,
        "exclude_agencies": exclude_agencies,
    }
    stats = await intel_queries.get_intel_stats(session)
    intel_live = bool(stats.get("prime_awards_ready") and stats.get("prime_award_count", 0) > 0)
    path_edges = parse_path_param(path)
    if path_edges:
        path_mode = mode if mode in {"money_flow", "teaming"} else "money_flow"
        analysis = analysis_from_path(mode=path_mode, edges=path_edges)
        analysis["mineru"] = mineru_ingest_status(settings)
        query = _facet_from_params(**facet_kwargs)
        return DrilldownResult(
            query=query,
            summary=describe_query(query) if query else analysis.get("summary", ""),
            mode=path_mode,
            analysis=analysis,
            intel_live=intel_live,
            status="ready",
            review_id=review_id,
        )

    query = _facet_from_params(**facet_kwargs)

    if not run:
        return DrilldownResult(
            query=query,
            summary=describe_query(query) if query else "",
            mode=mode,
            analysis={"idle": True, "mineru": mineru_ingest_status(settings), "modes": sorted(ANALYSIS_MODES)},
            intel_live=intel_live,
            status="idle",
        )

    if query is None:
        return DrilldownResult(
            query=None,
            summary="",
            mode=mode,
            analysis={},
            intel_live=intel_live,
            status="no_query",
            error="Set search facets above, then run analysis.",
        )

    if mode not in ANALYSIS_MODES:
        mode = "money_flow"

    if not intel_live:
        return DrilldownResult(
            query=query,
            summary=describe_query(query),
            mode=mode,
            analysis={},
            intel_live=False,
            status="loading",
            error="PG intel not ready — resume migration.",
        )

    analysis = await run_facet_analysis(session, query, mode)
    analysis = attach_echarts_option(analysis)
    analysis["mineru"] = mineru_ingest_status(settings)
    analysis["facet_summary"] = describe_query(query)
    analysis["intel_stats"] = {
        "prime_awards": stats.get("prime_award_count", 0),
        "subawards": stats.get("subaward_count", 0),
    }
    analysis["mcp_overlay"] = await fetch_mcp_overlay(
        settings, query, mode, include_mcp=include_mcp
    )
    if analysis.get("error"):
        return DrilldownResult(
            query=query,
            summary=describe_query(query),
            mode=mode,
            analysis=analysis,
            intel_live=True,
            status="error",
            error=str(analysis["error"]),
            review_id=review_id,
        )

    return DrilldownResult(
        query=query,
        summary=describe_query(query),
        mode=mode,
        analysis=analysis,
        intel_live=True,
        status="ready",
        review_id=review_id,
    )