"""Active pursuits — lifecycle filter, phase-band breakdown, display labels."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from thread.db.models import Opportunity
from thread.domain.enums import CapturePhaseBand, LifecycleState, MilestoneGate
from thread.services import opportunities as opp_svc

ACTIVE_PURSUIT_LIFECYCLES: frozenset[str] = frozenset(
    {
        LifecycleState.IDENTIFIED.value,
        LifecycleState.QUALIFIED.value,
        LifecycleState.PURSUING.value,
        LifecycleState.BID_DECIDED.value,
        LifecycleState.SUBMITTED.value,
    }
)

BIDDING_LIFECYCLE_STATES: frozenset[str] = frozenset(
    {
        LifecycleState.PURSUING.value,
        LifecycleState.BID_DECIDED.value,
        LifecycleState.SUBMITTED.value,
    }
)

PHASE_BAND_ORDER: tuple[str, ...] = (
    CapturePhaseBand.ACTIVATION.value,
    CapturePhaseBand.EVERGREEN.value,
)


@dataclass(frozen=True)
class PhaseBandSlice:
    band: str
    label: str
    count: int
    preview: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class PhaseBandWidget:
    total: int
    bands: tuple[PhaseBandSlice, ...]


def phase_band_label(band: str) -> str:
    return {
        CapturePhaseBand.EVERGREEN.value: "Evergreen",
        CapturePhaseBand.ACTIVATION.value: "Activation",
    }.get(band, band.replace("_", " ").title())


def milestone_gate_label(gate: str) -> str:
    return {
        MilestoneGate.MILESTONE_1.value: "MS1",
        MilestoneGate.MILESTONE_2.value: "MS2",
        MilestoneGate.MILESTONE_3.value: "MS3",
        MilestoneGate.MILESTONE_4.value: "MS4",
    }.get(gate, gate.replace("_", " ").upper())


def lifecycle_label(state: str) -> str:
    return {
        LifecycleState.IDENTIFIED.value: "Identified",
        LifecycleState.QUALIFIED.value: "Qualified",
        LifecycleState.PURSUING.value: "Pursuing",
        LifecycleState.BID_DECIDED.value: "Bid decided",
        LifecycleState.SUBMITTED.value: "Submitted",
        LifecycleState.AWARDED.value: "Awarded",
        LifecycleState.LOST.value: "Lost",
        LifecycleState.ARCHIVED.value: "Archived",
    }.get(state, state.replace("_", " ").title())


def urgency_tier(score: float) -> str:
    if score >= 0.75:
        return "hot"
    if score >= 0.4:
        return "warm"
    return "cool"


def is_active_pursuit(opp: Opportunity) -> bool:
    return opp.lifecycle_state in ACTIVE_PURSUIT_LIFECYCLES


async def build_pursuit_card(session: AsyncSession, opp: Opportunity) -> dict[str, Any]:
    pending = await opp_svc.pending_review_count(session, opp.id)
    return {
        "id": str(opp.id),
        "name": opp.name,
        "phase_band": opp.capture_phase_band,
        "phase_band_label": phase_band_label(opp.capture_phase_band),
        "milestone_gate": opp.current_milestone_gate,
        "milestone_gate_label": milestone_gate_label(opp.current_milestone_gate),
        "lifecycle_state": opp.lifecycle_state,
        "lifecycle_label": lifecycle_label(opp.lifecycle_state),
        "urgency_score": opp.urgency_score,
        "urgency_tier": urgency_tier(opp.urgency_score),
        "pending_review_count": pending,
        "is_bidding": opp.lifecycle_state in BIDDING_LIFECYCLE_STATES,
    }


async def build_active_pursuits(session: AsyncSession, opps: list[Opportunity]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for opp in opps:
        if not is_active_pursuit(opp):
            continue
        cards.append(await build_pursuit_card(session, opp))
    return cards


def build_phase_band_widget(pursuits: list[dict[str, Any]], *, preview_limit: int = 2) -> PhaseBandWidget:
    by_band: dict[str, list[dict[str, Any]]] = {}
    for pursuit in pursuits:
        by_band.setdefault(pursuit["phase_band"], []).append(pursuit)

    slices: list[PhaseBandSlice] = []
    for band in PHASE_BAND_ORDER:
        items = by_band.get(band, [])
        slices.append(
            PhaseBandSlice(
                band=band,
                label=phase_band_label(band),
                count=len(items),
                preview=tuple(items[:preview_limit]),
            )
        )

    return PhaseBandWidget(total=len(pursuits), bands=tuple(slices))