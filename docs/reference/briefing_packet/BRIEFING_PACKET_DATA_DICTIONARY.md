# Briefing Packet Data Dictionary Draft

Status: draft for user review  
Source references: local private PDF/PPTX in this folder  
Git handling: this folder is ignored because it contains organization-specific confidential material

## Purpose

This dictionary identifies the visible data elements and prose elements in the milestone briefing packet. It is intended to become the basis for Pydantic models, UI form fields, evidence mapping, and later deck export.

The deck contains four kinds of content:

| Kind          | Meaning                                          | Examples                                                                                |
| ------------- | ------------------------------------------------ | --------------------------------------------------------------------------------------- |
| Scalar data   | A single structured value                        | Salesforce ID, RFP Release Date, Total Contract Value, pWin %                           |
| Enum / choice | A constrained value                              | MS1/MS2/MS3/MS4, Prime/Sub, FFP/CPFF/CPAF/T&M/Multiple, A/B/O                           |
| Repeating row | A table/list item with the same columns repeated | Competition companies, pursuit team roles, risks, action items, approval criteria       |
| Prose         | Narrative or synthesized text                    | Opportunity context, What will it take to win, pricing strategy summary, risk responses |

Every field should eventually be represented as a traceable packet field rather than a raw value.

```text
PacketField[T]
- key: stable code identifier
- label: deck-facing label
- value: typed value or prose
- kind: scalar | enum | row | prose | computed | attachment
- source: human_input | evidence_inferred | model_inferred | imported | computed | unknown
- evidence_ids: tuple[str, ...]
- status: answered | partial | gap | assumption
- confidence: optional confidence label/score
- notes: optional user-facing explanation
```

## Slide 1 - Milestone Review Instructions & Expectations

Slide 1 is reference/instruction content, not opportunity-specific user data. Ariadne should preserve it as template metadata.

| Field key                                          | Deck label / concept   | Kind           | Notes                                        |
| -------------------------------------------------- | ---------------------- | -------------- | -------------------------------------------- |
| `milestone_instructions.ms_purpose`                | Milestone (MS) Purpose | prose          | Static template instruction.                 |
| `milestone_instructions.required_slide_rule`       | Required Slides        | prose          | Defines bottom-right milestone marker rule.  |
| `milestone_instructions.non_required_slide_rule`   | Non-Required Slides    | prose          | Defines red-x omission rule.                 |
| `milestone_instructions.approval_rule`             | MS Approval            | prose          | Uses organization TAM and BU TAM supplement. |
| `milestone_instructions.presentation_time_minutes` | Presentation Time      | scalar integer | Template default is 30 minutes.              |
| `milestone_profiles.ms1`                           | Milestone 1 profile    | row/prose      | Static profile for Qualification.            |
| `milestone_profiles.ms2`                           | Milestone 2 profile    | row/prose      | Static profile for Pursuit/No Pursuit.       |
| `milestone_profiles.ms3`                           | Milestone 3 profile    | row/prose      | Static profile for Bid/No-Bid.               |
| `milestone_profiles.ms4`                           | Milestone 4 profile    | row/prose      | Static profile for Pricing Approval.         |

## Slide 2 - Milestone Review Cover

| Field key          | Deck label       | Kind        | Likely source                                   |
| ------------------ | ---------------- | ----------- | ----------------------------------------------- |
| `business_unit`    | Business Unit    | scalar text | Human input or organization profile default.    |
| `operating_unit`   | Operating Unit   | scalar text | Human input or org profile.                     |
| `opportunity_name` | Opportunity Name | scalar text | Opportunity record.                             |
| `milestone_stage`  | Milestone #      | enum        | User-selected packet stage: MS1, MS2, MS3, MS4. |
| `packet_date`      | Date             | date        | Human input, default today.                     |
| `prepared_by`      | Prepared By      | scalar text | Human input or local profile.                   |
| `preparer_role`    | Role             | enum/text   | Human input or local profile, e.g. Capture.     |

## Slide 3 - Zero Harm Moment

| Field key             | Deck label                          | Kind             | Likely source                              |
| --------------------- | ----------------------------------- | ---------------- | ------------------------------------------ |
| `zero_harm_title`     | Insert Zero Harm Moment Title       | scalar text      | Human input.                               |
| `zero_harm_content`   | Include Zero Harm Moment title here | prose            | Human input or attached slide content.     |
| `zero_harm_media_ref` | Visual/media placeholder            | attachment       | Optional human-provided image/visual.      |
| `zero_harm_ready`     | Zero Harm slide populated?          | computed boolean | Derived from title/content/media presence. |

