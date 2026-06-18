"""Plain-language guides for Data Insights live explore cards."""

from __future__ import annotations

from typing import Any

INSIGHTS_EXPLORE_GUIDES: dict[str, dict[str, Any]] = {
    "usaspending_explore": {
        "title": "USAspending live explore",
        "accent": "magenta",
        "purpose": (
            "Portfolio-scale historical federal spend — expiring awards, incumbent context, "
            "and facet trends from the migrated PostgreSQL intel layer (not live SAM)."
        ),
        "when": (
            "Morning market scans, recompete identification, agency/component spend patterns, "
            "or competitor incumbent positioning before you invest capture."
        ),
        "output": (
            "Expiring contract rows with award_key, obligation, NAICS, and agency — "
            "Watch promotes explicit potential to Pulse; charts and drill-down land in this zone (Phase 17b)."
        ),
        "context_impact": (
            "Peer facets only — agency, sub-agency, recipient, NAICS, PSC in any combo. "
            "No platform default filter. Results update live as you type; PG migration must be ready."
        ),
        "tips": [
            "Watch ≠ Track: Watch adds to Pulse potential; Track commits an opportunity workspace.",
            "Saved bookmarks reopen this explore pane — they do not remote-control Pulse.",
            "Research on Pulse feeds the platform knowledge vault (agencies, competitors) — one ingress among many.",
            "Pinpoint award lookups: USAspending MCP on Tools → MCP Servers.",
        ],
    },
    "sam_explore": {
        "title": "SAM.gov live explore",
        "accent": "cyan",
        "purpose": (
            "Live solicitations and notices via SAM.gov MCP — supplements historical USAspending, "
            "not a replacement for PG intel trends."
        ),
        "when": (
            "New opportunity discovery, presolicitation monitoring, set-aside scans, "
            "or validating notice metadata before Track."
        ),
        "output": (
            "Notice rows with ID, title, agency, deadlines — Watch → Pulse watchlist with full provenance on Track."
        ),
        "context_impact": (
            "Requires SAM_GOV_API_KEY (~1000 req/day; rotate every 90 days). "
            "Explicit Run only — 60m cache; avoid repeated fetches."
        ),
        "tips": [
            "Click Run SAM explore to fetch — not on every keystroke (quota-aware).",
            "Entity/UEI detail: SAM MCP from workspace Research or skill chains.",
            "Outputs stay candidate until review gate promotes to trusted packet/vault fields.",
            "Pair with domain_intel digest on Pulse for bid-fit before Track.",
        ],
    },
}


def guide_for_explore(guide_id: str) -> dict[str, Any]:
    return dict(INSIGHTS_EXPLORE_GUIDES.get(guide_id, {}))