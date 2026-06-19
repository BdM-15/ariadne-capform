"""Phase 14f / 14l — full data dictionary catalog + MS gate alignment."""

from thread.domain.enums import MilestoneGate
from thread.domain.packet_field_catalog import PACKET_FIELD_SEEDS
from thread.domain.packet_field_seed import FIELD_SEED_BY_KEY, PACKET_ANSWERABLE_SEEDS

# All MS approval criteria from BRIEFING_PACKET_DATA_DICTIONARY.md
MS1_CRITERIA = (
    "ms1_strategic_fit_confirmed",
    "ms1_customer_decision_maker_identified",
    "ms1_customer_access_plan_established",
    "ms1_customer_funding_and_opportunity_credible",
    "ms1_acquisition_timeline_defined",
    "ms1_acquisition_strategy_understood",
    "ms1_business_unit_identified_accountable",
    "ms1_capture_manager_available_qualified",
    "ms1_oci_sweep_initiated",
)

MS2_CRITERIA = (
    "ms2_capture_strategy_plan_validated",
    "ms2_teaming_strategy_validated",
    "ms2_teaming_agreements_ready",
    "ms2_pursuit_team_available_qualified",
    "ms2_initial_pricing_strategy_acceptable",
    "ms2_oci_assessment_complete_acceptable",
    "ms2_pwin_reassessed_matured",
    "ms2_unique_hiring_investment_expenses_approved",
    "ms2_bp_budget_estimate_approved",
)

MS3_CRITERIA = (
    "ms3_trigger_condition_met",
    "ms3_influence_activities_success",
    "ms3_teaming_strategy_subcontractor_selection_in_place",
    "ms3_win_strategy_validated",
    "ms3_oci_reassessed_acceptable",
    "ms3_pwin_reassessed_matured",
    "ms3_pricing_strategy_ptw_approved",
    "ms3_execution_risks_acceptable",
    "ms3_bp_budget_adjustments_approved",
)

MS4_CRITERIA = (
    "ms4_compelling_compliant_proposal_developed",
    "ms4_pricing_acceptable",
    "ms4_execution_risks_continue_acceptable",
)

TEAM_SLIDE_MS1_FIELDS = (
    "operating_unit",
    "capture_manager",
    "bp_funding_request_amount",
    "bp_notes",
    "non_us_persons_participate",
)

PATH_TO_BLUE_ROW_SUFFIXES = (
    "_previous_status",
    "_current_status",
    "_status_update",
    "_next_steps",
)

PATH_TO_BLUE_AREAS = (
    "opportunity_shaping_customer_engagement",
    "path_pricing_strategy",
    "staffing_key_personnel",
    "tech_solutioning",
    "other_teaming_capex_facilities",
)


def test_catalog_covers_full_dictionary_scale():
    assert len(PACKET_ANSWERABLE_SEEDS) >= 135
    assert len(PACKET_FIELD_SEEDS) >= len(PACKET_ANSWERABLE_SEEDS)


def test_no_duplicate_keys():
    keys = [s.key for s in PACKET_FIELD_SEEDS]
    assert len(keys) == len(set(keys))


def test_all_approval_criteria_present():
    keys = {s.key for s in PACKET_FIELD_SEEDS}
    for key in (*MS1_CRITERIA, *MS2_CRITERIA, *MS3_CRITERIA, *MS4_CRITERIA):
        assert key in keys


def test_swot_quadrants_complete_and_ms1_applicable():
    keys = {s.key for s in PACKET_FIELD_SEEDS}
    for key in ("swot_strengths", "swot_weaknesses", "swot_opportunities", "swot_threats"):
        assert key in keys
        seed = FIELD_SEED_BY_KEY[key]
        assert MilestoneGate.MILESTONE_1 in seed.required_gates
        assert seed.reference_slide == "slide_8_swot"


def test_team_slide_bp_fields_visible_at_ms1():
    for key in TEAM_SLIDE_MS1_FIELDS:
        seed = FIELD_SEED_BY_KEY[key]
        assert MilestoneGate.MILESTONE_1 in seed.required_gates
        assert seed.reference_slide == "slide_6_team"


def test_path_to_blue_row_fields_per_pursuit_area():
    keys = {s.key for s in PACKET_FIELD_SEEDS}
    for area in PATH_TO_BLUE_AREAS:
        for suffix in PATH_TO_BLUE_ROW_SUFFIXES:
            key = f"{area}{suffix}"
            assert key in keys, key
            assert FIELD_SEED_BY_KEY[key].reference_slide == "slide_9_path_to_blue"


def test_answer_route_stubs_on_intel_fields():
    customer = FIELD_SEED_BY_KEY["customer_name"]
    assert customer.answer_route is not None
    assert "sam_mcp" in customer.answer_route.sources
    assert customer.answer_route.deterministic is True

    landscape = FIELD_SEED_BY_KEY["competitive_landscape_summary"]
    assert landscape.answer_route is not None
    assert "clew_intel" in landscape.answer_route.sources
    assert "grok_synthesis" in landscape.answer_route.feeds


def test_clew_feeds_money_flow_fields():
    prime = FIELD_SEED_BY_KEY["prime_name"]
    assert prime.answer_route is not None
    assert "clew_intel" in prime.answer_route.sources