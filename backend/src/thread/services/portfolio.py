"""Portfolio pulse — shared by API and HTMX UI."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.intel import pg_queries as intel_queries
from thread.services import opportunities as opp_svc
from thread.services.hot_signals import build_hot_signals_widget
from thread.services.intel_inbox import build_intel_inbox_widget
from thread.services.pursuits_display import build_capture_pursuits, build_phase_band_widget
from thread.services.knowledge_digest import build_knowledge_digest_widget
from thread.services.watchlist_display import build_watchlist_widget, watchlist_signals


def signal_opportunity_name(*, title: str, agency: str) -> str:
    recipient = (title or "").strip() or "Unknown recipient"
    agency_clean = (agency or "").strip()
    base = f"{recipient} — {agency_clean}" if agency_clean else recipient
    return base if len(base) <= 120 else f"{base[:117]}…"


async def build_portfolio_pulse(
    session: AsyncSession,
    settings: Settings,
    *,
    sam_force_refresh: bool = False,
) -> dict:
    del sam_force_refresh  # SAM live fetch moves to Insights explore; Pulse uses watchlist only.
    opps = await opp_svc.list_opportunities(session)
    cards = await build_capture_pursuits(session, opps)
    phase_band_widget = build_phase_band_widget(cards)

    stats = await intel_queries.get_intel_stats(session)
    intel_live = bool(stats.get("prime_awards_ready") and stats.get("prime_award_count", 0) > 0)

    watchlist = await build_watchlist_widget(session, settings)
    intel_signals = watchlist_signals(watchlist)

    hot_signals_widget = build_hot_signals_widget(
        intel_signals=intel_signals,
        intel_live=intel_live,
        lens_summary=f"{watchlist.count} watched" if watchlist.count else "Watchlist empty",
    )
    intel_inbox = await build_intel_inbox_widget(session, settings)
    knowledge_digest = build_knowledge_digest_widget(settings)

    return {
        "opportunities": cards,
        "phase_band_widget": phase_band_widget,
        "hot_signals_widget": hot_signals_widget,
        "intel_signals": intel_signals,
        "intel_stats": stats,
        "intel_inbox": intel_inbox,
        "watchlist": watchlist,
        "knowledge_digest": knowledge_digest,
    }