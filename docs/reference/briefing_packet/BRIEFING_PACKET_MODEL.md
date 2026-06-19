# Living Briefing Packet Model Draft

Status: draft for user review  
Source references: local private PDF/PPTX in this folder  
Git handling: this folder is ignored because it contains organization-specific confidential material

## Working Understanding

The milestone packet should not be treated as a generic dashboard. It is a slide-deck-shaped decision artifact. The deck is the face/skin of the workflow: it gives leaders the familiar review structure, expected slide order, timing, milestone indicators, approval criteria, and export surface.

Ariadne's evidence model is the under-the-hood layer. Evidence Items, assumptions, gaps, confidence, action items, and source traceability feed the packet. The exported/reviewed deck should stay clean and leadership-ready, while the app can reveal the evidence backing each slide, field, recommendation, answer, or gap.

The packet should know the opportunity's active milestone stage: MS1, MS2, MS3, or MS4. That stage determines which slides are required, which are optional/omittable, which fields are expected, and which approval criteria must be answered.

## Source Milestone Instructions

The following source instructions are retained verbatim for modeling. Ariadne's public/domain model can normalize names and fields later, but this private reference should preserve the original language.

```text
Milesonte Instructions:
Milestone (MS) Purpose: Provides opportunity updates to leadership and allows them the opportunity to evaluate viability, strategy, risks, rewards, and probability of winning the contract.
Required Slides: For MS1-4, you are only required to brief the corresponding slide number in the bottom right corner (MS1 – brief the slides with a 1 in the bottom right)
Non-Required Slides: For subcontract, non-competitive , and accelerated acquisition (OTA, CSO, Phase III, etc.) bids, several slides can be omitted from the deck. They will be indicated by a red x in the bottom right.
MS Approval: MS Approver, Sponsors, and Attendees are based on the organization TAM as well as Business Units (BU) TAM Supplement.
Presentation Time: 30 min (Slide Timing in Slide Title)
```

```text
Milestone 1: Qualification
Timeline: 12-24 months before Final RFP (FRFP) date
MS1 reviews the progress and development of an opportunity, including market intelligence gathering, strategic alignment, strategy and schedule for customer engagement including use of Growth Acceleration Team, early solutioning, past performance evaluation, white papers or demonstrations, teaming discussions, potential investments, & BU commitment.
At MS1, once approved as qualified, the Capture Manager (CM) is assigned.
The CM assesses the anticipated size of the opportunity against the TAM to determine the necessary level of executive review as the opportunity matures and moves into the Lead position as opportunity owner.
Briefer: Capture Manager, Account Executive / Manager, or Ops Lead
```

```text
Milestone 2:
Pursuit/No Pursuit
Timeline: 9-12 months before FRFP date
MS2 is an interim review of Capture progress to determine viability of continuing to provide funding and resources.
The CM has developed a comprehensive capture strategy and plan.
The CM presents updates on the Request for Proposal (RFP) shaping strategies, customer engagement strategy (e.g., client visits, call plans), pricing strategies, key or critical personnel hiring, competitive landscape, expanded teaming discussions, unique investment requirements, OCI assessment, Pwin maturation, and exercises to further evaluate team capabilities.
Upon approval, defined by the organization TAM, proposal activities commence with assignment of Proposal Manager (PropMgr).
Briefer: Capture Manager
```

```text
Milestone 3:
Bid/No-Bid
Timeline: At DRFP Release or ~30 days before FRFP date if no DRFP Expected
MS3 reviews Capture activities made by draft RFP (DRFP) or 30 days before Final RFP (FRFP) if a DRFP is not expected.
The CM has implemented the Capture Plan, advanced any unique investment activities, and matured Pwin.
The CM, PropMgr, and Ops Lead review and update relevant strategies upon RFP release (e.g., win strategy, teaming strategy, pricing strategy, recruiting/staffing strategy) to provide valuable context on requirements, those shaped by offerors, those the customer dropped, and those that were unexpected.
If an MS3 is conducted at DRFP, an MS3 update is conducted at FRFP to validate procurement strategy has not changed and no major deviations between DRFP and FRFP have occurred.
Briefer: Capture Manager
```

```text
Milestone 4:
Pricing Approval
Timeline: 7-14 days prior to Submission
MS4 is a compliance, pricing, and execution risk review conducted by Executive Leadership per the TAM.
The PropMgr confirms a compelling and compliant proposal has been developed and is being finalized, substantiated by successful Color Team reviews.
The CM, supported by the Pricing Lead and Contracts Manager, presents the bid price.
The Contracts Manager and a Legal point of contact conduct a review of the solution, teaming, and pricing strategies that went into developing the final cost.
The Ops Lead presents any accepted execution risks.
Briefer: Pricing Lead, Contracts Lead, Legal POC, Ops Lead, Capture Manager, and Proposal Manager
```

