"""Shared ECharts option builders — Insights Overview + Clew trace (ink/neon theme)."""

from __future__ import annotations

from typing import Any

MAGENTA = "#ff2bd6"
CYAN = "#00f0ff"
LIME = "#00ff9c"
AMBER = "#fbbf24"
TEXT = "#94a3b8"
TEXT_BRIGHT = "#e2e8f0"
GRID = "#1f2a44"
AXIS = "#64748b"

MAX_SANKEY_LINKS = 24


def attach_echarts_option(analysis: dict[str, Any]) -> dict[str, Any]:
    if analysis.get("error"):
        return analysis
    mode = analysis.get("mode")
    builders = {
        "spend_trend": _spend_trend_chart,
        "money_flow": _money_flow_sankey,
        "teaming": _teaming_sankey,
        "recipient_landscape": _recipient_landscape_chart,
    }
    builder = builders.get(mode or "")
    if builder is None:
        return analysis
    option = builder(analysis)
    if option:
        analysis["chart"] = option
    return analysis


def attach_entity_echarts(profile: dict[str, Any], kind: str) -> dict[str, Any]:
    if profile.get("error"):
        return profile
    charts: dict[str, Any] = {}
    spend = _spend_trend_chart({"bars": profile.get("spend_trend") or [], "mode": "spend_trend"})
    if spend:
        charts["spend_trend"] = spend
    if kind == "agency":
        sub_flow = _agency_sub_flow_chart(profile.get("agency_sub_flow") or [], profile)
        if sub_flow:
            charts["sub_flow"] = sub_flow
        contractors = _horizontal_bar_chart(
            profile.get("top_contractors") or [],
            title="Top contractors in slice",
            name_key="recipient",
        )
        if contractors:
            charts["top_contractors"] = contractors
    else:
        agencies = _horizontal_bar_chart(
            profile.get("top_agencies") or [],
            title="Top agencies",
            name_key="agency",
        )
        if agencies:
            charts["top_agencies"] = agencies
        naics_rows = [
            {"recipient": r["naics"], "millions": r["millions"]}
            for r in profile.get("top_naics") or []
        ]
        naics_chart = _horizontal_bar_chart(naics_rows, title="Top NAICS", name_key="recipient")
        if naics_chart:
            charts["top_naics"] = naics_chart
    set_aside = _donut_chart(
        profile.get("set_aside") or [],
        title="Set-aside mix",
        name_key="bucket",
    )
    if set_aside:
        charts["set_aside"] = set_aside
    extent = _horizontal_bar_chart(
        profile.get("extent_competed") or [],
        title="Extent competed",
        name_key="extent",
    )
    if extent:
        charts["extent_competed"] = extent
    if charts:
        profile["charts"] = charts
    return profile


def attach_overview_echarts(overview: dict[str, Any]) -> dict[str, Any]:
    if overview.get("error"):
        return overview
    charts: dict[str, Any] = {}
    intensity = _agency_intensity_scatter(overview.get("agency_intensity") or {})
    if intensity:
        charts["intensity"] = intensity
    sub_flow = _agency_sub_flow_chart(overview.get("agency_sub_flow") or [], overview)
    if sub_flow:
        charts["sub_flow"] = sub_flow
    spend = _spend_trend_chart({"bars": overview.get("spend_trend") or [], "mode": "spend_trend"})
    if spend:
        charts["spend_trend"] = spend
    set_aside = _donut_chart(
        overview.get("set_aside") or [],
        title="Set-aside mix",
        name_key="bucket",
    )
    if set_aside:
        charts["set_aside"] = set_aside
    extent = _horizontal_bar_chart(
        overview.get("extent_competed") or [],
        title="Extent competed",
        name_key="extent",
    )
    if extent:
        charts["extent_competed"] = extent
    recipients = _horizontal_bar_chart(
        overview.get("top_recipients") or [],
        title="Top recipients",
        name_key="recipient",
    )
    if recipients:
        charts["top_recipients"] = recipients
    if charts:
        overview["charts"] = charts
    return overview


def _tooltip(trigger: str = "item") -> dict[str, Any]:
    return {
        "trigger": trigger,
        "backgroundColor": "rgba(10, 14, 26, 0.92)",
        "borderColor": GRID,
        "textStyle": {"color": TEXT_BRIGHT, "fontSize": 11},
    }


def _grid(**overrides: Any) -> dict[str, Any]:
    base = {
        "left": "3%",
        "right": "4%",
        "bottom": "8%",
        "top": 56,
        "containLabel": True,
    }
    base.update(overrides)
    return base


def _title(text: str) -> dict[str, Any]:
    return {
        "text": text,
        "left": "center",
        "textStyle": {"color": TEXT_BRIGHT, "fontSize": 14, "fontWeight": 600},
    }


