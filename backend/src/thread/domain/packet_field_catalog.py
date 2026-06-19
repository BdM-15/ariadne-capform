"""Full briefing packet field catalog — BRIEFING_PACKET_DATA_DICTIONARY.md.

Packet = arrangement of these data elements on slides with MS gate applicability.
"""

from __future__ import annotations

from thread.domain.enums import (
    MilestoneGate,
    PacketFieldRouteKind,
    PacketFieldValueKind,
    PacketSection,
)
from thread.domain.packet_answer_sources import (
    ACTION_PLAN,
    CLEW,
    COMPUTED,
    CRM,
    FINANCE,
    GROK,
    HUMAN,
    MINERU,
    PG_INTEL,
    SAM_MCP,
    USASPENDING_MCP,
    VAULT,
    WEB_RESEARCH,
    AnswerRouteStub,
    resolve_answer_route,
)
from thread.domain.packet_field_seed import (
    ALL_MS,
    MS1_MS2,
    MS1_MS3,
    MS1_ONLY,
    MS2_UP,
    MS3_UP,
    PacketFieldSeed,
)

# Shorthand gates
MS4_ONLY = (MilestoneGate.MILESTONE_4,)


def _f(
    key: str,
    label: str,
    question: str,
    section: PacketSection,
    kind: PacketFieldValueKind,
    gates: tuple[MilestoneGate, ...],
    route: PacketFieldRouteKind,
    slide: str,
    *,
    sources: tuple[str, ...] = (),
    hint: str = "",
    deterministic: bool = False,
    feeds: tuple[str, ...] = (),
    template_only: bool = False,
) -> PacketFieldSeed:
    return PacketFieldSeed(
        key=key,
        label=label,
        question=question,
        section=section,
        value_kind=kind,
        required_gates=gates,
        route_kind=route,
        reference_slide=slide,
        answer_route=resolve_answer_route(
            route,
            sources=sources,
            hint=hint,
            deterministic=deterministic,
            feeds=feeds,
        ),
        template_only=template_only,
    )


def _ms1(key: str, label: str, q: str | None = None) -> PacketFieldSeed:
    return _f(
        key,
        label,
        q or f"Is {label.lower()} satisfied for MS1?",
        PacketSection.RECOMMENDATION_AND_NEXT_ACTIONS,
        PacketFieldValueKind.DECISION,
        MS1_ONLY,
        PacketFieldRouteKind.MODEL_SYNTHESIS,
        "slide_17_approval",
        sources=(VAULT, PG_INTEL, GROK, HUMAN),
        hint="Vault capture notes + intel evidence → Grok criterion answer",
    )


def _ms2(key: str, label: str, q: str | None = None) -> PacketFieldSeed:
    return _f(
        key,
        label,
        q or f"Is {label.lower()} for MS2?",
        PacketSection.RECOMMENDATION_AND_NEXT_ACTIONS,
        PacketFieldValueKind.DECISION,
        MS2_UP,
        PacketFieldRouteKind.MODEL_SYNTHESIS,
        "slide_17_approval",
        sources=(VAULT, CLEW, PG_INTEL, GROK, HUMAN),
        hint="Packet fields + Clew teaming/money_flow + Grok criterion synthesis",
    )


def _ms3(key: str, label: str, q: str | None = None) -> PacketFieldSeed:
    return _f(
        key,
        label,
        q or f"Is {label.lower()} for MS3?",
        PacketSection.RECOMMENDATION_AND_NEXT_ACTIONS,
        PacketFieldValueKind.DECISION,
        MS3_UP,
        PacketFieldRouteKind.MODEL_SYNTHESIS,
        "slide_18_approval",
        sources=(VAULT, CLEW, PG_INTEL, GROK, HUMAN),
        hint="Win/pricing/risk packet bundle → Grok MS3 gate answer",
    )


def _ms4(key: str, label: str, q: str | None = None) -> PacketFieldSeed:
    return _f(
        key,
        label,
        q or f"Is {label.lower()} for MS4?",
        PacketSection.RECOMMENDATION_AND_NEXT_ACTIONS,
        PacketFieldValueKind.DECISION,
        MS4_ONLY,
        PacketFieldRouteKind.SOURCE_BACKED_ANSWER,
        "slide_18_approval",
        sources=(FINANCE, HUMAN, GROK),
        hint="Pricing lead / finance model evidence → leadership sign-off",
    )


