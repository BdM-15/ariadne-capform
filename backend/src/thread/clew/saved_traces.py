"""Saved Clew trace bookmarks — `.thread/clew_traces.json`."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from thread.config import Settings
from thread.clew import ANALYSIS_MODES
from thread.intel.facet_query import InsightFacetQuery, _parse_codes, describe_query

_VALID_MODES = frozenset(ANALYSIS_MODES)


@dataclass(frozen=True)
class ClewSavedTrace:
    id: str
    name: str
    mode: str = "money_flow"
    agency: str | None = None
    sub_agency: str | None = None
    recipient: str | None = None
    naics_codes: tuple[str, ...] = ()
    psc_codes: tuple[str, ...] = ()
    include_mcp: bool = False
    description: str = ""
    saved_at: str = ""
    last_summary: str = ""

    def has_filters(self) -> bool:
        return bool(
            self.naics_codes or self.agency or self.sub_agency or self.recipient or self.psc_codes
        )

    def facet_query(self) -> InsightFacetQuery:
        return InsightFacetQuery(
            id=self.id,
            name=self.name,
            naics_codes=self.naics_codes,
            agency=self.agency,
            sub_agency=self.sub_agency,
            recipient=self.recipient,
            psc_codes=self.psc_codes,
            description=self.description,
        )


def _traces_path(settings: Settings) -> Path:
    return settings.resolve(settings.thread_state_dir) / "clew_traces.json"


def _slug_id(name: str, existing: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "trace"
    candidate = base[:48]
    suffix = 2
    while candidate in existing:
        candidate = f"{base[:40]}-{suffix}"
        suffix += 1
    return candidate


def trace_from_dict(raw: dict[str, Any]) -> ClewSavedTrace | None:
    trace_id = str(raw.get("id") or "").strip()
    name = str(raw.get("name") or trace_id).strip()
    if not trace_id or not name:
        return None
    mode = str(raw.get("mode") or "money_flow").strip()
    if mode not in _VALID_MODES:
        mode = "money_flow"
    trace = ClewSavedTrace(
        id=trace_id,
        name=name,
        mode=mode,
        agency=(str(raw["agency"]).strip() or None) if raw.get("agency") else None,
        sub_agency=(str(raw["sub_agency"]).strip() or None) if raw.get("sub_agency") else None,
        recipient=(str(raw["recipient"]).strip() or None) if raw.get("recipient") else None,
        naics_codes=_parse_codes(raw.get("naics_codes") or raw.get("naics")),
        psc_codes=_parse_codes(raw.get("psc_codes") or raw.get("psc")),
        include_mcp=bool(raw.get("include_mcp")),
        description=str(raw.get("description") or ""),
        saved_at=str(raw.get("saved_at") or ""),
        last_summary=str(raw.get("last_summary") or ""),
    )
    return trace if trace.has_filters() else None


def _write_traces(settings: Settings, traces: list[ClewSavedTrace]) -> None:
    path = _traces_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "id": t.id,
            "name": t.name,
            "mode": t.mode,
            "agency": t.agency,
            "sub_agency": t.sub_agency,
            "recipient": t.recipient,
            "naics_codes": list(t.naics_codes),
            "psc_codes": list(t.psc_codes),
            "include_mcp": t.include_mcp,
            "description": t.description,
            "saved_at": t.saved_at,
            "last_summary": t.last_summary,
        }
        for t in traces
    ]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_clew_traces(settings: Settings) -> tuple[ClewSavedTrace, ...]:
    path = _traces_path(settings)
    if not path.is_file():
        return ()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ()
    if not isinstance(raw, list):
        return ()
    traces: list[ClewSavedTrace] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        trace = trace_from_dict(item)
        if trace is not None:
            traces.append(trace)
    return tuple(sorted(traces, key=lambda t: t.name.lower()))


def save_clew_trace(settings: Settings, trace: ClewSavedTrace) -> ClewSavedTrace:
    traces = list(load_clew_traces(settings))
    by_id = {t.id: t for t in traces}
    by_id[trace.id] = trace
    ordered = sorted(by_id.values(), key=lambda t: t.name.lower())
    _write_traces(settings, ordered)
    return trace


def delete_clew_trace(settings: Settings, trace_id: str) -> bool:
    before = load_clew_traces(settings)
    after = [t for t in before if t.id != trace_id]
    if len(after) == len(before):
        return False
    _write_traces(settings, list(after))
    return True


def new_clew_trace_from_form(
    settings: Settings,
    *,
    name: str,
    mode: str = "money_flow",
    agency: str = "",
    sub_agency: str = "",
    recipient: str = "",
    naics_codes: str = "",
    psc_codes: str = "",
    include_mcp: bool = False,
    description: str = "",
    last_summary: str = "",
) -> ClewSavedTrace | None:
    clean_name = name.strip()
    if not clean_name:
        return None
    clean_mode = mode if mode in _VALID_MODES else "money_flow"
    trace = ClewSavedTrace(
        id=_slug_id(clean_name, {t.id for t in load_clew_traces(settings)}),
        name=clean_name,
        mode=clean_mode,
        agency=agency.strip() or None,
        sub_agency=sub_agency.strip() or None,
        recipient=recipient.strip() or None,
        naics_codes=_parse_codes(naics_codes),
        psc_codes=_parse_codes(psc_codes),
        include_mcp=include_mcp,
        description=description.strip(),
        saved_at=datetime.now(timezone.utc).isoformat(),
        last_summary=last_summary.strip(),
    )
    return trace if trace.has_filters() else None


def describe_trace(trace: ClewSavedTrace) -> str:
    facet_line = describe_query(trace.facet_query())
    mode_label = trace.mode.replace("_", " ")
    parts = [p for p in (facet_line, mode_label) if p]
    if trace.include_mcp:
        parts.append("live MCP")
    return " · ".join(parts)


def clew_trace_href(trace: ClewSavedTrace, *, run: bool = True) -> str:
    params: dict[str, str | int] = {
        "mode": trace.mode,
        "run": 1 if run else 0,
        "include_mcp": 1 if trace.include_mcp else 0,
    }
    if trace.agency:
        params["agency"] = trace.agency
    if trace.sub_agency:
        params["sub_agency"] = trace.sub_agency
    if trace.recipient:
        params["recipient"] = trace.recipient
    if trace.naics_codes:
        params["naics_codes"] = ",".join(trace.naics_codes)
    if trace.psc_codes:
        params["psc_codes"] = ",".join(trace.psc_codes)
    return "/clew?" + urlencode(params)