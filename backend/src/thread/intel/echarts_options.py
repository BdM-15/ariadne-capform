"""Shared ECharts option builders — Insights Overview + Clew trace (ink/neon theme)."""

from __future__ import annotations

from typing import Any

MAGENTA = "#ff2bd6"
CYAN = "#00f0ff"
LIME = "#00ff9c"
AMBER = "#fbbf24"
TIER_HIGH = "#ff2bd6"
TIER_MED = "#00f0ff"
TIER_LOW = "#64748b"
TEXT = "#94a3b8"
TEXT_BRIGHT = "#e2e8f0"
GRID = "#1f2a44"
AXIS = "#64748b"

MAX_SANKEY_LINKS = 24


def _non_negative_float(value: Any) -> float:
    try:
        n = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    if n != n:
        return 0.0
    return max(0.0, n)


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
    matrix = _agency_recipient_heatmap(profile.get("agency_recipient_matrix") or {})
    if matrix:
        charts["relationship_heatmap"] = matrix
    money = _money_flow_sankey({"flows": profile.get("money_flow") or [], "mode": "money_flow"})
    if money:
        charts["money_flow"] = money
    team_edges = profile.get("teaming") or []
    if team_edges and not profile.get("teaming_error"):
        team = _teaming_sankey({"edges": team_edges, "mode": "teaming"})
        if team:
            charts["teaming"] = team
    relations = profile.get("relations_graph") or profile.get("expose_graph") or {}
    rel_chart = _relations_force_graph(relations)
    if rel_chart:
        charts["relations_graph"] = rel_chart
    browse = _browse_funnel_sankey(profile.get("browse_funnel") or {})
    if browse:
        charts["browse_funnel"] = browse
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
    pricing = _pricing_bucket_chart(profile.get("pricing_buckets") or [])
    if pricing:
        charts["pricing_buckets"] = pricing
    if charts:
        profile["charts"] = charts
    return profile


def attach_competition_echarts(bundle: dict[str, Any]) -> dict[str, Any]:
    if bundle.get("error"):
        return bundle
    charts: dict[str, Any] = {}
    set_aside = _donut_chart(bundle.get("set_aside") or [], title="Set-aside mix", name_key="bucket")
    if set_aside:
        charts["set_aside"] = set_aside
    extent = _horizontal_bar_chart(
        bundle.get("extent_competed") or [],
        title="Extent competed",
        name_key="extent",
    )
    if extent:
        charts["extent_competed"] = extent
    pricing = _pricing_bucket_chart(bundle.get("pricing_buckets") or [])
    if pricing:
        charts["pricing_buckets"] = pricing
    vehicles = _vehicle_combo_chart(bundle.get("vehicle_breakdown") or [])
    if vehicles:
        charts["vehicle_breakdown"] = vehicles
    idv = _donut_chart(
        [{"bucket": r["channel"], "millions": r["millions"]} for r in bundle.get("idv_split") or []],
        title="IDV vs standalone",
        name_key="bucket",
    )
    if idv:
        charts["idv_split"] = idv
    ffp = bundle.get("ffp_shaping") or {}
    pressure = _ffp_pressure_chart(ffp.get("agency_pressure") or [])
    if pressure:
        charts["ffp_pressure"] = pressure
    if charts:
        bundle["charts"] = charts
    return bundle


def attach_trace_echarts(bundle: dict[str, Any]) -> dict[str, Any]:
    if bundle.get("error"):
        return bundle
    charts: dict[str, Any] = {}
    money = bundle.get("money_flow") or {}
    sankey = _money_flow_sankey(money) if money.get("flows") else None
    if sankey:
        charts["money_flow"] = sankey
    team = bundle.get("teaming") or {}
    if team.get("edges") and not team.get("error"):
        team_chart = _teaming_sankey(team)
        if team_chart:
            charts["teaming"] = team_chart
    matrix = _agency_recipient_heatmap(bundle.get("agency_recipient_matrix") or {})
    if matrix:
        charts["relationship_heatmap"] = matrix
    relations = bundle.get("relations_graph") or bundle.get("expose_graph") or {}
    rel_chart = _relations_force_graph(relations)
    if rel_chart:
        charts["relations_graph"] = rel_chart
        charts["expose_graph"] = rel_chart
    browse = _browse_funnel_sankey(bundle.get("browse_funnel") or {})
    if browse:
        charts["browse_funnel"] = browse
    if charts:
        bundle["charts"] = charts
    return bundle


