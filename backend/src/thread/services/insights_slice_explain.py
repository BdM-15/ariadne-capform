"""On-demand LLM narrative for an active Insights slice (Phase 2e-a)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from thread.config import Settings
from thread.intel.facet_query import InsightFacetQuery, describe_query
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
5. **Recommended next steps** — exactly 3 bullets, each a concrete action with **why now** \
(profile X agency because…, validate JV vs sub because parent-shadow…, prioritize Apr cluster because…)

Keep total length under ~500 words. Be direct and opinionated where the data supports it."""


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
            "Shipley gates: pursue | monitor | defer. Do not invent figures — only use this JSON."
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