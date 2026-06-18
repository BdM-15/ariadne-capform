"""SAM monitor widget — Pulse leads from SAM.gov MCP (12i)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from thread.config import Settings
from thread.intel.sam_query import (
    SamMonitorQuery,
    build_mcp_arguments,
    describe_sam_query,
    load_sam_queries,
    resolve_active_sam_query,
)
from thread.mcp.service import MCPService

SAM_SEARCH_TOOL = "search_opportunities"
# SAM public API: ~1000 requests/day per key; rotate key every 90 days.
CACHE_TTL_MINUTES = 60


@dataclass(frozen=True)
class SamNoticeLead:
    notice_id: str
    title: str
    agency: str
    solicitation_number: str | None
    response_deadline: str | None
    posted_date: str | None
    notice_type: str | None
    set_aside: str | None
    naics_code: str | None


@dataclass(frozen=True)
class SamMonitorWidget:
    configured: bool
    active_query: SamMonitorQuery | None
    saved_queries: tuple[SamMonitorQuery, ...]
    query_summary: str
    notices: tuple[SamNoticeLead, ...]
    status: str
    error: str | None
    fetched_at: datetime | None
    cache_hit: bool


def _cache_path(settings: Settings) -> Path:
    return settings.resolve(settings.thread_state_dir) / "sam_monitor_cache.json"


def _sam_configured(settings: Settings) -> bool:
    mcp = MCPService(settings)
    sam = next((s for s in mcp.list_servers() if s["id"] == "sam_gov"), None)
    return bool(sam and sam["configured"])


def _agency_label(row: dict[str, Any]) -> str:
    parts = [
        str(row.get("department") or row.get("fullParentPathName") or "").strip(),
        str(row.get("subtier") or row.get("subTier") or "").strip(),
        str(row.get("office") or row.get("officeAddress", {}).get("city") if isinstance(row.get("officeAddress"), dict) else "").strip(),
    ]
    clean = [p for p in parts if p]
    return " · ".join(clean[:2]) if clean else "Unknown agency"


def _pick_str(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        val = row.get(key)
        if val is None or val == "":
            continue
        return str(val).strip()
    return None


def parse_notices_from_mcp_output(raw: str | dict[str, Any]) -> list[SamNoticeLead]:
    payload: Any = raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}|\[[\s\S]*\]", text)
            if not match:
                return []
            payload = json.loads(match.group(0))

    rows: list[dict[str, Any]] = []
    if isinstance(payload, list):
        rows = [r for r in payload if isinstance(r, dict)]
    elif isinstance(payload, dict):
        for key in ("opportunitiesData", "opportunities", "results", "data"):
            val = payload.get(key)
            if isinstance(val, list):
                rows = [r for r in val if isinstance(r, dict)]
                break
            if isinstance(val, dict):
                for inner in ("opportunitiesData", "opportunities", "results"):
                    inner_val = val.get(inner)
                    if isinstance(inner_val, list):
                        rows = [r for r in inner_val if isinstance(r, dict)]
                        break
                if rows:
                    break

    leads: list[SamNoticeLead] = []
    for row in rows:
        notice_id = _pick_str(row, "noticeId", "notice_id", "id")
        title = _pick_str(row, "title", "opportunityTitle")
        if not notice_id or not title:
            continue
        leads.append(
            SamNoticeLead(
                notice_id=notice_id,
                title=title,
                agency=_agency_label(row),
                solicitation_number=_pick_str(row, "solicitationNumber", "sol_number"),
                response_deadline=_pick_str(row, "responseDeadLine", "response_deadline", "currentResponseDate"),
                posted_date=_pick_str(row, "postedDate", "posted_date"),
                notice_type=_pick_str(row, "baseType", "type", "noticeType"),
                set_aside=_pick_str(row, "typeOfSetAside", "setAside", "set_aside"),
                naics_code=_pick_str(row, "naicsCode", "naics_code"),
            )
        )
    return leads


def _read_cache(settings: Settings, query_id: str) -> tuple[list[SamNoticeLead], datetime] | None:
    path = _cache_path(settings)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("query_id") != query_id:
        return None
    fetched_raw = data.get("fetched_at")
    if not fetched_raw:
        return None
    try:
        fetched_at = datetime.fromisoformat(str(fetched_raw))
    except ValueError:
        return None
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - fetched_at
    if age > timedelta(minutes=CACHE_TTL_MINUTES):
        return None
    notices = [
        SamNoticeLead(**item)
        for item in data.get("notices") or []
        if isinstance(item, dict) and item.get("notice_id") and item.get("title")
    ]
    return notices, fetched_at


def _write_cache(settings: Settings, query_id: str, notices: list[SamNoticeLead]) -> datetime:
    fetched_at = datetime.now(timezone.utc)
    path = _cache_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "query_id": query_id,
        "fetched_at": fetched_at.isoformat(),
        "notices": [n.__dict__ for n in notices],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return fetched_at


async def fetch_sam_notices(
    settings: Settings,
    query: SamMonitorQuery,
    *,
    force_refresh: bool = False,
) -> tuple[list[SamNoticeLead], datetime | None, bool, str | None]:
    if not force_refresh:
        cached = _read_cache(settings, query.id)
        if cached:
            notices, fetched_at = cached
            return notices, fetched_at, True, None

    mcp = MCPService(settings)
    result = await mcp.invoke("sam_gov", SAM_SEARCH_TOOL, build_mcp_arguments(query))
    if not result.get("ok"):
        return [], None, False, str(result.get("error") or "SAM MCP invoke failed")

    output = result.get("output")
    if isinstance(output, dict):
        raw = json.dumps(output)
    else:
        raw = str(output or "")
    notices = parse_notices_from_mcp_output(raw)
    fetched_at = _write_cache(settings, query.id, notices)
    return notices, fetched_at, False, None


async def build_sam_explore_results(
    settings: Settings,
    query: SamMonitorQuery,
    *,
    force_refresh: bool = False,
) -> SamMonitorWidget:
    """Live SAM explore from explicit query — not tied to active lens."""
    configured = _sam_configured(settings)
    summary = describe_sam_query(query)

    if not configured:
        return SamMonitorWidget(
            configured=False,
            active_query=query,
            saved_queries=(),
            query_summary=summary,
            notices=(),
            status="not_configured",
            error=None,
            fetched_at=None,
            cache_hit=False,
        )

    if not query.has_filters():
        return SamMonitorWidget(
            configured=True,
            active_query=query,
            saved_queries=(),
            query_summary=summary,
            notices=(),
            status="no_query",
            error=None,
            fetched_at=None,
            cache_hit=False,
        )

    notices, fetched_at, cache_hit, error = await fetch_sam_notices(
        settings,
        query,
        force_refresh=force_refresh,
    )
    if error:
        return SamMonitorWidget(
            configured=True,
            active_query=query,
            saved_queries=(),
            query_summary=summary,
            notices=(),
            status="error",
            error=error,
            fetched_at=fetched_at,
            cache_hit=cache_hit,
        )

    status = "ready" if notices else "empty"
    return SamMonitorWidget(
        configured=True,
        active_query=query,
        saved_queries=(),
        query_summary=summary,
        notices=tuple(notices),
        status=status,
        error=None,
        fetched_at=fetched_at,
        cache_hit=cache_hit,
    )


async def build_sam_monitor_widget(
    settings: Settings,
    *,
    force_refresh: bool = False,
) -> SamMonitorWidget:
    saved = load_sam_queries(settings)
    active = resolve_active_sam_query(settings)
    configured = _sam_configured(settings)
    summary = describe_sam_query(active)

    if not configured:
        return SamMonitorWidget(
            configured=False,
            active_query=active,
            saved_queries=saved,
            query_summary=summary,
            notices=(),
            status="not_configured",
            error=None,
            fetched_at=None,
            cache_hit=False,
        )

    if active is None or not active.has_filters():
        return SamMonitorWidget(
            configured=True,
            active_query=active,
            saved_queries=saved,
            query_summary=summary,
            notices=(),
            status="no_query",
            error=None,
            fetched_at=None,
            cache_hit=False,
        )

    notices, fetched_at, cache_hit, error = await fetch_sam_notices(
        settings,
        active,
        force_refresh=force_refresh,
    )
    if error:
        return SamMonitorWidget(
            configured=True,
            active_query=active,
            saved_queries=saved,
            query_summary=summary,
            notices=(),
            status="error",
            error=error,
            fetched_at=fetched_at,
            cache_hit=cache_hit,
        )

    status = "ready" if notices else "empty"
    return SamMonitorWidget(
        configured=True,
        active_query=active,
        saved_queries=saved,
        query_summary=summary,
        notices=tuple(notices),
        status=status,
        error=None,
        fetched_at=fetched_at,
        cache_hit=cache_hit,
    )