## Slide 4 - Opportunity Synopsis

### Opportunity Details

| Field key                         | Deck label              | Kind        | Likely source                                               |
| --------------------------------- | ----------------------- | ----------- | ----------------------------------------------------------- |
| `salesforce_id`                   | Salesforce ID #         | scalar text | Human input or CRM/API later.                               |
| `draft_rfp_date`                  | Draft RFP Date          | date        | Evidence or human input.                                    |
| `kbr_role`                        | Prime/Sub Role          | enum        | Prime/Sub.                                                  |
| `rfp_release_date`                | RFP Release Date        | date        | Evidence or human input.                                    |
| `prime_name`                      | Prime Name              | scalar text | Human input/evidence; relevant when pursuing as sub.          |
| `proposal_due_date`               | Proposal Due Date       | date        | Solicitation evidence or human input.                       |
| `crm_stage`                       | Stage                   | enum/text   | Template shows 00-04. May map to opportunity lifecycle/CRM. |
| `award_date`                      | Award Date              | date        | Evidence or human input.                                    |
| `customer_name`                   | Customer Name           | scalar text | Evidence or human input.                                    |
| `contract_start_date`             | Contract Start          | date        | Evidence or human input.                                    |
| `mts_priority`                    | Capture Priority        | enum        | A, B, O.                                                    |
| `contract_end_date`               | Contract End            | date        | Evidence or human input.                                    |
| `financial_contract_type`         | Financial Contract Type | enum/list   | FFP, CPFF, CPAF, T&M, Multiple.                             |
| `total_contract_value`            | Total Contract Value    | money       | Evidence or human input.                                    |
| `new_business_or_recompete`       | New Business/Recompete  | enum/text   | Human input or opportunity context.                         |
| `bookable_revenue`                | Bookable Revenue        | money       | Finance model or human input.                               |
| `pwin_percent`                    | pWin %                  | percentage  | Model-assisted estimate requiring human approval.           |
| `operating_income_margin_percent` | Operating Income Margin | percentage  | Finance model or human input.                               |

### Primary Scope and Competition

| Field key                    | Deck label                          | Kind         | Likely source                                       |
| ---------------------------- | ----------------------------------- | ------------ | --------------------------------------------------- |
| `primary_scope_description`  | Primary Scope / Description of Work | prose        | RFP/SOW evidence plus user synthesis.               |
| `number_of_ftes`             | Number of FTEs                      | number/prose | Evidence or human input.                            |
| `competition_company_1_name` | Company 1                           | scalar text  | Human input/evidence.                               |
| `competition_company_1_role` | Incumbent                           | enum/text    | Evidence or human input; often incumbent indicator. |
| `competition_company_2_name` | Company 2                           | scalar text  | Human input/evidence.                               |
| `competition_company_2_role` | Company 2 role/notes                | scalar/prose | Optional.                                           |
| `competition_company_3_name` | Company 3                           | scalar text  | Human input/evidence.                               |
| `competition_company_3_role` | Company 3 role/notes                | scalar/prose | Optional.                                           |
| `small_business_goal`        | Small Business Goal                 | scalar/prose | Solicitation evidence or human input.               |
| `special_considerations`     | Special Consideration(s)            | prose/list   | Human input/evidence.                               |

Preferred repeating model:

```text
CompetitionCompany
- rank: int
- company_name: str
- role_or_position: incumbent | likely_prime | likely_sub | unknown | text
- notes: str | None
- evidence_ids: tuple[str, ...]
```

## Slide 5 - Opportunity BLUF

Slide 5 is mostly prose and recommendation synthesis. It should be backed by evidence and action gaps.

