"""Briefing packet slide catalog — MS gate markers and applicability (Phase 14c / 14k)."""

from __future__ import annotations

from thread.domain.enums import MilestoneGate

# Training / process slides from 2026 exemplar intro (not in export deck).
REFERENCE_SLIDE_IDS: frozenset[str] = frozenset(
    {
        "slide_ref_process_bluf",
        "slide_ref_faq",
        "slide_ref_milestone_overview",
        "slide_ref_promotion_overview",
    }
)

# Bottom-right MS markers per reference deck (brief the slides with your gate number).
SLIDE_MS_MARKERS: dict[str, frozenset[int]] = {
    "slide_ref_process_bluf": frozenset({1, 2, 3, 4}),
    "slide_ref_faq": frozenset({1, 2, 3, 4}),
    "slide_ref_milestone_overview": frozenset({1, 2, 3, 4}),
    "slide_ref_promotion_overview": frozenset({1, 2, 3, 4}),
    "slide_2_cover": frozenset({1, 2, 3, 4}),
    "slide_3_zero_harm": frozenset({1, 2, 3, 4}),
    "slide_4_synopsis": frozenset({1, 2, 3, 4}),
    "slide_5_bluf": frozenset({1, 2, 3, 4}),
    "slide_6_team": frozenset({1, 2, 3}),
    "slide_7_evaluation": frozenset({2, 3, 4}),
    "slide_8_swot": frozenset({1, 2, 3}),
    "slide_9_path_to_blue": frozenset({1, 2, 3}),
    "slide_10_pricing": frozenset({2, 3, 4}),
    "slide_11_proposed_pricing": frozenset({3, 4}),
    "slide_12_business_case": frozenset({2, 3, 4}),
    "slide_13_risks": frozenset({3, 4}),
    "slide_14_actions": frozenset({1, 2, 3, 4}),
    "slide_15_questions": frozenset({1, 2, 3, 4}),
    "slide_17_approval": frozenset({1, 2}),
    "slide_18_approval": frozenset({3, 4}),
}

# Bottom-right optional markers (slide shown, not required for gate).
SLIDE_MS_OPTIONAL_MARKERS: dict[str, frozenset[int]] = {
    "slide_6_team": frozenset({4}),
    "slide_7_evaluation": frozenset({1}),
    "slide_8_swot": frozenset({4}),
    "slide_9_path_to_blue": frozenset({4}),
    "slide_10_pricing": frozenset({1}),
    "slide_11_proposed_pricing": frozenset({1, 2}),
    "slide_12_business_case": frozenset({1}),
    "slide_13_risks": frozenset({1, 2}),
}

# Titles as shown on the slide (includes suggested timing from reference deck).
SLIDE_PRESENTATION_TITLES: dict[str, str] = {
    "slide_ref_process_bluf": "Milestone Process BLUF",
    "slide_ref_faq": "Milestone Deck FAQ",
    "slide_ref_milestone_overview": "Milestone Profiles & Timelines",
    "slide_ref_promotion_overview": "Pursuit Promotion Criteria Overview",
    "slide_2_cover": "Milestone Review (Cover)",
    "slide_3_zero_harm": "Zero Harm Moment (1 Min)",
    "slide_4_synopsis": "Opportunity Synopsis (2 Min)",
    "slide_5_bluf": "Opportunity BLUF (2 Min)",
    "slide_6_team": "Opportunity Team Assignments (1 Min)",
    "slide_7_evaluation": "Evaluation Methodology (2 Min)",
    "slide_8_swot": "Opportunity SWOT (2 Min)",
    "slide_9_path_to_blue": "Path to Blue (5 Min)",
    "slide_10_pricing": "Pricing Strategy (3 Min)",
    "slide_11_proposed_pricing": "Proposed Pricing Summary (2 Min)",
    "slide_12_business_case": "Execution Business Case Model (2 Min)",
    "slide_13_risks": "High Risk Elements (3 Min)",
    "slide_14_actions": "Action Plan (2 Min)",
    "slide_15_questions": "Questions? (3–5 Min)",
    "slide_17_approval": "MS1 & MS2 Approval Criteria",
    "slide_18_approval": "MS3 & MS4 Approval Criteria",
}

