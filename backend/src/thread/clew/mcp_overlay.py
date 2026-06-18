"""Phase 17b — optional live MCP supplement for Clew PG slice."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from thread.config import Settings
from thread.intel.facet_query import InsightFacetQuery
from thread.mcp.service import MCPService

_OVERLAY_LIMIT = 5


@dataclass(frozen=True)
class McpOverlayLayer:
    server: str
    tool: str
    label: str
    status: str
    rows: tuple[dict[str, str], ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class McpOverlayResult:
    enabled: bool
    status: str
    layers: tuple[McpOverlayLayer, ...] = ()
    note: str | None = None


def _parse_json_payload(raw: str | dict[str, Any]) -> Any:
    if isinstance(raw, dict):
        return raw
    text = str(raw).strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}|\[[\s\S]*\]", text)
        if match:
            return json.loads(match.group(0))
    return {}


def _first_str(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        val = row.get(key)
        if val is None or val == "":
            continue
        if isinstance(val, dict):
            nested = val.get("name") or val.get("code")
            if nested:
                return str(nested).strip()
        return str(val).strip()
    return None


def _money_label(row: dict[str, Any]) -> str | None:
    for key in (
        "Award Amount",
        "award_amount",
        "total_obligation",
        "obligated_amount",
        "subaward_amount",
        "amount",
        "action_obligation",
    ):
        val = row.get(key)
        if val is None or val == "":
            continue
        try:
            num = float(str(val).replace(",", "").replace("$", ""))
            if num >= 1_000_000:
                return f"${num / 1_000_000:.2f}M"
            if num >= 1_000:
                return f"${num / 1_000:.1f}K"
            return f"${num:,.0f}"
        except ValueError:
            return str(val)
    return None


def _extract_rows(payload: Any, *, title_keys: tuple[str, ...], subtitle_keys: tuple[str, ...]) -> list[dict[str, str]]:
    items: list[dict[str, Any]] = []
    if isinstance(payload, list):
        items = [r for r in payload if isinstance(r, dict)]
    elif isinstance(payload, dict):
        for key in ("results", "awards", "subawards", "data", "opportunitiesData", "records"):
            block = payload.get(key)
            if isinstance(block, list):
                items = [r for r in block if isinstance(r, dict)]
                break
            if isinstance(block, dict):
                nested = block.get("results") or block.get("data")
                if isinstance(nested, list):
                    items = [r for r in nested if isinstance(r, dict)]
                    break

    rows: list[dict[str, str]] = []
    for row in items[:_OVERLAY_LIMIT]:
        title = _first_str(row, *title_keys)
        if not title:
            continue
        subtitle = _first_str(row, *subtitle_keys) or ""
        amount = _money_label(row) or ""
        meta_parts = [
            _first_str(row, "Award ID", "award_id", "piid", "PIID", "noticeId", "notice_id"),
            _first_str(row, "awarding_agency_name", "Awarding Agency", "agency", "department"),
        ]
        meta = " · ".join(p for p in meta_parts if p) or ""
        rows.append({"title": title, "subtitle": subtitle, "amount": amount, "meta": meta})
    return rows


def _mcp_server_ready(settings: Settings, server_id: str) -> bool:
    mcp = MCPService(settings)
    row = next((s for s in mcp.list_servers() if s["id"] == server_id), None)
    return bool(row and row["configured"])


def _build_usaspending_args(query: InsightFacetQuery, mode: str) -> tuple[str, dict[str, Any], str]:
    if mode == "teaming" and query.recipient:
        return (
            "spending_by_subaward_grouped",
            {
                "keywords": query.recipient,
                "award_type": "contracts",
                "limit": _OVERLAY_LIMIT,
            },
            f"Live subawards mentioning “{query.recipient}”",
        )
    args: dict[str, Any] = {"award_type": "contracts", "limit": _OVERLAY_LIMIT}
    label = "Live contract awards"
    if query.recipient:
        args["keywords"] = query.recipient
        label = f"Live awards for “{query.recipient}”"
    if query.agency:
        args["awarding_agency"] = query.agency
        label = f"Live awards — {query.agency}"
    if query.naics_codes:
        args["naics_codes"] = query.naics_codes
    if query.psc_codes:
        args["psc_codes"] = query.psc_codes
    if mode == "spend_trend":
        return ("spending_over_time", {**args, "group": "fiscal_year"}, label + " (spend over time)")
    return ("search_awards", args, label)


def _build_sam_subaward_args(query: InsightFacetQuery) -> tuple[dict[str, Any], str] | None:
    if not query.recipient:
        return None
    return (
        {"subawardeeName": query.recipient, "limit": _OVERLAY_LIMIT},
        f"SAM FFATA subawards — sub “{query.recipient}”",
    )


async def fetch_mcp_overlay(
    settings: Settings,
    query: InsightFacetQuery | None,
    mode: str,
    *,
    include_mcp: bool = False,
    mcp_service: MCPService | None = None,
) -> dict[str, Any]:
    """Return serializable overlay dict for drill-down templates."""
    if not include_mcp:
        return {"enabled": False, "status": "skipped", "layers": []}

    if not settings.enable_live_mcps:
        return {
            "enabled": True,
            "status": "disabled",
            "layers": [],
            "note": "Live MCP disabled (ENABLE_LIVE_MCPS=false).",
        }

    if query is None or not query.has_filters():
        return {
            "enabled": True,
            "status": "no_query",
            "layers": [],
            "note": "Set facets before fetching live MCP supplement.",
        }

    service = mcp_service or MCPService(settings)
    layers: list[McpOverlayLayer] = []

    us_tool, us_args, us_label = _build_usaspending_args(query, mode)
    us_result = await service.invoke("usaspending", us_tool, us_args)
    if us_result.get("ok"):
        payload = _parse_json_payload(us_result.get("output") or "")
        title_keys = ("Recipient Name", "recipient_name", "subawardee_name", "prime_awardee_name", "name")
        subtitle_keys = ("Awarding Agency", "awarding_agency_name", "prime_awardee_name", "agency")
        rows = _extract_rows(payload, title_keys=title_keys, subtitle_keys=subtitle_keys)
        layers.append(
            McpOverlayLayer(
                server="usaspending",
                tool=us_tool,
                label=us_label,
                status="ready" if rows else "empty",
                rows=tuple(rows),
            )
        )
    else:
        layers.append(
            McpOverlayLayer(
                server="usaspending",
                tool=us_tool,
                label=us_label,
                status="error",
                error=str(us_result.get("error") or "invoke failed"),
            )
        )

    if mode == "teaming" and _mcp_server_ready(settings, "sam_gov"):
        sam_spec = _build_sam_subaward_args(query)
        if sam_spec:
            sam_args, sam_label = sam_spec
            sam_result = await service.invoke("sam_gov", "search_acquisition_subawards", sam_args)
            if sam_result.get("ok"):
                payload = _parse_json_payload(sam_result.get("output") or "")
                rows = _extract_rows(
                    payload,
                    title_keys=("subawardeeName", "subawardee_name", "legalBusinessName", "name"),
                    subtitle_keys=("primeAwardeeName", "prime_awardee_name", "primeName"),
                )
                layers.append(
                    McpOverlayLayer(
                        server="sam_gov",
                        tool="search_acquisition_subawards",
                        label=sam_label,
                        status="ready" if rows else "empty",
                        rows=tuple(rows),
                    )
                )
            else:
                layers.append(
                    McpOverlayLayer(
                        server="sam_gov",
                        tool="search_acquisition_subawards",
                        label=sam_label,
                        status="error",
                        error=str(sam_result.get("error") or "invoke failed"),
                    )
                )

    ready = sum(1 for layer in layers if layer.status == "ready" and layer.rows)
    status = "ready" if ready else ("partial" if layers else "empty")
    return {
        "enabled": True,
        "status": status,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "layers": [
            {
                "server": layer.server,
                "tool": layer.tool,
                "label": layer.label,
                "status": layer.status,
                "rows": list(layer.rows),
                "error": layer.error,
            }
            for layer in layers
        ],
        "note": "Live supplement — compare to PG bulk slice above; candidate until review.",
    }