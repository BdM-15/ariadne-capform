# Call Plan Data Dictionary Draft

Status: draft for user review  
Source reference: local private DOCX under `docs/reference/call_plan_template/`  
Git handling: the private template folder is ignored; this normalized dictionary is commit-safe reference material.

## Purpose

This dictionary identifies data elements in a customer call plan template and normalizes them into Ariadne concepts. It should help Quick Capture, Capture Intelligence Drafts, packet updates, action recommendations, Hermes improvement proposals, research prompts, and skill invocation.

The template contains four kinds of content:

| Kind | Meaning | Examples |
| ---- | ------- | -------- |
| Scalar data | Single value | meeting date, customer name, opportunity name |
| Enum / choice | Constrained value | requested by, contact frequency, degree of influence, type of exchange |
| Repeating row | Table/list item | attendees, discussion questions, action items |
| Prose | Narrative capture text | purpose, desired outcome, notes, customer issues |

Every field should eventually carry provenance and review status.

```text
CallPlanField[T]
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
```

## Section 1 - Call Plan Identity And Meeting Logistics

| Field key | Template concept | Kind | Likely source | Connected packet fields |
| --------- | ---------------- | ---- | ------------- | ----------------------- |
| `call_plan_id` | Call plan identifier | scalar text | computed | none |
| `opportunity_id` | Opportunity link | scalar text | opportunity record | `opportunity_name` |
| `opportunity_name` | Opportunity Name | scalar text | opportunity record or human input | `opportunity_name` |
| `salesforce_id` | Salesforce ID Number | scalar text | CRM/API later or human input | `salesforce_id` |
| `meeting_date` | Date | date | human input/calendar | packet timing context |
| `meeting_time` | Time | time | human input/calendar | none |
| `location_or_event` | Location/Event | scalar/prose | human input/calendar | none |
| `requested_by` | Requested By | enum | human input | none |
| `organization_branch` | Organization/Branch | scalar text | human input/evidence | customer or org context |
| `meeting_purpose` | Purpose of customer meeting | prose | human input/model draft | `opportunity_context`, `customer_need_funding_status` |
| `desired_outcome` | Desired Outcome | prose | human input/model draft | `what_it_takes_to_win`, `recommendation` |
| `key_discussion_points` | Key Discussion Points | prose/list | human input/model draft | `opportunity_context`, `what_it_takes_to_win` |
| `type_of_exchange` | Type of Exchange | enum | human input | customer engagement context |
| `decision_phase` | Decision Phase | enum/text | human input/model inferred | `crm_stage`, `milestone_stage` |
| `call_plan_status` | Call plan workflow status | enum | computed | none |

## Section 2 - Research / Investment Topics

| Field key | Template concept | Kind | Likely source | Connected packet fields |
| --------- | ---------------- | ---- | ------------- | ----------------------- |
| `existing_research_investments_to_discuss` | Existing research or innovation projects to bring to customer | prose/list | human input/capability catalog | `strategic_fit_summary`, `what_it_takes_to_win` |
| `potential_research_investment_need` | Potential investment to investigate for this customer | prose/list | meeting prep/customer signal | `unique_investment_requirements`, `what_it_takes_to_win` |

Note: the source template names a specific internal research acronym. Ariadne should model this generically as research or investment topics until a private export profile maps it back to organization-specific wording.

## Section 3 - Customer Contact And Attendees

| Field key | Template concept | Kind | Likely source | Connected packet fields |
| --------- | ---------------- | ---- | ------------- | ----------------------- |
| `customer_name` | Customer Name | scalar text | opportunity/evidence/human input | `customer_name` |
| `customer_poc_name` | Customer POC first and last name | person | human input/evidence | customer stakeholders |
| `customer_poc_email` | Customer POC email | scalar text | human input/evidence | customer stakeholders |
| `customer_poc_phone` | Customer POC phone | scalar text | human input/evidence | customer stakeholders |
| `customer_poc_role` | Customer POC organizational role | scalar text | human input/evidence | customer stakeholders |
| `contact_frequency` | Contact Frequency | enum | human input/history | customer engagement status |
| `customer_personality_type` | Personality Type | scalar/enum | subjective human note | customer stakeholder context |
| `degree_of_influence` | Degree of influence | enum | human judgment/evidence | customer stakeholder context |
| `customer_attendees` | Customer attendees | repeating row | human input/calendar | customer stakeholders |
| `organization_attendees` | Internal attendees | repeating row | human input/calendar | pursuit team |
| `customer_lead_attendee_id` | Identify customer lead | scalar/ref | human input | customer stakeholders |
| `internal_lead_attendee_id` | Identify internal lead | scalar/ref | human input | pursuit team |

Preferred repeating model:

