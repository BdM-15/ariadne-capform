# Risk Register Model Draft

Status: draft for user review  
Source reference: local private XLSX under `docs/reference/risk_register/`  
Git handling: private workbook files in this folder are ignored; this normalized model is commit-safe reference material.

## Working Understanding

A Risk Register is both a capture workflow and an eventual artifact. It tracks threats and upside opportunities that can affect win probability, price, schedule, transition, execution, contract terms, staffing, supply chain, technology, safety, reputation, and customer confidence.

The workbook should not become Ariadne's source of truth. Ariadne should model the underlying pursuit risk objects directly, then later export into a private workbook profile if needed:

```text
Opportunity -> Risk Register -> Risk Register Item -> Risk Response Plan -> Evidence / Action Plan / Packet Updates
```

Risk register work belongs close to the Living Briefing Packet and Call Plan workflows:

| Moment         | Ariadne job                                                                                                | Review rule                                    |
| -------------- | ---------------------------------------------------------------------------------------------------------- | ---------------------------------------------- |
| Intake         | Detect risk or opportunity signals from notes, uploads, call logs, packet gaps, and public-source research | Draft only; no trusted risk row without review |
| Framing        | Rewrite rough signals into threat/opportunity plus measurable impact language                              | User edits before promotion                    |
| Scoring        | Propose probability, impact, category, exposure, and confidence based on evidence                          | User confirms score and assumptions            |
| Response       | Draft mitigation, accept, cost, avoid, or opportunity-capture approach                                     | User approves before action/packet updates     |
| Follow-through | Create linked Action Plan Items, Packet Field Answers, and follow-up questions                             | Promotion preserves provenance                 |

## Core Concepts

| Concept              | Meaning                                                                                   | Ariadne connection                                          |
| -------------------- | ----------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| `Risk Register`      | Opportunity-scoped collection of risk and opportunity items.                              | Product Workflow / Engagement Artifact                      |
| `Risk Register Item` | One risk or opportunity row with statement, impact, category, score, response, and owner. | Capture Intelligence Draft Part promotion target            |
| `Risk Statement`     | Short title plus structured threat/opportunity description.                               | Drafted from raw notes, evidence, packet gaps, or call logs |
| `Measurable Impact`  | Cost, schedule, win probability, execution, compliance, or customer impact.               | Packet risk field and pWin/gate rationale input             |
| `Risk Response Plan` | Mitigate, accept, cost, avoid, or opportunity-capture action.                             | Capture Action Plan candidate                               |
| `Risk Score`         | Probability and impact assessment, with optional calculated severity.                     | Evidence-backed recommendation, review required             |
| `Risk Cost`          | Explicit cost exposure or provision when included in estimate.                            | Pricing/finance packet connection                           |
| `Risk Owner`         | Person or workstream accountable for response.                                            | Action Plan owner / pursuit team connection                 |

## Relationship To Existing Ariadne Concepts

- A `Risk Register` belongs to an `Opportunity`.
- A `Risk Register Item` can be drafted from a `Capture Intelligence Draft Part`, a `Call Plan Action Commitment`, a `Packet Field Answer`, a `Raw Capture Item`, or an `Evidence Item`.
- A risk or opportunity signal from a customer meeting should stay review-gated until the user accepts the source, framing, and response plan.
- Accepted risk items can update Living Briefing Packet risk fields, SWOT threats/opportunities, pricing exposure, schedule exposure, action plan items, and decision-gate recommendations.
- Risk statements should preserve the source raw item ID, draft ID, evidence IDs, reviewer rationale, and edit history.
- Hermes can observe repeated risk patterns and propose `Improvement Proposals`, such as missing risk prompts, weak response plans, recurring scoring disagreements, or a needed risk-register skill chain.

## Risk Register Lifecycle

```text
draft_signal -> framed_item -> scored_item -> response_planned -> promoted_outputs -> monitored -> closed
```

| Status             | Meaning                                                                              |
| ------------------ | ------------------------------------------------------------------------------------ |
| `draft_signal`     | Ariadne detected a possible risk or opportunity from raw material.                   |
| `framed_item`      | User or AI drafted threat/opportunity and measurable impact language.                |
| `scored_item`      | Probability and impact have been proposed or confirmed.                              |
| `response_planned` | Mitigation, acceptance, cost, avoidance, or opportunity-capture response is drafted. |
| `promoted_outputs` | Linked packet updates and action items have been accepted.                           |
| `monitored`        | Item remains active and reviewed over time.                                          |
| `closed`           | Item no longer needs active management.                                              |

## Evidence And Review Rules

- Private workbook templates and example rows are local reference only; do not commit them.
- Risk register fields should carry provenance and review status like packet fields and call-plan fields.
- Risk and opportunity statements are not facts by default; they are reviewable interpretations until supported by evidence.
- Probability, impact, and risk cost are recommendation fields; Ariadne can draft them, but human review is required before they affect gate recommendations, pricing, or packet outputs.
- No risk response plan should create trusted action items, packet field answers, or reusable insight without promotion.

## Data Dictionary Direction

Detailed draft: [RISK_REGISTER_DATA_DICTIONARY.md](RISK_REGISTER_DATA_DICTIONARY.md).

The first implementation should not build workbook export. It should strengthen Quick Capture and draft promotion:

```text
RiskRegisterItem
- key
- opportunity_id
- risk_or_opportunity
- category
- statement
- measurable_impact
- response_type
- response_plan
- probability
- impact
- owner
- evidence_ids
- source_raw_item_id
- source_draft_id
- review_status
```

The useful first product slice is inference and routing: turn rushed notes, call logs, uploaded text, and packet gaps into reviewable risk/opportunity draft parts that can become Action Plan Items, Packet Field Answers, or Risk Register Items after user approval.