def attach_overview_echarts(overview: dict[str, Any]) -> dict[str, Any]:
    if overview.get("error"):
        return overview
    charts: dict[str, Any] = {}
    intensity = _agency_intensity_scatter(overview.get("agency_intensity") or {})
    if intensity:
        charts["intensity"] = intensity
    motion_fy = _motion_fy_trend_chart(overview.get("spend_trend") or [])
    if motion_fy:
        charts["motion_fy_trend"] = motion_fy
    motion_payload = overview.get("motion") or {}
    channel_mix = _motion_channel_mix_chart(motion_payload.get("channels") or [])
    if channel_mix:
        charts["motion_channels"] = channel_mix
    q4_timing = _motion_q4_mix_shift_chart(motion_payload.get("timing") or {})
    if q4_timing:
        charts["motion_q4_timing"] = q4_timing
    expiring_ch = _motion_channel_bars_chart(
        motion_payload.get("expiring_channels") or [],
        title="Recompete channel split",
        mode="motion_expiring_channels",
    )
    if expiring_ch:
        charts["motion_expiring_channels"] = expiring_ch
    parent_shadow = _motion_parent_shadow_chart(motion_payload.get("parent_shadow") or {})
    if parent_shadow:
        charts["motion_parent_shadow"] = parent_shadow
    money_paths = _motion_money_paths_sankey(motion_payload.get("money_paths") or [])
    if money_paths:
        charts["motion_money_paths"] = money_paths
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
    pricing = _pricing_bucket_chart(overview.get("pricing_buckets") or [])
    if pricing:
        charts["pricing_buckets"] = pricing
    idv = _donut_chart(
        [{"bucket": r["channel"], "millions": r["millions"]} for r in overview.get("idv_split") or []],
        title="IDV vs standalone",
        name_key="bucket",
    )
    if idv:
        charts["idv_split"] = idv
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


