# Thread Reference Corpus

Authoritative domain references for packet fields, artifacts, intel schema, and Shipley methodology.
These files seed `packet_field_definitions`, vault `data-elements/`, intel PG column docs, and Grok prompts.

## Living Briefing Packet (central artifact)

| File | Role |
|------|------|
| [briefing_packet/BRIEFING_PACKET_MODEL.md](briefing_packet/BRIEFING_PACKET_MODEL.md) | Slide-deck-shaped decision artifact; MS1–MS4 gate model; slide catalog |
| [briefing_packet/BRIEFING_PACKET_DATA_DICTIONARY.md](briefing_packet/BRIEFING_PACKET_DATA_DICTIONARY.md) | **Primary seed** for `packet_field_definitions` — field keys, kinds, milestone gates |

Backend seed: `backend/src/thread/domain/packet_field_seed.py` (generated from MS1-critical subset; extend per dictionary).

## Call Plan (customer engagement)

| File | Role |
|------|------|
| [call_plan/CALL_PLAN_MODEL.md](call_plan/CALL_PLAN_MODEL.md) | Workflow: draft → prepared → held → promoted outputs |
| [call_plan/CALL_PLAN_DATA_DICTIONARY.md](call_plan/CALL_PLAN_DATA_DICTIONARY.md) | Field keys linked to packet fields via `connected_packet_fields` |

MVP: stub models + future artifact export profile. Research lens `call_plan_cro` uses this dictionary.

## Risk Register

| File | Role |
|------|------|
| [risk_register/RISK_REGISTER_MODEL.md](risk_register/RISK_REGISTER_MODEL.md) | Risk item lifecycle; links to packet slide 13 and Action Matrix |
| [risk_register/RISK_REGISTER_DATA_DICTIONARY.md](risk_register/RISK_REGISTER_DATA_DICTIONARY.md) | `RiskRegisterItem` field keys; scoring and response enums |

MVP: `proposal_risks` / `execution_risks` packet fields + repeating row stub.

## Federal spending / intel layer

| File | Role |
|------|------|
| [../usaspending/USAspending.gov Data Dictionary.pdf](../usaspending/USAspending.gov%20Data%20Dictionary.pdf) | Official column semantics for bulk award data |
| [../usaspending/data-dictionary-plain-english.md](../usaspending/data-dictionary-plain-english.md) | Capture-oriented plain-English field guide (from capture-insights) |

PG table `intel_usaspending_prime_awards` columns align with `PRIME_TARGET_FIELDS` in capture-insights ingest + this dictionary.

## Shipley methodology

| File | Role |
|------|------|
| [shipley/Shipley Capture Guide.pdf](shipley/Shipley%20Capture%20Guide.pdf) | Phase 0–6 lifecycle reference |
| [shipley/shipley_extracted.json](shipley/shipley_extracted.json) | Structured extracts for prompts (if present) |

Configure in `.env`: `REFERENCE_DOCS_ROOT=docs/reference`