## Milestone Stage Model

| Stage | Name                 | Timing                                                                         | Core decision question                                                                             | Primary briefer pattern                                                              |
| ----- | -------------------- | ------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| MS1   | Qualification        | 12-24 months before final RFP date                                             | Is this opportunity qualified enough to assign capture ownership and continue investment?          | Capture Manager, Account Executive/Manager, or Ops Lead                              |
| MS2   | Pursuit / No Pursuit | 9-12 months before final RFP date                                              | Is the capture strategy viable enough to keep funding, resources, and proposal preparation moving? | Capture Manager                                                                      |
| MS3   | Bid / No-Bid         | At draft RFP release or about 30 days before final RFP if no draft is expected | Are win strategy, teaming, pricing strategy, risk, and pursuit maturity strong enough to bid?      | Capture Manager                                                                      |
| MS4   | Pricing Approval     | 7-14 days before submission                                                    | Are final proposal, price, and execution risks acceptable for submission?                          | Pricing Lead, Contracts Lead, Legal POC, Ops Lead, Capture Manager, Proposal Manager |

## Slide Applicability

The template uses numbered milestone markers at the bottom of slides. The active marker(s) identify which milestone review(s) need the slide. The app should model this explicitly instead of assuming every slide appears for every milestone.

Proposed data shape:

```text
PacketSlideTemplate
- slide_number
- title
- timing_minutes
- required_for: set[MilestoneStage]
- optional_for: set[MilestoneStage]
- omit_when: list[OmissionRule]
- layout_kind
- evidence_slots: list[EvidenceSlot]
- output_slots: list[DeckSlot]
```

Open item: derive the exact `required_for` set from the PPTX/PDF milestone markers. The PDF text extraction exposes some milestone-specific wording, but the bottom marker row is visual. We should either read it manually from rendered slides or extract marker shape metadata from the PPTX.

## Observed Slide Catalog

This catalog summarizes the deck shape without copying the private template wholesale.

| Slide | Title / role                                   | Layout kind                        | Ariadne interpretation                                                                                                                                                                           |
| ----- | ---------------------------------------------- | ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1     | Milestone review instructions and expectations | Instruction / overview             | Explains the purpose of milestone reviews, milestone timing, required-slide marker convention, optional omissions, approval authority, and presentation time. Not a generated opportunity slide. |
| 2     | Milestone review cover                         | Cover                              | Opportunity name, business unit, operating unit, milestone number, date, preparer, role.                                                                                                         |
| 3     | Zero Harm Moment                               | Safety / ritual slide              | Usually user-authored or manually supplied. Ariadne can track whether populated but should not over-automate.                                                                                    |
| 4     | Opportunity Synopsis                           | Structured synopsis table          | Core opportunity metadata, dates, value, pWin, scope, competition, FTEs, small business goal, special considerations. Strong fit for Evidence-backed fields.                                     |
| 5     | Opportunity BLUF                               | Narrative decision summary         | Context, strategic fit, acquisition/capture progress, what it will take to win, recommendation. Content changes by MS1/MS2/MS3 expectations.                                                     |
| 6     | Opportunity Team Assignments                   | Resourcing matrix                  | Pursuit team roles and when they must be resourced. Includes per-role milestone markers such as MS1, MS2, MS3.                                                                                   |
| 7     | Evaluation Methodology                         | RFP/evaluation table               | Evaluation factors, possible ratings, basis of evaluated price, relative importance, customer award trends.                                                                                      |
| 8     | Opportunity SWOT                               | Four-column SWOT                   | Strengths, weaknesses, opportunities, threats. Could include generated graphic enhancements later, but the base content should remain evidence-backed.                                           |
| 9     | Opportunity Development Path to Blue           | Progress/status tracker            | Strategic fit, leadership highlights, win strategy, pursuit areas, previous/current status, updates, next steps/actions. Strong bridge to Action Plan Items.                                     |
| 10    | Pricing Strategy                               | Pricing strategy panels            | Pricing strategy summary, customer pricing/estimating guidance, pricing variables, position relative to competition. MS3 expectation is stronger than earlier stages.                        |
| 11    | Proposed Pricing Summary                       | Pricing summary placeholder        | No preliminary proposed price expected at MS1/MS2; preliminary price expected at MS3 when feasible; final price at MS4.                                                                          |
| 12    | Execution Business Case Model                  | Financial model table              | Preliminary business case at MS2, more mature at MS3 if needed, final at MS4 if needed.                                                                                                          |
| 13    | High Risk Elements                             | Proposal and execution risk tables | Proposal risks and execution risks with responses. Strong fit for risk evidence and action links.                                                                                                |
| 14    | Action Plan                                    | Action table                       | Action, responsible party, due date. This should be fed by Capture Action Plan Items.                                                                                                            |
| 15    | Questions                                      | Closing / legal notice             | Mostly deck ritual and meeting close. Not evidence-heavy.                                                                                                                                        |
| 16    | Milestone Review Pursuit Promotion Criteria    | Criteria overview                  | Milestone-by-milestone approval criteria and briefer expectations. Should become the source of readiness gates.                                                                                  |
| 17    | MS1 & MS2 Approval Decision                    | Approval answer table              | Criteria rows for MS1 and MS2, with concise answer cells. Each answer should be evidence-backed.                                                                                                 |
| 18    | MS3 & MS4 Approval Decision                    | Approval answer table              | Criteria rows for MS3 and MS4, with concise answer cells. Each answer should be evidence-backed.                                                                                                 |

