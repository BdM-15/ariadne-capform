"""Portfolio pulse — shared by API and HTMX UI."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.intel import pg_queries as intel_queries
from thread.intel.facet_query import (
    describe_query,
    load_insight_queries,
    resolve_active_radar_query,
)
from thread.services import opportunities as opp_svc
from thread.services.hot_signals import build_hot_signals_widget
from thread.services.pursuits_display import build_active_pursuits, build_phase_band_widget


def signal_opportunity_name(*, title: str, agency: str) -> str:
    recipient = (title or "").strip() or "Unknown recipient"
    agency_clean = (agency or "").strip()
    base = f"{recipient} — {agency_clean}" if agency_clean else recipient
    return base if len(base) <= 120 else f"{base[:117]}…"


async def build_portfolio_pulse(session: AsyncSession, settings: Settings) -> dict:
    opps = await opp_svc.list_opportunities(session)
    cards = await build_active_pursuits(session, opps)
    phase_band_widget = build_phase_band_widget(cards)

    active_query = resolve_active_radar_query(settings)
    query_summary = describe_query(active_query)
    saved_queries = load_insight_queries(settings)

    intel_signals: list[dict] = []
    stats = await intel_queries.get_intel_stats(session)
    intel_live = bool(stats.get("prime_awards_ready") and stats.get("prime_award_count", 0) > 0)

    if intel_live and active_query is not None and active_query.has_filters():
        expiring = await intel_queries.get_expiring_contracts_for_query(
            session,
            active_query,
            months_ahead=18,
            limit=12,
        )
        for row in expiring:
            intel_signals.append(
                {
                    "kind": "recompete_radar",
                    "award_key": row["award_key"],
                    "title": row["recipient"],
                    "agency": row["agency"],
                    "end_date": row["end_date"],
                    "months_to_end": row["months_to_end"],
                    "obligation": row["obligation"],
                    "naics_code": row["naics_code"],
                    "opportunity_name": signal_opportunity_name(
                        title=row["recipient"] or "",
                        agency=row["agency"] or "",
                    ),
                }
            )

    hot_signals_widget = build_hot_signals_widget(
        intel_signals=intel_signals,
        intel_live=intel_live,
        lens_summary=query_summary,
    )

    return {
        "opportunities": cards,
        "phase_band_widget": phase_band_widget,
        "hot_signals_widget": hot_signals_widget,
        "active_insight_query": active_query,
        "saved_insight_queries": saved_queries,
        "radar_query_summary": query_summary,
        "intel_signals": intel_signals,
        "intel_stats": stats,
    }