| Field key                       | Deck label                                  | Kind       | Likely source                                                                                            |
| ------------------------------- | ------------------------------------------- | ---------- | -------------------------------------------------------------------------------------------------------- |
| `opportunity_context`           | Opportunity Context / What You Need To Know | prose      | Model-assisted summary from opportunity knowledge and user input.                                        |
| `strategic_fit_summary`         | Strategic fit against BU/Division strategy  | prose      | User input, strategy docs, evidence.                                                                     |
| `acquisition_capture_progress`  | Acquisition/capture progress                | prose      | Evidence and capture notes.                                                                              |
| `customer_need_funding_status`  | Ongoing need / funding context              | prose      | Customer/funding evidence or gap.                                                                        |
| `competitive_landscape_summary` | Overall competitive landscape               | prose      | Competitive intelligence evidence.                                                                       |
| `ms1_bluf_focus`                | MS1-specific BLUF focus                     | prose      | Market intelligence, customer relationships, resources/talent, estimated B&P.                            |
| `ms2_bluf_focus`                | MS2-specific BLUF focus                     | prose      | Customer/contracting engagement, team gaps, gap closure approach, competitive/team strategy, updated B&P. |
| `ms3_bluf_focus`                | MS3-specific BLUF focus                     | prose      | MS2 closure progress, recruiting/staffing activation, additional B&P.                                    |
| `what_it_takes_to_win`          | What Will It Take To Win?                   | prose/list | Capture and operations recommendations and hurdles.                                                      |
| `recommendation`                | Recommendation                              | prose/enum | Leadership-ready recommendation, e.g. proceed/hold/no-bid/approve pricing.                               |

## Slide 6 - Opportunity Team Assignments

### Pursuit Team Rows

Each role should be a row with assigned person/organization, required-at milestone, and readiness.

```text
PursuitTeamAssignment
- role_key
- deck_role_label
- assigned_to
- required_at_milestone
- readiness_status
- notes
- evidence_ids
```

| Role key                 | Deck role label        | Required at MS | Kind                               |
| ------------------------ | ---------------------- | -------------- | ---------------------------------- |
| `business_unit_division` | Business Unit Division | MS1            | scalar text                        |
| `operating_unit`         | Operating Unit (OU)    | MS1            | scalar text                        |
| `capture_manager`        | Capture Manager        | MS1            | person                             |
| `operations_leader`      | Operations Leader      | MS1            | person                             |
| `solution_architect`     | Solution Architect     | MS2            | person / N/A for most sub pursuits |
| `proposal_manager`       | Proposal Manager       | MS2            | person / N/A for most sub pursuits |
| `proposal_coordinator`   | Proposal Coordinator   | MS2            | person / N/A for most sub pursuits |
| `contracts_lead`         | Contracts Lead         | MS2            | person                             |
| `technical_lead`         | Technical Lead         | MS2            | person                             |
| `staffing_boe_lead`      | Staffing/BOE Lead      | MS2            | person / N/A for most sub pursuits |
| `pricing_lead`           | Pricing Lead           | MS2            | person                             |
| `program_manager`        | Program Manager        | MS3            | person / N/A for most sub pursuits |

### Additional Resources and Funding

| Field key                            | Deck label                                           | Kind                           | Likely source          |
| ------------------------------------ | ---------------------------------------------------- | ------------------------------ | ---------------------- |
| `consultants`                        | Consultant(s)                                        | repeating person/resource list | Human input.           |
| `subject_matter_experts`             | Subject Matter Expert(s)                             | repeating person/resource list | Human input.           |
| `other_resources`                    | Other Resource(s)                                    | repeating resource list        | Human input.           |
| `subcontracts_functional_lead`       | Subcontracts                                         | person/text                    | Human input.           |
| `talent_acquisition_functional_lead` | Talent Acquisition                                   | person/text                    | Human input.           |
| `human_resources_functional_lead`    | Human Resources                                      | person/text                    | Human input.           |
| `finance_functional_lead`            | Finance                                              | person/text                    | Human input.           |
| `non_us_persons_participate`         | Will any Non-US Persons Participate in the Proposal? | boolean                        | Human/legal input.     |
| `bp_funding_request_amount`          | B&P Request                                          | money                          | Human input / finance. |
| `bp_notes`                           | B&P Notes                                            | prose                          | Human input.           |

## Slide 7 - Evaluation Methodology

| Field key                                   | Deck label                                | Kind            | Likely source                               |
| ------------------------------------------- | ----------------------------------------- | --------------- | ------------------------------------------- |
| `evaluation_document_date`                  | Date of Documents                         | date/month-year | Draft/final RFP evidence.                   |
| `technical_volume_rating_method`            | Technical Volume                          | enum/list       | Adjectival, Pass/Fail, or text.             |
| `management_volume_rating_method`           | Management Volume                         | enum/list       | Adjectival, Pass/Fail, or text.             |
| `past_performance_rating_method`            | Past Performance                          | enum/list       | Adjectival, Pass/Fail, or text.             |
| `cost_price_evaluation_method`              | Cost/Price                                | prose/list      | RFP evidence.                               |
| `basis_of_evaluated_price`                  | Basis of Evaluated Price                  | prose           | RFP/evaluation evidence.                    |
| `relative_importance_of_evaluation_factors` | Relative Importance of Evaluation Factors | prose           | Section M evidence and customer experience. |
| `observed_customer_award_trends`            | Observed Customer Award Trends            | prose           | Customer/history evidence.                  |
| `evaluation_factors`                        | Evaluation factor/subfactor table         | repeating row   | RFP evidence.                               |

