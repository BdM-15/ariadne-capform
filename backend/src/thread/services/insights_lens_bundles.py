"""Phase 17e-g — Competition + Trace lens bundles (DR methods inline, not Clew-only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.intel.charts import run_competition_lens, run_trace_lens
from thread.intel.echarts_options import attach_competition_echarts, attach_trace_echarts
from thread.intel.facet_query import InsightFacetQuery
from thread.intel.graph_trace import build_browse_funnel, enrich_relations_graph


@dataclass(frozen=True)
class LensBundleResult:
    bundle: dict[str, Any]
    status: str
    error: str | None = None


async def build_competition_bundle(
    session: AsyncSession,
    query: InsightFacetQuery | None,
) -> LensBundleResult:
    if query is None or not query.has_filters():
        return LensBundleResult(bundle={"idle": True}, status="idle")
    raw = await run_competition_lens(session, query)
    if raw.get("error"):
        return LensBundleResult(
            bundle=raw,
            status=str(raw.get("status") or "error"),
            error=str(raw["error"]),
        )
    bundle = attach_competition_echarts(raw)
    return LensBundleResult(bundle=bundle, status="ready")


async def build_trace_bundle(
    session: AsyncSession,
    query: InsightFacetQuery | None,
    settings: Settings | None = None,
) -> LensBundleResult:
    if query is None or not query.has_filters():
        return LensBundleResult(bundle={"idle": True}, status="idle")
    raw = await run_trace_lens(session, query)
    if raw.get("error"):
        return LensBundleResult(
            bundle=raw,
            status=str(raw.get("status") or "error"),
            error=str(raw["error"]),
        )
    relations = raw.get("relations_graph") or {}
    if relations and not relations.get("error"):
        seed = (query.recipient or "").strip()
        enriched = await enrich_relations_graph(
            relations,
            settings,
            recipient_uei=query.recipient_uei,
            seed_prime=seed or None,
        )
        raw = {**raw, "relations_graph": enriched, "expose_graph": enriched}
        raw["browse_funnel"] = build_browse_funnel(enriched)
    bundle = attach_trace_echarts(raw)
    return LensBundleResult(bundle=bundle, status="ready")