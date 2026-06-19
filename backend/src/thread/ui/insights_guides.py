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
            "Watch promotes explicit potential to Pulse. Clew (separate card / drawer) traces money paths."
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
            "Teaming uses FFATA subaward bulk — not prime-only. PDF parse is MinerU 3.3 (enable MINERU_ENABLED).",
        ],
    },
    "clew": {
        "title": "Clew — trace the money path",
        "accent": "magenta",
        "purpose": (
            "Thread's connect-the-dots research utility — trace how federal money moves across "
            "recipients, agencies, primes, subs, and time. Standalone page at "
            "/clew (Tools sidebar) — not embedded in Data Insights explore."
        ),
        "when": (
            "Market scans, recompete qualification, competitive landscape, teaming structure, "
            "or MS1 evidence — before Watch/Track or when deepening a watched opportunity."
        ),
        "output": (
            "Candidate charts and edge lists — spend trend, recipient→agency flows, prime→sub "
            "teaming, recipient concentration. Queue for review; trusted findings compound into "
            "the knowledge vault (agencies, competitors, market notes)."
        ),
        "context_impact": (
            "Dual data layer: (1) PostgreSQL bulk — intel_usaspending_prime_awards + subawards for "
            "portfolio-scale trends, teaming, concentration; (2) live MCP complement — USAspending MCP "
            "for pinpoint award/recipient lookups, SAM.gov MCP for notices, entities, live subaward "
            "discovery when bulk is stale or missing. Clew is a utility over both — separate from "
            "USAspending explore UI. MinerU 3.3 for solicitation PDF (MINERU_ENABLED + FastAPI)."
        ),
        "how_to_use": [
            "Open Clew from Tools → Clew, or follow a deep link from Data Insights explore or Pulse watchlist (recipient/agency/NAICS pre-filled).",
            "Set at least one facet — agency, sub-agency, recipient, NAICS, or PSC. Matching uses substring search (ILIKE), not exact labels; try a short fragment like Army or part of an incumbent name.",
            "Pick a mode: Money flow (recipient→agency), Spend trend (fiscal years), Teaming (prime→sub), or Recipient landscape (concentration).",
            "Click Run analysis. The ECharts chart is the PG bulk slice; expand Data table below for row-level detail.",
            "Optional: check Live MCP supplement before Run for USAspending pinpoint awards and (in Teaming + recipient) SAM FFATA subawards — slower, shown in a separate panel under the chart.",
            "Compare PG bulk (historical portfolio) to live MCP rows when both are present — bulk for trends, MCP for freshness.",
            "Queue for review when the slice is worth promoting; outputs stay candidate until you approve on /review.",
            "Teaming mode requires FFATA subaward migration (do not use --skip-subawards). SAM live subawards need SAM_GOV_API_KEY on Tools → MCP Servers.",
        ],
        "tips": [
            "Not DR-style graph browse yet — analytical top-N paths in a facet slice; click-to-expand nodes is 17b-interact (future).",
            "Facet autocomplete and semantic search (Army CIO → PG label) land in 17d / 17c — not required to type perfect agency strings today.",
            "Trusted Clew findings will compound into vault entity pages after review (17b-vault — ingest design TBD).",
            "Pair with USAspending explore for expiring awards; Clew for money-path and teaming structure on the same facets.",
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


def guide_for_clew() -> dict[str, Any]:
    return dict(INSIGHTS_EXPLORE_GUIDES.get("clew", {}))


def guide_for_connect_dots() -> dict[str, Any]:
    """Deprecated alias — use guide_for_clew."""
    return guide_for_clew()