def _motion_fy_trend_chart(bars: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not bars:
        return None
    labels = [f"FY{b['year']}" for b in bars]
    millions = [b.get("millions", 0) for b in bars]
    actions = [b.get("actions", 0) for b in bars]
    return {
        "backgroundColor": "transparent",
        "textStyle": {"color": TEXT},
        "title": _title("FY obligation pulse"),
        "tooltip": {**_tooltip("axis")},
        "legend": {
            "top": 28,
            "data": ["$ obligated", "Actions"],
            "textStyle": {"color": AXIS, "fontSize": 10},
        },
        "grid": _grid(top=72),
        "xAxis": {
            "type": "category",
            "data": labels,
            "axisLine": {"lineStyle": {"color": GRID}},
            "axisLabel": {"color": AXIS},
        },
        "yAxis": [
            {
                "type": "value",
                "name": "$M",
                "axisLabel": {"color": AXIS},
                "splitLine": {"lineStyle": {"color": GRID, "type": "dashed"}},
            },
            {
                "type": "value",
                "name": "Actions",
                "axisLabel": {"color": AXIS},
                "splitLine": {"show": False},
            },
        ],
        "series": [
            {
                "name": "$ obligated",
                "type": "bar",
                "data": [
                    {"value": m, "actions": actions[i]}
                    for i, m in enumerate(millions)
                ],
                "itemStyle": {"color": MAGENTA},
                "barMaxWidth": 40,
            },
            {
                "name": "Actions",
                "type": "line",
                "yAxisIndex": 1,
                "smooth": True,
                "symbol": "circle",
                "symbolSize": 7,
                "data": actions,
                "lineStyle": {"color": LIME, "width": 2},
                "itemStyle": {"color": LIME},
            },
        ],
        "_intel": {"mode": "motion_fy_trend", "tooltipTemplate": "motion_fy_trend"},
    }


_CHANNEL_COLORS: dict[str, str] = {
    "open_competed": LIME,
    "open_non_competed": AMBER,
    "set_aside_competed": CYAN,
    "set_aside_non_competed": MAGENTA,
    "vehicle_gated": TIER_MED,
    "other": TIER_LOW,
}


def _motion_channel_mix_chart(channels: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not channels:
        return None
    series = [
        {
            "name": ch.get("label") or ch.get("channel"),
            "type": "bar",
            "stack": "tam",
            "emphasis": {"focus": "series"},
            "label": {
                "show": True,
                "color": TEXT_BRIGHT,
                "fontSize": 9,
                "formatter": "{c}%",
            },
            "data": [
                {
                    "value": ch.get("pct", 0),
                    "millions": ch.get("millions", 0),
                    "actions": ch.get("actions", 0),
                    "channel": ch.get("channel"),
                    "label": {"show": float(ch.get("pct") or 0) >= 5.0},
                }
            ],
            "itemStyle": {"color": _CHANNEL_COLORS.get(str(ch.get("channel")), CYAN)},
            "barMaxWidth": 40,
        }
        for ch in channels
    ]
    return {
        "backgroundColor": "transparent",
        "textStyle": {"color": TEXT},
        "title": _title("Entry lane mix"),
        "tooltip": {**_tooltip("item")},
        "legend": {
            "type": "scroll",
            "bottom": 0,
            "textStyle": {"color": AXIS, "fontSize": 9},
        },
        "grid": _grid(top=72, bottom=52, left="4%", right="4%"),
        "xAxis": {
            "type": "value",
            "max": 100,
            "axisLabel": {"color": AXIS, "formatter": "{value}%"},
            "splitLine": {"lineStyle": {"color": GRID, "type": "dashed"}},
        },
        "yAxis": {
            "type": "category",
            "data": ["Slice obligations"],
            "axisLine": {"lineStyle": {"color": GRID}},
            "axisLabel": {"color": AXIS},
        },
        "series": series,
        "_intel": {"mode": "motion_channels", "tooltipTemplate": "motion_channel_pct"},
    }


def _motion_q4_mix_shift_chart(timing: dict[str, Any]) -> dict[str, Any] | None:
    periods = timing.get("periods") or []
    if not periods:
        return None
    series = [
        {
            "name": p.get("label") or p.get("channel"),
            "type": "bar",
            "stack": "mix",
            "emphasis": {"focus": "series"},
            "data": [
                {
                    "value": p.get("rest_mix_pct", 0),
                    "millions": p.get("rest_millions", 0),
                    "channel": p.get("channel"),
                },
                {
                    "value": p.get("q4_mix_pct", 0),
                    "millions": p.get("q4_millions", 0),
                    "channel": p.get("channel"),
                },
            ],
            "itemStyle": {"color": _CHANNEL_COLORS.get(str(p.get("channel")), CYAN)},
        }
        for p in periods
    ]
    return {
        "backgroundColor": "transparent",
        "textStyle": {"color": TEXT},
        "title": _title("Q4 mix shift"),
        "tooltip": {**_tooltip("axis"), "axisPointer": {"type": "shadow"}},
        "legend": {
            "type": "scroll",
            "top": 28,
            "textStyle": {"color": AXIS, "fontSize": 9},
        },
        "grid": _grid(top=96, bottom=40, left="6%", right="4%"),
        "xAxis": {
            "type": "category",
            "data": ["Oct–Jun mix", "Q4 mix"],
            "axisLabel": {"color": AXIS, "fontSize": 10},
            "axisLine": {"lineStyle": {"color": GRID}},
        },
        "yAxis": {
            "type": "value",
            "max": 100,
            "name": "% of period $",
            "axisLabel": {"color": AXIS, "formatter": "{value}%"},
            "splitLine": {"lineStyle": {"color": GRID, "type": "dashed"}},
        },
        "series": series,
        "_intel": {
            "mode": "motion_q4_timing",
            "tooltipTemplate": "motion_q4_mix",
            "insight": timing.get("insight") or "",
            "rest_total_millions": timing.get("rest_total_millions"),
            "q4_total_millions": timing.get("q4_total_millions"),
        },
    }


def _motion_channel_bars_chart(
    channels: list[dict[str, Any]],
    *,
    title: str,
    mode: str,
) -> dict[str, Any] | None:
    if not channels:
        return None
    labels = [ch.get("label") or ch.get("channel") for ch in channels]
    values = [ch.get("millions", 0) for ch in channels]
    colors = [_CHANNEL_COLORS.get(str(ch.get("channel")), CYAN) for ch in channels]
    return {
        "backgroundColor": "transparent",
        "textStyle": {"color": TEXT},
        "title": _title(title),
        "tooltip": {**_tooltip("axis")},
        "grid": _grid(top=72, left="28%"),
        "xAxis": {
            "type": "value",
            "axisLabel": {"color": AXIS},
            "splitLine": {"lineStyle": {"color": GRID, "type": "dashed"}},
        },
        "yAxis": {
            "type": "category",
            "data": labels,
            "axisLabel": {"color": AXIS, "fontSize": 9},
            "axisLine": {"lineStyle": {"color": GRID}},
        },
        "series": [
            {
                "type": "bar",
                "data": [
                    {
                        "value": v,
                        "millions": v,
                        "pct": ch.get("pct", 0),
                        "actions": ch.get("actions", 0),
                        "itemStyle": {"color": colors[i]},
                    }
                    for i, (v, ch) in enumerate(zip(values, channels))
                ],
                "barMaxWidth": 22,
            }
        ],
        "_intel": {"mode": mode, "tooltipTemplate": "motion_channel_value"},
    }


def _motion_parent_shadow_chart(shadow: dict[str, Any]) -> dict[str, Any] | None:
    independent = float(shadow.get("independent_millions") or 0)
    parent_backed = float(shadow.get("parent_backed_millions") or 0)
    eight_a_parent = float(shadow.get("eight_a_parent_millions") or 0)
    if independent + parent_backed <= 0:
        return None
    rows: list[tuple[str, float, str]] = [
        ("Independent SB prime", independent, LIME),
        ("Parent-backed prime", max(parent_backed - eight_a_parent, 0), AMBER),
    ]
    if eight_a_parent > 0:
        rows.append(("Parent-backed 8(a)", eight_a_parent, MAGENTA))
    labels = [r[0] for r in rows]
    return {
        "backgroundColor": "transparent",
        "textStyle": {"color": TEXT},
        "title": _title("Set-aside parent shadow"),
        "tooltip": {**_tooltip("axis")},
        "grid": _grid(top=72, left="32%"),
        "xAxis": {
            "type": "value",
            "axisLabel": {"color": AXIS},
            "splitLine": {"lineStyle": {"color": GRID, "type": "dashed"}},
        },
        "yAxis": {
            "type": "category",
            "data": labels,
            "axisLabel": {"color": AXIS, "fontSize": 9},
            "axisLine": {"lineStyle": {"color": GRID}},
        },
        "series": [
            {
                "type": "bar",
                "data": [
                    {
                        "value": v,
                        "millions": v,
                        "pct": shadow.get("independent_pct") if i == 0 else shadow.get("parent_backed_pct"),
                        "itemStyle": {"color": color},
                    }
                    for i, (label, v, color) in enumerate(rows)
                ],
                "barMaxWidth": 22,
            }
        ],
        "_intel": {"mode": "motion_parent_shadow", "tooltipTemplate": "motion_channel_value"},
    }


def _motion_money_paths_sankey(paths: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not paths:
        return None
    nodes: dict[str, dict[str, Any]] = {}
    links: list[dict[str, Any]] = []

    def _node(key: str, display: str, color: str) -> str:
        if key not in nodes:
            nodes[key] = {"name": key, "display": display, "itemStyle": {"color": color}}
        return key

    for row in paths[:MAX_SANKEY_LINKS]:
        agency = str(row.get("agency") or "(Agency)")[:42]
        channel = str(row.get("channel_label") or row.get("channel") or "Channel")[:36]
        recipient = str(row.get("recipient") or "(Prime)")[:42]
        millions = _non_negative_float(row.get("millions"))
        if millions <= 0:
            continue
        agency_key = _node(f"A::{agency}", agency, MAGENTA)
        channel_key = _node(f"C::{channel}", channel, AMBER)
        recipient_key = _node(f"R::{recipient}", recipient, CYAN)
        links.append({"source": agency_key, "target": channel_key, "value": millions})
        links.append({"source": channel_key, "target": recipient_key, "value": millions})

    if not links:
        return None
    return {
        "backgroundColor": "transparent",
        "textStyle": {"color": TEXT},
        "title": _title("Top money paths"),
        "tooltip": _tooltip(),
        "series": [
            {
                "type": "sankey",
                "emphasis": {"focus": "adjacency"},
                "nodeAlign": "justify",
                "layoutIterations": 32,
                "lineStyle": {"color": "gradient", "curveness": 0.45, "opacity": 0.4},
                "itemStyle": {"borderWidth": 0},
                "label": {"color": TEXT_BRIGHT, "fontSize": 9},
                "data": [{"name": n["name"], "itemStyle": n["itemStyle"]} for n in nodes.values()],
                "links": [{"source": l["source"], "target": l["target"], "value": max(l["value"], 0.01)} for l in links],
            }
        ],
        "_intel": {"mode": "motion_money_paths", "displayKey": "display"},
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


def _agency_recipient_heatmap(matrix: dict[str, Any]) -> dict[str, Any] | None:
    cells = matrix.get("cells") or []
    if not cells:
        return None
    agencies = matrix.get("agencies") or list(dict.fromkeys(c["agency"] for c in cells))[:10]
    recipients = matrix.get("recipients") or list(dict.fromkeys(c["recipient"] for c in cells))[:10]
    if not agencies or not recipients:
        return None
    agency_idx = {a: i for i, a in enumerate(agencies)}
    recipient_idx = {r: i for i, r in enumerate(recipients)}
    data = []
    max_actions = 1
    for c in cells:
        if c["agency"] not in agency_idx or c["recipient"] not in recipient_idx:
            continue
        actions = int(c.get("actions") or 0)
        max_actions = max(max_actions, actions)
        data.append([
            agency_idx[c["agency"]],
            recipient_idx[c["recipient"]],
            actions,
            c.get("millions", 0),
        ])
    if not data:
        return None
    return {
        "backgroundColor": "transparent",
        "textStyle": {"color": TEXT},
        "title": _title("Agency × contractor relationships"),
        "tooltip": {**_tooltip("item"), "position": "top"},
        "grid": {"left": "22%", "right": "6%", "top": 56, "bottom": "14%"},
        "xAxis": {
            "type": "category",
            "data": [_truncate(a, 24) for a in agencies],
            "splitArea": {"show": True},
            "axisLabel": {"color": AXIS, "rotate": 35, "fontSize": 9},
        },
        "yAxis": {
            "type": "category",
            "data": [_truncate(r, 28) for r in recipients],
            "splitArea": {"show": True},
            "axisLabel": {"color": TEXT_BRIGHT, "fontSize": 9},
        },
        "visualMap": {
            "min": 0,
            "max": max_actions,
            "calculable": False,
            "orient": "horizontal",
            "left": "center",
            "bottom": 0,
            "inRange": {"color": ["#0f172a", CYAN, LIME, MAGENTA]},
            "textStyle": {"color": AXIS, "fontSize": 9},
        },
        "series": [
            {
                "type": "heatmap",
                "data": data,
                "label": {"show": False},
                "emphasis": {"itemStyle": {"shadowBlur": 8, "shadowColor": "rgba(0,0,0,0.4)"}},
            }
        ],
        "_intel": {
            "mode": "relationship_heatmap",
            "agencies": agencies,
            "recipients": recipients,
            "drillField": "recipient",
            "drillLens": "competitor",
            "entityScope": "recipient",
        },
    }


def _pricing_bucket_chart(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    return {
        "backgroundColor": "transparent",
        "textStyle": {"color": TEXT},
        "title": _title("Contract pricing mix"),
        "tooltip": {**_tooltip("axis"), "axisPointer": {"type": "shadow"}},
        "grid": _grid(top=72),
        "xAxis": {
            "type": "category",
            "data": [_truncate(str(r.get("bucket") or "?"), 20) for r in rows],
            "axisLabel": {"color": AXIS, "rotate": 20, "fontSize": 9},
        },
        "yAxis": {
            "type": "value",
            "name": "$M",
            "axisLabel": {"color": AXIS},
            "splitLine": {"lineStyle": {"color": GRID, "type": "dashed"}},
        },
        "series": [
            {
                "type": "bar",
                "data": [r.get("millions", 0) for r in rows],
                "itemStyle": {"color": AMBER},
                "barMaxWidth": 40,
            }
        ],
        "_intel": {"mode": "pricing_buckets"},
    }


def _vehicle_combo_chart(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    vehicles = list(dict.fromkeys(r.get("vehicle") or "?" for r in rows))[:8]
    pricing_types = list(dict.fromkeys(r.get("pricing") or "?" for r in rows))[:6]
    series = []
    for pricing in pricing_types:
        values = []
        for vehicle in vehicles:
            match = next(
                (r for r in rows if r.get("vehicle") == vehicle and r.get("pricing") == pricing),
                None,
            )
            values.append(match.get("millions", 0) if match else 0)
        series.append({
            "name": _truncate(pricing, 22),
            "type": "bar",
            "stack": "vehicle",
            "emphasis": {"focus": "series"},
            "data": values,
            "barMaxWidth": 28,
        })
    return {
        "backgroundColor": "transparent",
        "textStyle": {"color": TEXT},
        "title": _title("Vehicle × pricing combinations"),
        "tooltip": {**_tooltip("axis"), "axisPointer": {"type": "shadow"}},
        "legend": {"top": 28, "textStyle": {"color": AXIS, "fontSize": 9}},
        "grid": _grid(top=88, bottom=48),
        "xAxis": {
            "type": "category",
            "data": [_truncate(v, 18) for v in vehicles],
            "axisLabel": {"color": AXIS, "rotate": 25, "fontSize": 9},
        },
        "yAxis": {
            "type": "value",
            "name": "$M",
            "axisLabel": {"color": AXIS},
            "splitLine": {"lineStyle": {"color": GRID, "type": "dashed"}},
        },
        "series": series,
        "_intel": {"mode": "vehicle_breakdown"},
    }


def _tier_color(tier: str) -> str:
    if tier == "high":
        return TIER_HIGH
    if tier == "medium":
        return TIER_MED
    return TIER_LOW


def _browse_funnel_sankey(funnel: dict[str, Any]) -> dict[str, Any] | None:
    flows = funnel.get("flows") or []
    if not flows:
        return None
    links = [{"source": f["source"], "target": f["target"], "value": f["millions"]} for f in flows]
    chart = _sankey_option(
        title="Browse funnel — multi-hop relations",
        links=links,
        source_label="from",
        target_label="to",
        mode="browse_funnel",
    )
    if chart:
        chart["_intel"] = {"mode": "browse_funnel", "expandable": False}
    return chart


def _relations_force_graph(graph: dict[str, Any]) -> dict[str, Any] | None:
    """DR expose/relations — multi-hop force graph; people is one node kind among several."""
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    if not nodes or not edges:
        return None

    kind_symbols = {
        "agency": "roundRect",
        "prime": "circle",
        "sub": "diamond",
        "vehicle": "rect",
        "person": "pin",
    }
    echarts_nodes = [
        {
            "id": n["id"],
            "name": _truncate(n.get("label") or n["id"], 32),
            "symbolSize": max(14, min(52, 12 + _non_negative_float(n.get("millions_total")) ** 0.5 * 4)),
            "symbol": kind_symbols.get(n.get("kind"), "circle"),
            "itemStyle": {"color": _tier_color(n.get("magnitude_tier", "low"))},
            "label": {"show": True, "color": TEXT_BRIGHT, "fontSize": 9},
            "value": n.get("millions_total", 0),
            **{k: n[k] for k in ("kind", "hop", "millions_in", "millions_out") if k in n},
        }
        for n in nodes
    ]
    edge_colors = {
        "obligation": CYAN,
        "teaming": LIME,
        "teaming_network": "#86efac",
        "vehicle_member": AMBER,
        "co_occurrence": MAGENTA,
        "person_affiliation": "#f472b6",
    }
    echarts_links = [
        {
            "source": e["source"],
            "target": e["target"],
            "value": max(_non_negative_float(e.get("millions")), 0.01),
            "lineStyle": {
                "color": edge_colors.get(e.get("kind"), TEXT),
                "width": max(1, min(6, _non_negative_float(e.get("millions")) ** 0.5)),
                "curveness": 0.15,
            },
            "kind": e.get("kind"),
        }
        for e in edges
    ]
    return {
        "backgroundColor": "transparent",
        "textStyle": {"color": TEXT},
        "title": _title("Relations trace — multi-hop graph"),
        "tooltip": _tooltip(),
        "series": [
            {
                "type": "graph",
                "layout": "force",
                "roam": True,
                "draggable": True,
                "focusNodeAdjacency": True,
                "force": {
                    "repulsion": 220,
                    "edgeLength": [80, 160],
                    "gravity": 0.08,
                },
                "data": echarts_nodes,
                "links": echarts_links,
                "emphasis": {"focus": "adjacency", "lineStyle": {"width": 4}},
            }
        ],
        "_intel": {
            "mode": "relations_graph",
            "drillField": "recipient",
            "expandable": True,
            "edgeKinds": list(edge_colors.keys()),
            "relationFamilies": graph.get("relation_families") or [],
            "maxHop": (graph.get("summary") or {}).get("max_hop"),
        },
    }


def graph_option_from_payload(graph: dict[str, Any]) -> dict[str, Any] | None:
    """Build ECharts option from relations graph JSON (expand merge)."""
    return _relations_force_graph(graph)


def _ffp_pressure_chart(agency_pressure: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not agency_pressure:
        return None
    rows = agency_pressure[:12]
    names = [_truncate(r["agency"], 32) for r in rows]
    return {
        "backgroundColor": "transparent",
        "textStyle": {"color": TEXT},
        "title": _title("FFP shaping — non-fixed pricing pressure by agency"),
        "tooltip": {**_tooltip("axis"), "axisPointer": {"type": "shadow"}},
        "grid": {**_grid(), "left": "30%"},
        "xAxis": {
            "type": "value",
            "name": "% non-fixed",
            "max": 100,
            "axisLabel": {"color": AXIS},
            "splitLine": {"lineStyle": {"color": GRID, "type": "dashed"}},
        },
        "yAxis": {
            "type": "category",
            "data": list(reversed(names)),
            "axisLabel": {"color": TEXT_BRIGHT, "fontSize": 9},
        },
        "series": [
            {
                "type": "bar",
                "data": [
                    {
                        "value": r.get("non_fixed_pct", 0),
                        "agency": r["agency"],
                        "tier": r.get("pressure_tier"),
                    }
                    for r in reversed(rows)
                ],
                "itemStyle": {"color": MAGENTA},
                "barMaxWidth": 14,
            }
        ],
        "_intel": {
            "mode": "ffp_pressure",
            "honeField": "agency",
            "drillLens": "agency",
            "entityScope": "agency",
        },
    }


def _truncate(text: str, max_len: int) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"