```text
EvaluationFactor
- factor_or_subfactor
- evaluation_considerations
- factor_description
- possible_ratings
- evidence_ids
```

## Slide 8 - Opportunity SWOT

| Field key            | Deck label    | Kind       | Likely source                       |
| -------------------- | ------------- | ---------- | ----------------------------------- |
| `swot_strengths`     | Strengths     | prose/list | Evidence and capture team judgment. |
| `swot_weaknesses`    | Weaknesses    | prose/list | Evidence and capture team judgment. |
| `swot_opportunities` | Opportunities | prose/list | Evidence and capture team judgment. |
| `swot_threats`       | Threats       | prose/list | Evidence and capture team judgment. |

Preferred row model if the UI needs traceability per bullet:

```text
SwotItem
- quadrant: strength | weakness | opportunity | threat
- statement
- evidence_ids
- confidence
- action_item_ids
```

## Slide 9 - Opportunity Development Path to Blue

### Summary Fields

| Field key                            | Deck label            | Kind       | Likely source              |
| ------------------------------------ | --------------------- | ---------- | -------------------------- |
| `path_to_blue_strategic_fit`         | Strategic Fit         | prose/list | Strategy/evidence/user.    |
| `path_to_blue_leadership_highlights` | Leadership Highlights | prose/list | User/model synthesis.      |
| `path_to_blue_win_strategy`          | Win Strategy          | prose/list | Capture strategy evidence. |

### Pursuit Area Rows

The progress scale shown on the slide is `1=None`, `2=Low`, `3=Medium`, `4=Good`, `5=Complete`.

```text
PathToBlueRow
- pursuit_area
- previous_status: none | low | medium | good | complete
- current_status: none | low | medium | good | complete
- status_update
- next_steps_actions
- evidence_ids
- action_item_ids
```

| Pursuit area key                          | Deck label                                | Kind          |
| ----------------------------------------- | ----------------------------------------- | ------------- |
| `opportunity_shaping_customer_engagement` | Opportunity Shaping / Customer Engagement | repeating row |
| `pricing_strategy`                        | Pricing Strategy                          | repeating row |
| `staffing_key_personnel`                  | Staffing / Key Personnel                  | repeating row |
| `tech_solutioning`                        | Tech Solutioning                          | repeating row |
| `other_teaming_capex_facilities`          | Other / Teaming, CapEx, Facilities        | repeating row |

## Slide 10 - Pricing Strategy

| Field key                              | Deck label                                    | Kind       | Likely source                              |
| -------------------------------------- | --------------------------------------------- | ---------- | ------------------------------------------ |
| `pricing_strategy_summary`             | Pricing Strategy Summary                      | prose/list | Pricing strategy and PTW evidence.         |
| `customer_pricing_estimating_guidance` | Customer Pricing and Estimating Guidance      | prose/list | RFP/prior solicitation evidence.           |
| `pricing_variables`                    | Pricing Variables                             | prose/list | Pricing model / capture judgment.          |
| `kbr_position_relative_to_competition` | Position Relative to Competition | prose/list | Competitive intelligence and price-to-win. |
| `pricing_strategy_risks_opportunities` | Pricing risks/opportunities                   | prose/list | Derived from strategy summary.             |

## Slide 11 - Proposed Pricing Summary

The source slide states there is no expectation of preliminary proposed price at MS1/MS2, preliminary proposed price at MS3 when feasible, and final proposed price at MS4.

| Field key                  | Deck label / concept                   | Kind                   | Likely source           |
| -------------------------- | -------------------------------------- | ---------------------- | ----------------------- |
| `proposed_price_available` | Proposed price available?              | boolean/computed       | Stage and pricing data. |
| `proposed_pricing_summary` | Proposed Pricing Summary               | prose/table attachment | Pricing lead/finance.   |
| `evaluated_price`          | Evaluated price                        | money                  | Pricing model.          |
| `price_metrics`            | Other price metrics                    | repeating row/prose    | Pricing model.          |
| `price_to_win_comparison`  | Compare to PTW recommendations         | prose/data             | Price-to-win analysis.  |
| `pricing_summary_rows`     | Major cost elements by contract period | repeating row          | Pricing model/import.   |

