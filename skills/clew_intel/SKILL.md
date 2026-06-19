---
name: clew_intel
description: Clew — trace money paths across recipients, agencies, primes, subs, and time over PostgreSQL intel.
metadata:
  capability: analyze
  personas_primary: capture_manager
  display_name: Clew
---

# Clew (`clew_intel`)

Research utility — not a screen. Traces how federal money moves across award data.

**Data layers:** PostgreSQL bulk (prime + FFATA subawards) for portfolio analytics; **USAspending MCP** and **SAM.gov MCP** for live complement (pinpoint awards, notices, entities, fresh subaward discovery). Findings are **candidate** until review; trusted promotion → vault via `vault_maintainer` + `obsidian-markdown` (17b-vault).

## Modes (facet-aware when `facet` in payload)

| Mode | Output |
|------|--------|
| `spend_trend` | Fiscal-year obligation bars |
| `money_flow` | Recipient → agency paths |
| `teaming` | Prime → sub edges (FFATA subawards) |
| `recipient_landscape` | Top recipients in facet slice |
| `snapshot` / `expiring` / `market` | Legacy NAICS snapshot helpers |

## Provenance & trust

- Cites `award_key`, agency, recipient on prime rows
- Results are **candidate** until human review (`/review`)
- Document parsing for solicitations: **MinerU 3.3** (Theseus)

## Invoke

From **Data Insights → Clew**, Pulse watchlist (future drawer), or API/skill runner:

`{ "mode": "money_flow", "facet": { "agency": "Army", "naics_codes": "541512" } }`