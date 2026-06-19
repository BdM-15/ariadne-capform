"""Phase 12d — active pursuits + phase-band widget data."""

from __future__ import annotations

import uuid

import pytest

from thread.domain.enums import CapturePhaseBand, LifecycleState
from thread.domain.schemas import OpportunityCreate
from thread.services import opportunities as opp_svc
from thread.services.portfolio import build_portfolio_pulse
from thread.services.pursuits_display import (
    build_active_pursuits,
    build_phase_band_widget,
    is_active_pursuit,
    milestone_gate_label,
    phase_band_label,
)


def test_phase_band_label():
    assert phase_band_label("evergreen") == "Evergreen"
    assert phase_band_label("activation") == "Activation"


def test_milestone_gate_label():
    assert milestone_gate_label("milestone_1") == "MS1"


@pytest.mark.asyncio
async def test_active_pursuits_exclude_archived(db_session):
    active = await opp_svc.create_opportunity(
        db_session,
        OpportunityCreate(name=f"Active {uuid.uuid4().hex[:6]}"),
    )
    archived = await opp_svc.create_opportunity(
        db_session,
        OpportunityCreate(name=f"Archived {uuid.uuid4().hex[:6]}"),
    )
    archived.lifecycle_state = LifecycleState.ARCHIVED.value
    await db_session.flush()

    all_opps = await opp_svc.list_opportunities(db_session)
    cards = await build_active_pursuits(db_session, all_opps)
    ids = {c["id"] for c in cards}
    assert str(active.id) in ids
    assert str(archived.id) not in ids
    assert is_active_pursuit(active) is True
    assert is_active_pursuit(archived) is False


@pytest.mark.asyncio
async def test_phase_band_widget_breakdown(db_session):
    opp_a = await opp_svc.create_opportunity(
        db_session,
        OpportunityCreate(
            name=f"Activation {uuid.uuid4().hex[:6]}",
            capture_phase_band=CapturePhaseBand.ACTIVATION,
        ),
    )
    opp_e = await opp_svc.create_opportunity(
        db_session,
        OpportunityCreate(
            name=f"Evergreen {uuid.uuid4().hex[:6]}",
            capture_phase_band=CapturePhaseBand.EVERGREEN,
        ),
    )
    cards = await build_active_pursuits(db_session, [opp_a, opp_e])
    widget = build_phase_band_widget(cards)

    assert widget.total == 2
    assert len(widget.bands) == 2
    by_band = {s.band: s.count for s in widget.bands}
    assert by_band["activation"] == 1
    assert by_band["evergreen"] == 1
    assert cards[0]["milestone_gate_label"] == "MS1"


@pytest.mark.asyncio
async def test_portfolio_pulse_includes_phase_band_widget(db_session, settings):
    pulse = await build_portfolio_pulse(db_session, settings)
    assert "phase_band_widget" in pulse
    assert hasattr(pulse["phase_band_widget"], "total")
    assert hasattr(pulse["phase_band_widget"], "bands")
    assert "hot_signals_widget" in pulse
    assert "watchlist" in pulse
    assert pulse["watchlist"].count >= 0