## Slide 12 - Execution Business Case Model

| Field key                        | Deck label / concept                  | Kind          | Likely source                                                   |
| -------------------------------- | ------------------------------------- | ------------- | --------------------------------------------------------------- |
| `business_case_summary`          | Execution Business Case Model summary | prose         | Finance/pricing/user.                                           |
| `business_case_rows`             | Cost element table                    | repeating row | Finance model/import.                                           |
| `conservative_revenue`           | Revenue - Conservative                | money         | Computed/imported.                                              |
| `optimistic_revenue`             | Revenue - Optimistic                  | money         | Computed/imported.                                              |
| `conservative_op_margin_percent` | OP Margin - Conservative              | percentage    | Computed/imported.                                              |
| `optimistic_op_margin_percent`   | OP Margin - Optimistic                | percentage    | Computed/imported.                                              |
| `cashflow_summary`               | Cashflow summary                      | prose/data    | Finance model; not explicit in table but named in expectations. |

```text
BusinessCaseRow
- cost_element
- clin_type
- conservative_estimated_cost
- conservative_profit_fee_percent
- conservative_price
- optimistic_estimated_cost
- optimistic_profit_fee_percent
- optimistic_price
```

## Slide 13 - High Risk Elements

| Field key         | Deck label      | Kind          | Likely source                           |
| ----------------- | --------------- | ------------- | --------------------------------------- |
| `proposal_risks`  | Proposal Risks  | repeating row | Capture/proposal evidence and judgment. |
| `execution_risks` | Execution Risks | repeating row | Ops/capture evidence and judgment.      |

```text
PacketRisk
- risk_category: proposal | execution
- risk_name
- risk_statement
- response
- severity
- owner
- evidence_ids
- action_item_ids
```

Template examples imply these common risk names:

- Page Count
- Submission Complexity
- Subcontractor Dependency
- Key Personnel Requirements
- Failure to Meet Solicitation Requirements
- Timeline for award and Transition
- Transition timeline
- Cost Risks
- Key Personnel Availability
- Bid vs. Execution Margin

## Slide 14 - Action Plan

This should be generated from Capture Action Plan Items when possible.

| Field key           | Deck label   | Kind          | Likely source        |
| ------------------- | ------------ | ------------- | -------------------- |
| `action_plan_items` | Action table | repeating row | Capture Action Plan. |

```text
PacketActionItem
- action
- responsible_party
- due_date
- status
- related_packet_slide
- related_evidence_ids
- action_plan_item_id
```

## Slide 15 - Questions

| Field key                 | Deck label / concept      | Kind         | Likely source          |
| ------------------------- | ------------------------- | ------------ | ---------------------- |
| `questions_slide_enabled` | Questions slide included? | boolean      | Template default true. |
| `questions_prompt`        | Questions?                | static/prose | Template.              |
| `legal_notice`            | Legal notice              | static/prose | Template.              |

## Slide 16 - Milestone Review Pursuit Promotion Criteria

Slide 16 is the overview of approval criteria. The fields below should be static template criteria plus answer status computed from slides 17-18.

| Field key                       | Deck concept                      | Kind                   |
| ------------------------------- | --------------------------------- | ---------------------- |
| `promotion_criteria_purpose`    | Criteria Purpose                  | static prose           |
| `promotion_criteria`            | All milestone criteria            | repeating criteria row |
| `promotion_criteria_completion` | Completion/readiness by milestone | computed summary       |

```text
ApprovalCriterion
- milestone_stage
- criterion_key
- criterion_text
- answer
- answer_status: answered | partial | gap | assumption
- evidence_ids
- confidence
- gap_summary
- action_item_ids
```

## Slide 17 - MS1 & MS2 Approval Decision

Each row needs a concise answer plus evidence/gap tracking.

### MS1 Criteria

