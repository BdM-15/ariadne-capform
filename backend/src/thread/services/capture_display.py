"""Capture lane home — post-identify pursuits and Living Briefing Packet entry."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.services import opportunities as opp_svc
from thread.services.pursuits_display import build_capture_pursuits, build_phase_band_widget


async def build_capture_home(session: AsyncSession, settings: Settings) -> dict:
    del settings
    opps = await opp_svc.list_opportunities(session)
    pursuits = await build_capture_pursuits(session, opps)
    return {
        "pursuits": pursuits,
        "phase_band_widget": build_phase_band_widget(pursuits),
    }