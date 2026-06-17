# Call Plan Model Draft

Status: draft for user review  
Source reference: local private DOCX under `docs/reference/call_plan_template/`  
Git handling: the private template folder is ignored; this normalized model is commit-safe reference material.

## Working Understanding

A Call Plan is a pre-meeting and post-meeting capture workflow. It turns an intended customer interaction into a prepared, outcome-driven engagement: why the meeting matters, what the team needs to learn, who owns each question, what customer signals are captured, and which follow-up commitments move the pursuit forward.

The template should not become the source of truth. Ariadne should treat it as an Artifact Export Profile candidate and model the underlying capture objects directly:

```text
Opportunity -> Call Plan -> Customer Meeting -> Customer Insight -> Capture Intelligence Draft -> Evidence / Action Plan / Packet Updates
```

The Call Plan should help Ariadne before, during, and after customer engagement:

| Moment                  | Ariadne job                                                                                             | Review rule                        |
| ----------------------- | ------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| Before meeting          | Prepare purpose, goals, roles, questions, likely customer issues, desired outcomes                      | User edits and approves before use |
| During or after meeting | Capture notes, customer signals, issues, hot buttons, needs, wants, motivations, fears, beliefs, biases | Raw notes stay review-gated        |
| After meeting           | Draft action commitments, follow-up questions, packet implications, evidence candidates                 | User accepts before trusted writes |

## Core Concepts

| Concept                       | Meaning                                                                                                   | Ariadne connection                                                 |
| ----------------------------- | --------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `Call Plan`                   | Planned customer interaction package tied to one Opportunity or exploratory capture thread.               | Product Workflow / Engagement Artifact                             |
| `Customer Meeting`            | One scheduled or completed engagement with logistics, attendees, purpose, and outcomes.                   | Source context for Raw Capture Items and Evidence Items            |
| `Call Plan Attendee`          | Customer or internal participant with role, contact info, influence, and meeting responsibility.          | Shared Knowledge Entity candidate for people/stakeholders          |
| `Customer Assessment`         | Pre-meeting view of how the customer sees the organization, including strengths and weaknesses.           | Capture Intelligence Draft input and customer-context packet input |
| `Discussion Guide`            | Ordered questions/topics with owners and follow-up prompts.                                               | Guided Capture Mentor and skill invocation input                   |
| `Customer Insight Profile`    | Structured view of issues, hot buttons, needs, wants, motivations, fears, beliefs, and biases.            | Opportunity Knowledge candidate after review                       |
| `Call Plan Action Commitment` | Follow-up action, deliverable, owner, and due date from the meeting.                                      | Capture Action Plan Item candidate                                 |
| `Engagement Log Reminder`     | Post-meeting requirement to log engagement and redact controlled info before upload to any external tool. | Compliance/reminder, not trusted evidence by itself                |

## Relationship To Existing Ariadne Concepts

- A `Call Plan` belongs to an `Opportunity` when the opportunity is known; otherwise it can start as an `Exploratory Capture Session`.
- A completed customer meeting can create one or more `Raw Capture Items` from notes, transcript fragments, or quick capture text.
- Quick Capture can use the call plan dictionary to infer a `Capture Intelligence Draft` with customer issues, needs, hot buttons, action candidates, packet implications, and follow-up questions.
- Accepted meeting notes become `Source Evidence`; Ariadne synthesis becomes `Derived Evidence` only after review.
- Accepted follow-up commitments become `Action Plan Items`.
- Accepted customer and opportunity data can update `Packet Field Answers` for the Living Briefing Packet.
- People, customers, organizations, and recurring needs can become `Shared Knowledge Entities` after review.
- Hermes can observe repeated call-plan friction and propose `Improvement Proposals`, such as missing question prompts, recurring customer themes, or better skill chains.

## Call Plan Lifecycle

```text
draft -> prepared -> held -> notes_captured -> draft_review -> promoted_outputs -> archived
```

| Status             | Meaning                                                                            |
| ------------------ | ---------------------------------------------------------------------------------- |
| `draft`            | Initial call plan created from opportunity context, quick capture, or human input. |
| `prepared`         | User has reviewed purpose, questions, roles, and desired outcomes.                 |
| `held`             | Meeting occurred; notes may or may not be captured yet.                            |
| `notes_captured`   | Raw notes or summary entered into Ariadne.                                         |
| `draft_review`     | Ariadne has created Capture Intelligence Draft outputs for user review.            |
| `promoted_outputs` | Accepted evidence/actions/packet updates have been written.                        |
| `archived`         | Meeting record retained for context and future learning.                           |

## Evidence And Review Rules

- Private call plan templates are export/profile references only; they are not committed.
- Private call logs and customer engagement examples in `docs/reference/call_plan_template/` are local-only reference examples for Ariadne, Hermes, and future skills. They can guide inference patterns, but extracted signals still enter through Quick Capture, Document Intake, or review-gated workflow outputs.
- Call plan fields should carry provenance just like packet fields.
- Customer perceptions, motivations, fears, beliefs, and biases are subjective signals; Ariadne should present them as reviewable notes, not facts.
- External engagement-tool upload reminders are task prompts, not evidence.
- Controlled or sensitive info must be redacted before any external upload; Ariadne should preserve this as a compliance reminder.
- No customer-facing artifact, engagement log, evidence item, action item, or packet answer should be finalized without human review.

## Data Dictionary Direction

Detailed draft: [CALL_PLAN_DATA_DICTIONARY.md](CALL_PLAN_DATA_DICTIONARY.md).

The first implementation should use Pydantic models behind a small interface, mirroring Packet Field discipline:

```text
CallPlanField
- key
- label
- value
- kind
- source
- evidence_ids
- status
- confidence
- notes
- connected_packet_fields
```

The useful first product slice is not document export. It is Quick Capture support: turn rushed meeting notes into a Capture Intelligence Draft that can identify customer issues, hot buttons, needs, wants, action candidates, and packet field update candidates.
