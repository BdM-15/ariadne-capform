"""Phase 17b.1 — DR-style encoded path deep-links for Clew Sankey preload."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlencode

from thread.clew.charts import attach_echarts_option

_PATH_SEP = ";"
_FIELD_SEP = ","


def _escape_field(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace(_FIELD_SEP, "\\,").replace(_PATH_SEP, "\\;")


def _unescape_field(text: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            out.append(text[i + 1])
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _split_fields(segment: str) -> list[str]:
    fields: list[str] = []
    buf: list[str] = []
    i = 0
    while i < len(segment):
        ch = segment[i]
        if ch == "\\" and i + 1 < len(segment):
            buf.append(segment[i + 1])
            i += 2
            continue
        if ch == _FIELD_SEP:
            fields.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    fields.append("".join(buf))
    return fields


def parse_path_param(raw: str) -> list[dict[str, Any]]:
    """Parse `src,tgt,value;…` edge list (DR deep-link pattern)."""
    edges: list[dict[str, Any]] = []
    for segment in (raw or "").split(_PATH_SEP):
        segment = segment.strip()
        if not segment:
            continue
        fields = _split_fields(segment)
        if len(fields) < 3:
            continue
        try:
            value = float(fields[-1].strip())
        except ValueError:
            continue
        if value <= 0:
            continue
        src = _unescape_field(fields[0]).strip()
        tgt = _unescape_field(fields[1]).strip()
        if not src or not tgt:
            continue
        edges.append({"source": src, "target": tgt, "value": value})
    return edges


def encode_path_param(edges: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for edge in edges:
        src = _escape_field(str(edge.get("source") or ""))
        tgt = _escape_field(str(edge.get("target") or ""))
        try:
            value = float(edge.get("value") or 0)
        except (TypeError, ValueError):
            continue
        if not src or not tgt or value <= 0:
            continue
        parts.append(f"{src}{_FIELD_SEP}{tgt}{_FIELD_SEP}{value:g}")
    return _PATH_SEP.join(parts)


def clew_path_href(
    *,
    mode: str = "money_flow",
    source: str = "",
    target: str = "",
    value: float | int = 0,
    agency: str = "",
    sub_agency: str = "",
    recipient: str = "",
    naics_codes: str = "",
    psc_codes: str = "",
) -> str:
    """Build `/clew?path=…` href for a single edge handoff."""
    path = encode_path_param([{"source": source, "target": target, "value": float(value)}])
    params: dict[str, str] = {"mode": mode}
    if path:
        params["path"] = path
    if agency.strip():
        params["agency"] = agency.strip()
    if sub_agency.strip():
        params["sub_agency"] = sub_agency.strip()
    if recipient.strip():
        params["recipient"] = recipient.strip()
    if naics_codes.strip():
        params["naics_codes"] = naics_codes.strip()
    if psc_codes.strip():
        params["psc_codes"] = psc_codes.strip()
    return "/clew?" + urlencode(params, quote_via=quote)


def analysis_from_path(*, mode: str, edges: list[dict[str, Any]]) -> dict[str, Any]:
    """Build Clew analysis + ECharts option from encoded edges (no PG round-trip)."""
    if mode == "teaming":
        analysis: dict[str, Any] = {
            "mode": "teaming",
            "edges": [
                {"prime": e["source"], "sub": e["target"], "millions": e["value"]}
                for e in edges
            ],
            "method": f"Pre-loaded path — {len(edges)} prime→sub edge(s) from deep-link (no PG query).",
        }
    else:
        mode = "money_flow"
        analysis = {
            "mode": "money_flow",
            "flows": [
                {"recipient": e["source"], "agency": e["target"], "millions": e["value"]}
                for e in edges
            ],
            "method": f"Pre-loaded path — {len(edges)} recipient→agency edge(s) from deep-link (no PG query).",
        }
    analysis["path_preloaded"] = True
    analysis["summary"] = "Deep-linked trace path"
    return attach_echarts_option(analysis)