def _agency_intensity_scatter(intensity: dict[str, Any]) -> dict[str, Any] | None:
    points = intensity.get("points") or []
    if not points:
        return None
    median_actions = float(intensity.get("median_actions") or 0)
    median_millions = float(intensity.get("median_millions") or 0)
    data = [
        {
            "value": [p["actions"], p["millions"]],
            "agency": p["agency"],
            "hot": p.get("hot"),
            "itemStyle": {"color": LIME if p.get("hot") else CYAN},
        }
        for p in points
    ]
    return {
        "backgroundColor": "transparent",
        "textStyle": {"color": TEXT},
        "title": _title("Capture intensity — actions × obligation"),
        "tooltip": {
            **_tooltip("item"),
            "formatter": None,
        },
        "grid": _grid(top=72, bottom=48),
        "xAxis": {
            "type": "value",
            "name": "Actions",
            "nameTextStyle": {"color": AXIS},
            "splitLine": {"lineStyle": {"color": GRID, "type": "dashed"}},
            "axisLabel": {"color": AXIS},
        },
        "yAxis": {
            "type": "value",
            "name": "$M obligated",
            "nameTextStyle": {"color": AXIS},
            "splitLine": {"lineStyle": {"color": GRID, "type": "dashed"}},
            "axisLabel": {"color": AXIS},
        },
        "series": [
            {
                "type": "scatter",
                "symbolSize": 14,
                "data": data,
                "markLine": {
                    "silent": True,
                    "lineStyle": {"color": AMBER, "type": "dashed", "opacity": 0.6},
                    "data": [
                        {"xAxis": median_actions},
                        {"yAxis": median_millions},
                    ],
                },
            }
        ],
        "_intel": {
            "mode": "agency_intensity",
            "honeField": "agency",
            "drillLens": "agency",
            "entityScope": "agency",
            "tooltipFields": ["agency", "actions", "millions"],
        },
    }


def _agency_sub_flow_chart(rows: list[dict[str, Any]], overview: dict[str, Any]) -> dict[str, Any] | None:
    if not rows:
        return None
    group = overview.get("agency_sub_flow_group") or rows[0].get("kind", "sub_agency")
    title = "Sub-agency flow" if group == "sub_agency" else "Office flow"
    names = [_truncate(r["label"], 40) for r in rows]
    values = [r["millions"] for r in rows]
    hone_field = "sub_agency" if group == "sub_agency" else "awarding_office"
    return {
        "backgroundColor": "transparent",
        "textStyle": {"color": TEXT},
        "title": _title(title),
        "tooltip": {**_tooltip("axis"), "axisPointer": {"type": "shadow"}},
        "grid": {**_grid(), "left": "32%"},
        "xAxis": {
            "type": "value",
            "name": "$M",
            "axisLabel": {"color": AXIS},
            "splitLine": {"lineStyle": {"color": GRID, "type": "dashed"}},
        },
        "yAxis": {
            "type": "category",
            "data": list(reversed(names)),
            "axisLabel": {"color": TEXT_BRIGHT, "fontSize": 10},
        },
        "series": [
            {
                "type": "bar",
                "data": [
                    {"value": v, "label": names[len(names) - 1 - i]}
                    for i, v in enumerate(reversed(values))
                ],
                "itemStyle": {"color": MAGENTA},
                "barMaxWidth": 16,
            }
        ],
        "_intel": {
            "mode": "sub_flow",
            "honeField": hone_field,
            "drillLens": "agency",
            "entityScope": group,
        },
    }


def _donut_chart(
    rows: list[dict[str, Any]],
    *,
    title: str,
    name_key: str,
) -> dict[str, Any] | None:
    if not rows:
        return None
    return {
        "backgroundColor": "transparent",
        "textStyle": {"color": TEXT},
        "title": _title(title),
        "tooltip": _tooltip(),
        "series": [
            {
                "type": "pie",
                "radius": ["42%", "68%"],
                "data": [
                    {"name": _truncate(str(r.get(name_key) or "?"), 28), "value": r.get("millions", 0)}
                    for r in rows
                ],
                "label": {"color": TEXT_BRIGHT, "fontSize": 10},
                "itemStyle": {"borderColor": "#0a0e1a", "borderWidth": 2},
            }
        ],
        "_intel": {"mode": "donut"},
    }


