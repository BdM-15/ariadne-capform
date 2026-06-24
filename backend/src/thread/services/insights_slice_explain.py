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

    hot_sample = sorted(
        [r for r in rows if int(r.get("months_to_end") or 99) <= 6],
        key=lambda r: int(r.get("months_to_end") or 99),
    )[:5]
    shape_sample = [r for r in rows if r.get("shape_gate") in ("shape_now", "monitor")][:5]

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
                "headline": s.get("headline"),
                "bullets": s.get("bullets") or [],
            }
            for s in shipley
        ],
        "motion": {
            "headline": motion.get("headline"),
            "bullets": (motion.get("bullets") or [])[:4],
        },
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
            }
            for r in shape_sample
        ],
        "data_note": (
            "USAspending prime awards (PG intel). Dollar amounts in metric cards are $M unless noted. "
            "Do not invent figures — only use values in this JSON."
        ),
    }


def _build_explain_messages(bundle: dict[str, Any]) -> list[dict[str, str]]:
    context_json = json.dumps(bundle, ensure_ascii=False, indent=2)
    return [
        {
            "role": "system",
            "content": (
                "You are a federal capture analyst using Shipley MS1 qualification framing. "
                "The operator ran a facet-defined market slice in Thread Data Insights. "
                "Write a concise slice narrative (3–5 short paragraphs, markdown OK): "
                "what this slice is, whether to pursue/monitor/defer on prime vs teaming lanes, "
                "recompete urgency, and shaping windows. "
                "End with **Recommended next steps** — 3 bullets with concrete actions "
                "(profile agency, teaming outreach, expiring review). "
                "Use ONLY numbers from the JSON payload. If a signal is weak, say so. "
                "No YAML frontmatter."
            ),
        },
        {
            "role": "user",
            "content": f"Explain this capture slice:\n\n{context_json[:16000]}",
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