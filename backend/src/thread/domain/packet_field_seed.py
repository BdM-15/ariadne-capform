"""Packet field seed model — full catalog in packet_field_catalog.py."""

from __future__ import annotations

from dataclasses import dataclass

from thread.domain.enums import (
    MilestoneGate,
    PacketFieldRouteKind,
    PacketFieldValueKind,
    PacketSection,
)
from thread.domain.packet_answer_sources import AnswerRouteStub

DECISION_IMPACT_TAGS: frozenset[str] = frozenset(
    {"qualify", "fund", "team", "price", "compliance", "recommend", "relationship"}
)
FIELD_PREREQUISITES: frozenset[str] = frozenset({"award_key", "notice_id", "mineru"})
DECISION_IMPACT_PRIORITY: dict[str, int] = {
    "qualify": 0,
    "fund": 1,
    "team": 2,
    "price": 3,
    "compliance": 4,
    "recommend": 5,
    "relationship": 6,
}

ALL_MS = (
    MilestoneGate.MILESTONE_1,
    MilestoneGate.MILESTONE_2,
    MilestoneGate.MILESTONE_3,
    MilestoneGate.MILESTONE_4,
)
MS1_ONLY = (MilestoneGate.MILESTONE_1,)
MS2_UP = (
    MilestoneGate.MILESTONE_2,
    MilestoneGate.MILESTONE_3,
    MilestoneGate.MILESTONE_4,
)
MS3_UP = (
    MilestoneGate.MILESTONE_3,
    MilestoneGate.MILESTONE_4,
)
MS1_MS2 = (
    MilestoneGate.MILESTONE_1,
    MilestoneGate.MILESTONE_2,
)
MS1_MS3 = (
    MilestoneGate.MILESTONE_1,
    MilestoneGate.MILESTONE_2,
    MilestoneGate.MILESTONE_3,
)


@dataclass(frozen=True)
class PacketFieldSeed:
    key: str
    label: str
    question: str
    section: PacketSection
    value_kind: PacketFieldValueKind
    required_gates: tuple[MilestoneGate, ...]
    route_kind: PacketFieldRouteKind
    reference_slide: str
    answer_route: AnswerRouteStub | None = None
    template_only: bool = False
    decision_impact: tuple[str, ...] = ()
    prerequisites: tuple[str, ...] = ()


def __getattr__(name: str):
    if name in ("PACKET_FIELD_SEEDS", "PACKET_ANSWERABLE_SEEDS", "FIELD_SEED_BY_KEY"):
        from thread.domain.packet_field_catalog import (
            FIELD_SEED_BY_KEY,
            PACKET_ANSWERABLE_SEEDS,
            PACKET_FIELD_SEEDS,
        )

        return {
            "PACKET_FIELD_SEEDS": PACKET_FIELD_SEEDS,
            "PACKET_ANSWERABLE_SEEDS": PACKET_ANSWERABLE_SEEDS,
            "FIELD_SEED_BY_KEY": FIELD_SEED_BY_KEY,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")