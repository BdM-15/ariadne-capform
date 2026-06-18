"""Briefing packet slide catalog — MS gate markers and applicability (Phase 14c)."""

from __future__ import annotations

from thread.domain.enums import MilestoneGate

# Bottom-right MS markers per reference deck (brief the slides with your gate number).
SLIDE_MS_MARKERS: dict[str, frozenset[int]] = {
    "slide_2_cover": frozenset({1, 2, 3, 4}),
    "slide_4_synopsis": frozenset({1, 2, 3, 4}),
    "slide_5_bluf": frozenset({1, 2, 3, 4}),
    "slide_6_team": frozenset({1, 2, 3, 4}),
    "slide_8_swot": frozenset({2, 3, 4}),
    "slide_10_pricing": frozenset({3, 4}),
    "slide_13_risks": frozenset({2, 3, 4}),
    "slide_17_approval": frozenset({1, 2}),
    "slide_18_approval": frozenset({3, 4}),
}

PACKET_SLIDE_ORDER: tuple[tuple[str, str], ...] = (
    ("slide_2_cover", "Cover"),
    ("slide_4_synopsis", "Synopsis"),
    ("slide_5_bluf", "BLUF"),
    ("slide_6_team", "Team"),
    ("slide_8_swot", "SWOT"),
    ("slide_10_pricing", "Pricing"),
    ("slide_13_risks", "Risks"),
    ("slide_17_approval", "MS1 & MS2 approval"),
    ("slide_18_approval", "MS3 & MS4 approval"),
)

_DEFAULT_SLIDE = PACKET_SLIDE_ORDER[0][0]

_GATE_NUM: dict[str, int] = {
    MilestoneGate.MILESTONE_1.value: 1,
    MilestoneGate.MILESTONE_2.value: 2,
    MilestoneGate.MILESTONE_3.value: 3,
    MilestoneGate.MILESTONE_4.value: 4,
}


def normalize_milestone_gate(gate: str | None) -> str:
    if gate in _GATE_NUM:
        return gate
    return MilestoneGate.MILESTONE_1.value


def gate_number(gate: str) -> int:
    return _GATE_NUM[normalize_milestone_gate(gate)]


def normalize_packet_slide(slide: str | None) -> str:
    if not slide:
        return _DEFAULT_SLIDE
    known = {sid for sid, _ in PACKET_SLIDE_ORDER}
    return slide if slide in known else _DEFAULT_SLIDE


def field_applicable_for_gate(required_gates: list[str] | tuple[str, ...] | None, gate: str) -> bool:
    if not required_gates:
        return True
    return normalize_milestone_gate(gate) in required_gates


def slide_applicability(slide_id: str, gate: str, *, fields_for_gate: int) -> str:
    """required | optional | omitted — per milestone marker convention."""
    markers = SLIDE_MS_MARKERS.get(slide_id, frozenset({1, 2, 3, 4}))
    gn = gate_number(gate)
    if gn in markers:
        return "required"
    if fields_for_gate > 0:
        return "optional"
    return "omitted"


def slide_visible(applicability: str) -> bool:
    return applicability != "omitted"