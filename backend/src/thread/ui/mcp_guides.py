"""Plain-language MCP guides for the Tools → MCP Servers page (RFP Intel briefing pattern)."""

from __future__ import annotations

from typing import Any

DEFAULT_MCP_GUIDE: dict[str, Any] = {
    "purpose": "Deterministic federal data via Model Context Protocol — skills opt in through SKILL.md metadata.",
    "when": "Use when a packet field or skill needs authoritative agency, award, or regulatory facts (not LLM guesswork).",
    "output": "Structured tool results with citations suitable for candidate → review → trusted promotion.",
    "context_impact": "Optional env keys unlock gated APIs; without keys, no-key servers still work for baseline intel.",
    "tips": [
        "Skills declare `metadata.mcps:` in frontmatter to allowlisted servers only.",
        "Outputs stay candidate until you approve in Review Queue.",
        "Prefer PG intel layer for bulk USAspending; MCP for live or narrow queries.",
    ],
}

MCP_SERVER_GUIDES: dict[str, dict[str, Any]] = {
    "usaspending": {
        "purpose": "Live USAspending.gov queries — awards, recipients, agencies, NAICS slices.",
        "when": "Drill-down on a specific award, recipient, or agency not already in the PG intel layer.",
        "output": "Award keys, obligation totals, period of performance — attach as evidence on packet fields.",
        "context_impact": "No API key required. Complements migrated DuckDB intel in PostgreSQL.",
        "tips": [
            "Use Data Insights / Pulse for portfolio-scale radar; MCP for pinpoint lookups.",
            "Pair with Clew (clew_intel skill) for money-path and relationship traces.",
        ],
    },
    "sam_gov": {
        "purpose": "SAM.gov entity and notice data for active solicitations and registrants.",
        "when": "Validate teaming partner UEIs, pull notice metadata, or live SAM explore on Data Insights.",
        "output": "Notice IDs, set-aside flags, response deadlines — candidate inputs for opportunity records.",
        "context_impact": "Requires SAM_GOV_API_KEY in .env (~1000 requests/day; rotate key every 90 days at sam.gov).",
        "tips": [
            "Data Insights SAM explore caches results 60 minutes — avoid repeated Run clicks.",
            "Store notice provenance on the opportunity record, not in free text only.",
            "Pair with Knowledge digest capabilities for bid/no-bid fit before Track.",
        ],
    },
    "ecfr": {
        "purpose": "Electronic Code of Federal Regulations — citeable regulatory text.",
        "when": "Compliance matrix stubs, staffing constraints, or SCA/Wage Determination cross-checks.",
        "output": "Section citations and excerpt text for packet / Studio artifacts.",
        "context_impact": "No key required.",
        "tips": ["Use for activation-band produce — not evergreen portfolio radar."],
    },
    "federal_register": {
        "purpose": "Federal Register documents and metadata.",
        "when": "Policy shifts, class deviations, or agency rule changes affecting capture strategy.",
        "output": "Document IDs, publication dates, agency — candidate research attachments.",
        "context_impact": "No key required.",
        "tips": [],
    },
    "regulations_gov": {
        "purpose": "Regulations.gov dockets and comments (when key configured).",
        "when": "Agency policy comments or presolicitation signals tied to a customer.",
        "output": "Docket metadata for research runs.",
        "context_impact": "May require API_DATA_GOV_KEY depending on upstream MCP packaging.",
        "tips": [],
    },
    "gsa_calc": {
        "purpose": "GSA CALC+ labor rate benchmarks.",
        "when": "Pricing sanity checks and PTW labor category alignment.",
        "output": "Rate bands by category and locality — candidate pricing evidence.",
        "context_impact": "No key required for baseline CALC+ MCP.",
        "tips": ["Studio / proposal readiness template will surface pricing gaps (Phase 21)."],
    },
    "gsa_perdiem": {
        "purpose": "GSA per-diem lodging and M&IE rates.",
        "when": "Travel-heavy pursuits, OCONUS staffing, or cost realism reviews.",
        "output": "Locality rates by fiscal year.",
        "context_impact": "No key required.",
        "tips": [],
    },
    "bls_oews": {
        "purpose": "BLS Occupational Employment and Wage Statistics.",
        "when": "Labor category mapping and wage competitiveness for capture pricing.",
        "output": "SOC/area wage percentiles — candidate evidence for PTW.",
        "context_impact": "BLS_API_KEY may be required depending on MCP build.",
        "tips": [],
    },
}


def guide_for_server(server_id: str) -> dict[str, Any]:
    base = dict(DEFAULT_MCP_GUIDE)
    specific = MCP_SERVER_GUIDES.get(server_id, {})
    base.update(specific)
    return base