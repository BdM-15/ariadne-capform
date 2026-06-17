# Risk Register Data Dictionary Draft

Status: draft for user review  
Source reference: local private XLSX under `docs/reference/risk_register/`  
Git handling: private workbook files in this folder are ignored; this normalized dictionary is commit-safe reference material.

## Purpose

This dictionary identifies data elements in the Risk and Opportunity Register workbook and normalizes them into Ariadne concepts. It should help Quick Capture, Capture Intelligence Drafts, packet updates, action recommendations, Hermes improvement proposals, research prompts, and future risk-register skill invocation.

The workbook contains five useful kinds of content:

| Kind               | Meaning                                   | Examples                                                       |
| ------------------ | ----------------------------------------- | -------------------------------------------------------------- |
| Scalar data        | Single value                              | pursuit name, Salesforce ID, prepared by, MS4 date             |
| Enum / choice      | Constrained value                         | risk/opportunity, category, response type, probability, impact |
| Repeating row      | One risk or opportunity item              | risk ID, statement, impact, response, score                    |
| Formula / computed | Derived workbook scoring or helper fields | risk scores, matrix references                                 |
| Reference lookup   | Controlled vocabulary                     | categories, response types, probability bands, impact bands    |

Every field should eventually carry provenance and review status.

```text
RiskRegisterField[T]
- key: stable code identifier
- label: template-facing or UI-facing label
- value: typed value or prose
- kind: scalar | enum | row | prose | computed | attachment
- source: human_input | evidence_inferred | model_inferred | imported | computed | unknown
- evidence_ids: tuple[str, ...]
- status: answered | partial | gap | assumption
- confidence: optional confidence label/score
- notes: optional user-facing explanation
- connected_packet_fields: tuple[str, ...]
- connected_call_plan_fields: tuple[str, ...]
```

## Section 1 - Register Identity

| Field key          | Workbook concept        | Kind        | Likely source                           | Connected packet fields                       |
| ------------------ | ----------------------- | ----------- | --------------------------------------- | --------------------------------------------- |
| `risk_register_id` | Register identifier     | scalar text | computed                                | none                                          |
| `opportunity_id`   | Opportunity link        | scalar text | opportunity record                      | `opportunity_name`                            |
| `pursuit_name`     | Salesforce Pursuit Name | scalar text | opportunity record or human input       | `opportunity_name`                            |
| `salesforce_id`    | Salesforce ID           | scalar text | CRM/API later or human input            | `salesforce_id`                               |
| `prepared_by`      | Prepared by             | person/text | human input or local profile            | `prepared_by`, pursuit team                   |
| `ms4_date`         | MS4 Date                | date        | packet milestone context or human input | `milestone_stage`, `packet_date`, gate timing |
| `status_date`      | Status Date             | date        | human input/computed                    | packet date/readiness context                 |
| `template_profile` | Workbook/export profile | scalar text | computed                                | artifact export profile                       |

## Section 2 - Risk Or Opportunity Row

| Field key             | Workbook concept                       | Kind          | Likely source                    | Connected packet fields                          |
| --------------------- | -------------------------------------- | ------------- | -------------------------------- | ------------------------------------------------ |
| `risk_item_id`        | Risk ID                                | scalar text   | computed/human input             | risk table row                                   |
| `risk_short_title`    | Risk Short Title / Risk Statement      | scalar/prose  | human input/model draft          | risk summary, SWOT                               |
| `risk_or_opportunity` | Risk or Opportunity                    | enum          | human input/model draft          | risks, opportunities, SWOT                       |
| `risk_category`       | Category                               | enum          | human input/model draft          | workstream/readiness/gap context                 |
| `risk_description`    | Risk or Opportunity Description        | prose         | model draft/human review         | risk narrative                                   |
| `measurable_impact`   | Measurable Impact of Event             | prose         | model draft/human review         | risk impact, pWin rationale, gate recommendation |
| `risk_response`       | Risk Response                          | prose         | model draft/human review         | mitigation approach, next actions                |
| `response_type`       | Mitigate, Accept, Cost, or Avoid       | enum          | human review/model draft         | action plan / pricing response                   |
| `risk_cost`           | Risk Cost if applicable                | money         | finance/pricing/human input      | pricing strategy, cost exposure                  |
| `risk_probability`    | Risk Probability                       | enum/score    | model draft/human review         | confidence/risk severity                         |
| `impact`              | Impact                                 | enum/score    | model draft/human review         | risk severity/gate rationale                     |
| `review_status`       | Ariadne review state                   | enum          | computed                         | packet field review state                        |
| `confidence`          | Ariadne confidence                     | score/label   | model inferred/reviewer adjusted | evidence status                                  |
| `source_evidence_ids` | Supporting evidence links              | repeating ref | accepted evidence                | source traceability                              |
| `source_raw_item_id`  | Originating raw capture item           | scalar ref    | computed                         | traceability                                     |
| `source_draft_id`     | Originating capture intelligence draft | scalar ref    | computed                         | traceability                                     |

