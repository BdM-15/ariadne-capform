"""Portfolio pulse — shared by API and HTMX UI."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.intel import pg_queries as intel_queries
from thread.services import opportunities as opp_svc
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

    intel_signals: list[dict] = []
    stats = await intel_queries.get_intel_stats(session)
    if stats["prime_awards_ready"] and stats["prime_award_count"] > 0:
        expiring = await intel_queries.get_expiring_contracts(
            session,
            [settings.default_naics],
            months_ahead=18,
            limit=8,
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

    return {
        "opportunities": cards,
        "phase_band_widget": phase_band_widget,
        "intel_signals": intel_signals,
        "intel_stats": stats,
    }