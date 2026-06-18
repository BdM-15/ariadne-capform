"""Packet field definitions seeded from BRIEFING_PACKET_DATA_DICTIONARY.md (MS1+ core).

Source: docs/reference/briefing_packet/BRIEFING_PACKET_DATA_DICTIONARY.md
Extend by parsing the full dictionary or adding rows from call_plan / risk_register cross-links.
"""

from __future__ import annotations

from dataclasses import dataclass

from thread.domain.enums import (
    MilestoneGate,
    PacketFieldRouteKind,
    PacketFieldValueKind,
    PacketSection,
)

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


# MS1-critical + high-value fields for MVP shell (expand toward full dictionary)
PACKET_FIELD_SEEDS: tuple[PacketFieldSeed, ...] = (
    PacketFieldSeed(
        "opportunity_name", "Opportunity Name", "What is the pursuit name?",
        PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.TEXT, ALL_MS,
        PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_2_cover",
    ),
    PacketFieldSeed(
        "customer_name", "Customer Name", "Which customer or buying command owns the need?",
        PacketSection.CUSTOMER_CONTEXT, PacketFieldValueKind.ENTITY, ALL_MS,
        PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_4_synopsis",
    ),
    PacketFieldSeed(
        "salesforce_id", "Salesforce ID", "CRM opportunity identifier?",
        PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.TEXT, ALL_MS,
        PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_4_synopsis",
    ),
    PacketFieldSeed(
        "rfp_release_date", "RFP Release Date", "When is the RFP expected or released?",
        PacketSection.REQUIREMENTS_AND_SCOPE, PacketFieldValueKind.DATE, MS2_UP,
        PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_4_synopsis",
    ),
    PacketFieldSeed(
        "proposal_due_date", "Proposal Due Date", "When is the proposal due?",
        PacketSection.REQUIREMENTS_AND_SCOPE, PacketFieldValueKind.DATE, MS2_UP,
        PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_4_synopsis",
    ),
    PacketFieldSeed(
        "prime_name", "Prime Name", "Who is expected to prime the pursuit?",
        PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.ENTITY, ALL_MS,
        PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_4_synopsis",
    ),
    PacketFieldSeed(
        "total_contract_value", "Total Contract Value", "What is the total contract value?",
        PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.MONEY, ALL_MS,
        PacketFieldRouteKind.SOURCE_PROFILE_LOOKUP, "slide_4_synopsis",
    ),
    PacketFieldSeed(
        "pwin_percent", "pWin %", "What is the probability of win?",
        PacketSection.COMPETITIVE_POSITION, PacketFieldValueKind.PERCENTAGE, MS2_UP,
        PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_4_synopsis",
    ),
    PacketFieldSeed(
        "primary_scope_description", "Primary Scope", "Description of work / primary scope?",
        PacketSection.REQUIREMENTS_AND_SCOPE, PacketFieldValueKind.PROSE, ALL_MS,
        PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_4_synopsis",
    ),
    PacketFieldSeed(
        "competitive_landscape_summary", "Competitive Landscape", "Overall competitive landscape?",
        PacketSection.COMPETITIVE_POSITION, PacketFieldValueKind.PROSE, ALL_MS,
        PacketFieldRouteKind.RESEARCH_OR_MCP, "slide_5_bluf",
    ),
    PacketFieldSeed(
        "opportunity_context", "Opportunity Context", "What does leadership need to know?",
        PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.PROSE, ALL_MS,
        PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_5_bluf",
    ),
    PacketFieldSeed(
        "what_it_takes_to_win", "What Will It Take To Win?", "Capture and ops hurdles to win?",
        PacketSection.SOLUTION_STRATEGY, PacketFieldValueKind.PROSE, MS2_UP,
        PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_5_bluf",
    ),
    PacketFieldSeed(
        "recommendation", "Recommendation", "Leadership-ready recommendation?",
        PacketSection.RECOMMENDATION_AND_NEXT_ACTIONS, PacketFieldValueKind.DECISION, ALL_MS,
        PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_5_bluf",
    ),
    PacketFieldSeed(
        "pricing_strategy_summary", "Pricing Strategy Summary", "Pricing strategy overview?",
        PacketSection.PRICE_TO_WIN, PacketFieldValueKind.PROSE, MS2_UP,
        PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_10_pricing",
    ),
    PacketFieldSeed(
        "swot_strengths", "SWOT Strengths", "Key strengths?",
        PacketSection.COMPETITIVE_POSITION, PacketFieldValueKind.PROSE, MS2_UP,
        PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_8_swot",
    ),
    PacketFieldSeed(
        "swot_weaknesses", "SWOT Weaknesses", "Key weaknesses?",
        PacketSection.COMPETITIVE_POSITION, PacketFieldValueKind.PROSE, MS2_UP,
        PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_8_swot",
    ),
    PacketFieldSeed(
        "proposal_risks", "Proposal Risks", "Proposal-phase risks?",
        PacketSection.RISKS_AND_GAPS, PacketFieldValueKind.PROSE, MS2_UP,
        PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_13_risks",
    ),
    PacketFieldSeed(
        "execution_risks", "Execution Risks", "Execution-phase risks?",
        PacketSection.RISKS_AND_GAPS, PacketFieldValueKind.PROSE, MS2_UP,
        PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_13_risks",
    ),
    PacketFieldSeed(
        "capture_manager", "Capture Manager", "Who owns capture?",
        PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.ENTITY, MS1_ONLY,
        PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_6_team",
    ),
    PacketFieldSeed(
        "milestone_stage", "Milestone Stage", "Active MS gate for this packet review?",
        PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.TEXT, ALL_MS,
        PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_2_cover",
    ),
    # Slide 17 — MS1 & MS2 approval criteria (expand toward full dictionary)
    PacketFieldSeed(
        "ms1_strategic_fit_confirmed", "Strategic fit confirmed?",
        "Is strategic fit confirmed for qualification?",
        PacketSection.RECOMMENDATION_AND_NEXT_ACTIONS, PacketFieldValueKind.DECISION, MS1_ONLY,
        PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_17_approval",
    ),
    PacketFieldSeed(
        "ms1_capture_manager_available_qualified", "Capture Manager available and qualified?",
        "Is a qualified Capture Manager available?",
        PacketSection.RECOMMENDATION_AND_NEXT_ACTIONS, PacketFieldValueKind.DECISION, MS1_ONLY,
        PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_17_approval",
    ),
    PacketFieldSeed(
        "ms2_capture_strategy_plan_validated", "Capture strategy and plan validated?",
        "Is the capture strategy and plan validated for pursuit?",
        PacketSection.RECOMMENDATION_AND_NEXT_ACTIONS, PacketFieldValueKind.DECISION, MS2_UP,
        PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_17_approval",
    ),
    PacketFieldSeed(
        "ms2_pwin_reassessed_matured", "pWin reassessed and matured?",
        "Has pWin been reassessed and matured for MS2?",
        PacketSection.COMPETITIVE_POSITION, PacketFieldValueKind.DECISION, MS2_UP,
        PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_17_approval",
    ),
    # Slide 18 — MS3 & MS4 approval criteria
    PacketFieldSeed(
        "ms3_win_strategy_validated", "Win strategy validated?",
        "Is the win strategy validated for bid/no-bid?",
        PacketSection.SOLUTION_STRATEGY, PacketFieldValueKind.DECISION, MS3_UP,
        PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_18_approval",
    ),
    PacketFieldSeed(
        "ms3_pricing_strategy_ptw_approved", "Pricing strategy and PTW approved?",
        "Are pricing strategy and price-to-win approved?",
        PacketSection.PRICE_TO_WIN, PacketFieldValueKind.DECISION, MS3_UP,
        PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_18_approval",
    ),
    PacketFieldSeed(
        "ms4_pricing_acceptable", "Pricing acceptable?",
        "Is final pricing acceptable for submission?",
        PacketSection.PRICE_TO_WIN, PacketFieldValueKind.DECISION, (MilestoneGate.MILESTONE_4,),
        PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_18_approval",
    ),
)