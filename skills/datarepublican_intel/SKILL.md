---
name: datarepublican_intel
description: Follow-the-money and connect-the-dots analysis over PostgreSQL intel — inspired by DataRepublican methods on federal award data.
metadata:
  capability: analyze
  personas_primary: capture_manager
---

# datarepublican_intel

## Inspiration

Methods from [DataRepublican](https://datarepublican.com) and [github.com/DataRepublican/datarepublican](https://github.com/DataRepublican/datarepublican): trace where money flows, map entities, and surface relationship structure.

Thread applies that doctrine to **federal capture** (USAspending + subawards + SAM MCP), not NGO/990 charity analytics. Data lives in migrated PG tables from capture-insights — not a live DataRepublican API.

## Modes (facet-aware when `facet` in payload)

| Mode | DR analogue | Output |
|------|-------------|--------|
| `spend_trend` | Funding flow over time | Fiscal-year obligation bars |
| `money_flow` | Charity graph / expose | Recipient → agency paths |
| `teaming` | People/entity relations | Prime → sub edges (FFATA subawards) |
| `recipient_landscape` | Federal grant search | Top recipients in facet slice |
| `snapshot` / `expiring` / `market` | — | Legacy NAICS snapshot helpers |

## Provenance & trust

- Cites `award_key`, agency, recipient on prime rows
- Results are **candidate** until human review (`/review`)
- Document parsing for solicitations: **MinerU 3.3** (Theseus) — not DataRepublican pdfparser

## Invoke

From **Data Insights → Connect the dots**, or API/skill runner with `{ "mode": "money_flow", "facet": { "agency": "Army", "naics_codes": "541512" } }`.