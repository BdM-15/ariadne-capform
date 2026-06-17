---
name: datarepublican_intel
description: Query PostgreSQL intel tables for award relationships, funding chains, and incumbent links.
metadata:
  capability: analyze
  personas_primary: capture_manager
---

# datarepublican_intel

Follow-the-money analysis over `intel_usaspending_prime_awards` and `intel_relationships`.
Cites `award_key` and agency/recipient provenance. Results are review-gated candidates.