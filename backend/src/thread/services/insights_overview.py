"""Phase 17e — Insights Overview lens (shared intel charts + ECharts payloads)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.intel import pg_queries as intel_queries
from thread.intel.charts import run_slice_overview
from thread.intel.echarts_options import attach_overview_echarts
from thread.intel.slice_cache import get_cached_overview, store_cached_overview
from thread.intel.facet_query import InsightFacetQuery, describe_query
from thread.services.insights_explore import _facet_from_params

_OPEN_SET_ASIDE_BUCKETS = frozenset({"(Not Applicable)", "NO SET ASIDE USED"})

# ponytail: chart ? tooltips — read + use strings for Overview ECharts panels
OVERVIEW_CHART_GUIDES: dict[str, dict[str, str]] = {
    "intensity": {
        "label": "Capture intensity",
        "read": "Each dot is a funding agency. Horizontal = action count; vertical = obligated $M. Lime dots are above the median on both axes.",
        "use": "Start agency-first: click a lime (hot) agency to open its profile and expiring list.",
    },
    "motion_fy_trend": {
        "label": "FY obligation pulse",
        "read": "Government fiscal years (Oct–Sep). Magenta bars = obligated $M; lime line = prime action count in that FY.",
        "use": "Pair with the FY momentum card — if dollars rise but the action line stays flat, awards are getting larger (fewer, bigger deals).",
    },
    "motion_channels": {
        "label": "Entry lane mix",
        "read": "100% bar of slice obligations by capture lane — open competed, set-aside, sole/limited, IDV/vehicle.",
        "use": "Read the percentages first. Direct-prime lane is open · competed only; set-aside bands require SB/8(a) or a teammate.",
    },
    "motion_q4_timing": {
        "label": "Q4 mix shift",
        "read": "100% stacked comparison of obligation mix Oct–Jun vs Q4 — shows whether year-end spend shifts into set-aside or sole-source lanes.",
        "use": "Watch the set-aside band widen in Q4 — that is the offload lane; plan teammate outreach before Jul, not a new open RFP push.",
    },
    "motion_expiring_channels": {
        "label": "Recompete channel split",
        "read": "Expiring pipeline (18 mo) broken into the same entry channels as historical TAM.",
        "use": "Compare to the channel stack — upcoming recompetes may be vehicle-gated or set-aside even when historical TAM looked open.",
    },
    "motion_parent_shadow": {
        "label": "Set-aside parent shadow",
        "read": "Set-aside obligations where the prime has a different parent company — entity-owned 8(a) / LB portfolio heuristic.",
        "use": "Parent-backed set-aside primes may still need a sub — but JV structure differs from teaming with an independent 8(a).",
    },
    "motion_money_paths": {
        "label": "Top money paths",
        "read": "Largest agency → entry channel → prime recipient obligation paths in this slice.",
        "use": "Follow the dominant path — if it routes through set-aside, open a Competitor profile and plan a sub pitch, not a prime bid.",
    },
    "set_aside": {
        "label": "Set-aside mix",
        "read": "Share of obligated dollars by set-aside bucket (full-and-open vs small business, etc.).",
        "use": "High restricted share → validate teaming, JV, or set-aside eligibility before you chase the slice.",
    },
    "extent_competed": {
        "label": "Extent competed",
        "read": "How work was competed — full-and-open, sole source, limited competition, and similar buckets.",
        "use": "Low competed share means displacement is harder; adjust capture strategy and price-to-win expectations.",
    },
    "idv_split": {
        "label": "IDV vs standalone",
        "read": "Share of dollars on IDV/vehicle awards versus standalone definitive contracts.",
        "use": "IDV-heavy slices usually require vehicle position — don't assume every deal will be an open RFP.",
    },
    "pricing_buckets": {
        "label": "Contract pricing mix",
        "read": "Obligations grouped by pricing type — firm fixed, time & materials, cost-reimbursable, and similar.",
        "use": "High non-fixed share → contracting style and shaping matter; pair with expiring timeline and shape badges below.",
    },
    "top_recipients": {
        "label": "Top recipients",
        "read": "Largest prime contractors in the slice by obligated dollars.",
        "use": "Click a bar to open a Competitor profile — incumbents, agencies, and expiring awards for that prime.",
    },
    "expiring_timeline": {
        "label": "Expiring timeline",
        "read": "Monthly buckets of contracts ending in the next 18 months. Cyan bars = obligated $M; amber line = action count.",
        "use": "Spot recompete clusters before they hit — pair with shape badges on rows below for flexible-pricing shaping windows.",
    },
}


def overview_chart_guides() -> dict[str, dict[str, str]]:
    return {k: dict(v) for k, v in OVERVIEW_CHART_GUIDES.items()}


def chart_guide_tooltip(guide: dict[str, str]) -> str:
    parts = [guide.get("read", ""), guide.get("use", "")]
    return " ".join(p.strip() for p in parts if p and p.strip())


_SUB_ONLY_CHANNELS = frozenset({"set_aside_competed", "set_aside_non_competed"})
_DIRECT_PRIME_CHANNELS = frozenset({"open_competed"})


def _channel_millions(channels: list[dict[str, Any]], keys: frozenset[str]) -> float:
    return sum(float(c.get("millions") or 0) for c in channels if c.get("channel") in keys)


def overview_motion_brief(
    motion: dict[str, Any],
    *,
    recompete_m: float = 0.0,
) -> dict[str, Any]:
    """Entry-lane story — prime-eligible vs sub-only, teaming targets, year-end skew."""
    channels: list[dict[str, Any]] = list(motion.get("channels") or [])
    timing = motion.get("timing") or {}
    teaming: list[dict[str, Any]] = list(motion.get("teaming_targets") or [])
    parent = motion.get("parent_shadow") or {}
    expiring: list[dict[str, Any]] = list(motion.get("expiring_channels") or [])
    paths: list[dict[str, Any]] = list(motion.get("money_paths") or [])

    tam = sum(float(c.get("millions") or 0) for c in channels) or 0.0
    direct_m = _channel_millions(channels, _DIRECT_PRIME_CHANNELS)
    sub_m = _channel_millions(channels, _SUB_ONLY_CHANNELS)
    vehicle_m = _channel_millions(channels, frozenset({"vehicle_gated"}))
    hard_m = _channel_millions(channels, frozenset({"open_non_competed"}))

    direct_pct = round(100.0 * direct_m / tam, 1) if tam > 0 else 0.0
    sub_pct = round(100.0 * sub_m / tam, 1) if tam > 0 else 0.0
    vehicle_pct = round(100.0 * vehicle_m / tam, 1) if tam > 0 else 0.0
    hard_pct = round(100.0 * hard_m / tam, 1) if tam > 0 else 0.0

    exp_tam = sum(float(c.get("millions") or 0) for c in expiring) or 0.0
    exp_direct_pct = (
        round(100.0 * _channel_millions(expiring, _DIRECT_PRIME_CHANNELS) / exp_tam, 1)
        if exp_tam > 0
        else None
    )

    headline = (
        f"{direct_pct:.0f}% direct-prime · {sub_pct:.0f}% sub/teaming only"
        if tam > 0
        else "Run slice for entry-lane breakdown"
    )

    bullets: list[str] = []
    if sub_pct >= 25:
        bullets.append(
            f"{sub_pct:.0f}% (${sub_m:.1f}M) requires a set-aside prime — you cannot prime this spend "
            "without SB/8(a) status or a teammate, regardless of technical capability."
        )
    if vehicle_pct >= 20:
        bullets.append(
            f"{vehicle_pct:.0f}% (${vehicle_m:.1f}M) is IDV/vehicle-gated — need vehicle position, "
            "not standalone open RFP pursuit."
        )
    if hard_pct >= 15:
        bullets.append(
            f"{hard_pct:.0f}% is open but sole-source or limited — displacement is hard; "
            "consider flank via teaming or past-performance lane."
        )
    timing_insight = str(timing.get("insight") or "").strip()
    if timing_insight:
        bullets.append(timing_insight)
    parent_pct = float(parent.get("parent_backed_pct") or 0)
    if parent_pct >= 20:
        eight_a_pct = float(parent.get("eight_a_parent_pct") or 0)
        extra = f" ({eight_a_pct:.0f}% entity-owned 8(a) heuristic)" if eight_a_pct >= 8 else ""
        bullets.append(
            f"{parent_pct:.0f}% of set-aside $ flows to primes with a different parent{extra} — "
            "validate JV vs sub strategy before outreach."
        )
    if exp_direct_pct is not None and recompete_m > 0 and exp_direct_pct < direct_pct - 8:
        bullets.append(
            f"Recompete pipe tilts restricted — only {exp_direct_pct:.0f}% of expiring ${recompete_m:.1f}M "
            f"is open · competed vs {direct_pct:.0f}% historical TAM."
        )
    if paths:
        top = paths[0]
        bullets.append(
            f"Dominant path: {str(top.get('agency') or '')[:36]} → "
            f"{top.get('channel_label') or ''} → {str(top.get('recipient') or '')[:32]} "
            f"(${float(top.get('millions') or 0):.1f}M)."
        )

    actions: list[dict[str, Any]] = []
    if teaming:
        top_bucket = teaming[0]
        top_prime = (top_bucket.get("primes") or [{}])[0]
        prime_name = top_prime.get("recipient")
        if prime_name:
            actions.append(
                {
                    "label": f"Profile teaming prime {str(prime_name)[:36]}",
                    "kind": "drill",
                    "entity_kind": "competitor",
                    "entity_scope": "recipient",
                    "value": prime_name,
                }
            )
    if paths:
        path_recipient = paths[0].get("recipient")
        if path_recipient and not any(a.get("value") == path_recipient for a in actions):
            actions.append(
                {
                    "label": f"Profile path incumbent {str(path_recipient)[:36]}",
                    "kind": "drill",
                    "entity_kind": "competitor",
                    "entity_scope": "recipient",
                    "value": path_recipient,
                }
            )
    if sub_pct >= 25:
        actions.append({"label": "Review teaming targets below", "kind": "anchor", "href": "#insights-motion-teaming"})
    while len(actions) < 2:
        actions.append({"label": "Refine facets and re-run slice", "kind": "hint"})

    return {
        "headline": headline,
        "bullets": bullets[:5],
        "actions": actions[:3],
        "direct_prime_pct": direct_pct,
        "sub_only_pct": sub_pct,
        "vehicle_pct": vehicle_pct,
        "q4_insight": timing_insight,
        "teaming_targets": teaming,
    }


def overview_capture_verdict(
    overview: dict[str, Any],
    *,
    query: InsightFacetQuery | None = None,
    pipeline: dict[str, int | float] | None = None,
) -> dict[str, Any]:
    """Template-ready verdict cards + slice brief from existing overview payload."""
    kpis = overview.get("kpis") or {}
    tam = float(kpis.get("millions") or 0)
    intensity = overview.get("agency_intensity") or {}
    hot_agencies: list[str] = list(intensity.get("hot_agencies") or [])
    spend_bars: list[dict[str, Any]] = list(overview.get("spend_trend") or [])
    recipients: list[dict[str, Any]] = list(overview.get("top_recipients") or [])
    set_aside_rows: list[dict[str, Any]] = list(overview.get("set_aside") or [])

    momentum_pct: float | None = None
    momentum_year: int | None = None
    if len(spend_bars) >= 2:
        prev, last = spend_bars[-2], spend_bars[-1]
        momentum_year = int(last.get("year") or 0) or None
        prev_m = float(prev.get("millions") or 0)
        last_m = float(last.get("millions") or 0)
        if prev_m > 0:
            momentum_pct = round(100.0 * (last_m - prev_m) / prev_m, 1)

    pipe = pipeline or {}
    recompete_count = int(pipe.get("count") or 0)
    recompete_m = float(pipe.get("millions") or 0)

    top3_m = sum(float(r.get("millions") or 0) for r in recipients[:3])
    concentration_pct = round(100.0 * top3_m / tam, 1) if tam > 0 else None

    set_aside_total = sum(float(r.get("millions") or 0) for r in set_aside_rows)
    restricted_m = sum(
        float(r.get("millions") or 0)
        for r in set_aside_rows
        if str(r.get("bucket") or "") not in _OPEN_SET_ASIDE_BUCKETS
    )
    access_pct = round(100.0 * restricted_m / set_aside_total, 1) if set_aside_total > 0 else None

    cards: list[dict[str, Any]] = [
        {
            "id": "tam",
            "label": "TAM",
            "value": f"${tam:.1f}M",
            "hint": f"{int(kpis.get('award_count') or 0):,} prime actions",
            "tooltip": (
                "Total addressable market — sum of federal obligations on prime awards "
                "in your active facet slice (PG intel, not live SAM)."
            ),
        },
        {
            "id": "momentum",
            "label": "FY momentum",
            "value": (
                f"{momentum_pct:+.1f}%"
                if momentum_pct is not None
                else "—"
            ),
            "hint": (
                f"YoY into FY{momentum_year}"
                if momentum_year
                else "Need 2+ fiscal years"
            ),
            "tooltip": (
                "Year-over-year change in obligated dollars between the last two "
                "fiscal years with spend in this slice."
            ),
        },
        {
            "id": "recompete",
            "label": "Recompete pipe",
            "value": f"${recompete_m:.1f}M",
            "hint": f"{recompete_count:,} expiring · 18 mo",
            "tooltip": (
                "Contracts ending in the next 18 months that match your facets — "
                "obligation total and count across the full slice, not just the list below."
            ),
        },
        {
            "id": "hot_agencies",
            "label": "Hot agencies",
            "value": str(len(hot_agencies)),
            "hint": "Above median spend & volume",
            "tooltip": (
                "Funding agencies above the capture-intensity median on both spend "
                "and action volume — start agency-first qualification here."
            ),
        },
        {
            "id": "concentration",
            "label": "Concentration",
            "value": f"{concentration_pct:.0f}%" if concentration_pct is not None else "—",
            "hint": "Top 3 contractors share",
            "tooltip": (
                "Share of slice obligations held by the top three prime recipients — "
                "high concentration means fewer incumbents dominate the market."
            ),
        },
        {
            "id": "access",
            "label": "Set-aside mix",
            "value": f"{access_pct:.0f}%" if access_pct is not None else "—",
            "hint": "Obligations with set-aside",
            "tooltip": (
                "Percent of obligations tagged with a set-aside (not full-and-open). "
                "Signals how much of the market is restricted vs open competition."
            ),
        },
    ]

    slice_label = describe_query(query) if query else "Active slice"
    top_agency = hot_agencies[0] if hot_agencies else None
    top_recipient = (recipients[0].get("recipient") if recipients else None) or None

    bullets: list[str] = [slice_label]
    if top_agency:
        bullets.append(f"Lead agency motion: {top_agency} is above the capture-intensity line.")
    if momentum_pct is not None:
        direction = "up" if momentum_pct >= 0 else "down"
        bullets.append(f"Spend trending {direction} {abs(momentum_pct):.1f}% into the latest fiscal year.")
    if recompete_count:
        bullets.append(f"{recompete_count:,} contracts (${recompete_m:.1f}M) expire in the next 18 months.")

    actions: list[dict[str, Any]] = []
    if top_agency:
        actions.append(
            {
                "label": f"Profile {top_agency[:48]}",
                "kind": "drill",
                "entity_kind": "agency",
                "entity_scope": "agency",
                "value": top_agency,
            }
        )
    if recompete_count:
        actions.append({"label": "Review expiring pipeline", "kind": "anchor", "href": "#insights-slice-expiring"})
    if top_recipient:
        actions.append(
            {
                "label": f"Profile {str(top_recipient)[:40]}",
                "kind": "drill",
                "entity_kind": "competitor",
                "entity_scope": "recipient",
                "value": top_recipient,
            }
        )
    while len(actions) < 3:
        actions.append({"label": "Refine facets and re-run slice", "kind": "hint"})

    motion_data = overview.get("motion") or {}
    motion_brief = overview_motion_brief(motion_data, recompete_m=recompete_m)

    return {
        "cards": cards,
        "chart_guides": overview_chart_guides(),
        "motion": motion_brief,
        "brief": {
            "title": "Slice brief",
            "headline": f"${tam:.1f}M market · {int(kpis.get('agency_count') or 0)} agencies",
            "bullets": bullets[:4],
            "actions": actions[:3],
        },
    }


@dataclass(frozen=True)
class OverviewResult:
    query: InsightFacetQuery | None
    summary: str
    overview: dict[str, Any]
    intel_live: bool
    status: str
    error: str | None = None
    cache_hit: bool = False
    cache_age_seconds: float | None = None


def overview_charts_json(overview: dict[str, Any]) -> str:
    charts = overview.get("charts") or {}
    return json.dumps(charts, separators=(",", ":"))


async def build_overview(
    session: AsyncSession,
    settings: Settings,
    *,
    agency: str = "",
    sub_agency: str = "",
    recipient: str = "",
    naics_codes: str = "",
    psc_codes: str = "",
    awarding_office: str = "",
    funding_office: str = "",
    recipient_uei: str = "",
    pop_state: str = "",
    extent_competed: str = "",
    type_of_set_aside: str = "",
    run: bool = False,
) -> OverviewResult:
    stats = await intel_queries.get_intel_stats(session)
    intel_live = bool(stats.get("prime_awards_ready") and stats.get("prime_award_count", 0) > 0)
    query = _facet_from_params(
        agency=agency,
        sub_agency=sub_agency,
        recipient=recipient,
        naics_codes=naics_codes,
        psc_codes=psc_codes,
        awarding_office=awarding_office,
        funding_office=funding_office,
        recipient_uei=recipient_uei,
        pop_state=pop_state,
        extent_competed=extent_competed,
        type_of_set_aside=type_of_set_aside,
    )

    if not run:
        return OverviewResult(
            query=query,
            summary=describe_query(query) if query else "",
            overview={"idle": True},
            intel_live=intel_live,
            status="idle",
        )

    if query is None:
        return OverviewResult(
            query=None,
            summary="",
            overview={},
            intel_live=intel_live,
            status="no_query",
            error="Set at least one facet, then run slice.",
        )

    if not intel_live:
        return OverviewResult(
            query=query,
            summary=describe_query(query),
            overview={},
            intel_live=False,
            status="loading",
            error="PG intel not ready — resume migration.",
        )

    cache = get_cached_overview(settings, query)
    if cache and cache.overview:
        overview = attach_overview_echarts(dict(cache.overview))
        return OverviewResult(
            query=query,
            summary=describe_query(query),
            overview=overview,
            intel_live=True,
            status="ready",
            cache_hit=True,
            cache_age_seconds=cache.age_seconds,
        )

    raw = await run_slice_overview(session, query, use_cache=False)
    if raw.get("error"):
        return OverviewResult(
            query=query,
            summary=describe_query(query),
            overview=raw,
            intel_live=True,
            status=str(raw.get("status") or "error"),
            error=str(raw["error"]),
        )

    store_cached_overview(settings, query, raw)
    overview = attach_overview_echarts(raw)
    return OverviewResult(
        query=query,
        summary=describe_query(query),
        overview=overview,
        intel_live=True,
        status="ready",
    )