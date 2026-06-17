"""Portfolio pulse — shared by API and HTMX UI."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.intel import pg_queries as intel_queries
from thread.services import opportunities as opp_svc


def signal_opportunity_name(*, title: str, agency: str) -> str:
    recipient = (title or "").strip() or "Unknown recipient"
    agency_clean = (agency or "").strip()
    base = f"{recipient} — {agency_clean}" if agency_clean else recipient
    return base if len(base) <= 120 else f"{base[:117]}…"


async def build_portfolio_pulse(session: AsyncSession, settings: Settings) -> dict:
    opps = await opp_svc.list_opportunities(session)
    cards = []
    for opp in opps:
        pending = await opp_svc.pending_review_count(session, opp.id)
        cards.append(
            {
                "id": str(opp.id),
                "name": opp.name,
                "phase_band": opp.capture_phase_band,
                "milestone_gate": opp.current_milestone_gate,
                "urgency_score": opp.urgency_score,
                "pending_review_count": pending,
            }
        )

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
        "intel_signals": intel_signals,
        "intel_stats": stats,
    }