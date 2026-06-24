"""On-demand LLM narrative for an active Insights slice (Phase 2e-a)."""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from typing import Any

from thread.config import Settings
from thread.intel.facet_query import InsightFacetQuery, describe_query
from thread.intel.sql_expressions import EXPIRING_MONTHS_AHEAD
from thread.llm.router import (
    CompletionResult,
    LlmRouterError,
    LlmTaskKind,
    LlmUnavailableError,
    complete,
    probe_ollama,
)


class SliceExplainError(Exception):
    """User-facing explain failure."""


SLICE_EXPLAIN_SYSTEM_PROMPT = """You are a senior federal capture strategist with 20+ years in GovCon BD — \
Shipley MS1 qualification, FAR/DFARS competition lanes, IDV/vehicle mechanics, set-aside teaming, \
and recompete displacement. The operator is using Thread Data Insights: a PG-grounded slice of \
USAspending prime awards filtered by facets (NAICS, agency, etc.).

Your job is **analyst-grade synthesis**, not a metric readout. The JSON payload is authoritative for \
numbers — never invent figures, agencies, or contract names. When data is thin, say what you cannot \
conclude and why.

**Do NOT:**
- Open with a list of KPI values the operator already sees on cards
- Repeat every Shipley gate headline verbatim
- Give generic "profile agencies / review expiring" filler without prioritization logic

**Do:**
- Interpret **what the slice means** for a small business or mid-tier prime pursuing work here
- Compare signals (e.g., TAM entry lanes vs recompete pipe mix; concentration vs hot agencies)
- Call out **actionable tensions** — where historical TAM says pursue but expiring pipe says team; \
where vehicle-gated $ blocks direct prime; where momentum down shifts timing
- Name **specific entities** from samples (agencies, incumbents) when present in JSON
- Use GovCon vocabulary: full-and-open, set-aside flow, IDV gating, incumbent displacement, \
shaping window, recompete cluster

**Structure (markdown, no YAML frontmatter):**

1. **Slice read** — 2–3 sentences: what market this is, scale, and the single strongest signal
2. **Pursuit lanes** — prime vs teaming vs defer; cite entry-lane / set-aside / vehicle evidence
3. **Market dynamics** — momentum, concentration, agency heat; who dominates and what that implies
4. **Recompete & shaping clock** — urgency, peak cluster, shape_now/monitor samples if any
5. **Pipeline gap & pivot** — when `pipeline_health.forward_looking_capture_advised` is true, \
or FY trend / expiring timeline shows lulls (e.g. thin FY27 recompete pipe), say plainly that \
**historical recompetes alone cannot fill the pipeline**. Recommend a pivot: adjacent agencies \
from hot_agencies / concentration, widen NAICS facets, and **forward-looking SAM.gov pursuit** \
(CSO, open solicitations, OTA, BAA, Sources Sought) — cite `sam_notice_types_to_consider`. \
Propose 2–3 concrete SAM monitor facets (NAICS + agency keyword + notice type) matched to the slice.
6. **Recommended next steps** — exactly 3 bullets, each a concrete action with **why now** \
(profile X agency because…, stand up SAM monitor for CSO+NAICS because recompete lull…, \
prioritize Apr cluster because…)

When pipeline is recompete-heavy, steps 5–6 stay recompete-first. When thin/lumpy, step 5 leads.

Keep total length under ~550 words. Be direct and opinionated where the data supports it. \
Flag export-worthy decisions (pivot strategy, monitor recommendations) the operator may want in \
tasks or briefing notes — do not invent task IDs."""


@dataclass(frozen=True)
class SliceExplainAvailability:
    cloud_configured: bool
    cloud_model: str
    local_enabled: bool
    local_reachable: bool
    local_model: str


@dataclass(frozen=True)
class SliceExplainResult:
    text: str
    provider: str
    model: str
    error: str | None = None


async def slice_explain_availability(settings: Settings) -> SliceExplainAvailability:
    local_enabled = bool(settings.local_admin_model_enabled)
    local_reachable = await probe_ollama(settings) if local_enabled else False
    return SliceExplainAvailability(
        cloud_configured=bool(settings.xai_api_key),
        cloud_model=settings.reasoning_llm_model,
        local_enabled=local_enabled,
        local_reachable=local_reachable,
        local_model=settings.local_daily_model,
    )


def _gov_fy_from_month(month: str) -> int | None:
    try:
        year_s, month_s = month.split("-", 1)
        year = int(year_s)
        mon = int(month_s)
    except (ValueError, AttributeError):
        return None
    return year if mon >= 10 else year - 1