## Required Model Concepts

These concepts should exist in Ariadne before the packet UI becomes real:

- Milestone Stage: MS1, MS2, MS3, MS4.
- Packet Slide Template: canonical slide definition, not a one-off UI card.
- Slide Applicability: required/optional/omittable for each milestone.
- Slide Marker: the numbered bottom marker(s) that explain why a slide is included.
- Deck Slot: a visible placeholder or field on a slide.
- Evidence Slot: the under-the-hood evidence requirement that feeds a visible deck slot.
- Approval Criterion: a milestone-specific decision question that must receive a concise answer.
- Criterion Answer: the leadership-ready answer, backed by evidence, assumptions, gaps, and confidence.
- Graphic Insert: optional generated visual, chart, or huashu-design artifact inserted into a slide when useful.
- Artifact Export Profile: private mapping from Ariadne packet content into this specific deck skin.

## Data Dictionary Direction

We have not created the detailed deck data dictionary in code yet. The current Pydantic packet model only knows about packet readiness, canonical packet sections, evidence status, briefing view, and coverage view. It does not yet know deck-level fields such as `business_unit`, `operating_unit`, `prepared_by`, `role`, `milestone_stage`, `salesforce_id`, `draft_rfp_date`, `pwin`, or slide-specific answer fields.

Detailed draft: [BRIEFING_PACKET_DATA_DICTIONARY.md](BRIEFING_PACKET_DATA_DICTIONARY.md).

Recommendation: use Pydantic, not dataclasses, for the first real data dictionary. Pydantic fits Ariadne better because these values need validation, defaults, JSON/API serialization, UI display, import/export, and evidence provenance. Dataclasses would be fine for tiny internal records, but the packet dictionary is a product contract.

Proposed data dictionary layers:

```text
BriefingPacketData
- packet_identity: PacketIdentityData
- opportunity_synopsis: OpportunitySynopsisData
- pursuit_team: PursuitTeamData
- evaluation_methodology: EvaluationMethodologyData
- swot: SwotData
- path_to_blue: PathToBlueData
- pricing_strategy: PricingStrategyData
- pricing_summary: PricingSummaryData
- business_case: BusinessCaseData
- risks: RiskElementsData
- action_plan: ActionPlanData
- approval_decisions: ApprovalDecisionData
```

Each field should carry value provenance, because some values are manually entered, some are inferred from Evidence Items, and some are left as gaps until the user provides them.

```text
PacketField
- key: stable field name, such as business_unit
- label: deck-facing label, such as Business Unit
- value: current value, such as Readiness & Sustainment
- source: human_input | evidence_inferred | model_inferred | imported | unknown
- evidence_ids: source Evidence Items supporting the value
- confidence: optional confidence label or score
- status: answered | partial | gap | assumption
- notes: optional explanation for the user
```

Example fields to model first:

| Field key                 | Deck label              | Example value                  | Likely source                               |
| ------------------------- | ----------------------- | ------------------------------ | ------------------------------------------- |
| `business_unit`           | Business Unit           | Readiness & Sustainment        | Human input or organization profile default |
| `operating_unit`          | Operating Unit          | TBD                            | Human input                                 |
| `opportunity_name`        | Opportunity Name        | AFLCMC recompete support       | Opportunity record                          |
| `milestone_stage`         | Milestone #             | MS1 / MS2 / MS3 / MS4          | Human-selected workflow state               |
| `prepared_by`             | Prepared By             | User name                      | Human input or local profile                |
| `role`                    | Role                    | Capture                        | Human input or local profile                |
| `salesforce_id`           | Salesforce ID #         | TBD                            | Human input or CRM/API later                |
| `customer_name`           | Customer Name           | TBD                            | Evidence or human input                     |
| `draft_rfp_date`          | Draft RFP Date          | TBD                            | Evidence or human input                     |
| `rfp_release_date`        | RFP Release Date        | TBD                            | Evidence or human input                     |
| `proposal_due_date`       | Proposal Due Date       | TBD                            | Evidence or human input                     |
| `award_date`              | Award Date              | TBD                            | Evidence or human input                     |
| `contract_start`          | Contract Start          | TBD                            | Evidence or human input                     |
| `contract_end`            | Contract End            | TBD                            | Evidence or human input                     |
| `kbr_role`                | Prime/Sub Role          | Prime/Sub                      | Human input                                 |
| `prime_name`              | Prime Name              | TBD                            | Human input or evidence                     |
| `financial_contract_type` | Financial Contract Type | FFP, CPFF, CPAF, T&M, Multiple | Evidence or human input                     |
| `total_contract_value`    | Total Contract Value    | TBD                            | Evidence or human input                     |
| `bookable_revenue`        | Bookable Revenue        | TBD                            | Human input or finance model                |
| `pwin`                    | pWin %                  | TBD                            | Model-assisted with human approval          |
| `operating_income_margin` | Operating Income Margin | TBD                            | Finance model or human input                |

The next implementation slice should introduce these as Pydantic models behind a small interface, then tests should prove the app can identify missing required fields for a selected milestone.

## Evidence Feeding Rules

The UI should let the user inspect evidence behind the deck, but the deck itself should remain clean.

Proposed rule:

```text
Evidence Items -> Evidence Slots -> Deck Slots -> Slide -> Packet -> Export Profile
```

Examples:

- Opportunity Synopsis fields should cite source evidence for dates, contract value, customer, incumbent, pWin, revenue, and scope.
- BLUF recommendation should cite customer context, strategic fit, competition, capture progress, funding, and action gaps.
- Path to Blue status should be backed by workstream maturity and action-plan progress.
- Approval Decision answers should be concise, but each answer should have an expandable evidence packet: source IDs, assumptions, confidence, gaps, and recommended next action.
- Action Plan slide should be generated from Capture Action Plan Items, not manually duplicated.

## Deck Skin / Visual Language

The review surface should look like a slide-deck workspace, not a dashboard.

Observed skin characteristics:

- 16:9 slide canvas.
- White slide background.
- Large navy slide title with thin blue underline.
- Blue section headers for major table bands.
- Teal/green accent headers for secondary sections and progress/status concepts.
- Light blue row fills and alternating row backgrounds.
- Dark blue footer band with copyright/confidentiality area, milestone marker strip, and slide number.
- Dense tables are normal and expected; the packet is not a spacious marketing layout.
- Bottom milestone marker row is functionally important, not decorative.

The app review UI should probably show a slide navigator and a slide canvas preview, with an evidence inspector beside or below it. The leadership deck preview should be visually close to the template. The evidence inspector can be Ariadne-native and does not need to appear in the exported deck.

## Proposed Review UI Shape

First improved UI pass should include:

1. Milestone selector: MS1 / MS2 / MS3 / MS4.
2. Slide navigator filtered by required slides for the selected milestone.
3. Slide canvas preview in the deck skin.
4. Slide metadata panel showing required/optional status, timing, marker numbers, readiness, and open gaps.
5. Evidence inspector showing Evidence Items, assumptions, confidence, gaps, and action links for the selected slide/slot.
6. Optional insert slots for generated visuals, such as huashu-design graphics, without replacing the required deck structure.

## Implementation Plan Before App Changes

Do not jump straight to CSS. Model the packet first.

1. Add milestone stage and slide template concepts to the packet domain model.
2. Add a private/reference-derived slide catalog for the demo packet, without committing the confidential template.
3. Add tests that selecting MS1/MS2/MS3/MS4 filters required slides correctly.
4. Add tests that approval criteria are stage-specific and answer slots can carry evidence/gap status.
5. Replace the current generic packet review page with a slide-deck review surface.
6. Keep issue #4 open until the user approves the first real deck-shaped UI.

## Open Questions For User Review

1. Should the app treat slide 1 instructions as always visible in the UI, or only as a help/reference page outside the actual packet?
2. Should Zero Harm Moment be part of Ariadne packet generation, or simply tracked as a manual slide that must be attached/populated?
3. Should the app default to one milestone packet at a time, or allow an opportunity to carry all MS1-MS4 packets as a history/timeline?
4. For slide markers, should a slide with multiple markers be included in every marked milestone by default?
5. Which optional/omittable cases matter first: subcontract, non-competitive, accelerated acquisition, or something else?
6. Should huashu-design visuals be preview-only until explicitly promoted into the deck?