```text
CallPlanAttendee
- attendee_id
- name
- email
- phone
- organization
- role
- attendee_type: customer | internal | partner | unknown
- meeting_lead: bool
- influence_level: high | medium | low | unknown
- notes
- evidence_ids
```

## Section 4 - Pre-Meeting Customer Assessment

| Field key | Template concept | Kind | Likely source | Connected packet fields |
| --------- | ---------------- | ---- | ------------- | ----------------------- |
| `customer_assessment_strengths` | Strengths | prose/list | human input/evidence/model draft | `swot_strengths`, `strategic_fit_summary` |
| `customer_assessment_weaknesses` | Weaknesses | prose/list | human input/evidence/model draft | `swot_weaknesses`, `what_it_takes_to_win` |
| `customer_current_view_summary` | Customer assessment summary | prose | model synthesis/human review | `customer_need_funding_status`, `opportunity_context` |

These fields are subjective and should stay in review until backed by evidence or user confirmation.

## Section 5 - Discussion Topics And Questions

| Field key | Template concept | Kind | Likely source | Connected packet fields |
| --------- | ---------------- | ---- | ------------- | ----------------------- |
| `discussion_topics` | Discussion topics | repeating row | human input/model draft | `opportunity_context`, `what_it_takes_to_win` |
| `question_owner` | Owner name | person/ref | human input | pursuit team/action owner |
| `planned_question` | Question | prose | human input/model draft | evidence gap prompts |
| `planned_follow_up_question` | Follow-up question | prose | human input/model draft | evidence gap prompts |
| `question_sequence` | Intentional question order | scalar integer | computed/human input | none |

Preferred repeating model:

```text
CallPlanQuestion
- sequence
- topic
- owner
- question
- follow_up_question
- objective
- related_gap_key
- related_packet_fields
```

## Section 6 - Customer Information And Insight Profile

| Field key | Template concept | Kind | Likely source | Connected packet fields |
| --------- | ---------------- | ---- | ------------- | ----------------------- |
| `customer_issues` | Issues | prose/list | notes/evidence/model draft | `opportunity_context`, risk fields |
| `customer_hot_buttons` | Hot Buttons | prose/list | notes/evidence/model draft | `customer_need_funding_status`, `what_it_takes_to_win` |
| `customer_needs` | Needs | prose/list | notes/evidence/model draft | `customer_need_funding_status` |
| `customer_wants` | Wants | prose/list | notes/evidence/model draft | `what_it_takes_to_win`, discriminator fields |
| `customer_motivations` | Motivations | prose/list | notes/evidence/model draft | `opportunity_context`, `recommendation` |
| `customer_fears` | Fears | prose/list | notes/evidence/model draft | risk fields, `what_it_takes_to_win` |
| `customer_beliefs` | Beliefs | prose/list | notes/evidence/model draft | `competitive_landscape_summary`, strategy fields |
| `customer_biases` | Biases | prose/list | notes/evidence/model draft | `competitive_landscape_summary`, `swot_threats` |
| `customer_need_want_summary` | Customer Need/Wants | prose | meeting notes/model synthesis | `customer_need_funding_status`, `what_it_takes_to_win` |
| `funding_status` | Funding Status | prose/enum | notes/evidence/human input | `customer_need_funding_status` |

Preferred grouped model:

```text
CustomerInsightProfile
- issues
- hot_buttons
- needs
- wants
- motivations
- fears
- beliefs
- biases
- funding_status
- evidence_ids
- confidence
- review_status
```

## Section 7 - Meeting Notes And Summary

| Field key | Template concept | Kind | Likely source | Connected packet fields |
| --------- | ---------------- | ---- | ------------- | ----------------------- |
| `meeting_notes` | Notes | prose | raw meeting notes | evidence candidates |
| `meeting_summary` | Meeting Notes and Summary | prose | model draft/human review | `opportunity_context`, `acquisition_capture_progress` |
| `what_changed` | What changed after meeting | prose/list | model draft/human review | packet gap updates/action plan |
| `source_evidence_candidates` | Evidence candidates from notes | repeating row | model draft | Evidence Items after review |
| `packet_update_candidates` | Packet update candidates from notes | repeating row | model draft | Packet Field Answers after review |

## Section 8 - Action Items And Follow-Up