def _analyze_pipeline_health(
    *,
    overview: dict[str, Any],
    pipeline_stats: dict[str, int | float] | None,
    expiring_row_count: int,
) -> dict[str, Any]:
    """Deterministic signals for recompete-thin / FY-lull → SAM pivot reasoning."""
    fy_trend = list(overview.get("spend_trend") or [])
    expiring_tl = overview.get("expiring_timeline") or {}
    buckets = list(expiring_tl.get("buckets") or [])

    stats = pipeline_stats or {}
    recompete_count = int(stats.get("count") or 0)
    recompete_m = float(stats.get("millions") or 0)

    fy_signals: list[str] = []
    if len(fy_trend) >= 2:
        last = fy_trend[-1]
        prior = fy_trend[-2]
        last_m = float(last.get("millions") or 0)
        prior_m = float(prior.get("millions") or 0)
        last_actions = int(last.get("actions") or 0)
        prior_actions = int(prior.get("actions") or 0)
        last_year = last.get("year")
        if prior_m > 0 and last_m < prior_m * 0.85:
            fy_signals.append(f"FY{last_year} obligated $ down vs prior FY in slice")
        if prior_actions > 0 and last_actions < prior_actions * 0.85:
            fy_signals.append(f"FY{last_year} prime action count declining vs prior FY")

    bucket_contracts = [int(b.get("contracts") or 0) for b in buckets]
    median_contracts = statistics.median(bucket_contracts) if bucket_contracts else 0.0
    lull_threshold = max(1.0, median_contracts * 0.25) if median_contracts else 1.0
    lull_months = [
        str(b.get("month") or "")
        for b in buckets
        if int(b.get("contracts") or 0) <= lull_threshold
    ]

    expiring_by_fy: dict[str, dict[str, float | int]] = {}
    for bucket in buckets:
        fy = _gov_fy_from_month(str(bucket.get("month") or ""))
        if fy is None:
            continue
        key = str(fy)
        slot = expiring_by_fy.setdefault(key, {"contracts": 0, "millions": 0.0})
        slot["contracts"] = int(slot["contracts"]) + int(bucket.get("contracts") or 0)
        slot["millions"] = float(slot["millions"]) + float(bucket.get("millions") or 0)

    thin_recompete = recompete_count < 8 and recompete_m < 2.0 and expiring_row_count < 12
    lumpy_timeline = len(lull_months) >= max(3, len(buckets) // 3) if buckets else False
    forward_pivot = thin_recompete or lumpy_timeline or bool(fy_signals)

    return {
        "expiring_window_months": EXPIRING_MONTHS_AHEAD,
        "recompete_contracts": recompete_count,
        "recompete_millions": recompete_m,
        "expiring_list_rows": expiring_row_count,
        "fy_trend_signals": fy_signals,
        "expiring_timeline_lull_months": lull_months[:10],
        "expiring_by_gov_fy": expiring_by_fy,
        "recompete_insufficient_for_pipeline": thin_recompete,
        "forward_looking_capture_advised": forward_pivot,
        "sam_pivot_doctrine": (
            "USAspending shows historical prime awards and expiring base contracts only. "
            "When the recompete pipe is thin or lumpy (e.g. FY27 gap), net-new pipeline must come "
            "from adjacent buyers, widened facets, and live SAM.gov notices — not incumbent displacement alone."
        ),
        "sam_notice_types_to_consider": [
            "Commercial Solutions Opening (CSO)",
            "Combined Synopsis/Solicitation (open)",
            "Other Transaction Authority (OTA)",
            "Broad Agency Announcement (BAA)",
            "Sources Sought / RFI",
        ],
        "future_actions": [
            "Export explain narrative to task / briefing (Phase 17j-b — not wired yet)",
            "Auto-provision SAM monitors from explain recommendations (Phase 17j-a)",
        ],
    }


def _pct_of_total(rows: list[dict[str, Any]], total_m: float, key: str = "millions") -> list[dict[str, Any]]:
    if total_m <= 0:
        return []
    out: list[dict[str, Any]] = []
    for row in rows[:6]:
        m = float(row.get(key) or 0)
        out.append({
            "label": row.get("bucket") or row.get("extent") or row.get("recipient") or row.get("channel"),
            "millions": m,
            "pct": round(100.0 * m / total_m, 1),
            "actions": row.get("actions"),
        })
    return out


def build_slice_explain_bundle(
    *,
    query: InsightFacetQuery | None,
    overview_verdict: dict[str, Any],
    overview: dict[str, Any],
    expiring_rows: tuple[dict[str, Any], ...] | list[dict[str, Any]] = (),
    pipeline_stats: dict[str, int | float] | None = None,
) -> dict[str, Any]:
    """Compact PG-grounded payload for LLM — numbers must match UI."""
    rows = list(expiring_rows)
    motion = overview_verdict.get("motion") or {}
    shipley = overview_verdict.get("shipley") or []
    cards = overview_verdict.get("cards") or []
    expiring_tl = overview.get("expiring_timeline") or {}
    kpis = overview.get("kpis") or {}
    tam_m = float(kpis.get("millions") or 0)

    hot_sample = sorted(
        [r for r in rows if int(r.get("months_to_end") or 99) <= 6],
        key=lambda r: int(r.get("months_to_end") or 99),
    )[:5]
    shape_sample = [r for r in rows if r.get("shape_gate") in ("shape_now", "monitor")][:5]

    intensity = overview.get("agency_intensity") or {}
    channels = (overview.get("motion") or {}).get("channels") or []
    pipeline_health = _analyze_pipeline_health(
        overview=overview,
        pipeline_stats=pipeline_stats,
        expiring_row_count=len(rows),
    )

    return {
        "facet_query": describe_query(query) if query else "No query",
        "metric_cards": [
            {"id": c.get("id"), "label": c.get("label"), "value": c.get("value"), "hint": c.get("hint")}
            for c in cards
        ],
        "shipley_gates": [
            {
                "id": s.get("id"),
                "gate": s.get("gate"),
                "gate_label": s.get("gate_label"),
                "headline": s.get("headline"),
                "bullets": s.get("bullets") or [],
                "action": s.get("action"),
            }
            for s in shipley
        ],
        "motion": {
            "headline": motion.get("headline"),
            "bullets": (motion.get("bullets") or [])[:5],
            "direct_prime_pct": motion.get("direct_prime_pct"),
            "sub_only_pct": motion.get("sub_only_pct"),
            "vehicle_pct": motion.get("vehicle_pct"),
            "entry_lanes": [
                {
                    "channel": ch.get("channel"),
                    "label": ch.get("label"),
                    "pct": ch.get("pct"),
                    "millions": ch.get("millions"),
                    "actions": ch.get("actions"),
                }
                for ch in channels[:6]
            ],
        },
        "market_access": {
            "set_aside_mix": _pct_of_total(list(overview.get("set_aside") or []), tam_m),
            "extent_competed": _pct_of_total(list(overview.get("extent_competed") or []), tam_m),
            "idv_split": _pct_of_total(
                [{"bucket": r.get("channel"), **r} for r in (overview.get("idv_split") or [])],
                tam_m,
            ),
            "pricing_top": _pct_of_total(list(overview.get("pricing_buckets") or []), tam_m),
        },
        "concentration": {
            "top_recipients": [
                {
                    "recipient": r.get("recipient"),
                    "millions": r.get("millions"),
                    "actions": r.get("actions"),
                }
                for r in (overview.get("top_recipients") or [])[:5]
            ],
            "hot_agencies": list(intensity.get("hot_agencies") or [])[:8],
            "agency_median": {
                "actions": intensity.get("median_actions"),
                "millions": intensity.get("median_millions"),
            },
        },
        "fy_trend": [
            {"year": b.get("year"), "millions": b.get("millions"), "actions": b.get("actions")}
            for b in (overview.get("spend_trend") or [])[-5:]
        ],
        "expiring_timeline_insight": expiring_tl.get("insight"),
        "expiring_timeline_buckets": [
            {
                "month": b.get("month"),
                "contracts": b.get("contracts"),
                "millions": b.get("millions"),
            }
            for b in (expiring_tl.get("buckets") or [])[:24]
        ],
        "pipeline_health": pipeline_health,
        "expiring_sample_count": len(rows),
        "hot_expiring_sample": [
            {
                "recipient": r.get("recipient"),
                "months_to_end": r.get("months_to_end"),
                "obligation": r.get("obligation"),
                "shape_gate": r.get("shape_gate"),
                "agency": r.get("agency"),
            }
            for r in hot_sample
        ],
        "shape_expiring_sample": [
            {
                "recipient": r.get("recipient"),
                "shape_gate": r.get("shape_gate"),
                "shape_reason": r.get("shape_reason"),
                "agency": r.get("agency"),
            }
            for r in shape_sample
        ],
        "data_note": (
            "USAspending prime awards (PG intel). Dollar fields in millions unless obligation is raw USD "
            "on expiring samples. Metric card values are pre-formatted for display. "
            "Shipley gates: pursue | monitor | defer. pipeline_health.forward_looking_capture_advised "
            "signals recompete-thin slices — recommend SAM.gov forward pursuit when true. "
            "Do not invent figures or live SAM results — only use this JSON."
        ),
    }


def _build_explain_messages(bundle: dict[str, Any]) -> list[dict[str, str]]:
    context_json = json.dumps(bundle, ensure_ascii=False, indent=2)
    return [
        {"role": "system", "content": SLICE_EXPLAIN_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Analyze this capture slice for an operator deciding whether and how to pursue. "
                "Synthesize — do not summarize cards.\n\n"
                f"{context_json[:24000]}"
            ),
        },
    ]


async def explain_slice(
    settings: Settings,
    *,
    bundle: dict[str, Any],
    provider_choice: str = "cloud",
) -> SliceExplainResult:
    choice = (provider_choice or "cloud").strip().lower()
    try:
        result: CompletionResult = await complete(
            settings,
            task_kind=LlmTaskKind.REASONING,
            messages=_build_explain_messages(bundle),
            max_tokens=min(settings.llm_max_output_tokens, 2048),
            provider_choice=choice,
        )
    except LlmUnavailableError as exc:
        raise SliceExplainError(str(exc)) from exc
    except LlmRouterError as exc:
        raise SliceExplainError(str(exc)) from exc

    text = (result.text or "").strip()
    if not text:
        raise SliceExplainError("Model returned an empty response.")
    return SliceExplainResult(
        text=text,
        provider=result.provider.value,
        model=result.model,
    )