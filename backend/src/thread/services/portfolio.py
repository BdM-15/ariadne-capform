"""Portfolio pulse — shared by API and HTMX UI."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.intel import pg_queries as intel_queries
from thread.intel.saved_lenses import load_saved_lenses, naics_codes_for_radar, radar_lens_summary
from thread.services.hot_signals import build_hot_signals_widget
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
    naics_codes = naics_codes_for_radar(settings)
    lens_summary = radar_lens_summary(settings)
    saved_lenses = load_saved_lenses(settings)
    intel_live = bool(stats.get("prime_awards_ready") and stats.get("prime_award_count", 0) > 0)
    if intel_live:
        expiring = await intel_queries.get_expiring_contracts(
            session,
            naics_codes,
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
        lens_summary=lens_summary,
    )

    return {
        "opportunities": cards,
        "phase_band_widget": phase_band_widget,
        "hot_signals_widget": hot_signals_widget,
        "saved_lenses": saved_lenses,
        "radar_naics_codes": naics_codes,
        "radar_lens_summary": lens_summary,
        "intel_signals": intel_signals,
        "intel_stats": stats,
    }