def _path_to_blue_row(area_key: str, area_label: str) -> list[PacketFieldSeed]:
    """Path-to-blue pursuit area — progress scale 1–5 (none→complete)."""
    slide = "slide_9_path_to_blue"
    scale_hint = "1=None, 2=Low, 3=Medium, 4=Good, 5=Complete"
    return [
        _f(
            f"{area_key}_previous_status",
            f"{area_label} — Previous Status",
            f"Previous maturity for {area_label.lower()}?",
            PacketSection.SOLUTION_STRATEGY,
            PacketFieldValueKind.TEXT,
            MS1_MS3,
            PacketFieldRouteKind.SOURCE_BACKED_ANSWER,
            slide,
            sources=(HUMAN,),
            hint=scale_hint,
        ),
        _f(
            f"{area_key}_current_status",
            f"{area_label} — Current Status",
            f"Current maturity for {area_label.lower()}?",
            PacketSection.SOLUTION_STRATEGY,
            PacketFieldValueKind.TEXT,
            MS1_MS3,
            PacketFieldRouteKind.SOURCE_BACKED_ANSWER,
            slide,
            sources=(HUMAN,),
            hint=scale_hint,
        ),
        _f(
            f"{area_key}_status_update",
            f"{area_label} — Status Update",
            f"What changed for {area_label.lower()}?",
            PacketSection.SOLUTION_STRATEGY,
            PacketFieldValueKind.PROSE,
            MS1_MS3,
            PacketFieldRouteKind.SOURCE_BACKED_ANSWER,
            slide,
            sources=(HUMAN, ACTION_PLAN),
            hint="Narrative update since last milestone",
        ),
        _f(
            f"{area_key}_next_steps",
            f"{area_label} — Next Steps",
            f"Next steps for {area_label.lower()}?",
            PacketSection.SOLUTION_STRATEGY,
            PacketFieldValueKind.PROSE,
            MS1_MS3,
            PacketFieldRouteKind.SOURCE_BACKED_ANSWER,
            slide,
            sources=(HUMAN, ACTION_PLAN),
            hint="Dated actions closing pursuit gaps",
        ),
    ]


def _team_role(key: str, label: str, gates: tuple[MilestoneGate, ...]) -> PacketFieldSeed:
    return _f(
        key,
        label,
        f"Who is assigned as {label}?",
        PacketSection.OPPORTUNITY_OVERVIEW,
        PacketFieldValueKind.ENTITY,
        gates,
        PacketFieldRouteKind.SOURCE_BACKED_ANSWER,
        "slide_6_team",
        sources=(HUMAN, CRM),
        hint="Org roster / CRM contact or manual assignment",
    )