Preferred repeating model:

```text
RiskRegisterItem
- risk_item_id
- opportunity_id
- risk_or_opportunity: risk | opportunity
- category
- short_title
- description
- measurable_impact
- response_plan
- response_type: mitigate | accept | cost | avoid | opportunity_capture | unknown
- risk_cost
- probability
- impact
- owner
- status
- evidence_ids
- source_raw_item_id
- source_draft_id
- source_draft_part_id
- reviewer_rationale
- review_edits
```

## Section 3 - Controlled Lookups

The active workbook exposes these useful lookup families. Ariadne should keep them configurable because later private export profiles may use different labels.

| Lookup key            | Workbook values observed                                                                                   | Notes                                                                                 |
| --------------------- | ---------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| `risk_or_opportunity` | Risk, Opportunity                                                                                          | Primary item type.                                                                    |
| `risk_category`       | Contractual, ESH, Labor, Management, Procurement, Property, Regional, Supply Chain, Technology, Transition | Maps naturally to capture workstreams and packet gaps.                                |
| `response_type`       | Mitigate, Accept, Cost, Avoid                                                                              | Workbook labels; Ariadne may add `opportunity_capture` internally for upside actions. |
| `risk_probability`    | Low <35%, Medium 35-65%, High >65%                                                                         | Good enough for first review UI; do not over-model matrix math yet.                   |
| `impact`              | Marginal, Moderate, Significant                                                                            | First-stage qualitative severity label.                                               |

## Section 4 - Expanded / Future Fields

The workbook also includes an older expanded format with richer risk management fields. These should be future-ready but not implemented in the first Quick Capture slice.

| Field group            | Example fields                                                                      | Ariadne use                                 |
| ---------------------- | ----------------------------------------------------------------------------------- | ------------------------------------------- |
| `risk_status`          | open/closed, status comments, occurred, major risk                                  | Lifecycle for active risk management.       |
| `ownership`            | risk owner, responsible manager, responsible entity                                 | Action Plan owner and accountability.       |
| `treatment`            | treatment, risk control, plan overview, plan status                                 | Risk Response Plan detail.                  |
| `multi_factor_scoring` | probability, manageability, cost, schedule, environment, safety, reputation         | Later risk scoring module.                  |
| `associations`         | primary association, associated risks                                               | Knowledge Graph / related risk connections. |
| `schedule_impact`      | impacted activities, optimistic/most likely/pessimistic days                        | Schedule risk analysis and packet timing.   |
| `cost_impact`          | cost mapping, probability event will occur, optimistic/most likely/pessimistic cost | Pricing and risk cost exposure.             |
| `upload_notes`         | PRM upload notes                                                                    | Artifact export / external tool reminder.   |

## Shared Fields With Briefing Packet Dictionary

These overlaps should become explicit connections so Ariadne can show when a risk-register field can inform an existing packet field, packet gap, or action plan item.

| Risk register field   | Briefing packet field / concept                          | Connection                                                                                                           |
| --------------------- | -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `pursuit_name`        | `opportunity_name`                                       | Same Opportunity identity.                                                                                           |
| `salesforce_id`       | `salesforce_id`                                          | Same CRM/opportunity identifier.                                                                                     |
| `prepared_by`         | `prepared_by`, pursuit team                              | Same preparer/accountability context.                                                                                |
| `ms4_date`            | `milestone_stage`, `packet_date`                         | Gate timing and pricing approval readiness.                                                                          |
| `risk_short_title`    | risk summary / SWOT                                      | User-facing risk headline.                                                                                           |
| `risk_or_opportunity` | `swot_opportunities`, `swot_threats`, packet risk fields | Distinguishes upside from threat.                                                                                    |
| `risk_category`       | Core Capture Workstream / packet section                 | Routes risk to customer, transition, pricing, staffing, supply chain, technology, contractual, or execution context. |
| `risk_description`    | risks, `opportunity_context`, `what_it_takes_to_win`     | Narrative input after review.                                                                                        |
| `measurable_impact`   | risk impact, pWin rationale, gate recommendation         | Explains why the risk matters.                                                                                       |
| `risk_response`       | mitigation approach, `recommendation`, action plan       | Becomes response narrative and next actions.                                                                         |
| `response_type`       | gate recommendation / pricing treatment                  | Accept, cost, avoid, mitigate affects decision recommendation.                                                       |
| `risk_cost`           | pricing strategy, cost exposure                          | Pricing and estimate input if approved.                                                                              |
| `risk_probability`    | confidence/severity                                      | Risk severity and assumption context.                                                                                |
| `impact`              | packet risk severity                                     | Helps rank risks in packet view.                                                                                     |
| `source_evidence_ids` | evidence traceability                                    | Same Evidence Item links.                                                                                            |

## Shared Fields With Call Plan / Engagement Examples