| Field key | Template concept | Kind | Likely source | Connected packet fields |
| --------- | ---------------- | ---- | ------------- | ----------------------- |
| `action_item_next_step` | Action Item/Next Step | repeating row | notes/human input/model draft | `action_plan` |
| `deliverable` | Deliverable | scalar/prose | notes/human input/model draft | `action_plan` |
| `owner` | Owner | person/ref | notes/human input | `action_plan` owner |
| `due_date` | Due Date | date | notes/human input | `action_plan` due date |
| `follow_up_requirements` | Follow-up commitments | prose/list | notes/model draft | `action_plan`, packet gaps |
| `meeting_goal_achieved` | Did meeting achieve intended goals? | boolean/prose | human review | `acquisition_capture_progress` |
| `actions_documented` | Were clear actions, owners, follow-ups documented? | boolean | computed/human review | action readiness |
| `engagement_log_required` | Log engagement in external tool | boolean | template/default | none |
| `redaction_required_before_external_upload` | Redact controlled info before upload | boolean | template/default | compliance reminder |

Preferred repeating model:

```text
CallPlanActionCommitment
- action
- deliverable
- owner
- due_date
- related_customer_signal
- related_packet_fields
- evidence_ids
- status
```

## Shared Fields With Briefing Packet Dictionary

These overlaps should become explicit connections so Ariadne can show when one call plan field can inform an existing packet field or action plan item.

| Call plan field | Briefing packet field / concept | Connection |
| --------------- | -------------------------------- | ---------- |
| `opportunity_name` | `opportunity_name` | Same Opportunity identity. |
| `salesforce_id` | `salesforce_id` | Same CRM/opportunity identifier. |
| `customer_name` | `customer_name` | Same customer identity; candidate Shared Knowledge Entity. |
| `organization_branch` | customer/org context | May refine customer organization scope. |
| `meeting_purpose` | `opportunity_context`, `customer_need_funding_status` | Can explain why engagement matters. |
| `desired_outcome` | `what_it_takes_to_win`, `recommendation` | Can shape next-step recommendation. |
| `key_discussion_points` | `opportunity_context`, `what_it_takes_to_win` | Can become packet narrative inputs after review. |
| `decision_phase` | `crm_stage`, `milestone_stage` | Can help map engagement to lifecycle/milestone context. |
| `customer_assessment_strengths` | `swot_strengths`, `strategic_fit_summary` | Can feed SWOT and fit narrative. |
| `customer_assessment_weaknesses` | `swot_weaknesses`, `what_it_takes_to_win` | Can feed gap/risk mitigation work. |
| `customer_issues` | `opportunity_context`, risk fields | Can become evidence-backed problem statement. |
| `customer_hot_buttons` | `customer_need_funding_status`, `what_it_takes_to_win` | Can guide win themes and customer context. |
| `customer_needs` | `customer_need_funding_status` | Direct customer need input. |
| `customer_wants` | `what_it_takes_to_win`, discriminator candidates | Differentiator input when evidence-backed. |
| `customer_motivations` | `opportunity_context`, `recommendation` | Explains likely decision drivers. |
| `customer_fears` | risk fields, `what_it_takes_to_win` | Can create mitigation actions. |
| `customer_beliefs` | `competitive_landscape_summary` | May shape positioning or ghost strategy. |
| `customer_biases` | `competitive_landscape_summary`, `swot_threats` | Competitive/customer perception signal. |
| `funding_status` | `customer_need_funding_status` | Same funding feasibility concept. |
| `meeting_summary` | `opportunity_context`, `acquisition_capture_progress` | Can update packet narrative after review. |
| `action_item_next_step` | action plan slide / Capture Action Plan Item | Same action concept. |
| `deliverable` | action plan deliverable/context | Defines expected output for action. |
| `owner` | action plan owner | Same accountability concept. |
| `due_date` | action plan due date | Same timing concept. |

## Quick Capture Inference Hints

When raw notes mention a customer meeting, Ariadne should consider these draft outputs:

| Raw signal | Draft output candidate |
| ---------- | ---------------------- |
| Customer pain, complaint, issue | `customer_issues`, `customer_hot_buttons`, possible Evidence Item |
| Must-have requirement | `customer_needs`, packet customer context update |
| Nice-to-have preference | `customer_wants`, discriminator candidate |
| Budget, unfunded need, timing concern | `funding_status`, risk/gap candidate |
| Named person and role | `customer_poc` or attendee Shared Knowledge Entity candidate |
| Commitment, owner, date | `CallPlanActionCommitment` / Action Plan Item candidate |
| Follow-up question | `CallPlanQuestion` or Capture Intelligence Draft follow-up question |
| Perception of organization strength/weakness | SWOT update candidate, confidence-gated |

## First Implementation Recommendation

Do not build document export first. Use this dictionary to strengthen Quick Capture and review workflows:

1. Detect when raw capture text appears to be customer-meeting material.
2. Draft customer issues, needs, wants, hot buttons, action commitments, packet update candidates, and follow-up questions.
3. Show shared packet-field connections before promotion.
4. Require user approval before creating Evidence Items, Action Plan Items, Packet Field Answers, or Shared Knowledge Entities.