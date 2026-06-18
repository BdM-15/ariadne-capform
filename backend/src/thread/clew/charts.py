"""ECharts option builders for Clew trace results (client-side render on /clew)."""

from __future__ import annotations

from typing import Any

MAGENTA = "#ff2bd6"
CYAN = "#00f0ff"
LIME = "#00ff9c"
TEXT = "#94a3b8"
TEXT_BRIGHT = "#e2e8f0"
GRID = "#1f2a44"
AXIS = "#64748b"

MAX_SANKEY_LINKS = 24


def attach_echarts_option(analysis: dict[str, Any]) -> dict[str, Any]:
    """Add ECharts `chart` option dict when analysis has plottable rows."""
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


def _tooltip() -> dict[str, Any]:
    return {
        "trigger": "item",
        "backgroundColor": "rgba(10, 14, 26, 0.92)",
        "borderColor": GRID,
        "textStyle": {"color": TEXT_BRIGHT, "fontSize": 11},
    }


def _grid() -> dict[str, Any]:
    return {
        "left": "3%",
        "right": "4%",
        "bottom": "8%",
        "top": 56,
        "containLabel": True,
    }


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
        "title": {
            "text": "Obligation trend (facet slice)",
            "left": "center",
            "textStyle": {"color": TEXT_BRIGHT, "fontSize": 14, "fontWeight": 600},
        },
        "tooltip": {**_tooltip(), "trigger": "axis"},
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
                    {
                        "value": v,
                        "actions": actions[i],
                        "itemStyle": {
                            "color": {
                                "type": "linear",
                                "x": 0,
                                "y": 0,
                                "x2": 0,
                                "y2": 1,
                                "colorStops": [
                                    {"offset": 0, "color": MAGENTA},
                                    {"offset": 1, "color": "rgba(255, 43, 214, 0.35)"},
                                ],
                            },
                        },
                    }
                    for i, v in enumerate(values)
                ],
                "emphasis": {"focus": "series"},
                "barMaxWidth": 48,
            }
        ],
        "_clew": {"mode": "spend_trend", "tooltipTemplate": "year_value_actions"},
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
        "title": {
            "text": title,
            "left": "center",
            "textStyle": {"color": TEXT_BRIGHT, "fontSize": 14, "fontWeight": 600},
        },
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
                "data": [
                    {"name": n["name"], "itemStyle": n["itemStyle"]}
                    for n in nodes.values()
                ],
                "links": sankey_links,
            }
        ],
        "_clew": {"mode": mode, "displayKey": "display"},
    }


def _money_flow_sankey(analysis: dict[str, Any]) -> dict[str, Any] | None:
    flows = analysis.get("flows") or []
    links = [
        {
            "source": f["recipient"],
            "target": f["agency"],
            "value": f["millions"],
        }
        for f in flows
    ]
    return _sankey_option(
        title="Money flow — recipient → agency",
        links=links,
        source_label="recipient",
        target_label="agency",
        mode="money_flow",
    )


def _teaming_sankey(analysis: dict[str, Any]) -> dict[str, Any] | None:
    edges = analysis.get("edges") or []
    links = [
        {
            "source": e["prime"],
            "target": e["sub"],
            "value": e["millions"],
        }
        for e in edges
    ]
    return _sankey_option(
        title="Teaming — prime → subcontractor",
        links=links,
        source_label="prime",
        target_label="sub",
        mode="teaming",
    )


def _recipient_landscape_chart(analysis: dict[str, Any]) -> dict[str, Any] | None:
    recipients = analysis.get("recipients") or []
    if not recipients:
        return None
    names = [_truncate(r["recipient"], 36) for r in recipients]
    values = [r["millions"] for r in recipients]
    return {
        "backgroundColor": "transparent",
        "textStyle": {"color": TEXT},
        "title": {
            "text": "Recipient concentration",
            "left": "center",
            "textStyle": {"color": TEXT_BRIGHT, "fontSize": 14, "fontWeight": 600},
        },
        "tooltip": {**_tooltip(), "trigger": "axis", "axisPointer": {"type": "shadow"}},
        "grid": {**_grid(), "left": "28%"},
        "xAxis": {
            "type": "value",
            "name": "$M",
            "nameTextStyle": {"color": AXIS},
            "axisLine": {"show": False},
            "splitLine": {"lineStyle": {"color": GRID, "type": "dashed"}},
            "axisLabel": {"color": AXIS},
        },
        "yAxis": {
            "type": "category",
            "data": list(reversed(names)),
            "axisLine": {"lineStyle": {"color": GRID}},
            "axisLabel": {"color": TEXT_BRIGHT, "fontSize": 10},
        },
        "series": [
            {
                "type": "bar",
                "data": list(reversed(values)),
                "itemStyle": {
                    "color": {
                        "type": "linear",
                        "x": 0,
                        "y": 0,
                        "x2": 1,
                        "y2": 0,
                        "colorStops": [
                            {"offset": 0, "color": "rgba(255, 43, 214, 0.35)"},
                            {"offset": 1, "color": MAGENTA},
                        ],
                    }
                },
                "barMaxWidth": 18,
            }
        ],
        "_clew": {"mode": "recipient_landscape"},
    }


def _truncate(text: str, max_len: int) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"