The private call-plan examples and engagement logs can help Ariadne infer risk signals, but they remain ignored local reference material. Any extracted signal still needs review before promotion.

| Call plan / engagement field | Risk register field                               | Connection                                                      |
| ---------------------------- | ------------------------------------------------- | --------------------------------------------------------------- |
| `meeting_purpose`            | `risk_category`, `risk_description`               | Context for why a risk was discussed.                           |
| `desired_outcome`            | `risk_response`, `response_type`                  | Desired customer or pursuit outcome can shape mitigation.       |
| `key_discussion_points`      | `risk_short_title`, `risk_description`            | Discussion topics can become risk/opportunity statements.       |
| `customer_issues`            | `risk_description`, `measurable_impact`           | Customer pain can become threat or opportunity framing.         |
| `customer_hot_buttons`       | `impact`, `risk_response`                         | Priorities can change severity and response plan.               |
| `customer_needs`             | `risk_category`, `risk_response`                  | Need gaps can create action-oriented risk responses.            |
| `customer_fears`             | `risk_probability`, `impact`, `risk_description`  | Concern signals can inform probability/impact, review required. |
| `funding_status`             | `risk_category`, `measurable_impact`, `risk_cost` | Funding issues can become cost/schedule/pWin risk.              |
| `meeting_summary`            | `risk_description`, `source_evidence_ids`         | Meeting notes become source evidence candidates.                |
| `action_item_next_step`      | `risk_response`, Action Plan Item                 | Follow-up can mitigate or exploit a risk/opportunity.           |
| `owner`                      | `owner`                                           | Same accountability concept.                                    |
| `due_date`                   | response due date / Action Plan Item due date     | Same timing concept.                                            |

## Quick Capture Inference Hints

When raw notes, pasted text, uploads, call logs, or engagement examples mention risk-like signals, Ariadne should consider these draft outputs:

| Raw signal                                             | Draft output candidate                               |
| ------------------------------------------------------ | ---------------------------------------------------- |
| "risk", "concern", "weak", "threat", "gap", "issue"    | Risk Register Item candidate                         |
| "opportunity", "advantage", "upside", "could improve"  | Opportunity item candidate                           |
| Customer complaint or hot button                       | Risk description plus packet customer-context update |
| Funding, budget, cost, estimate, price pressure        | Risk cost / pricing exposure candidate               |
| Transition, staffing, supply chain, schedule           | Category and measurable impact candidate             |
| Mitigation, response, workaround, partner, proof point | Risk Response Plan candidate                         |
| Named owner or due date                                | Action Plan Item candidate linked to risk response   |
| Low/medium/high likelihood or severity language        | Probability/impact draft, review required            |

## Skill And Agent Placeholders

These names are placeholders so Ariadne remembers likely capability connections without pretending the skills already exist.

| Placeholder                    | Purpose                                                                                      | Likely inputs                                                     | Review rule                       |
| ------------------------------ | -------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- | --------------------------------- |
| `risk_register_builder`        | Draft normalized risk/opportunity items from raw notes, uploads, call logs, and packet gaps. | Raw Capture Item, Capture Intelligence Draft Part, Evidence Items | User approves before promotion.   |
| `risk_statement_framer`        | Rewrite rough notes into threat/opportunity plus measurable impact language.                 | Draft risk signal, source context                                 | User edits before trusted row.    |
| `risk_scoring_recommender`     | Suggest probability, impact, category, and confidence.                                       | Evidence, reference context, historical examples                  | Human confirmation required.      |
| `risk_response_planner`        | Draft mitigation, accept, cost, avoid, or opportunity-capture response plan.                 | Risk item, packet gaps, action plan context                       | Human approval before actions.    |
| `packet_risk_update_mapper`    | Map accepted risk items to packet fields, SWOT, recommendation, and gate rationale.          | Risk Register Item, Packet Field Answers                          | Review before packet write.       |
| `call_log_risk_extractor`      | Extract risk/opportunity signals from private call logs and engagement examples.             | Call Plan notes/examples, uploaded text                           | Draft only; no trusted evidence.  |
| `pricing_risk_exposure_helper` | Draft risk-cost and pricing exposure questions.                                              | Risk item, estimate context, pricing packet fields                | Ask before finance-sensitive use. |
| `hermes_risk_pattern_observer` | Detect repeated risk patterns and propose workflow or skill improvements.                    | Accepted risk items, discarded drafts, edits                      | Improvement Proposal only.        |

## First Implementation Recommendation

Do not build workbook export first. Use this dictionary to strengthen Quick Capture and review workflows:

1. Detect when raw capture text appears to contain a risk or upside opportunity.
2. Draft risk/opportunity statement, category, impact, response, probability, and follow-up questions.
3. Show shared packet-field, call-plan, and action-plan connections before promotion.
4. Require user approval before creating Risk Register Items, Evidence Items, Action Plan Items, Packet Field Answers, or Shared Knowledge Entities.