# Footer slide numbers from reference deck (for operator cross-reference).
SLIDE_DECK_NUMBERS: dict[str, str] = {
    "slide_ref_process_bluf": "—",
    "slide_ref_faq": "—",
    "slide_ref_milestone_overview": "1",
    "slide_ref_promotion_overview": "—",
    "slide_2_cover": "2",
    "slide_3_zero_harm": "3",
    "slide_4_synopsis": "4",
    "slide_5_bluf": "5",
    "slide_6_team": "6",
    "slide_7_evaluation": "7",
    "slide_8_swot": "8",
    "slide_9_path_to_blue": "9",
    "slide_10_pricing": "10",
    "slide_11_proposed_pricing": "11",
    "slide_12_business_case": "12",
    "slide_13_risks": "13",
    "slide_14_actions": "14",
    "slide_15_questions": "15",
    "slide_17_approval": "16",
    "slide_18_approval": "17–18",
}

REFERENCE_SLIDE_SUMMARIES: dict[str, str] = {
    "slide_ref_process_bluf": (
        "Milestone process overview: shorter decks, embedded timing, formal promotion criteria, "
        "earlier pricing ownership at MS2, and CRM automation for synopsis and team slides."
    ),
    "slide_ref_faq": (
        "Teams may adapt or replace slides; not every slide is required per milestone — follow bottom-right "
        "MS markers. Pricing slides owned by Pricing/PP&C from MS2. Quick-turn bids may omit slides."
    ),
    "slide_ref_milestone_overview": (
        "MS1 Qualify (12–24 mo before FRFP), MS2 Pursuit/No Pursuit (9–12 mo), MS3 Bid/No-Bid (DRFP or ~30 days "
        "before FRFP), MS4 Pricing Approval (7–14 days before submission)."
    ),
    "slide_ref_promotion_overview": (
        "Objective promotion checklists per milestone — validate readiness before briefing leadership. "
        "Mirrored on MS1&2 and MS3&4 approval slides in the live deck."
    ),
}

PACKET_SLIDE_ORDER: tuple[tuple[str, str], ...] = (
    ("slide_ref_process_bluf", "Process BLUF"),
    ("slide_ref_faq", "FAQ"),
    ("slide_ref_milestone_overview", "Milestone profiles"),
    ("slide_ref_promotion_overview", "Promotion criteria"),
    ("slide_2_cover", "Cover"),
    ("slide_3_zero_harm", "Zero Harm"),
    ("slide_4_synopsis", "Synopsis"),
    ("slide_5_bluf", "BLUF"),
    ("slide_6_team", "Team assignments"),
    ("slide_7_evaluation", "Evaluation"),
    ("slide_8_swot", "SWOT"),
    ("slide_9_path_to_blue", "Path to Blue"),
    ("slide_10_pricing", "Pricing strategy"),
    ("slide_11_proposed_pricing", "Proposed pricing"),
    ("slide_12_business_case", "Business case"),
    ("slide_13_risks", "Risks"),
    ("slide_14_actions", "Action plan"),
    ("slide_15_questions", "Questions"),
    ("slide_17_approval", "MS1 & MS2 approval"),
    ("slide_18_approval", "MS3 & MS4 approval"),
)

_DEFAULT_SLIDE = "slide_2_cover"

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
    """required | optional | reference | omitted — per milestone marker convention."""
    if slide_id in REFERENCE_SLIDE_IDS:
        return "reference"
    markers = SLIDE_MS_MARKERS.get(slide_id, frozenset({1, 2, 3, 4}))
    optional_markers = SLIDE_MS_OPTIONAL_MARKERS.get(slide_id, frozenset())
    gn = gate_number(gate)
    if gn in markers:
        return "required"
    if gn in optional_markers:
        return "optional"
    if fields_for_gate > 0:
        return "optional"
    return "omitted"


def slide_visible(applicability: str) -> bool:
    return applicability != "omitted"


def is_reference_slide(slide_id: str) -> bool:
    return slide_id in REFERENCE_SLIDE_IDS