| Criterion key                                   | Deck criterion                                        | Kind             |
| ----------------------------------------------- | ----------------------------------------------------- | ---------------- |
| `ms1_strategic_fit_confirmed`                   | Strategic fit confirmed?                              | criterion answer |
| `ms1_customer_decision_maker_identified`        | Customer decision-maker identified?                   | criterion answer |
| `ms1_customer_access_plan_established`          | Viable customer access plan established?              | criterion answer |
| `ms1_customer_funding_and_opportunity_credible` | Customer has funding and opportunity is credible?     | criterion answer |
| `ms1_acquisition_timeline_defined`              | Anticipated acquisition timeline defined?             | criterion answer |
| `ms1_acquisition_strategy_understood`           | Customer's potential acquisition strategy understood? | criterion answer |
| `ms1_business_unit_identified_accountable`      | Business Unit identified and accountable?             | criterion answer |
| `ms1_capture_manager_available_qualified`       | Capture Manager available and qualified?              | criterion answer |
| `ms1_oci_sweep_initiated`                       | OCI Sweep has been initiated?                         | criterion answer |

### MS2 Criteria

| Criterion key                                    | Deck criterion                                  | Kind             |
| ------------------------------------------------ | ----------------------------------------------- | ---------------- |
| `ms2_capture_strategy_plan_validated`            | Capture strategy and plan validated?            | criterion answer |
| `ms2_teaming_strategy_validated`                 | Teaming strategy validated?                     | criterion answer |
| `ms2_teaming_agreements_ready`                   | Teaming agreements ready for execution?         | criterion answer |
| `ms2_pursuit_team_available_qualified`           | Pursuit Team members available and qualified?   | criterion answer |
| `ms2_initial_pricing_strategy_acceptable`        | Initial pricing strategy acceptable?            | criterion answer |
| `ms2_oci_assessment_complete_acceptable`         | OCI assessment is complete and acceptable?      | criterion answer |
| `ms2_pwin_reassessed_matured`                    | Pwin reassessed and matured?                    | criterion answer |
| `ms2_unique_hiring_investment_expenses_approved` | Unique hiring and investment expenses approved? | criterion answer |
| `ms2_bp_budget_estimate_approved`                | B&P budget estimate approved?                   | criterion answer |

## Slide 18 - MS3 & MS4 Approval Decision

### MS3 Criteria

| Criterion key                                           | Deck criterion                                     | Kind                      |
| ------------------------------------------------------- | -------------------------------------------------- | ------------------------- | -------------------------------------------------------------------------------- |
| `ms3_trigger_condition_met`                             | DRFP released or FRFP expected ~30 days w/no DRFP? | criterion answer          |
| `ms3_influence_activities_success`                      | Influence activities demonstrated success?         | criterion answer          |
| `ms3_teaming_strategy_subcontractor_selection_in_place` | Documented teaming strategy and subs in place?     | criterion answer          |
| `ms3_win_strategy_validated`                            | Win strategy validated?                            | criterion answer          |
| `ms3_oci_reassessed_acceptable`                         | OCI reassessed and still acceptable?               | criterion answer          |
| `ms3_pwin_reassessed_matured`                           | Pwin reassessed and matured?                       | criterion answer          |
| `ms3_pricing_strategy_ptw_approved`                     | Pricing strategy and PTW approved?                 | criterion answer          |
| `ms3_execution_risks_acceptable`                        | Execution risks assessed and deemed acceptable?    | criterion answer          |
| `ms3_bp_budget_adjustments_approved`                    | Adjustments to B&P budget estimate approved?       | criterion answer / verify | Present in criteria overview; verify whether it appears on final approval slide. |

### MS4 Criteria

| Criterion key                                 | Deck criterion                                                     | Kind             |
| --------------------------------------------- | ------------------------------------------------------------------ | ---------------- |
| `ms4_compelling_compliant_proposal_developed` | Compelling and compliant proposal developed?                       | criterion answer |
| `ms4_pricing_acceptable`                      | Pricing acceptable based on accuracy, realism, and reasonableness? | criterion answer |
| `ms4_execution_risks_continue_acceptable`     | Execution risks continue to be acceptable?                         | criterion answer |

## Cross-Slide Data Objects

These are the Pydantic objects I would create before a full UI pass.

```text
BriefingPacketData
- identity: PacketIdentityData
- synopsis: OpportunitySynopsisData
- bluf: OpportunityBlufData
- team: PursuitTeamData
- evaluation: EvaluationMethodologyData
- swot: SwotData
- path_to_blue: PathToBlueData
- pricing_strategy: PricingStrategyData
- proposed_pricing: ProposedPricingData
- business_case: BusinessCaseData
- risks: RiskElementsData
- actions: PacketActionPlanData
- approval_decisions: ApprovalDecisionData
```

The first implementation should not try to perfectly fill every field. It should model required fields, mark gaps, and preserve provenance so Ariadne can ask for human input or infer from evidence later.