_CATALOG: list[PacketFieldSeed] = [
    # --- Slide 2 Cover ---
    _f("business_unit", "Business Unit", "Which business unit owns the pursuit?", PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.TEXT, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_2_cover", sources=(HUMAN, CRM), hint="Org profile default or operator"),

    _f("opportunity_name", "Opportunity Name", "What is the pursuit name?", PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.TEXT, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_2_cover", sources=(SAM_MCP, HUMAN), hint="SAM title or operator"),
    _f("milestone_stage", "Milestone Stage", "Active MS gate for this packet review?", PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.TEXT, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_2_cover", sources=(HUMAN,), hint="Operator MS gate selector (Phase 14 remainder)"),
    _f("packet_date", "Packet Date", "Date of this briefing?", PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.DATE, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_2_cover", sources=(HUMAN,), hint="Default today"),
    _f("prepared_by", "Prepared By", "Who prepared this packet?", PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.TEXT, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_2_cover", sources=(HUMAN,), hint="Operator / local profile"),
    _f("preparer_role", "Preparer Role", "Role of preparer (e.g. Capture)?", PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.TEXT, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_2_cover", sources=(HUMAN,), hint="Operator entry"),
    # --- Slide 3 Zero Harm ---
    _f("zero_harm_title", "Zero Harm Moment Title", "Title for Zero Harm slide?", PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.TEXT, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_3_zero_harm", sources=(HUMAN,), hint="Operator-provided safety moment"),
    _f("zero_harm_content", "Zero Harm Content", "Zero Harm moment narrative?", PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.PROSE, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_3_zero_harm", sources=(HUMAN,), hint="Operator prose or attached content"),
    _f("zero_harm_media_ref", "Zero Harm Media", "Visual/media reference?", PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.TEXT, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_3_zero_harm", sources=(HUMAN,), hint="Attachment path or URL"),
    # --- Slide 4 Synopsis — opportunity details ---
    _f("salesforce_id", "Salesforce ID", "CRM opportunity identifier?", PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.TEXT, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_4_synopsis", sources=(CRM, HUMAN), hint="CRM import when wired"),
    _f("draft_rfp_date", "Draft RFP Date", "Expected draft RFP date?", PacketSection.REQUIREMENTS_AND_SCOPE, PacketFieldValueKind.DATE, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_4_synopsis", sources=(SAM_MCP, HUMAN), hint="SAM dates or operator"),
    _f("kbr_role", "Prime/Sub Role", "Prime or subcontractor role?", PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.TEXT, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_4_synopsis", sources=(HUMAN, SAM_MCP), hint="Teaming posture — operator or SAM set-aside context"),
    _f("rfp_release_date", "RFP Release Date", "When is the RFP expected or released?", PacketSection.REQUIREMENTS_AND_SCOPE, PacketFieldValueKind.DATE, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_4_synopsis", sources=(SAM_MCP, HUMAN), deterministic=True, hint="SAM notice response timeline"),
    _f("prime_name", "Prime Name", "Who is expected to prime?", PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.ENTITY, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_4_synopsis", sources=(USASPENDING_MCP, PG_INTEL, CLEW), deterministic=True, hint="USAspending incumbent / Clew money_flow top recipient"),
    _f("proposal_due_date", "Proposal Due Date", "When is the proposal due?", PacketSection.REQUIREMENTS_AND_SCOPE, PacketFieldValueKind.DATE, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_4_synopsis", sources=(SAM_MCP, HUMAN), deterministic=True, hint="SAM notice deadline"),
    _f("crm_stage", "CRM Stage", "CRM lifecycle stage (00–04)?", PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.TEXT, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_4_synopsis", sources=(CRM, HUMAN), hint="CRM sync or operator"),
    _f("award_date", "Award Date", "Expected or actual award date?", PacketSection.REQUIREMENTS_AND_SCOPE, PacketFieldValueKind.DATE, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_4_synopsis", sources=(USASPENDING_MCP, PG_INTEL), deterministic=True, hint="USAspending period of performance end / recompete signal"),
    _f("customer_name", "Customer Name", "Which customer or buying command?", PacketSection.CUSTOMER_CONTEXT, PacketFieldValueKind.ENTITY, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_4_synopsis", sources=(SAM_MCP, USASPENDING_MCP, VAULT), deterministic=True, hint="SAM agency + USAspending awarding agency; vault agency page"),
    _f("contract_start_date", "Contract Start", "Contract start date?", PacketSection.REQUIREMENTS_AND_SCOPE, PacketFieldValueKind.DATE, ALL_MS, PacketFieldRouteKind.SOURCE_PROFILE_LOOKUP, "slide_4_synopsis", sources=(USASPENDING_MCP, PG_INTEL), deterministic=True, hint="USAspending award PoP start"),
    _f("mts_priority", "Capture Priority", "Priority band (A/B/O)?", PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.TEXT, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_4_synopsis", sources=(HUMAN,), hint="Leadership priority assignment"),
    _f("contract_end_date", "Contract End", "Contract end date?", PacketSection.REQUIREMENTS_AND_SCOPE, PacketFieldValueKind.DATE, ALL_MS, PacketFieldRouteKind.SOURCE_PROFILE_LOOKUP, "slide_4_synopsis", sources=(USASPENDING_MCP, PG_INTEL), deterministic=True, hint="USAspending PoP end — recompete radar input", feeds=(CLEW,)),
    _f("financial_contract_type", "Financial Contract Type", "FFP, CPFF, CPAF, T&M, Multiple?", PacketSection.PRICE_TO_WIN, PacketFieldValueKind.TEXT, ALL_MS, PacketFieldRouteKind.SOURCE_PROFILE_LOOKUP, "slide_4_synopsis", sources=(USASPENDING_MCP, PG_INTEL), deterministic=True, hint="USAspending type_of_contract_pricing"),
    _f("total_contract_value", "Total Contract Value", "Total contract value?", PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.MONEY, ALL_MS, PacketFieldRouteKind.SOURCE_PROFILE_LOOKUP, "slide_4_synopsis", sources=(USASPENDING_MCP, PG_INTEL), deterministic=True, hint="USAspending obligated amount on award_key"),
    _f("new_business_or_recompete", "New Business / Recompete", "New business or recompete?", PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.TEXT, ALL_MS, PacketFieldRouteKind.RESEARCH_OR_MCP, "slide_4_synopsis", sources=(PG_INTEL, CLEW, VAULT), hint="Recompete radar + incumbent match on award_key"),
    _f("bookable_revenue", "Bookable Revenue", "Bookable revenue estimate?", PacketSection.PRICE_TO_WIN, PacketFieldValueKind.MONEY, ALL_MS, PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_4_synopsis", sources=(FINANCE, GROK, HUMAN), hint="Finance model or operator"),
    _f("pwin_percent", "pWin %", "Probability of win?", PacketSection.COMPETITIVE_POSITION, PacketFieldValueKind.PERCENTAGE, ALL_MS, PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_4_synopsis", sources=(PG_INTEL, CLEW, VAULT, GROK), hint="Competitive intel + Grok estimate — review gate"),
    _f("operating_income_margin_percent", "Operating Income Margin", "Operating income margin %?", PacketSection.PRICE_TO_WIN, PacketFieldValueKind.PERCENTAGE, ALL_MS, PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_4_synopsis", sources=(FINANCE, GROK), hint="Finance model"),
    _f("primary_scope_description", "Primary Scope", "Description of work / primary scope?", PacketSection.REQUIREMENTS_AND_SCOPE, PacketFieldValueKind.PROSE, ALL_MS, PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_4_synopsis", sources=(SAM_MCP, MINERU, GROK), hint="SAM description + MinerU SOW parse → Grok summary"),
    _f("number_of_ftes", "Number of FTEs", "Estimated FTE count?", PacketSection.REQUIREMENTS_AND_SCOPE, PacketFieldValueKind.TEXT, ALL_MS, PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_4_synopsis", sources=(MINERU, GROK, HUMAN), hint="SOW evidence or staffing model"),
    _f("competition_company_1_name", "Competitor 1", "Primary competitor / incumbent?", PacketSection.COMPETITIVE_POSITION, PacketFieldValueKind.ENTITY, ALL_MS, PacketFieldRouteKind.RESEARCH_OR_MCP, "slide_4_synopsis", sources=(USASPENDING_MCP, PG_INTEL, CLEW), deterministic=True, hint="USAspending top recipient on NAICS/agency facet"),
    _f("competition_company_1_role", "Competitor 1 Role", "Incumbent or challenger role?", PacketSection.COMPETITIVE_POSITION, PacketFieldValueKind.TEXT, ALL_MS, PacketFieldRouteKind.RESEARCH_OR_MCP, "slide_4_synopsis", sources=(PG_INTEL, CLEW), hint="Incumbent if matches award recipient"),
    _f("competition_company_2_name", "Competitor 2", "Second competitor?", PacketSection.COMPETITIVE_POSITION, PacketFieldValueKind.ENTITY, ALL_MS, PacketFieldRouteKind.RESEARCH_OR_MCP, "slide_4_synopsis", sources=(CLEW, PG_INTEL, WEB_RESEARCH), hint="Clew recipient_landscape rank 2"),
    _f("competition_company_2_role", "Competitor 2 Role", "Role/notes for competitor 2?", PacketSection.COMPETITIVE_POSITION, PacketFieldValueKind.TEXT, ALL_MS, PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_4_synopsis", sources=(WEB_RESEARCH, GROK), hint="Research + synthesis"),
    _f("competition_company_3_name", "Competitor 3", "Third competitor?", PacketSection.COMPETITIVE_POSITION, PacketFieldValueKind.ENTITY, ALL_MS, PacketFieldRouteKind.RESEARCH_OR_MCP, "slide_4_synopsis", sources=(CLEW, PG_INTEL), hint="Clew landscape rank 3"),
    _f("competition_company_3_role", "Competitor 3 Role", "Role/notes for competitor 3?", PacketSection.COMPETITIVE_POSITION, PacketFieldValueKind.TEXT, ALL_MS, PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_4_synopsis", sources=(WEB_RESEARCH, GROK), hint="Research + synthesis"),
    _f("small_business_goal", "Small Business Goal", "Small business participation goal?", PacketSection.REQUIREMENTS_AND_SCOPE, PacketFieldValueKind.TEXT, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_4_synopsis", sources=(SAM_MCP, MINERU), hint="SAM set-aside / solicitation text"),
    _f("special_considerations", "Special Considerations", "Special acquisition considerations?", PacketSection.REQUIREMENTS_AND_SCOPE, PacketFieldValueKind.PROSE, ALL_MS, PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_4_synopsis", sources=(SAM_MCP, MINERU, GROK), hint="Solicitation flags → Grok summary"),
    # --- Slide 5 BLUF ---
    _f("opportunity_context", "Opportunity Context", "What does leadership need to know?", PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.PROSE, ALL_MS, PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_5_bluf", sources=(VAULT, PG_INTEL, SAM_MCP, GROK), hint="Vault + intel + SAM → Grok BLUF context"),
    _f("strategic_fit_summary", "Strategic Fit", "Fit against BU/Division strategy?", PacketSection.SOLUTION_STRATEGY, PacketFieldValueKind.PROSE, MS1_MS2, PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_5_bluf", sources=(VAULT, GROK, HUMAN), hint="domain_intel capabilities + Grok"),
    _f("acquisition_capture_progress", "Capture Progress", "Acquisition/capture progress?", PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.PROSE, ALL_MS, PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_5_bluf", sources=(ACTION_PLAN, VAULT, GROK), hint="Action plan status + vault notes"),
    _f("customer_need_funding_status", "Customer Need / Funding", "Ongoing need and funding context?", PacketSection.CUSTOMER_CONTEXT, PacketFieldValueKind.PROSE, ALL_MS, PacketFieldRouteKind.CUSTOMER_CALL_PLAN, "slide_5_bluf", sources=(USASPENDING_MCP, WEB_RESEARCH, VAULT, GROK), hint="USAspending agency spend + customer research"),
    _f("competitive_landscape_summary", "Competitive Landscape", "Overall competitive landscape?", PacketSection.COMPETITIVE_POSITION, PacketFieldValueKind.PROSE, ALL_MS, PacketFieldRouteKind.RESEARCH_OR_MCP, "slide_5_bluf", sources=(CLEW, PG_INTEL, VAULT, WEB_RESEARCH, GROK), hint="Clew traces + vault competitors → Grok prose"),
    _f("ms1_bluf_focus", "MS1 BLUF Focus", "MS1 focus: market intel, relationships, B&P?", PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.PROSE, MS1_ONLY, PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_5_bluf", sources=(PG_INTEL, VAULT, GROK), hint="Intel inbox + vault for qualification gate"),
    _f("ms2_bluf_focus", "MS2 BLUF Focus", "MS2 focus: engagement, gaps, teaming, B&P?", PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.PROSE, MS2_UP, PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_5_bluf", sources=(CLEW, VAULT, GROK), hint="Teaming + gap-fill Clew modes"),
    _f("ms3_bluf_focus", "MS3 BLUF Focus", "MS3 focus: closure, staffing, B&P?", PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.PROSE, MS3_UP, PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_5_bluf", sources=(VAULT, GROK, HUMAN), hint="Packet completion + staffing status"),
    _f("what_it_takes_to_win", "What Will It Take To Win?", "Capture and ops hurdles to win?", PacketSection.SOLUTION_STRATEGY, PacketFieldValueKind.PROSE, MS2_UP, PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_5_bluf", sources=(VAULT, CLEW, GROK), hint="SWOT + Clew + vault win themes"),
    _f("recommendation", "Recommendation", "Leadership-ready recommendation?", PacketSection.RECOMMENDATION_AND_NEXT_ACTIONS, PacketFieldValueKind.DECISION, ALL_MS, PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_5_bluf", sources=(GROK, HUMAN), hint="Synthesis of packet gaps → proceed/hold/no-bid"),
    # --- Slide 6 Team ---
    _f("operating_unit", "Operating Unit (OU)", "Which operating unit owns the pursuit?", PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.TEXT, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_6_team", sources=(HUMAN, CRM), hint="Assigned at MS1 — org profile or operator"),
    _team_role("business_unit_division", "Business Unit Division", ALL_MS),
    _team_role("capture_manager", "Capture Manager", ALL_MS),
    _team_role("operations_leader", "Operations Leader", ALL_MS),
    _team_role("solution_architect", "Solution Architect", ALL_MS),
    _team_role("proposal_manager", "Proposal Manager", ALL_MS),
    _team_role("proposal_coordinator", "Proposal Coordinator", ALL_MS),
    _team_role("contracts_lead", "Contracts Lead", ALL_MS),
    _team_role("technical_lead", "Technical Lead", ALL_MS),
    _team_role("staffing_boe_lead", "Staffing/BOE Lead", ALL_MS),
    _team_role("pricing_lead", "Pricing Lead", ALL_MS),
    _team_role("program_manager", "Program Manager", ALL_MS),
    _f("consultants", "Consultants", "Consultant resources?", PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.PROSE, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_6_team", sources=(HUMAN,), hint="Team roster"),
    _f("subject_matter_experts", "Subject Matter Experts", "SME resources?", PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.PROSE, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_6_team", sources=(HUMAN,), hint="Team roster — list format"),
    _f("other_resources", "Other Resources", "Other pursuit resources?", PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.PROSE, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_6_team", sources=(HUMAN,), hint="Team roster"),
    _f("subcontracts_functional_lead", "Subcontracts Lead", "Subcontracts functional lead?", PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.ENTITY, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_6_team", sources=(HUMAN,), hint="Functional lead assignment"),
    _f("talent_acquisition_functional_lead", "Talent Acquisition Lead", "TA functional lead?", PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.ENTITY, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_6_team", sources=(HUMAN,), hint="Functional lead assignment"),
    _f("human_resources_functional_lead", "Human Resources Lead", "HR functional lead?", PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.ENTITY, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_6_team", sources=(HUMAN,), hint="Functional lead assignment"),
    _f("finance_functional_lead", "Finance Lead", "Finance functional lead?", PacketSection.OPPORTUNITY_OVERVIEW, PacketFieldValueKind.ENTITY, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_6_team", sources=(HUMAN,), hint="Functional lead assignment"),
    _f("non_us_persons_participate", "Non-US Persons Participate?", "Will non-US persons participate?", PacketSection.RISKS_AND_GAPS, PacketFieldValueKind.BOOLEAN, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_6_team", sources=(HUMAN,), hint="Legal/compliance input"),
    _f("bp_funding_request_amount", "B&P Request", "B&P funding request amount?", PacketSection.PRICE_TO_WIN, PacketFieldValueKind.MONEY, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_6_team", sources=(FINANCE, HUMAN), hint="B&P Funding Request line on team slide"),
    _f("bp_notes", "B&P Notes", "B&P funding notes?", PacketSection.PRICE_TO_WIN, PacketFieldValueKind.PROSE, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_6_team", sources=(HUMAN,), hint="B&P Notes line on team slide"),
    # --- Slide 7 Evaluation ---
    _f("evaluation_document_date", "Evaluation Document Date", "Date of evaluation documents?", PacketSection.REQUIREMENTS_AND_SCOPE, PacketFieldValueKind.DATE, MS2_UP, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_7_evaluation", sources=(MINERU, SAM_MCP), hint="RFP Section M date"),
    _f("technical_volume_rating_method", "Technical Volume Rating", "Technical rating method?", PacketSection.REQUIREMENTS_AND_SCOPE, PacketFieldValueKind.TEXT, MS2_UP, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_7_evaluation", sources=(MINERU,), hint="Section M extract"),
    _f("management_volume_rating_method", "Management Volume Rating", "Management rating method?", PacketSection.REQUIREMENTS_AND_SCOPE, PacketFieldValueKind.TEXT, MS2_UP, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_7_evaluation", sources=(MINERU,), hint="Section M extract"),
    _f("past_performance_rating_method", "Past Performance Rating", "Past performance rating method?", PacketSection.REQUIREMENTS_AND_SCOPE, PacketFieldValueKind.TEXT, MS2_UP, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_7_evaluation", sources=(MINERU,), hint="Section M extract"),
    _f("cost_price_evaluation_method", "Cost/Price Evaluation", "Cost/price evaluation approach?", PacketSection.REQUIREMENTS_AND_SCOPE, PacketFieldValueKind.PROSE, MS2_UP, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_7_evaluation", sources=(MINERU, GROK), hint="Section M + synthesis"),
    _f("basis_of_evaluated_price", "Basis of Evaluated Price", "Basis of evaluated price?", PacketSection.PRICE_TO_WIN, PacketFieldValueKind.PROSE, MS3_UP, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_7_evaluation", sources=(MINERU,), hint="RFP pricing instructions"),
    _f("relative_importance_of_evaluation_factors", "Evaluation Factor Importance", "Relative importance of factors?", PacketSection.REQUIREMENTS_AND_SCOPE, PacketFieldValueKind.PROSE, MS2_UP, PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_7_evaluation", sources=(MINERU, GROK), hint="Section M → Grok summary"),
    _f("observed_customer_award_trends", "Customer Award Trends", "Observed customer award trends?", PacketSection.COMPETITIVE_POSITION, PacketFieldValueKind.PROSE, MS2_UP, PacketFieldRouteKind.RESEARCH_OR_MCP, "slide_7_evaluation", sources=(PG_INTEL, CLEW, WEB_RESEARCH, GROK), hint="Historical awards + research"),
    _f("evaluation_factors", "Evaluation Factors Table", "Factor/subfactor table (JSON rows)?", PacketSection.REQUIREMENTS_AND_SCOPE, PacketFieldValueKind.PROSE, MS2_UP, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_7_evaluation", sources=(MINERU,), hint="Structured Section M parse"),
    # --- Slide 8 SWOT (required MS1–MS3 per deck marker) ---
    _f("swot_strengths", "SWOT Strengths", "Key strengths?", PacketSection.COMPETITIVE_POSITION, PacketFieldValueKind.PROSE, ALL_MS, PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_8_swot", sources=(VAULT, PG_INTEL, GROK), hint="Capabilities + past performance evidence"),
    _f("swot_weaknesses", "SWOT Weaknesses", "Key weaknesses?", PacketSection.COMPETITIVE_POSITION, PacketFieldValueKind.PROSE, ALL_MS, PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_8_swot", sources=(VAULT, CLEW, GROK), hint="Gap-fill teaming + honest gap analysis"),
    _f("swot_opportunities", "SWOT Opportunities", "Key opportunities?", PacketSection.COMPETITIVE_POSITION, PacketFieldValueKind.PROSE, ALL_MS, PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_8_swot", sources=(PG_INTEL, WEB_RESEARCH, GROK), hint="Market signals + research"),
    _f("swot_threats", "SWOT Threats", "Key threats?", PacketSection.COMPETITIVE_POSITION, PacketFieldValueKind.PROSE, ALL_MS, PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_8_swot", sources=(CLEW, WEB_RESEARCH, GROK), hint="Competitor concentration + intel"),
    # --- Slide 9 Path to Blue ---
    _f("path_to_blue_strategic_fit", "Path to Blue — Strategic Fit", "Strategic fit progress?", PacketSection.SOLUTION_STRATEGY, PacketFieldValueKind.PROSE, MS1_MS3, PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_9_path_to_blue", sources=(VAULT, GROK), hint="Strategy alignment synthesis"),
    _f("path_to_blue_leadership_highlights", "Path to Blue — Leadership", "Leadership highlights?", PacketSection.SOLUTION_STRATEGY, PacketFieldValueKind.PROSE, MS1_MS3, PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_9_path_to_blue", sources=(GROK, HUMAN), hint="Customer engagement highlights"),
    _f("path_to_blue_win_strategy", "Path to Blue — Win Strategy", "Win strategy progress?", PacketSection.SOLUTION_STRATEGY, PacketFieldValueKind.PROSE, MS1_MS3, PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_9_path_to_blue", sources=(VAULT, GROK), hint="Win themes from vault + packet"),
    *_path_to_blue_row("opportunity_shaping_customer_engagement", "Customer Engagement"),
    *_path_to_blue_row("path_pricing_strategy", "Pricing Strategy"),
    *_path_to_blue_row("staffing_key_personnel", "Staffing / Key Personnel"),
    *_path_to_blue_row("tech_solutioning", "Tech Solutioning"),
    *_path_to_blue_row("other_teaming_capex_facilities", "Teaming / CapEx / Facilities"),
    # --- Slide 10 Pricing Strategy ---
    _f("pricing_strategy_summary", "Pricing Strategy Summary", "Pricing strategy overview?", PacketSection.PRICE_TO_WIN, PacketFieldValueKind.PROSE, MS2_UP, PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_10_pricing", sources=(FINANCE, VAULT, GROK), hint="PTW + competitive pricing synthesis"),
    _f("customer_pricing_estimating_guidance", "Customer Pricing Guidance", "Customer pricing/estimating guidance?", PacketSection.PRICE_TO_WIN, PacketFieldValueKind.PROSE, MS2_UP, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_10_pricing", sources=(MINERU,), hint="RFP pricing instructions"),
    _f("pricing_variables", "Pricing Variables", "Key pricing variables?", PacketSection.PRICE_TO_WIN, PacketFieldValueKind.PROSE, MS3_UP, PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_10_pricing", sources=(FINANCE, GROK), hint="Pricing model drivers"),
    _f("kbr_position_relative_to_competition", "Position vs Competition", "Price position vs competition?", PacketSection.PRICE_TO_WIN, PacketFieldValueKind.PROSE, MS3_UP, PacketFieldRouteKind.RESEARCH_OR_MCP, "slide_10_pricing", sources=(CLEW, PG_INTEL, GROK), hint="Incumbent spend + competitive landscape"),
    _f("pricing_strategy_risks_opportunities", "Pricing Risks/Opportunities", "Pricing risks and opportunities?", PacketSection.PRICE_TO_WIN, PacketFieldValueKind.PROSE, MS3_UP, PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_10_pricing", sources=(GROK,), hint="Derived from pricing strategy"),
    # --- Slide 11 Proposed Pricing ---
    _f("proposed_price_available", "Proposed Price Available?", "Is proposed price available for this MS?", PacketSection.PRICE_TO_WIN, PacketFieldValueKind.BOOLEAN, MS3_UP, PacketFieldRouteKind.COMPUTED, "slide_11_proposed_pricing", sources=(COMPUTED,), deterministic=True, hint="Derived from stage + pricing data presence"),
    _f("proposed_pricing_summary", "Proposed Pricing Summary", "Proposed pricing summary?", PacketSection.PRICE_TO_WIN, PacketFieldValueKind.PROSE, MS3_UP, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_11_proposed_pricing", sources=(FINANCE, HUMAN), hint="Pricing lead input"),
    _f("evaluated_price", "Evaluated Price", "Evaluated price?", PacketSection.PRICE_TO_WIN, PacketFieldValueKind.MONEY, MS3_UP, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_11_proposed_pricing", sources=(FINANCE,), hint="Pricing model output"),
    _f("price_metrics", "Price Metrics", "Other price metrics?", PacketSection.PRICE_TO_WIN, PacketFieldValueKind.PROSE, MS3_UP, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_11_proposed_pricing", sources=(FINANCE,), hint="Pricing model rows"),
    _f("price_to_win_comparison", "Price-to-Win Comparison", "Compare to PTW recommendations?", PacketSection.PRICE_TO_WIN, PacketFieldValueKind.PROSE, MS3_UP, PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_11_proposed_pricing", sources=(FINANCE, GROK), hint="PTW analysis synthesis"),
    _f("pricing_summary_rows", "Pricing Summary Rows", "Major cost elements by period?", PacketSection.PRICE_TO_WIN, PacketFieldValueKind.PROSE, MS3_UP, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_11_proposed_pricing", sources=(FINANCE,), hint="Pricing import / model"),
    # --- Slide 12 Business Case ---
    _f("business_case_summary", "Business Case Summary", "Execution business case summary?", PacketSection.PRICE_TO_WIN, PacketFieldValueKind.PROSE, MS2_UP, PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_12_business_case", sources=(FINANCE, GROK), hint="Finance narrative"),
    _f("business_case_rows", "Business Case Rows", "Cost element table?", PacketSection.PRICE_TO_WIN, PacketFieldValueKind.PROSE, MS2_UP, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_12_business_case", sources=(FINANCE,), hint="Finance model import"),
    _f("conservative_revenue", "Conservative Revenue", "Conservative revenue?", PacketSection.PRICE_TO_WIN, PacketFieldValueKind.MONEY, MS2_UP, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_12_business_case", sources=(FINANCE,), hint="Model output"),
    _f("optimistic_revenue", "Optimistic Revenue", "Optimistic revenue?", PacketSection.PRICE_TO_WIN, PacketFieldValueKind.MONEY, MS2_UP, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_12_business_case", sources=(FINANCE,), hint="Model output"),
    _f("conservative_op_margin_percent", "Conservative OP Margin", "Conservative operating margin %?", PacketSection.PRICE_TO_WIN, PacketFieldValueKind.PERCENTAGE, MS2_UP, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_12_business_case", sources=(FINANCE,), hint="Model output"),
    _f("optimistic_op_margin_percent", "Optimistic OP Margin", "Optimistic operating margin %?", PacketSection.PRICE_TO_WIN, PacketFieldValueKind.PERCENTAGE, MS2_UP, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_12_business_case", sources=(FINANCE,), hint="Model output"),
    _f("cashflow_summary", "Cashflow Summary", "Cashflow summary?", PacketSection.PRICE_TO_WIN, PacketFieldValueKind.PROSE, MS2_UP, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_12_business_case", sources=(FINANCE,), hint="Finance model"),
    # --- Slide 13 Risks ---
    _f("proposal_risks", "Proposal Risks", "Proposal-phase risks?", PacketSection.RISKS_AND_GAPS, PacketFieldValueKind.PROSE, ALL_MS, PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_13_risks", sources=(MINERU, GROK, HUMAN), hint="Compliance/shred gaps → risk rows"),
    _f("execution_risks", "Execution Risks", "Execution-phase risks?", PacketSection.RISKS_AND_GAPS, PacketFieldValueKind.PROSE, ALL_MS, PacketFieldRouteKind.MODEL_SYNTHESIS, "slide_13_risks", sources=(VAULT, GROK, HUMAN), hint="Ops/past performance risk synthesis"),
    # --- Slide 14 Actions ---
    _f("action_plan_items", "Action Plan Items", "Capture action plan rows?", PacketSection.RECOMMENDATION_AND_NEXT_ACTIONS, PacketFieldValueKind.PROSE, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_14_actions", sources=(ACTION_PLAN,), deterministic=True, hint="Sync from workspace Actions matrix"),
    # --- Slide 15 Questions ---
    _f("questions_slide_enabled", "Questions Slide Enabled?", "Include questions slide?", PacketSection.RECOMMENDATION_AND_NEXT_ACTIONS, PacketFieldValueKind.BOOLEAN, ALL_MS, PacketFieldRouteKind.SOURCE_BACKED_ANSWER, "slide_15_questions", sources=(HUMAN,), hint="Template toggle", template_only=True),
    # --- Slide 17 MS1 & MS2 approval ---
    _ms1("ms1_strategic_fit_confirmed", "Strategic fit confirmed?"),
    _ms1("ms1_customer_decision_maker_identified", "Customer decision-maker identified?"),
    _ms1("ms1_customer_access_plan_established", "Viable customer access plan established?"),
    _ms1("ms1_customer_funding_and_opportunity_credible", "Customer funding and opportunity credible?"),
    _ms1("ms1_acquisition_timeline_defined", "Anticipated acquisition timeline defined?"),
    _ms1("ms1_acquisition_strategy_understood", "Customer acquisition strategy understood?"),
    _ms1("ms1_business_unit_identified_accountable", "Business Unit identified and accountable?"),
    _ms1("ms1_capture_manager_available_qualified", "Capture Manager available and qualified?"),
    _ms1("ms1_oci_sweep_initiated", "OCI Sweep initiated?"),
    _ms2("ms2_capture_strategy_plan_validated", "Capture strategy and plan validated?"),
    _ms2("ms2_teaming_strategy_validated", "Teaming strategy validated?"),
    _ms2("ms2_teaming_agreements_ready", "Teaming agreements ready for execution?"),
    _ms2("ms2_pursuit_team_available_qualified", "Pursuit Team available and qualified?"),
    _ms2("ms2_initial_pricing_strategy_acceptable", "Initial pricing strategy acceptable?"),
    _ms2("ms2_oci_assessment_complete_acceptable", "OCI assessment complete and acceptable?"),
    _ms2("ms2_pwin_reassessed_matured", "pWin reassessed and matured?"),
    _ms2("ms2_unique_hiring_investment_expenses_approved", "Unique hiring/investment expenses approved?"),
    _ms2("ms2_bp_budget_estimate_approved", "B&P budget estimate approved?"),
    # --- Slide 18 MS3 & MS4 approval ---
    _ms3("ms3_trigger_condition_met", "DRFP released or FRFP expected ~30 days?"),
    _ms3("ms3_influence_activities_success", "Influence activities demonstrated success?"),
    _ms3("ms3_teaming_strategy_subcontractor_selection_in_place", "Teaming strategy and subs in place?"),
    _ms3("ms3_win_strategy_validated", "Win strategy validated?"),
    _ms3("ms3_oci_reassessed_acceptable", "OCI reassessed and acceptable?"),
    _ms3("ms3_pwin_reassessed_matured", "pWin reassessed and matured?"),
    _ms3("ms3_pricing_strategy_ptw_approved", "Pricing strategy and PTW approved?"),
    _ms3("ms3_execution_risks_acceptable", "Execution risks acceptable?"),
    _ms3("ms3_bp_budget_adjustments_approved", "B&P budget adjustments approved?"),
    _ms4("ms4_compelling_compliant_proposal_developed", "Compelling compliant proposal developed?"),
    _ms4("ms4_pricing_acceptable", "Pricing acceptable?"),
    _ms4("ms4_execution_risks_continue_acceptable", "Execution risks continue acceptable?"),
]

_seen: set[str] = set()
_deduped: list[PacketFieldSeed] = []
for _seed in _CATALOG:
    if _seed.key in _seen:
        continue
    _seen.add(_seed.key)
    _deduped.append(_seed)
PACKET_FIELD_SEEDS: tuple[PacketFieldSeed, ...] = tuple(_deduped)

FIELD_SEED_BY_KEY: dict[str, PacketFieldSeed] = {s.key: s for s in PACKET_FIELD_SEEDS}

# Opportunity-answerable fields (excludes template-only)
PACKET_ANSWERABLE_SEEDS: tuple[PacketFieldSeed, ...] = tuple(
    s for s in PACKET_FIELD_SEEDS if not s.template_only
)