def _horizontal_bar_chart(
    rows: list[dict[str, Any]],
    *,
    title: str,
    name_key: str,
) -> dict[str, Any] | None:
    if not rows:
        return None
    names = [_truncate(str(r.get(name_key) or "?"), 36) for r in rows]
    values = [r.get("millions", 0) for r in rows]
    hone_field = "recipient" if name_key == "recipient" else ("agency" if name_key == "agency" else None)
    chart: dict[str, Any] = {
        "backgroundColor": "transparent",
        "textStyle": {"color": TEXT},
        "title": _title(title),
        "tooltip": {**_tooltip("axis"), "axisPointer": {"type": "shadow"}},
        "grid": {**_grid(), "left": "28%"},
        "xAxis": {
            "type": "value",
            "name": "$M",
            "splitLine": {"lineStyle": {"color": GRID, "type": "dashed"}},
            "axisLabel": {"color": AXIS},
        },
        "yAxis": {
            "type": "category",
            "data": list(reversed(names)),
            "axisLabel": {"color": TEXT_BRIGHT, "fontSize": 10},
        },
        "series": [
            {
                "type": "bar",
                "data": list(reversed(values)),
                "itemStyle": {"color": CYAN},
                "barMaxWidth": 16,
            }
        ],
        "_intel": {"mode": "hbar"},
    }
    if hone_field:
        chart["_intel"]["honeField"] = hone_field
        chart["_intel"]["drillLens"] = "competitor" if hone_field == "recipient" else "agency"
        chart["_intel"]["entityScope"] = (
            "recipient" if hone_field == "recipient" else ("agency" if hone_field == "agency" else hone_field)
        )
    return chart


def _spend_trend_chart(analysis: dict[str, Any]) -> dict[str, Any] | None:
    bars = analysis.get("bars") or []
    if not bars:
        return None
    years = [str(b["year"]) for b in bars]
    values = [b["millions"] for b in bars]
    actions = [b.get("actions", 0) for b in bars]
    return {
        "backgroundColor": "transparent",
        "textStyle": {"color": TEXT},
        "title": _title("Obligation trend (facet slice)"),
        "tooltip": {**_tooltip("axis")},
        "grid": _grid(),
        "xAxis": {
            "type": "category",
            "data": years,
            "axisLine": {"lineStyle": {"color": GRID}},
            "axisLabel": {"color": AXIS},
        },
        "yAxis": {
            "type": "value",
            "name": "$M obligated",
            "nameTextStyle": {"color": AXIS},
            "axisLine": {"show": False},
            "splitLine": {"lineStyle": {"color": GRID, "type": "dashed"}},
            "axisLabel": {"color": AXIS},
        },
        "series": [
            {
                "name": "Obligations",
                "type": "bar",
                "data": [
                    {"value": v, "actions": actions[i]}
                    for i, v in enumerate(values)
                ],
                "itemStyle": {"color": MAGENTA},
                "barMaxWidth": 48,
            }
        ],
        "_intel": {"mode": "spend_trend", "tooltipTemplate": "year_value_actions"},
    }


def _sankey_option(
    *,
    title: str,
    links: list[dict[str, Any]],
    source_label: str,
    target_label: str,
    mode: str,
) -> dict[str, Any] | None:
    if not links:
        return None
    trimmed = links[:MAX_SANKEY_LINKS]
    nodes: dict[str, dict[str, Any]] = {}

    def _node(name: str, side: str) -> str:
        key = f"{side}::{name}"
        if key not in nodes:
            nodes[key] = {
                "name": key,
                "display": name,
                "itemStyle": {"color": MAGENTA if side == source_label else CYAN},
            }
        return key

    sankey_links = []
    for row in trimmed:
        src = _node(str(row["source"]), source_label)
        tgt = _node(str(row["target"]), target_label)
        sankey_links.append({"source": src, "target": tgt, "value": max(float(row["value"]), 0.01)})

    return {
        "backgroundColor": "transparent",
        "textStyle": {"color": TEXT},
        "title": _title(title),
        "tooltip": _tooltip(),
        "series": [
            {
                "type": "sankey",
                "emphasis": {"focus": "adjacency"},
                "nodeAlign": "justify",
                "layoutIterations": 32,
                "lineStyle": {"color": "gradient", "curveness": 0.5, "opacity": 0.45},
                "itemStyle": {"borderWidth": 0},
                "label": {"color": TEXT_BRIGHT, "fontSize": 10},
                "data": [{"name": n["name"], "itemStyle": n["itemStyle"]} for n in nodes.values()],
                "links": sankey_links,
            }
        ],
        "_intel": {"mode": mode, "displayKey": "display"},
    }


def _money_flow_sankey(analysis: dict[str, Any]) -> dict[str, Any] | None:
    flows = analysis.get("flows") or []
    links = [{"source": f["recipient"], "target": f["agency"], "value": f["millions"]} for f in flows]
    return _sankey_option(
        title="Money flow — recipient → agency",
        links=links,
        source_label="recipient",
        target_label="agency",
        mode="money_flow",
    )


def _teaming_sankey(analysis: dict[str, Any]) -> dict[str, Any] | None:
    edges = analysis.get("edges") or []
    links = [{"source": e["prime"], "target": e["sub"], "value": e["millions"]} for e in edges]
    return _sankey_option(
        title="Teaming — prime → subcontractor",
        links=links,
        source_label="prime",
        target_label="sub",
        mode="teaming",
    )


def _recipient_landscape_chart(analysis: dict[str, Any]) -> dict[str, Any] | None:
    return _horizontal_bar_chart(
        analysis.get("recipients") or [],
        title="Recipient concentration",
        name_key="recipient",
    )


def _truncate(text: str, max_len: int) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"